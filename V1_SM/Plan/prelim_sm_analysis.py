"""Preliminary analysis of starter motor parquet files for V1_SM_plan.

Outputs per-VIN inventory, crank-event statistics, signal health, and
data-quality findings to STARTER MOTOR/Plan/prelim_sm_analysis_results.md
"""
import polars as pl
from pathlib import Path

ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery")
SM_FAILED = ROOT / "Data/processed/starter_motor_complete/2026-03-06-12-38-23-starter_motor_failed.parquet"
SM_NONFAIL = ROOT / "Data/processed/starter_motor_complete/2026-03-06-12-39-14-starter_motor_non_failed.parquet"
OUT = ROOT / "STARTER MOTOR/Plan/prelim_sm_analysis_results.md"

SENT_CSP_RPM_ANR = 65535.0
SENT_ANR_NEG = -5000.0

lines = []
def md(s=""):
    lines.append(s)

def clean(lf: pl.LazyFrame) -> pl.LazyFrame:
    return lf.with_columns([
        pl.when(pl.col("CSP") >= SENT_CSP_RPM_ANR).then(None).otherwise(pl.col("CSP")).alias("CSP"),
        pl.when(pl.col("RPM") >= SENT_CSP_RPM_ANR).then(None).otherwise(pl.col("RPM")).alias("RPM"),
        pl.when((pl.col("ANR") >= SENT_CSP_RPM_ANR) | (pl.col("ANR") <= SENT_ANR_NEG)).then(None).otherwise(pl.col("ANR")).alias("ANR"),
        pl.when((pl.col("VSI") <= 0.0) | (pl.col("VSI") >= 255.0)).then(None).otherwise(pl.col("VSI")).alias("VSI"),
    ])

