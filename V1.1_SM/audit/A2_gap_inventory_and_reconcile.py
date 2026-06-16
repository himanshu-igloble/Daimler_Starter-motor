"""
A2_gap_inventory_and_reconcile.py — audit steps 1 (gap inventory), 4 (sparkline
vs raw), 5 (crank ticks), 6 (known-numbers reconciliation).

Requires A1_raw_daily_recompute.py outputs.
Writes: STARTER MOTOR/V1.1/results/V1_1_SM_data_gap_inventory.csv
        STARTER MOTOR/V1.1/audit/out/A2_results.txt (console mirror)
"""
from pathlib import Path
import datetime as dt
import numpy as np
import polars as pl

ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery")
SM = ROOT / "STARTER MOTOR"
AUDIT = SM / "V1.1" / "audit"
DAILY_DIR = SM / "V1.1" / "cache" / "daily"
DQ_CSV = SM / "results" / "V1_SM_data_quality.csv"
EVENTS_PQ = SM / "cache" / "events" / "V1_SM_crank_events.parquet"
OUT_CSV = SM / "V1.1" / "results" / "V1_1_SM_data_gap_inventory.csv"

GAP_VINS = {"VIN1_F_SM": 72, "VIN4_F_SM": 97, "VIN5_F_SM": 32,
            "VIN8_F_SM": 37, "VIN9_F_SM": 142}
MIN_GAP_DAYS = 7

raw_daily = pl.read_parquet(str(AUDIT / "A1_raw_daily.parquet"))
raw_meta = pl.read_csv(str(AUDIT / "A1_raw_vin_meta.csv"))
dq = pl.read_csv(str(DQ_CSV), infer_schema_length=200)

vins = sorted(raw_meta["vin_label"].to_list())
assert len(vins) == 34, f"expected 34 VINs, got {len(vins)}"

lines = []
def log(s=""):
    print(s)
    lines.append(s)

# ===========================================================================
# CHECK 6 — known-numbers reconciliation vs V1_SM_data_quality.csv
# ===========================================================================
log("=" * 78)
log("CHECK 6 — RAW vs V1_SM_data_quality.csv (rows, t_start, t_end, active_days)")
log("=" * 78)
n_ok = 0
for v in vins:
    m = raw_meta.filter(pl.col("vin_label") == v).to_dicts()[0]
    q = dq.filter(pl.col("vin_label") == v).to_dicts()[0]
    ok_rows = int(m["rows"]) == int(q["rows"])
    ok_ts = str(m["t_start"])[:19].replace("T", " ") == str(q["t_start"])[:19]
    ok_te = str(m["t_end"])[:19].replace("T", " ") == str(q["t_end"])[:19]
    ok_ad = int(m["active_days"]) == int(q["active_days_total"])
    ok = ok_rows and ok_ts and ok_te and ok_ad
    n_ok += ok
    flag = "PASS" if ok else "FAIL"
    log(f"  {v:<13} rows {m['rows']:>9}/{q['rows']:<9} t_start {str(m['t_start'])[:19]} "
        f"t_end {str(m['t_end'])[:19]} active {m['active_days']:>3}/{q['active_days_total']:<3} [{flag}]")
log(f"CHECK 6 verdict: {n_ok}/34 agree -> {'PASS' if n_ok == 34 else 'FAIL'}")

# ===========================================================================
# CHECK 1a — cache reproduces raw active-day sets exactly
# ===========================================================================
log()
log("=" * 78)
log("CHECK 1a — daily cache active-date sets == raw active-date sets")
log("=" * 78)
n_ok = 0
cache_daily = {}
for v in vins:
    c = pl.read_parquet(str(DAILY_DIR / f"V1_1_SM_daily_{v}.parquet"))
    cache_daily[v] = c
    raw_dates = set(raw_daily.filter(pl.col("vin_label") == v)["date"].to_list())
    cache_dates = set(c["date"].to_list())
    only_raw = sorted(raw_dates - cache_dates)
    only_cache = sorted(cache_dates - raw_dates)
    # n_rows per day must also agree
    j = (raw_daily.filter(pl.col("vin_label") == v).select(["date", "n_rows"])
         .join(c.select(["date", pl.col("n_rows").alias("n_rows_c")]), on="date", how="inner"))
    nrow_mismatch = int((j["n_rows"] != j["n_rows_c"]).sum())
    ok = not only_raw and not only_cache and nrow_mismatch == 0
    n_ok += ok
    if not ok:
        log(f"  {v:<13} FAIL  raw-only={only_raw[:5]} cache-only={only_cache[:5]} "
            f"n_rows mismatches={nrow_mismatch}")
log(f"CHECK 1a verdict: {n_ok}/34 VINs cache==raw active days & per-day row counts "
    f"-> {'PASS' if n_ok == 34 else 'FAIL'}")

# ===========================================================================
# CHECK 1b — gap inventory (>= 7 zero-telemetry days) from RAW dates
# ===========================================================================
log()
log("=" * 78)
log(f"CHECK 1b — gap inventory (>= {MIN_GAP_DAYS} consecutive zero-telemetry days)")
log("=" * 78)
inv = []
for v in vins:
    dates = sorted(raw_daily.filter(pl.col("vin_label") == v)["date"].to_list())
    for d1, d2 in zip(dates[:-1], dates[1:]):
        missing = (d2 - d1).days - 1
        if missing >= MIN_GAP_DAYS:
            inv.append({"vin": v, "gap_start": str(d1 + dt.timedelta(days=1)),
                        "gap_end": str(d2 - dt.timedelta(days=1)),
                        "days": missing, "type": "mid_history"})
    if v in GAP_VINS:
        q = dq.filter(pl.col("vin_label") == v).to_dicts()[0]
        t_end_date = dt.datetime.fromisoformat(str(q["t_end"])).date()
        jco = dt.date.fromisoformat(str(q["jcopendate"]))
        days = (jco - t_end_date).days
        inv.append({"vin": v, "gap_start": str(t_end_date + dt.timedelta(days=1)),
                    "gap_end": str(jco), "days": days, "type": "terminal_silent"})
        exp = GAP_VINS[v]
        log(f"  {v}: terminal silent gap {days}d (expected {exp}) "
            f"[{'PASS' if days == exp else 'FAIL'}]")

