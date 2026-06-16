# E2: final-120-day signature cards for the 14 failed VINs + NF reference -> archetype grouping
import glob
import numpy as np, pandas as pd, polars as pl
from scipy.stats import theilslopes
from scipy.cluster.hierarchy import linkage, fcluster

ROOT = "D:/Daimler-starter_motor_alternator_battery/STARTER MOTOR"
OUT = f"{ROOT}/V1.1/discovery/out"
SILENT_GAP = {"VIN1_F_SM": 72, "VIN4_F_SM": 97, "VIN5_F_SM": 32, "VIN8_F_SM": 37, "VIN9_F_SM": 142}
SMA_DEAD = {"VIN8_F_SM", "VIN9_F_SM", "VIN10_NF_SM", "VIN11_NF_SM", "VIN12_NF_SM", "VIN13_NF_SM", "VIN20_NF_SM"}

ev = pl.read_parquet(f"{ROOT}/cache/events/V1_SM_crank_events.parquet").filter(~pl.col("artifact"))
evp = ev.to_pandas()
evp["success"] = evp["success"].astype(bool)
evp["retry_within_120s"] = evp["retry_within_120s"].astype(bool)

cards = []
for f in sorted(glob.glob(f"{ROOT}/cache/weekly/V1_SM_weekly_*.parquet")):
    w = pl.read_parquet(f).filter(pl.col("n_rows") > 0).sort("week").to_pandas()
    vin = w["vin_label"].iloc[0]
    failed = bool(w["failed"].iloc[0])
    t_end = w["week"].max() + pd.Timedelta(days=6)  # end of last observed week
    e = evp[evp.vin_label == vin]
    e120 = e[e.days_before_t_end <= 120]
    ebase = e[e.days_before_t_end > 120]
    e30 = e[e.days_before_t_end <= 30]

    def fcr(d):  # failed-crank rate
        return float((~d.success).mean()) if len(d) else np.nan
    def rr(d):
        return float(d.retry_within_120s.mean()) if len(d) else np.nan

    # max failed cranks in any single day, last 120d (burst detector)
    if len(e120):
        ef = e120.loc[~e120.success.values]
        daily_fail = ef.groupby(ef.ts_start.dt.date).size()
        max_daily_failed = int(daily_fail.max()) if len(daily_fail) else 0
    else:
        max_daily_failed = np.nan

    # weekly windows
    w["days_to_end"] = (t_end - w["week"]).dt.days
    w120 = w[w.days_to_end <= 126]
    wbase = w[w.days_to_end > 126]
    dstd_120 = w120.vsi_drive_std.mean()
    dstd_base = wbase.vsi_drive_std.mean()
    # rest-VSI trend last 120d (Theil-Sen V/week)
    rv = w120.dropna(subset=["vsi_rest_median"])
    rest_slope = theilslopes(rv.vsi_rest_median, np.arange(len(rv)))[0] if len(rv) >= 5 else np.nan
    rest_delta = (w120.vsi_rest_median.mean() - wbase.vsi_rest_median.mean()
                  if wbase.vsi_rest_median.notna().sum() >= 4 and w120.vsi_rest_median.notna().sum() >= 2 else np.nan)
    # telemetry density taper: last 4 obs weeks vs lifetime median
    taper = float(w.n_rows.tail(4).mean() / w.n_rows.median()) if len(w) >= 8 else np.nan

    cards.append(dict(
        vin_label=vin, failed=failed, sma_dead=vin in SMA_DEAD,
        n_events_120=len(e120), n_events_base=len(ebase),
        fcr_base=round(fcr(ebase), 4) if len(ebase) else np.nan,
        fcr_120=round(fcr(e120), 4) if len(e120) else np.nan,
        fcr_30=round(fcr(e30), 4) if len(e30) else np.nan,
        retry_base=round(rr(ebase), 4) if len(ebase) else np.nan,
        retry_120=round(rr(e120), 4) if len(e120) else np.nan,
        max_daily_failed_120=max_daily_failed,
        dip_depth_delta=round(float(e120.dip_depth.mean() - ebase.dip_depth.mean()), 3)
            if len(e120) > 5 and len(ebase) > 5 else np.nan,
        vsi_drive_std_120=round(float(dstd_120), 4) if dstd_120 == dstd_120 else np.nan,
        vsi_drive_std_ratio=round(float(dstd_120 / dstd_base), 3) if dstd_base and dstd_base == dstd_base else np.nan,
        rest_vsi_slope_120=round(float(rest_slope), 4) if rest_slope == rest_slope else np.nan,
        rest_vsi_delta=round(float(rest_delta), 3) if rest_delta == rest_delta else np.nan,
        density_taper=round(taper, 3) if taper == taper else np.nan,
        silent_gap_d=SILENT_GAP.get(vin, 0),
    ))