for label, path, is_failed in [("FAILED", SM_FAILED, True), ("NON-FAILED", SM_NONFAIL, False)]:
    lf = pl.scan_parquet(path)
    schema = lf.collect_schema()
    md(f"\n## SM {label} file")
    md(f"Path: `{path.name}`")
    md(f"Columns: {schema.names()}")

    lfc = clean(lf)

    # Per-VIN inventory
    agg_exprs = [
        pl.len().alias("rows"),
        pl.col("timestamp").min().alias("ts_min"),
        pl.col("timestamp").max().alias("ts_max"),
        pl.col("timestamp").dt.date().n_unique().alias("active_days"),
        (pl.col("SMA") == 1).sum().alias("sma1_rows"),
        pl.col("SMA").is_null().sum().alias("sma_nulls"),
        pl.col("VSI").mean().alias("vsi_mean"),
        pl.col("VSI").quantile(0.01).alias("vsi_p01"),
        pl.col("VSI").is_null().sum().alias("vsi_nulls"),
        (pl.col("GED") == 2).sum().alias("ged2_rows"),
        (pl.col("GED") == 3).sum().alias("ged3_rows"),
        pl.col("GED").is_null().sum().alias("ged_nulls"),
        pl.col("RPM").mean().alias("rpm_mean"),
        pl.col("CSP").mean().alias("csp_mean"),
    ]
    if is_failed:
        agg_exprs += [
            pl.col("SALEDATE").first().alias("saledate"),
            pl.col("JCOPENDATE").first().alias("jcopendate"),
        ]
    inv = lfc.group_by("VIN").agg(agg_exprs).sort("VIN").collect(engine="streaming")

    md(f"\n### Per-VIN inventory ({label})")
    md("| VIN | rows | first ts | last ts | active days | SMA=1 rows | VSI mean | VSI p01 | GED2 | GED3 |" + (" sale | jcopen | obs→fail gap |" if is_failed else ""))
    md("|---|---|---|---|---|---|---|---|---|---|" + ("---|---|---|" if is_failed else ""))
    for r in inv.iter_rows(named=True):
        base = (f"| {r['VIN']} | {r['rows']:,} | {str(r['ts_min'])[:10]} | {str(r['ts_max'])[:10]} | "
                f"{r['active_days']} | {r['sma1_rows']} | "
                f"{r['vsi_mean']:.2f} | {r['vsi_p01']:.2f} | {r['ged2_rows']} | {r['ged3_rows']} |")
        if is_failed:
            jco = r["jcopendate"]
            tsmax = r["ts_max"]
            gap = (jco - tsmax.date()).days if (jco is not None and tsmax is not None) else None
            base += f" {r['saledate']} | {jco} | {gap}d |"
        md(base)

    # Null summary
    nulls = lfc.select([
        pl.len().alias("total"),
        pl.col("VSI").is_null().sum().alias("VSI_null"),
        pl.col("SMA").is_null().sum().alias("SMA_null"),
        pl.col("GED").is_null().sum().alias("GED_null"),
        pl.col("CSP").is_null().sum().alias("CSP_null"),
        pl.col("RPM").is_null().sum().alias("RPM_null"),
        pl.col("ANR").is_null().sum().alias("ANR_null"),
    ]).collect(engine="streaming")
    r = nulls.row(0, named=True)
    md(f"\n### Null rates after sentinel cleaning ({label})")
    md(f"Total rows: {r['total']:,}")
    for c in ["CSP", "RPM", "ANR", "VSI", "SMA", "GED"]:
        md(f"- {c}: {r[c+'_null']:,} nulls ({100*r[c+'_null']/r['total']:.1f}%)")

    # VSI scaling check: distribution of raw VSI to detect x0.2 scaling subpopulation
    vsi_dist = lf.filter((pl.col("VSI") > 0) & (pl.col("VSI") < 255)).select([
        (pl.col("VSI") > 36).sum().alias("gt36"),
        (pl.col("VSI") <= 36).sum().alias("le36"),
        pl.col("VSI").max().alias("vmax"),
        pl.col("VSI").quantile(0.999).alias("p999"),
    ]).collect(engine="streaming").row(0, named=True)
    md(f"\n### VSI scaling check ({label})")
    md(f"- VSI in (0,255): >36V raw: {vsi_dist['gt36']:,} rows; <=36V: {vsi_dist['le36']:,} rows; max={vsi_dist['vmax']:.1f}, p99.9={vsi_dist['p999']:.1f}")

    # Crank events: group consecutive SMA=1 rows into events per VIN
    crank = (
        lfc.filter(pl.col("SMA").is_not_null())
        .sort(["VIN", "timestamp"])
        .with_columns(
            ((pl.col("SMA") == 1) & (pl.col("SMA").shift(1).over("VIN") != 1)).cast(pl.Int32).alias("crank_start")
        )
        .filter(pl.col("SMA") == 1)
        .with_columns(pl.col("crank_start").cum_sum().over("VIN").alias("event_id"))
        .group_by(["VIN", "event_id"])
        .agg([
            pl.len().alias("n_rows"),
            (pl.col("timestamp").max() - pl.col("timestamp").min()).dt.total_seconds().alias("dur_s"),
            pl.col("VSI").min().alias("vsi_min_during_crank"),
            pl.col("RPM").max().alias("rpm_max_during_crank"),
            pl.col("timestamp").min().alias("event_ts"),
        ])
    ).collect(engine="streaming")

    ev_summary = crank.group_by("VIN").agg([
        pl.len().alias("n_crank_events"),
        pl.col("n_rows").mean().alias("avg_rows_per_event"),
        pl.col("dur_s").mean().alias("avg_dur_s"),
        pl.col("dur_s").max().alias("max_dur_s"),
        pl.col("vsi_min_during_crank").mean().alias("avg_min_vsi"),
        pl.col("vsi_min_during_crank").min().alias("worst_min_vsi"),
    ]).sort("VIN")

    md(f"\n### Crank events (consecutive SMA=1 runs) ({label})")
    md("| VIN | events | avg rows/event | avg dur (s) | max dur (s) | avg min-VSI | worst min-VSI |")
    md("|---|---|---|---|---|---|---|")
    for r in ev_summary.iter_rows(named=True):
        amv = f"{r['avg_min_vsi']:.2f}" if r["avg_min_vsi"] is not None else "—"
        wmv = f"{r['worst_min_vsi']:.2f}" if r["worst_min_vsi"] is not None else "—"
        md(f"| {r['VIN']} | {r['n_crank_events']} | {r['avg_rows_per_event']:.1f} | {r['avg_dur_s']:.1f} | {r['max_dur_s']:.0f} | {amv} | {wmv} |")

    tot_events = crank.height
    md(f"\nTotal crank events ({label}): {tot_events:,}")

    # Sampling interval check
    samp = (
        lfc.sort(["VIN", "timestamp"])
        .with_columns((pl.col("timestamp").diff().over("VIN")).dt.total_seconds().alias("dt"))
        .filter(pl.col("dt").is_not_null() & (pl.col("dt") > 0))
        .select([
            pl.col("dt").median().alias("median_dt"),
            pl.col("dt").quantile(0.99).alias("p99_dt"),
            (pl.col("dt") > 3600).sum().alias("gaps_gt_1h"),
            (pl.col("dt") > 86400).sum().alias("gaps_gt_1d"),
        ]).collect(engine="streaming")
    ).row(0, named=True)
    md(f"\n### Sampling cadence ({label})")
    md(f"- median Δt: {samp['median_dt']:.1f}s · p99 Δt: {samp['p99_dt']:.1f}s · gaps >1h: {samp['gaps_gt_1h']:,} · gaps >1d: {samp['gaps_gt_1d']:,}")

OUT.write_text("\n".join(["# Preliminary SM Data Analysis (auto-generated)", *lines]), encoding="utf-8")
print(f"Wrote {OUT}")
