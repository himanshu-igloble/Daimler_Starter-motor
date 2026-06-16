# E4: month-of-year effects on vsi_drive_std, crank success, rest VSI — whole fleet pooled,
# conditioned on SMA-config cohort. Tests whether the NF "trending" FP problem is seasonal.
import glob
import numpy as np, pandas as pd, polars as pl
from scipy.stats import kruskal

ROOT = "D:/Daimler-starter_motor_alternator_battery/STARTER MOTOR"
OUT = f"{ROOT}/V1.1/discovery/out"
SMA_DEAD = {"VIN8_F_SM", "VIN9_F_SM", "VIN10_NF_SM", "VIN11_NF_SM", "VIN12_NF_SM", "VIN13_NF_SM", "VIN20_NF_SM"}
SEASON = {12: "winter", 1: "winter", 2: "winter", 3: "summer", 4: "summer", 5: "summer",
          6: "monsoon", 7: "monsoon", 8: "monsoon", 9: "monsoon", 10: "post-monsoon", 11: "post-monsoon"}

wk = []
for f in sorted(glob.glob(f"{ROOT}/cache/weekly/V1_SM_weekly_*.parquet")):
    w = pl.read_parquet(f).filter(pl.col("n_rows") > 0).to_pandas()
    wk.append(w)
wk = pd.concat(wk, ignore_index=True)
wk["month"] = pd.to_datetime(wk.week).dt.month
wk["season"] = wk.month.map(SEASON)
wk["cohort"] = np.where(wk.vin_label.isin(SMA_DEAD), "sma_dead", "sma_alive")

# VIN-month means (each VIN-month one obs -> no VIN weighting)
vm = wk.groupby(["vin_label", "cohort", "failed", "month", "season"], as_index=False).agg(
    vsi_drive_std=("vsi_drive_std", "mean"), vsi_rest_median=("vsi_rest_median", "mean"))

res = []
for metric in ["vsi_drive_std", "vsi_rest_median"]:
    for coh in ["sma_alive", "sma_dead"]:
        d = vm[(vm.cohort == coh)].dropna(subset=[metric])
        groups = [d[metric][d.month == m] for m in range(1, 13) if (d.month == m).sum() >= 3]
        if len(groups) >= 6:
            p = kruskal(*groups)[1]
            monthly = d.groupby("month")[metric].median()
            seas = d.groupby("season")[metric].median()
            res.append(dict(metric=metric, cohort=coh, n_vinmonths=len(d), kw_p=round(p, 4),
                            month_min=f"{monthly.idxmin()}:{monthly.min():.3f}",
                            month_max=f"{monthly.idxmax()}:{monthly.max():.3f}",
                            **{f"med_{k}": round(v, 3) for k, v in seas.items()}))
seasdf = pd.DataFrame(res)
seasdf.to_csv(f"{OUT}/E4_seasonality_tests.csv", index=False)
print(seasdf.to_string(index=False))

# crank success by month (events; SMA-alive cohort only; also condition on failed)
ev = pl.read_parquet(f"{ROOT}/cache/events/V1_SM_crank_events.parquet").filter(~pl.col("artifact")).to_pandas()
ev["success"] = ev.success.astype(bool)
ev = ev[~ev.vin_label.isin(SMA_DEAD)]
ev["month"] = ev.ts_start.dt.month
ev["season"] = ev.month.map(SEASON)
# per VIN-month success rate, NF only (avoid failure-proximity contamination)
evn = ev[~ev.failed.astype(bool)]
vms = evn.groupby(["vin_label", "month"]).agg(sr=("success", "mean"), n=("success", "size")).reset_index()
vms = vms[vms.n >= 5]
groups = [vms.sr[vms.month == m] for m in range(1, 13) if (vms.month == m).sum() >= 3]
p = kruskal(*groups)[1]
mon = vms.groupby("month").sr.median().round(4)
print(f"\nNF crank success rate by month (VIN-month medians, n>=5 events): KW p={p:.4f}")
print(mon.to_string())
vms.groupby("month").agg(sr_med=("sr", "median"), n_vinmonths=("sr", "size")).round(4).to_csv(f"{OUT}/E4_crank_success_by_month.csv")

# Is the causal std-ratio "trending" flag seasonal? For NF trucks: flag weeks where
# trailing-4wk vsi_drive_std / expanding mean > 1.30 (NF p90 from E3); count flags per calendar month.
flags = []
for v, g in wk[wk.failed == 0].sort_values("week").groupby("vin_label"):
    s = g.vsi_drive_std.astype(float).reset_index(drop=True)
    ratio = s.rolling(4, min_periods=2).mean() / s.expanding(min_periods=8).mean()
    gg = g.reset_index(drop=True)
    gg["flag"] = (ratio > 1.30).fillna(False).values
    flags.append(gg[["vin_label", "month", "season", "flag"]])
flags = pd.concat(flags)
bym = flags.groupby("month").agg(flag_rate=("flag", "mean"), n_wk=("flag", "size"))
bys = flags.groupby("season").agg(flag_rate=("flag", "mean"), n_wk=("flag", "size"))
from scipy.stats import chi2_contingency
ct = pd.crosstab(flags.season, flags.flag)
chi_p = chi2_contingency(ct)[1]
print(f"\nNF causal-ratio>1.30 flag rate by month (chi2 season p={chi_p:.4f}):")
print(bym.round(3).to_string())
print(bys.round(3).to_string())
bym.round(4).to_csv(f"{OUT}/E4_nf_trendflag_by_month.csv")

# t_end month distribution (does NF history end in a high-flag season? relevant to last90-window features)
te = wk.groupby(["vin_label", "failed"]).week.max().reset_index()
te["m_end"] = pd.to_datetime(te.week).dt.month
print("\nt_end month distribution (failed / NF):")
print(pd.crosstab(te.m_end, te.failed).to_string())
print("E4 done")