inv_df = pl.DataFrame(inv).sort(["vin", "gap_start"])
inv_df.write_csv(str(OUT_CSV))
log(f"  wrote {OUT_CSV} ({len(inv_df)} gaps)")
log()
log("  Full inventory:")
for r in inv_df.to_dicts():
    log(f"    {r['vin']:<13} {r['gap_start']} -> {r['gap_end']}  {r['days']:>3}d  {r['type']}")
mid = inv_df.filter(pl.col("type") == "mid_history")
log()
log(f"  VINs with >= {MIN_GAP_DAYS}d mid-history gaps: "
    f"{mid['vin'].n_unique()}/34 ; total mid-history gaps: {len(mid)}")
log("  Largest mid-history gaps fleet-wide:")
for r in mid.sort("days", descending=True).head(8).to_dicts():
    log(f"    {r['vin']:<13} {r['gap_start']} -> {r['gap_end']}  {r['days']}d")

# VIN1_F_SM Aug-Oct 2025 specifics
log()
log("  VIN1_F_SM 2025-08-01..2025-11-30 detail (raw rows per active day):")
v1 = (raw_daily.filter((pl.col("vin_label") == "VIN1_F_SM") &
                       (pl.col("date") >= dt.date(2025, 8, 1)))
      .sort("date").select(["date", "n_rows", "vsi_drive_rows"]))
for r in v1.to_dicts():
    log(f"    {r['date']}  n_rows={r['n_rows']:>6}  drive_rows={r['vsi_drive_rows']:>6}")

# ===========================================================================
# CHECK 4 — sparkline inputs (cache) vs raw recompute, 3 VINs x 5 random days
# ===========================================================================
log()
log("=" * 78)
log("CHECK 4 — cache vsi_drive_mean/p05/p95 vs raw recompute (3 VINs x 5 days)")
log("=" * 78)
rng = np.random.RandomState(42)
n_ok, n_tot = 0, 0
for v in ["VIN1_F_SM", "VIN6_F_SM", "VIN12_NF_SM"]:
    c = cache_daily[v].filter(pl.col("vsi_drive_rows") > 0).sort("date")
    r = raw_daily.filter(pl.col("vin_label") == v).filter(pl.col("vsi_drive_rows") > 0).sort("date")
    idx = rng.choice(len(c), size=5, replace=False)
    for i in sorted(idx):
        cd = c.row(int(i), named=True)
        rd = r.filter(pl.col("date") == cd["date"]).to_dicts()[0]
        diffs = {k: abs(float(cd[k]) - float(rd[k]))
                 for k in ["vsi_drive_mean", "vsi_drive_p05", "vsi_drive_p95"]}
        ok = all(dv < 1e-5 for dv in diffs.values())
        n_ok += ok
        n_tot += 1
        log(f"  {v:<13} {cd['date']}  mean {cd['vsi_drive_mean']:.5f}/{rd['vsi_drive_mean']:.5f} "
            f"p05 {cd['vsi_drive_p05']:.3f}/{rd['vsi_drive_p05']:.3f} "
            f"p95 {cd['vsi_drive_p95']:.3f}/{rd['vsi_drive_p95']:.3f} "
            f"maxdiff={max(diffs.values()):.2e} [{'PASS' if ok else 'FAIL'}]")
log(f"CHECK 4 verdict: {n_ok}/{n_tot} -> {'PASS' if n_ok == n_tot else 'FAIL'}")

# ===========================================================================
# CHECK 5 — crank tick dates == failed non-artifact crank dates (2 VINs)
# ===========================================================================
log()
log("=" * 78)
log("CHECK 5 — red tick dates == failed (success=False, artifact=False) cranks")
log("=" * 78)
ev = pl.read_parquet(str(EVENTS_PQ))
import importlib.util
spec = importlib.util.spec_from_file_location(
    "graphs_mod", SM / "V1.1" / "src" / "V1_1_SM_daily_risk_graphs.py")
gm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gm)

for v in ["VIN6_F_SM", "VIN11_F_SM"]:
    indep = (ev.filter((pl.col("vin_label") == v) &
                       (pl.col("success") == False) &
                       (pl.col("artifact") == False))
             .with_columns(pl.col("ts_start").dt.date().alias("d")))
    indep_dates = sorted(indep["d"].unique().to_list())
    script = gm.FAILED_CRANKS.get(v)
    script_dates = sorted([d.date() for d in script.index]) if script is not None else []
    ok = indep_dates == script_dates
    log(f"  {v:<13} independent={len(indep_dates)} dates, script ticks={len(script_dates)} dates, "
        f"sets equal: {ok} [{'PASS' if ok else 'FAIL'}]")
    if not ok:
        log(f"    only-indep: {sorted(set(indep_dates)-set(script_dates))[:5]}")
        log(f"    only-script: {sorted(set(script_dates)-set(indep_dates))[:5]}")

(AUDIT / "out").mkdir(exist_ok=True)
(AUDIT / "out" / "A2_results.txt").write_text("\n".join(lines), encoding="utf-8")
print("\nwrote", AUDIT / "out" / "A2_results.txt")
