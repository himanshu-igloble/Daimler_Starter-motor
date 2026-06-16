# E3: degradation trajectory shapes — causal weekly vsi_std_ratio + rolling failed-crank rate,
# aligned on last 40 OBSERVED weeks, failed VINs vs NF envelope. Plot-free, numeric shape classes.
import glob
import numpy as np, pandas as pd, polars as pl
from scipy.stats import spearmanr

ROOT = "D:/Daimler-starter_motor_alternator_battery/STARTER MOTOR"
OUT = f"{ROOT}/V1.1/discovery/out"
ALIGN = 40

ev = pl.read_parquet(f"{ROOT}/cache/events/V1_SM_crank_events.parquet").filter(~pl.col("artifact")).to_pandas()
ev["success"] = ev["success"].astype(bool)
ev["week"] = ev["ts_start"].dt.to_period("W-SUN").dt.start_time  # match weekly cache Monday anchor? verify below

traj = {}
for f in sorted(glob.glob(f"{ROOT}/cache/weekly/V1_SM_weekly_*.parquet")):
    w = pl.read_parquet(f).filter(pl.col("n_rows") > 0).sort("week").to_pandas()
    vin = w.vin_label.iloc[0]; failed = bool(w.failed.iloc[0])
    # causal within-week std ratio: trailing-4-week mean of vsi_drive_std / expanding mean (>=8 wks history)
    s = w.vsi_drive_std.astype(float)
    roll4 = s.rolling(4, min_periods=2).mean()
    expand = s.expanding(min_periods=8).mean()
    ratio = (roll4 / expand).values
    # rolling 4-week failed-crank rate from events mapped onto observed weeks
    e = ev[ev.vin_label == vin].copy()
    wk_keys = pd.to_datetime(w.week).dt.to_period("W-SUN").dt.start_time
    fail_by_wk = e.groupby("week").agg(n=("success", "size"), nf=("success", lambda x: (~x).sum()))
    n = fail_by_wk.reindex(wk_keys.values)["n"].fillna(0).values
    nf_ = fail_by_wk.reindex(wk_keys.values)["nf"].fillna(0).values
    rn = pd.Series(n).rolling(4, min_periods=1).sum().values
    rf = pd.Series(nf_).rolling(4, min_periods=1).sum().values
    fcr = np.where(rn > 0, rf / np.maximum(rn, 1), np.nan)
    traj[vin] = dict(failed=failed, ratio=ratio, fcr=fcr, nweeks=len(w))

def last_align(a, k=ALIGN):
    a = np.asarray(a, dtype=float)
    out = np.full(k, np.nan)
    m = min(k, len(a))
    out[-m:] = a[-m:]
    return out

R = {v: last_align(d["ratio"]) for v, d in traj.items()}
F = {v: last_align(d["fcr"]) for v, d in traj.items()}
nf_vins = [v for v, d in traj.items() if not d["failed"]]
f_vins = [v for v, d in traj.items() if d["failed"]]

# NF envelope per aligned position
nfR = np.vstack([R[v] for v in nf_vins])
nfF = np.vstack([F[v] for v in nf_vins])
envR_med, envR_p90 = np.nanmedian(nfR, 0), np.nanpercentile(nfR, 90, 0)
envF_p90 = np.nanpercentile(nfF, 90, 0)
env = pd.DataFrame(dict(pos=np.arange(-ALIGN, 0), ratio_med=envR_med, ratio_p90=envR_p90, fcr_p90=envF_p90))
env.round(4).to_csv(f"{OUT}/E3_nf_envelope.csv", index=False)
print("NF envelope ratio_p90 (mean over positions): %.3f; fcr_p90 mean: %.3f" % (np.nanmean(envR_p90), np.nanmean(envF_p90)))

def shape(series, env_p90):
    s = np.asarray(series, float)
    m = ~np.isnan(s)
    if m.sum() < 10:
        return dict(shape="INSUFFICIENT", trend_rho=np.nan, late_delta=np.nan, wks_above_p90_last12=np.nan)
    t = np.arange(len(s))[m]; y = s[m]
    rho = spearmanr(t, y)[0]
    late = np.nanmean(s[-8:]) - np.nanmean(s[-28:-8])
    above = int(np.nansum((s[-12:] > env_p90[-12:])))
    if above >= 4 and late > 0.10 * max(np.nanmean(np.abs(y)), 1e-9):
        cls = "LATE_SPIKE" if rho < 0.5 else "MONOTONE_DRIFT"
    elif rho >= 0.5:
        cls = "MONOTONE_DRIFT"
    else:
        cls = "FLAT"
    return dict(shape=cls, trend_rho=round(rho, 3), late_delta=round(float(late), 4), wks_above_p90_last12=above)

rows = []
for v in f_vins + nf_vins:
    r1 = shape(R[v], envR_p90); r2 = shape(F[v], envF_p90)
    rows.append(dict(vin_label=v, failed=traj[v]["failed"],
                     ratio_shape=r1["shape"], ratio_rho=r1["trend_rho"], ratio_late_delta=r1["late_delta"],
                     ratio_wks_gt_nfp90_last12=r1["wks_above_p90_last12"],
                     fcr_shape=r2["shape"], fcr_rho=r2["trend_rho"], fcr_late_delta=r2["late_delta"],
                     fcr_wks_gt_nfp90_last12=r2["wks_above_p90_last12"]))
sh = pd.DataFrame(rows)
sh.to_csv(f"{OUT}/E3_trajectory_shapes.csv", index=False)
print("\nFAILED trajectory shapes:")
print(sh[sh.failed].to_string(index=False))
print("\nNF shape distribution (honest FP check):")
print(sh[~sh.failed].groupby("ratio_shape").size().to_string())
print(sh[~sh.failed].groupby("fcr_shape").size().to_string())
print("\nNF VINs with ratio_wks_gt_nfp90_last12 >= 4:", sh[(~sh.failed) & (sh.ratio_wks_gt_nfp90_last12 >= 4)].vin_label.tolist())
print("FAILED VINs with ratio_wks_gt_nfp90_last12 >= 4:", sh[(sh.failed) & (sh.ratio_wks_gt_nfp90_last12 >= 4)].vin_label.tolist())
print("E3 done")
