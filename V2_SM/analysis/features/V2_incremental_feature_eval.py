"""
V2_incremental_feature_eval.py
Bounded incremental-feature evaluation for SM V2 program.
Evaluates two candidates against the frozen V1.1 production protocol.

Candidates:
  cold_dip_delta90     — reuse probe P3 CSV (pre-computed)
  rpm_rise_lag_delta90 — compute from raw parquet (lazy scan, non-SMA-dead VINs)

Run: py -3 "STARTER MOTOR/V2_program/analysis/features/V2_incremental_feature_eval.py"
"""
import json
import math
import sys
import time
import warnings
from collections import Counter
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")

ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR")
OUT = ROOT / "V2_program" / "analysis" / "features" / "out"
OUT.mkdir(parents=True, exist_ok=True)

# ── Production constants (frozen V1.1) ──────────────────────────────────────
ALPHA_MW = 0.10
AUROC_MIN = 0.60
CORR_MAX = 0.85
STABLE_FRAC = 0.80
POOL_CAP = 10
SUBSET_MIN, SUBSET_MAX = 3, 6
RIDGE_ALPHA = 1.0
SEED_BOOT = 42
SEED_PERM = 43
TIER_GREEN, TIER_RED = 0.35, 0.55

MODAL_SUBSET = [
    "vsi_withinwk_std_ratio_30d_w",
    "rest_vsi_p05_delta90",
    "vsi_range_trend",
    "dip_depth_last90_delta",
]
V1_1_NESTED_AUROC = 0.9321
MODAL_NONNESTED_AUROC_EXPECTED = 0.9357

SMA_DEAD = [
    "VIN8_F_SM", "VIN9_F_SM",
    "VIN10_NF_SM", "VIN11_NF_SM", "VIN12_NF_SM", "VIN13_NF_SM", "VIN20_NF_SM",
]

GREEN_FAILED = ["VIN1_F_SM", "VIN3_F_SM", "VIN4_F_SM", "VIN9_F_SM"]
YOUDEN_FPS = ["VIN5_NF_SM", "VIN20_NF_SM", "VIN2_NF_SM", "VIN10_NF_SM", "VIN15_NF_SM"]

# ── Exact ridge/LOVO replica from V1.1 ──────────────────────────────────────
def ridge_z(Xtr, ytr, Xte, alpha=RIDGE_ALPHA):
    Xtr = Xtr.copy(); Xte = Xte.copy()
    med = np.nanmedian(Xtr, axis=0)
    med = np.where(np.isnan(med), 0.0, med)
    for j in range(Xtr.shape[1]):
        Xtr[np.isnan(Xtr[:, j]), j] = med[j]
        Xte[np.isnan(Xte[:, j]), j] = med[j]
    mu, sd = Xtr.mean(0), Xtr.std(0)
    sd = np.where(sd == 0, 1.0, sd)
    Xtr = (Xtr - mu) / sd; Xte = (Xte - mu) / sd
    yp = 2.0 * ytr - 1.0
    yc = yp - yp.mean()
    k = Xtr.shape[1]
    beta = np.linalg.solve(Xtr.T @ Xtr + alpha * np.eye(k), Xtr.T @ yc)
    return Xte @ beta + yp.mean()


def sigmoid(z):
    return np.where(z >= 0,
                    1.0 / (1.0 + np.exp(-np.abs(z))),
                    np.exp(-np.abs(z)) / (1.0 + np.exp(-np.abs(z))))


def lovo_z(X, yy):
    nn = len(yy)
    z = np.empty(nn)
    idx = np.arange(nn)
    for i in range(nn):
        tr = idx != i
        z[i] = ridge_z(X[tr], yy[tr], X[i:i + 1])[0]
    return z


