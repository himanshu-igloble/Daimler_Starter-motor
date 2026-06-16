"""
B1_audit_existing.py — Agent B, V1.1 feature audit, Part 1.
Audits the 23 V1 features (read-only on V1 artifacts):
  1. Redundancy structure (Spearman corr matrix + |r|>=0.7 clusters)
  2. Jackknife (leave-one-VIN-out) sensitivity of single-feature AUROC
  3. Time-proxy check: corr of every feature vs observation-length/epoch metrics
  4. VIN8_F_SM miss diagnosis: feature profile vs cohorts

Outputs (to STARTER MOTOR/V1.1/audit/out/):
  B1_corr_matrix.csv, B1_jackknife_auroc.csv, B1_time_proxy.csv, B1_vin8_profile.csv
Run: py -3 B1_audit_existing.py
"""
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
import warnings
warnings.filterwarnings("ignore")

ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR")
OUT = ROOT / "V1.1" / "audit" / "out"
OUT.mkdir(parents=True, exist_ok=True)

fm = pd.read_csv(ROOT / "results" / "V1_SM_feature_matrix.csv")
FEATS = [c for c in fm.columns if c not in ("vin_label", "failed")]
y = fm["failed"].values.astype(int)
WINNERS = ["vsi_std_ratio_30d", "vsi_dominant_freq", "failed_crank_rate_last90", "vsi_range_trend"]


def rank_auroc(scores, labels):
    mask = np.isfinite(scores)
    s, l = scores[mask], labels[mask]
    if l.sum() == 0 or (1 - l).sum() == 0:
        return np.nan
    pos, neg = s[l == 1], s[l == 0]
    u = sum((neg < p).sum() + 0.5 * (neg == p).sum() for p in pos)
    return u / (len(pos) * len(neg))


# ── 1. Redundancy: Spearman correlation matrix + clusters ────────────────────
X = fm[FEATS].astype(float)
corr = X.corr(method="spearman")
corr.to_csv(OUT / "B1_corr_matrix.csv")

# connected components at |r| >= 0.7
thr = 0.70
adj = (corr.abs() >= thr).values
np.fill_diagonal(adj, False)
visited, clusters = set(), []
for i, f in enumerate(FEATS):
    if f in visited:
        continue
    stack, comp = [i], []
    while stack:
        j = stack.pop()
        if FEATS[j] in visited:
            continue
        visited.add(FEATS[j])
        comp.append(FEATS[j])
        stack.extend(k for k in range(len(FEATS)) if adj[j, k] and FEATS[k] not in visited)
    if len(comp) > 1:
        clusters.append(comp)

print("=" * 78)
print(f"1. REDUNDANCY CLUSTERS (|Spearman r| >= {thr})")
print("=" * 78)
if clusters:
    for c in clusters:
        print(f"  cluster: {c}")
        for a in c:
            for b in c:
                if a < b:
                    print(f"    r({a}, {b}) = {corr.loc[a, b]:+.3f}")
else:
    print("  none")

# pairwise high correlations involving winners
print("\n  Winner pairwise correlations:")
for a in WINNERS:
    for b in WINNERS:
        if a < b:
            print(f"    r({a:<28}, {b:<28}) = {corr.loc[a, b]:+.3f}")
print("\n  Top |r| pairs overall (>= 0.5):")
pairs = []
for i, a in enumerate(FEATS):
    for b in FEATS[i + 1:]:
        r = corr.loc[a, b]
        if np.isfinite(r) and abs(r) >= 0.5:
            pairs.append((abs(r), a, b, r))
for _, a, b, r in sorted(pairs, reverse=True):
    print(f"    {a:<28} {b:<28} r={r:+.3f}")

# ── 2. Jackknife AUROC sensitivity ───────────────────────────────────────────
print("\n" + "=" * 78)
print("2. JACKKNIFE (leave-one-VIN-out) SINGLE-FEATURE AUROC SENSITIVITY")
print("=" * 78)
rows = []
for f in FEATS:
    v = fm[f].values.astype(float)
    full = rank_auroc(v, y)
    full_o = max(full, 1 - full)
    jk = []
    infl = []
    for i in range(len(y)):
        m = np.ones(len(y), bool)
        m[i] = False
        a = rank_auroc(v[m], y[m])
        a_o = max(a, 1 - a) if np.isfinite(a) else np.nan
        jk.append(a_o)
        infl.append((full_o - a_o, fm["vin_label"].iloc[i]))
    jk = np.array(jk)
    worst_drop, worst_vin = max(infl)  # largest positive drop = removing that VIN hurts most? sign:
    # full - jk > 0 means removing VIN *lowers* AUROC -> VIN was carrying signal
    best_gain, best_vin = min(infl)
    rows.append({
        "feature": f, "auroc_full": round(full_o, 4),
        "jk_min": round(np.nanmin(jk), 4), "jk_max": round(np.nanmax(jk), 4),
        "jk_std": round(np.nanstd(jk), 4),
        "max_drop_vin": worst_vin, "max_drop": round(worst_drop, 4),
        "max_gain_vin": best_vin, "max_gain": round(-best_gain, 4),
    })
jk_df = pd.DataFrame(rows).sort_values("auroc_full", ascending=False)
jk_df.to_csv(OUT / "B1_jackknife_auroc.csv", index=False)
print(jk_df.to_string(index=False))

