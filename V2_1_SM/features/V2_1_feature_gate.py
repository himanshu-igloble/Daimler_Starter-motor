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
OUT = ROOT / "V2.1" / "features" / "out"
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

# ── V2.1 candidates from cached CSVs ────────────────────────────────────────
CAND_FEATS = ["intercrank_cv_delta90", "z_cold_dip_delta90", "anr_pos_mean_delta90"]
mat_ext = mat.copy()
for cand in CAND_FEATS:
    c = pd.read_csv(OUT / f"{cand}_cache.csv")
    cmap = dict(zip(c["vin_label"], c[cand]))
    arr = np.array([cmap.get(v, np.nan) for v in vins], dtype=float)
    for i, v in enumerate(vins):
        if v in SMA_DEAD:
            arr[i] = np.nan
    mat_ext[cand] = arr
    print(f"  {cand}: {np.isfinite(arr).sum()}/34 non-NaN")

# ── E1: Admissibility Screen ─────────────────────────────────────────────────
print("\n" + "=" * 60)
print("E1: Admissibility Screen")
print("=" * 60)

MODAL_FEATS = MODAL_SUBSET

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

ADD_THR = 0.01
e2 = {}
for cand in CAND_FEATS:
    p_c = plain_lovo(make_X_with(mat_ext, [cand]), y)
    a_c = rank_auroc(p_c, y)
    e2[cand] = {"auroc": round(float(a_c), 4), "delta": round(float(a_c - a_modal), 4)}
    print(f"  modal-4 + {cand}: AUROC={a_c:.4f} delta={a_c - a_modal:+.4f}")

V1_1_POOL = [
    "vsi_std_ratio_30d_L40", "vsi_withinwk_std_ratio_30d_w", "vsi_range_trend",
    "vsi_trend_persistence", "failed_crank_rate_last90", "retry_burst_rate_last90",
    "extended_crank_tail_rate_last90", "first_crank_fail_rate_last90",
    "rest_vsi_p05_delta90", "dip_depth_last90_delta",
]
# Verify feature matrix has all V1.1 features
for f in V1_1_POOL:
    assert f in mat.columns, f"Missing V1.1 feature: {f}"

print("\n" + "=" * 60)
print("E3: nested rerun (only if a candidate cleared E2)")
print("=" * 60)
passers = [c for c in CAND_FEATS if e2[c]["delta"] >= ADD_THR]
if not passers:
    print("E3 SKIPPED — no candidate cleared E2 (+0.01). All HOLD.")
    a_nested_exp = None
else:
    EXPANDED_POOL = V1_1_POOL + passers
    p_nested_exp, details_exp = nested_lovo(mat_ext, y, EXPANDED_POOL)
    a_nested_exp = rank_auroc(p_nested_exp, y)
    print(f"  Expanded nested AUROC = {a_nested_exp:.4f} (V1.1 = {V1_1_NESTED_AUROC})")

print("\n" + "=" * 60)
print("E4: Verdict")
print("=" * 60)
verdicts = {}
for cand in CAND_FEATS:
    flag = adm_df[adm_df.feature == cand]["proxy_flags"].iloc[0]
    d = e2[cand]["delta"]
    if flag:
        verdicts[cand] = ("HOLD", f"proxy flag: {flag}")
    elif d >= ADD_THR:
        verdicts[cand] = ("ADD", f"E2 delta={d:+.4f} >= +0.01")
    elif d > 0:
        verdicts[cand] = ("HOLD", f"real but weak: E2 delta={d:+.4f}")
    else:
        verdicts[cand] = ("REJECT", f"E2 delta={d:+.4f} <= 0")
    print(f"  {cand}: {verdicts[cand][0]} — {verdicts[cand][1]}")

import json
summary = {"reconciliation": {"computed": round(float(a_modal), 4), "expected": MODAL_NONNESTED_AUROC_EXPECTED, "pass": bool(diff <= 0.002)},
           "E1": adm_df.to_dict(orient="records"), "E2": e2,
           "E3_expanded_nested_auroc": (round(float(a_nested_exp), 4) if a_nested_exp is not None else None),
           "verdicts": {k: {"verdict": v[0], "reason": v[1]} for k, v in verdicts.items()}}
(OUT / "V2_1_gate_summary.json").write_text(json.dumps(summary, indent=2, default=str))
print("\nSaved V2_1_gate_summary.json")