def rank_auroc(s, l):
    m = np.isfinite(s)
    s, l = s[m], l[m]
    if l.sum() == 0 or (1 - l).sum() == 0:
        return np.nan
    r = stats.rankdata(s)
    n1 = int(l.sum())
    return (r[l == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * (len(l) - n1))


def mw_p(a, b):
    if len(a) == 0 or len(b) == 0:
        return np.nan
    try:
        return float(stats.mannwhitneyu(a, b, alternative="two-sided").pvalue)
    except ValueError:
        return np.nan


def youden_thr(yy, p):
    order = np.argsort(-p)
    ps, ys = p[order], yy[order]
    P, N = ys.sum(), len(ys) - ys.sum()
    tps = np.cumsum(ys); fps = np.cumsum(1 - ys)
    jj = tps / P - fps / N
    distinct = np.r_[np.diff(ps) != 0, True]
    best = np.argmax(np.where(distinct, jj, -np.inf))
    return float(ps[best])


def mcc_at(yy, p, thr):
    pred = (p >= thr).astype(int)
    tp = int(((pred == 1) & (yy == 1)).sum()); tn = int(((pred == 0) & (yy == 0)).sum())
    fp = int(((pred == 1) & (yy == 0)).sum()); fn = int(((pred == 0) & (yy == 1)).sum())
    den = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    return (tp * tn - fp * fn) / den if den > 0 else 0.0


def screen_pool(Xdf, yy, feats):
    nn = len(yy)
    recs = []
    for ft in feats:
        v = Xdf[ft].values.astype(float)
        m = np.isfinite(v)
        if m.sum() < 6 or len(np.unique(yy[m])) < 2:
            recs.append((ft, np.nan, np.nan, False)); continue
        p = mw_p(v[m & (yy == 1)], v[m & (yy == 0)])
        a = rank_auroc(v, yy); a = max(a, 1 - a)
        recs.append((ft, p, a, bool(np.isfinite(p) and p < ALPHA_MW
                                    and np.isfinite(a) and a >= AUROC_MIN)))
    scr = pd.DataFrame(recs, columns=["feature", "mw_p", "auroc", "ok"])
    survivors = scr[scr["ok"]].sort_values("auroc", ascending=False)["feature"].tolist()
    kept = []
    for ft in survivors:
        ok = True
        for kft in kept:
            a_, b_ = Xdf[ft].values.astype(float), Xdf[kft].values.astype(float)
            m = np.isfinite(a_) & np.isfinite(b_)
            if m.sum() >= 4:
                r = stats.spearmanr(a_[m], b_[m])[0]
                if np.isfinite(r) and abs(r) >= CORR_MAX:
                    ok = False; break
        if ok:
            kept.append(ft)
    stable_min = math.ceil(STABLE_FRAC * nn)
    counts = {f: 0 for f in kept}
    for i in range(nn):
        km = np.arange(nn) != i
        ys = yy[km]
        for ft in kept:
            v = Xdf[ft].values.astype(float)[km]
            m = np.isfinite(v)
            p = mw_p(v[m & (ys == 1)], v[m & (ys == 0)])
            if np.isfinite(p) and p < ALPHA_MW:
                counts[ft] += 1
    pool = [f for f in kept if counts[f] >= stable_min]
    pool = (scr[scr["feature"].isin(pool)].sort_values("auroc", ascending=False)
            .head(POOL_CAP)["feature"].tolist())
    rank = scr.sort_values("auroc", ascending=False)["feature"].tolist()
    return pool, rank


def subset_search(Xdf, yy, pool, rank):
    if len(pool) == 0:
        pool = rank[:1]
    k_lo = min(SUBSET_MIN, len(pool))
    k_hi = min(SUBSET_MAX, len(pool))
    best = None
    for k in range(k_lo, k_hi + 1):
        for feats in combinations(pool, k):
            X = Xdf[list(feats)].values.astype(float)
            z = lovo_z(X, yy)
            p = sigmoid(z)
            a = rank_auroc(p, yy)
            thr = youden_thr(yy, p)
            mcc = mcc_at(yy, p, thr)
            cand = (round(a, 10), -k, round(mcc, 10))
            if best is None or cand > best[0]:
                best = (cand, list(feats), z, a)
    return best[1], best[2], best[3]


def nested_lovo(Xdf, yy, feats_all):
    nn = len(yy)
    probs = np.empty(nn)
    details = []
    for i in range(nn):
        tr = np.arange(nn) != i
        df_tr = Xdf.loc[tr].reset_index(drop=True)
        y_tr = yy[tr]
        pool, rank = screen_pool(df_tr, y_tr, feats_all)
        feats, z_in, a_in = subset_search(df_tr, y_tr, pool, rank)
        z_te = ridge_z(df_tr[feats].values.astype(float), y_tr,
                       Xdf.loc[[i], feats].values.astype(float))[0]
        probs[i] = sigmoid(np.array([z_te]))[0]
        details.append({"feats": feats, "pool": pool})
    return probs, details


# ── Load V1.1 data ───────────────────────────────────────────────────────────
print("Loading V1.1 feature matrix ...")
mat = pd.read_csv(ROOT / "V1.1" / "results" / "V1_1_SM_feature_matrix.csv")
vins = mat["vin_label"].tolist()
y = mat["failed"].astype(int).values
n = len(y)
assert n == 34 and y.sum() == 14, f"Unexpected matrix shape: {n} rows, {y.sum()} failed"

# ── Load proxy variables for E1 ─────────────────────────────────────────────
print("Loading weekly cache for proxy variables ...")
wk_all = pd.concat(
    [pd.read_parquet(f) for f in sorted((ROOT / "cache/weekly").glob("V1_SM_weekly_*.parquet"))],
    ignore_index=True
)
wk_all["week"] = pd.to_datetime(wk_all["week"])
proxy_rows = []
for vin in vins:
    w = wk_all[wk_all["vin_label"] == vin]
    wmf = w[w["active_days"] >= 2]
    wm40 = wmf.sort_values("week").tail(40)
    t_end_approx = wmf["week"].max() + pd.Timedelta(days=6)
    proxy_rows.append({
        "vin_label": vin,
        "n_weeks_masked": len(wmf),
        "t_start_ord": w["week"].min().toordinal(),
        "span_days": (w["week"].max() - w["week"].min()).days,
        "t_end_approx": t_end_approx,
        "win_start_l40": wm40["week"].iloc[0] if len(wm40) > 0 else pd.NaT,
    })
px = pd.DataFrame(proxy_rows)

# ── Candidate 1: cold_dip_delta90 — reuse probe CSV ─────────────────────────
print("Loading cold_dip_delta90 from P3 probe CSV ...")
cold_probe = pd.read_csv(
    ROOT / "V2_program" / "probes" / "out" / "P3_cold_warm_per_vin.csv"
)
# Merge on vin_label, set NaN for SMA-dead
cold_map = dict(zip(cold_probe["vin_label"], cold_probe["cold_dip_delta90"]))
cold_dip = np.array([cold_map.get(v, np.nan) for v in vins], dtype=float)
# Force SMA-dead to NaN
for i, v in enumerate(vins):
    if v in SMA_DEAD:
        cold_dip[i] = np.nan
print(f"  cold_dip_delta90: {np.isfinite(cold_dip).sum()}/34 non-NaN "
      f"(SMA-dead={sum(1 for v in vins if v in SMA_DEAD)} forced NaN)")

# ── Candidate 2: rpm_rise_lag_delta90 — compute from raw parquet ─────────────
print("\nComputing rpm_rise_lag_delta90 from raw parquet ...")

FAILED_PARQUET = (
    Path(r"D:\Daimler-starter_motor_alternator_battery\Data\processed\starter_motor_complete")
    / "2026-03-06-12-38-23-starter_motor_failed.parquet"
)
NF_PARQUET = (
    Path(r"D:\Daimler-starter_motor_alternator_battery\Data\processed\starter_motor_complete")
    / "2026-03-06-12-39-14-starter_motor_non_failed.parquet"
)

ev_all = pd.read_parquet(ROOT / "cache/events" / "V1_SM_crank_events.parquet")
ev_all["ts_start"] = pd.to_datetime(ev_all["ts_start"])

WINDOW_S = 60  # 60-second window around event start

def compute_rpm_rise_per_event(ev_subset, raw_df):
    """For each event row in ev_subset, find time-to-RPM>=550 (in 5-second samples).
    Returns dict of event_id -> lag_samples (NaN if RPM never reached 550 in window).
    raw_df must be sorted by timestamp."""
    raw_df = raw_df.sort_values("timestamp").reset_index(drop=True)
    ts_arr = raw_df["timestamp"].values
    rpm_arr = raw_df["RPM"].values
    results = {}
    window = np.timedelta64(WINDOW_S, "s")
    for _, row in ev_subset.iterrows():
        ts = np.datetime64(row["ts_start"])
        # Binary search for window start
        lo = np.searchsorted(ts_arr, ts)
        hi = np.searchsorted(ts_arr, ts + window)
        if lo >= hi:
            results[row["event_id"]] = np.nan
            continue
        rpms = rpm_arr[lo:hi]
        valid = np.isfinite(rpms)
        above = valid & (rpms >= 550)
        if above.any():
            idx = above.argmax()
            results[row["event_id"]] = int(idx)
        else:
            results[row["event_id"]] = np.nan
    return results

RPM_CACHE = OUT / "rpm_rise_per_vin_cache.csv"

if RPM_CACHE.exists():
    rpm_cache_df = pd.read_csv(RPM_CACHE)
    rpm_lag_per_vin = dict(zip(rpm_cache_df["vin_label"], rpm_cache_df["rpm_rise_lag_delta90"]))
    print(f"  Loaded RPM rise cache ({len(rpm_lag_per_vin)} VINs) from {RPM_CACHE}")
    t_rpm_total = 0.0
else:
    t_rpm_start = time.time()
    rpm_lag_per_vin = {}

    for vin in vins:
        if vin in SMA_DEAD:
            rpm_lag_per_vin[vin] = np.nan
            continue

        is_failed = "_F_SM" in vin
        base_vin = vin.replace("_F_SM", "").replace("_NF_SM", "")
        src_parquet = FAILED_PARQUET if is_failed else NF_PARQUET

        ev_vin = ev_all[
            (ev_all["vin_label"] == vin)
            & (ev_all["artifact"] == False)
            & (ev_all["success"] == True)
        ].copy()

        if len(ev_vin) == 0:
            rpm_lag_per_vin[vin] = np.nan
            continue

        vin_px = px[px["vin_label"] == vin].iloc[0]
        t_end = vin_px["t_end_approx"]
        t_90_cutoff = t_end - pd.Timedelta(days=90)
        win_start = vin_px["win_start_l40"]

        ev_last90 = ev_vin[ev_vin["ts_start"] >= t_90_cutoff]
        ev_baseline = ev_vin[
            (ev_vin["ts_start"] >= win_start) & (ev_vin["ts_start"] < t_90_cutoff)
        ]

        if len(ev_last90) < 3 and len(ev_baseline) < 3:
            rpm_lag_per_vin[vin] = np.nan
            continue

        try:
            raw_df = pd.read_parquet(
                src_parquet,
                filters=[("VIN", "==", base_vin)],
                columns=["VIN", "timestamp", "RPM"]
            )
            raw_df["timestamp"] = pd.to_datetime(raw_df["timestamp"])
        except Exception as e:
            print(f"  WARNING: failed to read raw parquet for {vin}: {e}")
            rpm_lag_per_vin[vin] = np.nan
            continue

        lag_last90 = compute_rpm_rise_per_event(ev_last90, raw_df) if len(ev_last90) > 0 else {}
        lag_baseline = compute_rpm_rise_per_event(ev_baseline, raw_df) if len(ev_baseline) > 0 else {}

        lags90_vals = [vv for vv in lag_last90.values() if np.isfinite(vv)]
        lags_base_vals = [vv for vv in lag_baseline.values() if np.isfinite(vv)]

        if len(lags90_vals) >= 3 and len(lags_base_vals) >= 3:
            rpm_lag_per_vin[vin] = float(np.mean(lags90_vals) - np.mean(lags_base_vals))
        else:
            rpm_lag_per_vin[vin] = np.nan

        n90 = len(lags90_vals)
        nbase = len(lags_base_vals)
        val = rpm_lag_per_vin[vin]
        m90s = f"{np.mean(lags90_vals):.2f}" if lags90_vals else "NaN"
        mbases = f"{np.mean(lags_base_vals):.2f}" if lags_base_vals else "NaN"
        print(f"  {vin}: lag90={m90s}(n={n90}), base={mbases}(n={nbase}), delta={val}")

    t_rpm_total = time.time() - t_rpm_start
    print(f"\nRPM rise computation: {t_rpm_total:.1f}s")

    # Save cache
    cache_df = pd.DataFrame({"vin_label": vins,
                              "rpm_rise_lag_delta90": [rpm_lag_per_vin.get(v, np.nan) for v in vins]})
    cache_df.to_csv(RPM_CACHE, index=False)
    print(f"  Saved RPM rise cache to {RPM_CACHE}")

rpm_rise = np.array([rpm_lag_per_vin.get(v, np.nan) for v in vins], dtype=float)
print(f"rpm_rise_lag_delta90: {np.isfinite(rpm_rise).sum()}/34 non-NaN")

# ── Add candidates to feature matrix ────────────────────────────────────────
mat_ext = mat.copy()
mat_ext["cold_dip_delta90"] = cold_dip
mat_ext["rpm_rise_lag_delta90"] = rpm_rise

# ── E1: Admissibility Screen ─────────────────────────────────────────────────
print("\n" + "=" * 60)
print("E1: Admissibility Screen")
print("=" * 60)

MODAL_FEATS = MODAL_SUBSET
CAND_FEATS = ["cold_dip_delta90", "rpm_rise_lag_delta90"]

adm_rows = []
for feat in CAND_FEATS:
    v = mat_ext[feat].values.astype(float)
    m = np.isfinite(v)
    n_nonnull = int(m.sum())

    # MW p-value
    if m[y == 1].sum() >= 3 and m[y == 0].sum() >= 3:
        mwp = mw_p(v[m & (y == 1)], v[m & (y == 0)])
    else:
        mwp = np.nan

    # AUROC
    a_raw = rank_auroc(v, y)
    auroc = max(a_raw, 1 - a_raw) if np.isfinite(a_raw) else np.nan

    # Spearman vs proxy vars
    proxy_r = {}
    flags = []
    for pcol in ["n_weeks_masked", "t_start_ord", "span_days"]:
        pv = px[pcol].values.astype(float)
        mm = m & np.isfinite(pv)
        r = stats.spearmanr(v[mm], pv[mm])[0] if mm.sum() >= 6 else np.nan
        proxy_r[pcol] = r
        if np.isfinite(r) and abs(r) > 0.5:
            flags.append(f"|r_{pcol}|={abs(r):.3f}>0.5")

    # Pearson vs each modal feature
    modal_r = {}
    for mf in MODAL_FEATS:
        mv_arr = mat_ext[mf].values.astype(float)
        mm = m & np.isfinite(mv_arr)
        r = stats.pearsonr(v[mm], mv_arr[mm])[0] if mm.sum() >= 6 else np.nan
        modal_r[mf] = r

    # Print results
    mwp_str = f"{mwp:.4f}" if np.isfinite(mwp) else "NaN"
    auroc_str = f"{auroc:.4f}" if np.isfinite(auroc) else "NaN"
    print(f"\n{feat}:")
    print(f"  n_nonnull={n_nonnull}, MW_p={mwp_str}, AUROC={auroc_str}")
    r_nwk = proxy_r["n_weeks_masked"]
    r_tst = proxy_r["t_start_ord"]
    r_sp = proxy_r["span_days"]
    r_nwk_s = f"{r_nwk:+.3f}" if np.isfinite(r_nwk) else "NaN"
    r_tst_s = f"{r_tst:+.3f}" if np.isfinite(r_tst) else "NaN"
    r_sp_s = f"{r_sp:+.3f}" if np.isfinite(r_sp) else "NaN"
    print(f"  Spearman proxy: r_nwk={r_nwk_s}, r_tstart={r_tst_s}, r_span={r_sp_s}")
    print(f"  Pearson vs modal features:")
    for mf, r in modal_r.items():
        r_s = f"{r:+.3f}" if np.isfinite(r) else "NaN"
        print(f"    vs {mf}: r={r_s}")
    if flags:
        print(f"  FLAGS: {', '.join(flags)}")

    adm_rows.append({
        "feature": feat,
        "n_nonnull": n_nonnull,
        "mw_p": round(float(mwp), 5) if np.isfinite(mwp) else np.nan,
        "auroc": round(float(auroc), 4) if np.isfinite(auroc) else np.nan,
        "r_n_weeks": round(float(proxy_r["n_weeks_masked"]), 3) if np.isfinite(proxy_r["n_weeks_masked"]) else np.nan,
        "r_t_start": round(float(proxy_r["t_start_ord"]), 3) if np.isfinite(proxy_r["t_start_ord"]) else np.nan,
        "r_span_days": round(float(proxy_r["span_days"]), 3) if np.isfinite(proxy_r["span_days"]) else np.nan,
        "proxy_flags": "; ".join(flags) if flags else "",
        "r_vs_vsi_withinwk": round(float(modal_r.get("vsi_withinwk_std_ratio_30d_w", np.nan)), 3),
        "r_vs_rest_vsi_p05": round(float(modal_r.get("rest_vsi_p05_delta90", np.nan)), 3),
        "r_vs_vsi_range_trend": round(float(modal_r.get("vsi_range_trend", np.nan)), 3),
        "r_vs_dip_depth": round(float(modal_r.get("dip_depth_last90_delta", np.nan)), 3),
        "proxy_flag": bool(flags),
    })

adm_df = pd.DataFrame(adm_rows)
adm_df.to_csv(OUT / "admissibility.csv", index=False)
print(f"\nSaved: {OUT / 'admissibility.csv'}")

# ── E2: Fixed-subset LOVO increment ─────────────────────────────────────────
print("\n" + "=" * 60)
print("E2: Fixed-Subset LOVO Increment")
print("=" * 60)

modal_X = mat[MODAL_SUBSET].values.astype(float)

def plain_lovo(X, yy):
    """Plain 34-fold LOVO (no re-screening) — returns sigmoid probs."""
    n_ = len(yy)
    z = np.empty(n_)
    for i in range(n_):
        tr = np.arange(n_) != i
        z[i] = ridge_z(X[tr], yy[tr], X[i:i+1])[0]
    return sigmoid(z)

print("(a) Modal-4 reconciliation ...")
t0 = time.time()
p_modal = plain_lovo(modal_X, y)
a_modal = rank_auroc(p_modal, y)
print(f"  Modal-4 LOVO AUROC = {a_modal:.4f}  (expected {MODAL_NONNESTED_AUROC_EXPECTED:.4f})")
diff = abs(a_modal - MODAL_NONNESTED_AUROC_EXPECTED)
if diff > 0.002:
    print(f"  STOP: reconciliation FAILED (diff={diff:.4f} > 0.002 tolerance)")
    sys.exit(1)
else:
    print(f"  Reconciliation OK (diff={diff:.4f} <= 0.002)")

def make_X_with(base_df, extra_cols):
    cols = MODAL_SUBSET + extra_cols
    return base_df[cols].values.astype(float)

print("\n(b) Modal-4 + cold_dip_delta90 ...")
p_cold = plain_lovo(make_X_with(mat_ext, ["cold_dip_delta90"]), y)
a_cold = rank_auroc(p_cold, y)
delta_cold = a_cold - a_modal
print(f"  AUROC = {a_cold:.4f}  delta = {delta_cold:+.4f}")

print("\n(c) Modal-4 + rpm_rise_lag_delta90 ...")
p_rpm = plain_lovo(make_X_with(mat_ext, ["rpm_rise_lag_delta90"]), y)
a_rpm = rank_auroc(p_rpm, y)
delta_rpm = a_rpm - a_modal
print(f"  AUROC = {a_rpm:.4f}  delta = {delta_rpm:+.4f}")

print("\n(d) Modal-4 + both ...")
p_both = plain_lovo(make_X_with(mat_ext, ["cold_dip_delta90", "rpm_rise_lag_delta90"]), y)
a_both = rank_auroc(p_both, y)
delta_both = a_both - a_modal
print(f"  AUROC = {a_both:.4f}  delta = {delta_both:+.4f}")

# Per-VIN probability changes for Green-tier failed + Youden FPs
print("\n  Per-VIN prob changes (Green-tier failed + Youden FPs):")
print(f"  {'VIN':<18} {'modal_p':>8} {'cold_p':>8} {'rpm_p':>8} {'both_p':>8} "
      f"{'d_cold':>8} {'d_rpm':>8} {'d_both':>8}")
for i, vin in enumerate(vins):
    if vin in GREEN_FAILED or vin in YOUDEN_FPS:
        print(f"  {vin:<18} {p_modal[i]:>8.4f} {p_cold[i]:>8.4f} {p_rpm[i]:>8.4f} "
              f"{p_both[i]:>8.4f} {p_cold[i]-p_modal[i]:>+8.4f} "
              f"{p_rpm[i]-p_modal[i]:>+8.4f} {p_both[i]-p_modal[i]:>+8.4f}")

# Save increment CSV
incr_rows = []
for combo_name, probs_arr, auroc_val, delta_val in [
    ("modal_4_baseline", p_modal, a_modal, 0.0),
    ("modal_4_plus_cold_dip", p_cold, a_cold, delta_cold),
    ("modal_4_plus_rpm_rise", p_rpm, a_rpm, delta_rpm),
    ("modal_4_plus_both", p_both, a_both, delta_both),
]:
    row = {
        "subset": combo_name,
        "lovo_auroc": round(float(auroc_val), 4),
        "delta_vs_modal4": round(float(delta_val), 4),
    }
    for i, vin in enumerate(vins):
        row[vin] = round(float(probs_arr[i]), 4)
    incr_rows.append(row)

incr_df = pd.DataFrame(incr_rows)
incr_df.to_csv(OUT / "increment_lovo.csv", index=False)
print(f"\nSaved: {OUT / 'increment_lovo.csv'}")

# ── E3: Full nested rerun with expanded pool (10+2=12) ──────────────────────
print("\n" + "=" * 60)
print("E3: Full nested rerun — expanded pool (10+2=12) EXPLORATORY")
print("=" * 60)

V1_1_POOL = [
    "vsi_std_ratio_30d_L40", "vsi_withinwk_std_ratio_30d_w", "vsi_range_trend",
    "vsi_trend_persistence", "failed_crank_rate_last90", "retry_burst_rate_last90",
    "extended_crank_tail_rate_last90", "first_crank_fail_rate_last90",
    "rest_vsi_p05_delta90", "dip_depth_last90_delta",
]
# Verify feature matrix has all V1.1 features
for f in V1_1_POOL:
    assert f in mat.columns, f"Missing V1.1 feature: {f}"

EXPANDED_POOL = V1_1_POOL + ["cold_dip_delta90", "rpm_rise_lag_delta90"]

print(f"  Expanded pool: {len(EXPANDED_POOL)} features (10 V1.1 + 2 candidates)")
print(f"  NOTE: This is EXPLORATORY — post-hoc pool expansion = new selection event.")
print(f"  Multiplicity caveat: results do not constitute independent validation.\n")

t0 = time.time()
p_nested_exp, details_exp = nested_lovo(mat_ext, y, EXPANDED_POOL)
t_nested = time.time() - t0
a_nested_exp = rank_auroc(p_nested_exp, y)

print(f"  Expanded nested AUROC = {a_nested_exp:.4f}  (V1.1 baseline = {V1_1_NESTED_AUROC:.4f})")
print(f"  Delta vs V1.1 nested  = {a_nested_exp - V1_1_NESTED_AUROC:+.4f}")
print(f"  Runtime: {t_nested:.1f}s")

# Winner subset frequency
feat_freq = Counter(f for d in details_exp for f in d["feats"])
subset_freq = Counter(tuple(sorted(d["feats"])) for d in details_exp)
pool_selection = Counter(f for d in details_exp for f in d["pool"])

print(f"\n  Feature frequency (selected in outer folds):")
for f, cnt in feat_freq.most_common():
    marker = " ***CANDIDATE***" if f in CAND_FEATS else ""
    print(f"    {f:<42} {cnt}/34{marker}")

# Check candidate selection count
cold_folds = feat_freq.get("cold_dip_delta90", 0)
rpm_folds = feat_freq.get("rpm_rise_lag_delta90", 0)
cold_pool_folds = pool_selection.get("cold_dip_delta90", 0)
rpm_pool_folds = pool_selection.get("rpm_rise_lag_delta90", 0)

print(f"\n  Candidate selection counts:")
print(f"    cold_dip_delta90:     selected in {cold_folds}/34 outer folds "
      f"(pool entry: {cold_pool_folds}/34 folds)")
print(f"    rpm_rise_lag_delta90: selected in {rpm_folds}/34 outer folds "
      f"(pool entry: {rpm_pool_folds}/34 folds)")

# Save nested summary CSV
nested_rows = []
for i, (vin, d) in enumerate(zip(vins, details_exp)):
    nested_rows.append({
        "vin_label": vin,
        "failed": int(y[i]),
        "prob_expanded": round(float(p_nested_exp[i]), 4),
        "winner_feats": "|".join(d["feats"]),
        "k": len(d["feats"]),
        "cold_dip_in_winner": int("cold_dip_delta90" in d["feats"]),
        "rpm_rise_in_winner": int("rpm_rise_lag_delta90" in d["feats"]),
    })
nested_df = pd.DataFrame(nested_rows)
nested_df.to_csv(OUT / "nested_expanded_summary.csv", index=False)
print(f"\nSaved: {OUT / 'nested_expanded_summary.csv'}")

# ── E4: Honest Verdict ───────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("E4: Honest Verdict")
print("=" * 60)

def verdict(cand, delta_e2, folds_e3, adm_flags):
    """ADD if E2 delta >= +0.01 AND E3 >= 10/34 folds AND no admissibility flag.
    HOLD if signal real but redundant/weak. REJECT otherwise."""
    if adm_flags:
        return "HOLD", f"admissibility flag: {adm_flags}"
    if delta_e2 >= 0.01 and folds_e3 >= 10:
        return "ADD", f"E2 delta={delta_e2:+.4f} >= +0.01, E3 folds={folds_e3}/34 >= 10"
    elif delta_e2 > 0 or folds_e3 >= 5:
        return "HOLD", (f"signal real but weak/insufficient: "
                        f"E2 delta={delta_e2:+.4f}, E3 folds={folds_e3}/34")
    else:
        return "REJECT", f"E2 delta={delta_e2:+.4f} <= 0, E3 folds={folds_e3}/34 < 5"

# cold_dip
cold_adm_row = adm_df[adm_df["feature"] == "cold_dip_delta90"].iloc[0]
cold_flags = cold_adm_row["proxy_flags"]
cold_verdict, cold_reason = verdict("cold_dip_delta90", delta_cold, cold_folds, cold_flags)

# rpm_rise
rpm_adm_row = adm_df[adm_df["feature"] == "rpm_rise_lag_delta90"].iloc[0]
rpm_flags = rpm_adm_row["proxy_flags"]
rpm_verdict, rpm_reason = verdict("rpm_rise_lag_delta90", delta_rpm, rpm_folds, rpm_flags)

print(f"\n  cold_dip_delta90:     {cold_verdict}")
print(f"    Reason: {cold_reason}")
print(f"\n  rpm_rise_lag_delta90: {rpm_verdict}")
print(f"    Reason: {rpm_reason}")

# ── Summary JSON ─────────────────────────────────────────────────────────────
summary = {
    "created": "2026-06-12",
    "protocol": "V1.1 frozen LOVO Ridge alpha=1.0, seeds boot=42 perm=43",
    "reconciliation": {
        "expected_modal4_nonnested_auroc": MODAL_NONNESTED_AUROC_EXPECTED,
        "computed": round(float(a_modal), 4),
        "diff": round(diff, 4),
        "pass": diff <= 0.002
    },
    "E1": {
        "cold_dip_delta90": adm_rows[0],
        "rpm_rise_lag_delta90": adm_rows[1],
    },
    "E2": {
        "modal4_baseline": round(float(a_modal), 4),
        "modal4_plus_cold_dip": round(float(a_cold), 4),
        "modal4_plus_rpm_rise": round(float(a_rpm), 4),
        "modal4_plus_both": round(float(a_both), 4),
        "delta_cold_dip": round(float(delta_cold), 4),
        "delta_rpm_rise": round(float(delta_rpm), 4),
        "delta_both": round(float(delta_both), 4),
    },
    "E3": {
        "note": "EXPLORATORY — post-hoc pool expansion, multiplicity caveat mandatory",
        "expanded_nested_auroc": round(float(a_nested_exp), 4),
        "v1_1_baseline_auroc": V1_1_NESTED_AUROC,
        "delta_vs_v1_1": round(float(a_nested_exp - V1_1_NESTED_AUROC), 4),
        "cold_dip_folds_selected": int(cold_folds),
        "rpm_rise_folds_selected": int(rpm_folds),
        "cold_dip_folds_pool": int(cold_pool_folds),
        "rpm_rise_folds_pool": int(rpm_pool_folds),
        "feature_frequency": {k: int(v) for k, v in feat_freq.most_common()},
        "runtime_s": round(t_nested, 1),
    },
    "E4": {
        "cold_dip_delta90": {"verdict": cold_verdict, "reason": cold_reason},
        "rpm_rise_lag_delta90": {"verdict": rpm_verdict, "reason": rpm_reason},
    },
    "rpm_rise_computation": {
        "method": "raw parquet lazy scan, ±60s window, samples x5s",
        "non_sma_dead_vins": 27,
        "runtime_s": round(t_rpm_total, 1),
        "n_nonnull": int(np.isfinite(rpm_rise).sum()),
    }
}

def _j(obj):
    """Recursively convert numpy scalars to Python native for JSON serialization."""
    if isinstance(obj, dict):
        return {k: _j(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_j(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj

with open(OUT / "eval_summary.json", "w") as f:
    json.dump(_j(summary), f, indent=2)
print(f"\nSaved: {OUT / 'eval_summary.json'}")
print("\nE1-E4 evaluation complete.")