# ── 3. Time-proxy check ──────────────────────────────────────────────────────
print("\n" + "=" * 78)
print("3. TIME-PROXY / EPOCH-LEAKAGE CHECK")
print("=" * 78)
weekly_files = sorted((ROOT / "cache" / "weekly").glob("*.parquet"))
wk_all = pd.concat([pd.read_parquet(f) for f in weekly_files], ignore_index=True)
wk_all["week"] = pd.to_datetime(wk_all["week"])
ev = pd.read_parquet(ROOT / "cache" / "events" / "V1_SM_crank_events.parquet")
ev = ev[ev["artifact"] == False].copy()
ev["ts_start"] = pd.to_datetime(ev["ts_start"])

proxy_rows = []
for vin in fm["vin_label"]:
    w = wk_all[wk_all["vin_label"] == vin]
    wm = w[w["active_days"] >= 2]
    e = ev[ev["vin_label"] == vin]
    proxy_rows.append({
        "vin_label": vin,
        "n_weeks_total": len(w),
        "n_weeks_masked": len(wm),
        "active_days_total": int(w["active_days"].sum()),
        "t_start_ord": w["week"].min().toordinal(),
        "t_end_ord": w["week"].max().toordinal(),
        "span_days": (w["week"].max() - w["week"].min()).days,
        "n_events": len(e),
    })
px = pd.DataFrame(proxy_rows)
PROXIES = ["n_weeks_total", "n_weeks_masked", "active_days_total",
           "t_start_ord", "t_end_ord", "span_days", "n_events"]

print("\n  Do the proxies themselves discriminate failed vs NF? (oriented AUROC, MW p)")
for p in PROXIES:
    v = px[p].values.astype(float)
    a = rank_auroc(v, y)
    mwp = stats.mannwhitneyu(v[y == 1], v[y == 0]).pvalue
    fmean, nfmean = v[y == 1].mean(), v[y == 0].mean()
    print(f"    {p:<18} AUROC={max(a,1-a):.3f} (dir={'F>NF' if a>0.5 else 'F<NF'}) "
          f"p={mwp:.4f}  F_mean={fmean:.1f} NF_mean={nfmean:.1f}")

tp_rows = []
for f in FEATS:
    v = fm[f].values.astype(float)
    row = {"feature": f, "auroc": round(max(rank_auroc(v, y), 1 - rank_auroc(v, y)), 3)}
    for p in PROXIES:
        m = np.isfinite(v)
        r, _ = stats.spearmanr(v[m], px[p].values[m])
        row[f"r_{p}"] = round(r, 3)
    row["max_abs_r_proxy"] = max(abs(row[f"r_{p}"]) for p in PROXIES)
    tp_rows.append(row)
tp = pd.DataFrame(tp_rows).sort_values("max_abs_r_proxy", ascending=False)
tp.to_csv(OUT / "B1_time_proxy.csv", index=False)
print("\n  Feature vs proxy Spearman r (sorted by max |r|; flag >= 0.5):")
print(tp.to_string(index=False))

# ── 4. VIN8_F_SM miss diagnosis ──────────────────────────────────────────────
print("\n" + "=" * 78)
print("4. VIN8_F_SM PROFILE (missed failure, LOVO P=0.303)")
print("=" * 78)
v8 = fm[fm["vin_label"] == "VIN8_F_SM"].iloc[0]
rows = []
for f in FEATS:
    v = fm[f].values.astype(float)
    val = float(v8[f]) if np.isfinite(float(v8[f])) else np.nan
    pct = np.nan
    if np.isfinite(val):
        m = np.isfinite(v)
        pct = 100.0 * (v[m] < val).mean()
    rows.append({
        "feature": f, "vin8_value": val, "fleet_pctile": round(pct, 1),
        "F_median": round(np.nanmedian(v[y == 1]), 4),
        "NF_median": round(np.nanmedian(v[y == 0]), 4),
        "winner": f in WINNERS,
    })
v8df = pd.DataFrame(rows)
v8df.to_csv(OUT / "B1_vin8_profile.csv", index=False)
print(v8df.to_string(index=False))

# VIN8 telemetry context
w8 = wk_all[wk_all["vin_label"] == "VIN8_F_SM"].sort_values("week")
w8m = w8[w8["active_days"] >= 2]
gaps = w8["week"].diff().dt.days.dropna()
print(f"\n  VIN8_F_SM weekly cache: {len(w8)} weeks total, {len(w8m)} masked (active>=2), "
      f"span {w8['week'].min().date()} -> {w8['week'].max().date()}")
print(f"  Max inter-week gap: {gaps.max():.0f} days; gaps > 14d: {(gaps > 14).sum()}")
e8 = ev[ev["vin_label"] == "VIN8_F_SM"]
print(f"  Crank events (non-artifact): {len(e8)}; last-90d events: {(e8['days_before_t_end'] <= 90).sum()}")
e8s = e8[e8["success"].notna()]
e8s_90 = e8s[e8s["days_before_t_end"] <= 90]
print(f"  failed_crank_rate overall: {(~e8s['success'].astype(bool)).mean():.4f} "
      f"(n={len(e8s)}); last90: {(~e8s_90['success'].astype(bool)).mean():.4f} (n={len(e8s_90)})")
# last 8 masked weeks of vsi_drive_mean
print(f"  Last 8 masked weeks vsi_drive_mean: "
      f"{np.round(w8m['vsi_drive_mean'].tail(8).values.astype(float), 2)}")
print(f"  All-weeks std vsi_drive_mean: {np.nanstd(w8m['vsi_drive_mean'].values.astype(float)):.3f}; "
      f"last-4 std: {np.nanstd(w8m['vsi_drive_mean'].tail(4).values.astype(float)):.3f}")
print("\nDone. Outputs in", OUT)