cards = pd.DataFrame(cards)
cards["fcr_ratio"] = (cards.fcr_120 / cards.fcr_base.replace(0, np.nan)).round(2)
cards["retry_ratio"] = (cards.retry_120 / cards.retry_base.replace(0, np.nan)).round(2)
cards.to_csv(f"{OUT}/E2_signature_cards_all34.csv", index=False)

nf = cards[~cards.failed]
fc = cards[cards.failed].set_index("vin_label")
print("NF reference (median [p10,p90]):")
for c in ["fcr_120", "fcr_ratio", "retry_120", "vsi_drive_std_ratio", "rest_vsi_slope_120",
          "rest_vsi_delta", "dip_depth_delta", "density_taper", "max_daily_failed_120"]:
    v = nf[c].dropna()
    print(f"  {c}: {v.median():.4f} [{v.quantile(.1):.4f}, {v.quantile(.9):.4f}] (n={len(v)})")

print("\nFAILED-VIN CARDS:")
print(fc.drop(columns=["failed"]).to_string())

# ---- archetype assignment (rule-based, NF-referenced; thresholds = NF p90/p10) ----
thr = {c: nf[c].dropna().quantile(0.9) for c in ["fcr_120", "retry_120", "vsi_drive_std_ratio", "dip_depth_delta", "max_daily_failed_120"]}
thr_lo = {c: nf[c].dropna().quantile(0.1) for c in ["rest_vsi_slope_120", "rest_vsi_delta", "density_taper"]}
print("\nNF p90 thresholds:", {k: round(v, 4) for k, v in thr.items()})
print("NF p10 thresholds:", {k: round(v, 4) for k, v in thr_lo.items()})

def assign(r):
    ev_flags = []
    crank_burst = ((r.fcr_120 == r.fcr_120 and r.fcr_120 > thr["fcr_120"]) or
                   (r.retry_120 == r.retry_120 and r.retry_120 > thr["retry_120"]) or
                   (r.max_daily_failed_120 == r.max_daily_failed_120 and r.max_daily_failed_120 > thr["max_daily_failed_120"]))
    battery = ((r.rest_vsi_slope_120 == r.rest_vsi_slope_120 and r.rest_vsi_slope_120 < thr_lo["rest_vsi_slope_120"]) or
               (r.rest_vsi_delta == r.rest_vsi_delta and r.rest_vsi_delta < thr_lo["rest_vsi_delta"])) and \
              (r.dip_depth_delta == r.dip_depth_delta and r.dip_depth_delta > 0)
    vsi_vol = r.vsi_drive_std_ratio == r.vsi_drive_std_ratio and r.vsi_drive_std_ratio > thr["vsi_drive_std_ratio"]
    if crank_burst: ev_flags.append("CRANK_BURST")
    if battery: ev_flags.append("BATTERY_DECLINE")
    if vsi_vol: ev_flags.append("VSI_VOLATILITY")
    if r.silent_gap_d >= 30: ev_flags.append(f"SILENT_GAP_{int(r.silent_gap_d)}d")
    if not ev_flags or ev_flags == [f"SILENT_GAP_{int(r.silent_gap_d)}d"] and r.silent_gap_d >= 30:
        pass
    return "+".join(ev_flags) if ev_flags else "NONE"

fc2 = fc.reset_index()
fc2["flags"] = fc2.apply(assign, axis=1)
fc2.to_csv(f"{OUT}/E2_failed_cards_flags.csv", index=False)
print("\nFLAGS:")
print(fc2[["vin_label", "flags"]].to_string(index=False))

# ---- hierarchical clustering of failed cards on the signature vector ----
sig_cols = ["fcr_ratio", "retry_120", "vsi_drive_std_ratio", "rest_vsi_slope_120", "dip_depth_delta", "density_taper"]
M = fc2[sig_cols].copy()
M = M.fillna(M.median())
Mz = (M - M.mean()) / M.std().replace(0, 1)
L = linkage(Mz.values, method="ward")
for k in [3, 4]:
    fc2[f"hclust_k{k}"] = fcluster(L, k, criterion="maxclust")
print("\nhclust on cards:")
print(fc2[["vin_label", "hclust_k3", "hclust_k4", "flags"]].sort_values("hclust_k3").to_string(index=False))
fc2.to_csv(f"{OUT}/E2_failed_cards_flags.csv", index=False)
print("\nE2 done")
