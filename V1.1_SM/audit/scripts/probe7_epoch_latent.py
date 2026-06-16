"""Probe 7 — (a) Epoch/extraction-batch structure beyond V1's calendar-truncation
control; (b) latent degradation screen: last-8-weeks delta vs own baseline,
failed vs NF, on weekly-cache channels and crank-event channels.
"""
import polars as pl
import numpy as np
from pathlib import Path
from scipy.stats import mannwhitneyu

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "STARTER MOTOR/V1.1/audit"
WK = ROOT / "STARTER MOTOR/cache/weekly"
EV = ROOT / "STARTER MOTOR/cache/events/V1_SM_crank_events.parquet"

wk = pl.concat([pl.read_parquet(p) for p in sorted(WK.glob("*.parquet"))])

# ---------- (a) epoch structure ----------
span = wk.group_by("vin_label", "failed").agg(
    pl.col("week").min().alias("w_start"), pl.col("week").max().alias("w_end"))
span = span.with_columns(
    pl.col("w_end").dt.epoch("d").alias("end_ord"),
    pl.col("w_start").dt.epoch("d").alias("start_ord"),
)
y = span["failed"].to_numpy()
for c in ("end_ord", "start_ord"):
    x = span[c].to_numpy().astype(float)
    u, p = mannwhitneyu(x[y], x[~y], alternative="two-sided")
    print(f"{c}: AUROC(F high)={u/(y.sum()*(~y).sum()):.3f} p={p:.5f}")
print(span.sort("w_end").select("vin_label", "w_start", "w_end").to_pandas().to_string())

# firmware cohort (SMA-dead) vs extraction end
sma_dead = {"VIN8_F_SM", "VIN9_F_SM", "VIN10_NF_SM", "VIN11_NF_SM", "VIN12_NF_SM", "VIN13_NF_SM", "VIN20_NF_SM"}
span = span.with_columns(pl.col("vin_label").is_in(sma_dead).alias("sma_dead"))
print(span.group_by("sma_dead").agg(pl.col("w_end").max().alias("w_end_max"), pl.col("w_end").min().alias("w_end_min"), pl.len()))

# ---------- (b) latent degradation: last 8 weeks vs own prior baseline ----------
wk = wk.with_columns(
    (pl.col("sma1_rows") / pl.col("active_days").clip(1)).alias("sma1_per_aday"),
    (pl.col("n_rows") / pl.col("active_days").clip(1)).alias("rows_per_aday"),
)
chans = ["vsi_rest_median", "vsi_rest_p05", "vsi_drive_mean", "vsi_drive_std",
         "vsi_drive_p95", "rpm_mean", "csp_mean", "anr_pos_mean",
         "sma1_per_aday", "rows_per_aday"]
wk = wk.with_columns(pl.col("week").rank("ordinal", descending=True).over("vin_label").alias("wk_from_end"))
rows = []
for vin in wk["vin_label"].unique():
    d = wk.filter(pl.col("vin_label") == vin)
    last = d.filter(pl.col("wk_from_end") <= 8)
    base = d.filter(pl.col("wk_from_end") > 8)
    if len(base) < 8:
        continue
    r = {"vin_label": vin, "failed": bool(d["failed"][0])}
    for c in chans:
        b, l = base[c].drop_nulls(), last[c].drop_nulls()
        if len(b) >= 4 and len(l) >= 2:
            bs = b.std()
            r[f"d_{c}"] = float(l.median() - b.median())
            r[f"z_{c}"] = float((l.median() - b.median()) / bs) if bs and bs > 0 else None
    rows.append(r)
lat = pl.DataFrame(rows)
lat.write_csv(OUT / "probe7_latent_last8wk_delta.csv")

y2 = lat["failed"].to_numpy()
print("\nLatent screen: last-8-weeks median minus prior-baseline median (delta), F vs NF")
res = []
for c in chans:
    col = f"d_{c}"
    if col not in lat.columns:
        continue
    x = lat[col].to_numpy().astype(float)
    ok = ~np.isnan(x)
    yf, xv = y2[ok], x[ok]
    if yf.sum() < 5 or (~yf).sum() < 5:
        continue
    u, p = mannwhitneyu(xv[yf], xv[~yf], alternative="two-sided")
    auc = u / (yf.sum() * (~yf).sum())
    res.append({"channel": c, "delta_auroc_F_high": round(auc, 3), "p": round(p, 4),
                "mean_dF": round(float(xv[yf].mean()), 4), "mean_dNF": round(float(xv[~yf].mean()), 4),
                "nF": int(yf.sum()), "nNF": int((~yf).sum())})
sc = pl.DataFrame(res).sort("delta_auroc_F_high", descending=True)
sc.write_csv(OUT / "probe7_latent_screen.csv")
with pl.Config(tbl_rows=20, tbl_width_chars=160):
    print(sc)

# ---------- crank-event final-60d shift ----------
ev = pl.read_parquet(EV).filter(~pl.col("artifact"))
rows = []
for vin in ev["vin_label"].unique():
    d = ev.filter(pl.col("vin_label") == vin)
    last = d.filter(pl.col("days_before_t_end") <= 60)
    base = d.filter(pl.col("days_before_t_end") > 60)
    if len(last) < 10 or len(base) < 30:
        continue
    rows.append({
        "vin_label": vin, "failed": bool(d["failed"][0]),
        "d_dip": float((last["dip_depth"].median() or np.nan) - (base["dip_depth"].median() or np.nan)),
        "d_recov": float((last["recovery_slope"].median() or np.nan) - (base["recovery_slope"].median() or np.nan)),
        "d_minvsi": float((last["min_vsi_crank"].median() or np.nan) - (base["min_vsi_crank"].median() or np.nan)),
        "d_success": float(last["success"].mean() - base["success"].mean()),
        "d_retry": float(last["retry_within_120s"].mean() - base["retry_within_120s"].mean()),
        "n_last": len(last), "n_base": len(base),
    })
ce = pl.DataFrame(rows)
ce.write_csv(OUT / "probe7_crank_final60d_delta.csv")
y3 = ce["failed"].to_numpy()
print("\nCrank-event final-60d delta screen:")
for c in ("d_dip", "d_recov", "d_minvsi", "d_success", "d_retry"):
    x = ce[c].to_numpy().astype(float)
    ok = ~np.isnan(x)
    yf, xv = y3[ok], x[ok]
    if yf.sum() < 4 or (~yf).sum() < 4:
        print(c, "insufficient n"); continue
    u, p = mannwhitneyu(xv[yf], xv[~yf], alternative="two-sided")
    print(f"{c}: AUROC={u/(yf.sum()*(~yf).sum()):.3f} p={p:.4f} meanF={xv[yf].mean():.4f} meanNF={xv[~yf].mean():.4f} nF={yf.sum()} nNF={(~yf).sum()}")
