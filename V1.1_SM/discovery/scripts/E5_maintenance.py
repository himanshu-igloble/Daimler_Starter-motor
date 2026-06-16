# E5: maintenance/operational fingerprints — rest-VSI step changes (battery replacement),
# duty-cycle clusters (cohort-conditioned).
import glob
import numpy as np, pandas as pd, polars as pl
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import AgglomerativeClustering

ROOT = "D:/Daimler-starter_motor_alternator_battery/STARTER MOTOR"
OUT = f"{ROOT}/V1.1/discovery/out"
SMA_DEAD = {"VIN8_F_SM", "VIN9_F_SM", "VIN10_NF_SM", "VIN11_NF_SM", "VIN12_NF_SM", "VIN13_NF_SM", "VIN20_NF_SM"}

ev = pl.read_parquet(f"{ROOT}/cache/events/V1_SM_crank_events.parquet").filter(~pl.col("artifact")).to_pandas()

steps, duty = [], []
for f in sorted(glob.glob(f"{ROOT}/cache/weekly/V1_SM_weekly_*.parquet")):
    w = pl.read_parquet(f).filter(pl.col("n_rows") > 0).sort("week").to_pandas()
    vin = w.vin_label.iloc[0]; failed = bool(w.failed.iloc[0])
    # --- step scan on vsi_rest_median (battery replacement = sustained step UP) ---
    for col in ["vsi_rest_median", "vsi_drive_mean"]:
        s = w[col].astype(float).values
        wkdate = pd.to_datetime(w.week).values
        m = ~np.isnan(s)
        si, di = s[m], wkdate[m]
        best = None
        if len(si) >= 16:
            for i in range(8, len(si) - 8):
                a, b = si[:i], si[i:]
                step = np.median(b) - np.median(a)
                pooled_mad = (np.median(np.abs(a - np.median(a))) + np.median(np.abs(b - np.median(b)))) / 2 + 1e-6
                snr = abs(step) / pooled_mad
                if best is None or abs(step) > abs(best[0]):
                    best = (step, snr, di[i])
        if best:
            steps.append(dict(vin_label=vin, failed=failed, signal=col, step_V=round(best[0], 3),
                              snr=round(best[1], 2), step_week=pd.Timestamp(best[2]).date()))
    # --- duty cycle features ---
    e = ev[ev.vin_label == vin]
    n_days = max(w.active_days.sum(), 1)
    duty.append(dict(vin_label=vin, failed=failed, sma_dead=vin in SMA_DEAD,
                     cranks_per_active_day=len(e) / n_days,
                     active_days_per_week=w.active_days.mean(),
                     rpm_mean=np.nanmean(w.rpm_mean), csp_mean=np.nanmean(w.csp_mean),
                     anr_pos_mean=np.nanmean(w.anr_pos_mean),
                     rows_per_active_day=w.n_rows.sum() / n_days))

steps = pd.DataFrame(steps)
steps.to_csv(f"{OUT}/E5_step_changes_all.csv", index=False)
big = steps[(steps.signal == "vsi_rest_median") & (steps.step_V.abs() >= 0.5) & (steps.snr >= 2)]
print("Sustained rest-VSI steps |dV|>=0.5, SNR>=2 (battery-replacement candidates if positive):")
print(big.sort_values("step_V", ascending=False).to_string(index=False))
bigd = steps[(steps.signal == "vsi_drive_mean") & (steps.step_V.abs() >= 0.4) & (steps.snr >= 2)]
print("\nSustained drive-VSI steps |dV|>=0.4, SNR>=2 (regulator/alternator service):")
print(bigd.sort_values("step_V", ascending=False).to_string(index=False))

# --- duty-cycle clustering, conditioned on cohort (crank-rate features only valid within cohort) ---
duty = pd.DataFrame(duty)
duty.to_csv(f"{OUT}/E5_duty_cycle.csv", index=False)
for coh, d in [("sma_alive", duty[~duty.sma_dead]), ("sma_dead", duty[duty.sma_dead])]:
    cols = ["cranks_per_active_day", "active_days_per_week", "rpm_mean", "csp_mean", "anr_pos_mean"]
    X = d[cols].fillna(d[cols].median())
    if len(d) < 6:
        print(f"\n{coh}: n={len(d)} too small to cluster; ranges:")
        print(d[["vin_label", "failed"] + cols].round(2).to_string(index=False))
        continue
    Z = StandardScaler().fit_transform(X)
    for k in [2, 3]:
        lab = AgglomerativeClustering(n_clusters=k).fit_predict(Z)
        d2 = d.copy(); d2["cl"] = lab
        comp = d2.groupby("cl").agg(n=("vin_label", "size"), n_failed=("failed", "sum"),
                                    cranks_day=("cranks_per_active_day", "median"),
                                    act_days_wk=("active_days_per_week", "median"),
                                    rpm=("rpm_mean", "median"), csp=("csp_mean", "median"))
        print(f"\n{coh} duty clusters k={k}:")
        print(comp.round(2).to_string())
print("E5 done")
