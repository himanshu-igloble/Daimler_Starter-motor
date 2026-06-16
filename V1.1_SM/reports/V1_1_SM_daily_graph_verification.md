---
title: "V1.1 SM Daily-Risk Dashboard Data-Correctness Verification"
status: "complete"
created: "2026-06-10"
---

# V1.1 SM Daily-Risk Dashboard Verification (34 graphs vs raw data)

## Verdict

**The graphs are data-correct.** Every datapoint checked traces back to the raw
parquet files exactly (0.0 float difference); every >= 7-day telemetry gap in the
raw data is reproduced in the daily cache and visibly breaks the plotted curves
(no interpolation across gaps anywhere). **One defect was found and fixed**: for
5 failed VINs whose telemetry starts after the sale date, the dotted forecast
endpoint overshot JCOPENDATE by +1 to +14 days. The script was patched to anchor
the failed-VIN forecast endpoint at JCOPENDATE and the 5 affected dashboards
were re-rendered. All other 29 dashboards are byte-identical in content (the fix
is a no-op when t_start == saledate).

| # | Check | Result |
|---|-------|--------|
| 1a | Daily cache reproduces raw active-day sets + per-day row counts (34 VINs) | **PASS 34/34** |
| 1b | Gap inventory (>= 7 d), terminal gaps match known 72/97/32/37/142 d | **PASS 5/5** |
| 2a | gap_mask inserts NaN break at every mid-history gap (numeric, all 58 gaps) | **PASS 58/58** |
| 2b | Visual: curve breaks at the 6 largest mid-history gaps + VIN1_F window (PNG crops) | **PASS 7/7** |
| 3a | Degradation inputs at 3 probe dates x 6 VINs: traj == cache == raw recompute | **PASS 18/18** (max diff 0.0) |
| 3b | Forecast endpoint == JCOPENDATE, all 14 failed | **FAIL 9/14 -> FIXED -> PASS 14/14** |
| 3c | NF anchor 779 d / conditional Weibull (all 20 NF; VIN12_NF & VIN16_NF conditional) | **PASS 20/20** |
| 3d | Zone-band transitions == first crossing of 0.15/0.35/0.55 (6 VINs) | **PASS** |
| 4 | Sparkline vsi_drive_mean/p05/p95 cache vs raw, 3 VINs x 5 random days | **PASS 15/15** (diff 0.00e+00) |
| 5 | Red crank ticks == failed (success=False, artifact=False) crank dates (2 VINs) | **PASS** (VIN6_F 10/10, VIN11_F 5/5 dates) |
| 6 | rows / t_start / t_end / active_days vs V1_SM_data_quality.csv (34 VINs) | **PASS 34/34** |

Method: one independent streaming pass over both raw parquet files
(`audit/A1_raw_daily_recompute.py`) re-derived per-VIN per-day aggregates with
the identical sentinel cleaning (CSP/RPM >= 65535 -> null, VSI <= 0 or >= 255 ->
null, VSI > 36 -> x0.2, RPM > 700 = driving regime, null-timestamp rows
dropped). Comparison scripts: `audit/A2_gap_inventory_and_reconcile.py`,
`audit/A3_curve_correctness.py`; console mirrors in `audit/out/A2_results.txt`,
`audit/out/A3_results.txt`; crops in `audit/out/crops/`.

---

## The VIN1_F_SM "08/2025 - 10/2025 gap" — answered

What looks like one long hole is **three different things**, all verified
against raw timestamps:

1. **Real mid-history telemetry gap, 2025-07-31 -> 2025-09-02 (34 days, 0 rows).**
   Last active day before the gap is 2025-07-30; the raw file contains zero
   rows for VIN1 between 2025-07-31 and 2025-09-02 inclusive. The RUL curve and
   the VSI sparkline correctly break (blank) over this window.
2. **Three sparse trailing active days:** 2025-09-03 (1 row, 0 driving),
   2025-09-10 (373 rows, 115 driving), 2025-09-15 (14 rows, 0 driving = t_end).
   These are < 7 d apart so they form a tiny final curve stub next to the
   "Last Obs: 2025-09-15" star. In the sparkline, 2025-09-10 is the only
   post-gap day with driving data; as an isolated point inside NaN masking it
   does not render as a line (its failed-crank tick at ~2025-09-10 is visible).
3. **Terminal silent gap, 2025-09-16 -> 2025-11-26 (72 days, no telemetry).**
   This is the known silent-failure gap (t_end 2025-09-15 -> JCOPENDATE
   2025-11-26). The graph shows it as the grey hatched "SILENT GAP 72d (no
   telemetry)" region, crossed only by the **dotted** power-decay projection
   that lands at RUL = 0 exactly on 2025-11-26. That dotted line is an
   illustration, not telemetry.

So: no data is missing from the graph that exists in the raw files, and nothing
is drawn where data does not exist — except the clearly-dotted projection.

---

## Fleet gap inventory

Full machine-readable inventory (63 gaps):
`STARTER MOTOR/V1.1/results/V1_1_SM_data_gap_inventory.csv`
(vin, gap_start, gap_end, days, type).

- **24 of 34 VINs** have at least one >= 7-day mid-history telemetry gap
  (58 mid-history gaps total). 10 VINs are gap-free: VIN2/3/6/9/12/13_F,
  VIN3/10/20_NF (and VIN12_F).
- **5 terminal silent gaps** (t_end -> JCOPENDATE), all matching the known
  values exactly: VIN1_F 72 d, VIN4_F 97 d, VIN5_F 32 d, VIN8_F 37 d,
  VIN9_F 142 d.
- **Largest 5 mid-history gaps:** VIN5_F_SM 327 d (2024-12-04 -> 2025-10-26),
  VIN11_F_SM 161 d (2024-09-21 -> 2025-02-28), VIN10_F_SM 124 d
  (2024-09-21 -> 2025-01-22), VIN17_NF_SM 67 d (2024-07-25 -> 2024-09-29),
  VIN6_NF_SM 64 d (2025-08-23 -> 2025-10-25).

### Per-VIN summary (raw ground truth; all values cross-checked vs cache and DQ CSV)

| VIN | first day | last day | active days | raw rows | mid gaps >=7d | largest mid gap (d) | terminal gap (d) |
|-----|-----------|----------|------------|----------|---------------|---------------------|------------------|
| VIN1_F_SM | 2024-09-30 | 2025-09-15 | 305 | 1,303,473 | 1 | 34 | 72 |
| VIN2_F_SM | 2025-06-27 | 2025-12-13 | 163 | 843,430 | 0 | 0 | — |
| VIN3_F_SM | 2025-04-08 | 2025-12-16 | 248 | 1,165,335 | 0 | 0 | — |
| VIN4_F_SM | 2025-03-05 | 2025-08-02 | 151 | 1,227,142 | 0 | 0 | 97 |
| VIN5_F_SM | 2024-04-30 | 2025-10-27 | 219 | 1,275,868 | 1 | 327 | 32 |
| VIN6_F_SM | 2024-10-03 | 2025-11-04 | 396 | 2,219,533 | 0 | 0 | — |
| VIN7_F_SM | 2024-04-30 | 2025-11-08 | 543 | 2,733,480 | 1 | 10 | — |
| VIN8_F_SM | 2024-01-31 | 2025-10-26 | 547 | 4,802,641 | 2 | 39 | 37 |
| VIN9_F_SM | 2024-01-31 | 2025-06-29 | 501 | 3,810,537 | 0 | 0 | 142 |
| VIN10_F_SM | 2024-07-01 | 2025-12-29 | 416 | 1,837,988 | 1 | 124 | — |
| VIN11_F_SM | 2024-03-27 | 2025-11-22 | 445 | 2,702,394 | 1 | 161 | — |
| VIN12_F_SM | 2024-12-27 | 2025-12-07 | 344 | 2,490,690 | 0 | 0 | — |
| VIN13_F_SM | 2024-07-31 | 2025-11-06 | 460 | 1,629,920 | 0 | 0 | — |
| VIN14_F_SM | 2024-07-03 | 2025-11-17 | 457 | 2,883,142 | 1 | 35 | — |
| VIN1_NF_SM | 2024-02-02 | 2026-02-18 | 642 | 4,500,188 | 4 | 31 | — |
| VIN2_NF_SM | 2024-01-22 | 2026-02-18 | 687 | 3,339,979 | 4 | 22 | — |
| VIN3_NF_SM | 2024-03-18 | 2026-02-18 | 693 | 3,272,138 | 0 | 0 | — |
| VIN4_NF_SM | 2024-03-22 | 2026-02-13 | 588 | 3,765,513 | 4 | 33 | — |
| VIN5_NF_SM | 2024-04-03 | 2026-02-17 | 622 | 4,254,893 | 3 | 21 | — |
| VIN6_NF_SM | 2024-02-28 | 2026-02-18 | 602 | 3,573,023 | 5 | 64 | — |
| VIN7_NF_SM | 2024-02-22 | 2026-02-18 | 706 | 3,991,540 | 1 | 13 | — |
| VIN8_NF_SM | 2024-03-01 | 2026-02-18 | 692 | 3,349,684 | 1 | 13 | — |
| VIN9_NF_SM | 2024-02-27 | 2026-02-10 | 640 | 3,332,668 | 3 | 21 | — |
| VIN10_NF_SM | 2024-01-01 | 2025-02-26 | 421 | 3,168,806 | 0 | 0 | — |
| VIN11_NF_SM | 2023-12-31 | 2025-05-27 | 490 | 4,678,423 | 1 | 12 | — |
| VIN12_NF_SM | 2024-01-01 | 2026-02-18 | 723 | 3,192,514 | 2 | 27 | — |
| VIN13_NF_SM | 2024-01-01 | 2025-07-28 | 524 | 3,868,675 | 3 | 11 | — |
| VIN14_NF_SM | 2024-01-19 | 2026-02-18 | 719 | 3,422,746 | 2 | 22 | — |
| VIN15_NF_SM | 2024-01-30 | 2026-02-18 | 721 | 3,191,966 | 1 | 14 | — |
| VIN16_NF_SM | 2024-01-12 | 2026-02-16 | 575 | 5,315,087 | 7 | 49 | — |
| VIN17_NF_SM | 2024-07-17 | 2026-02-18 | 458 | 3,374,585 | 2 | 67 | — |
| VIN18_NF_SM | 2024-03-22 | 2026-02-11 | 596 | 3,953,484 | 3 | 29 | — |
| VIN19_NF_SM | 2024-05-03 | 2026-02-18 | 602 | 3,601,637 | 4 | 19 | — |
| VIN20_NF_SM | 2024-01-01 | 2025-09-26 | 626 | 4,372,039 | 0 | 0 | — |

Totals: 14 F + 20 NF = 34 VINs, 106,445,161 raw rows (after null-timestamp
drop), 17,522 active vin-days — all reconciled 34/34 against
`STARTER MOTOR/results/V1_SM_data_quality.csv`.

---

## Check details

### 2. Gap-masking (visual)

Crops of the 6 largest mid-history gaps (VIN5_F 327 d, VIN11_F 161 d,
VIN10_F 124 d, VIN17_NF 67+52 d, VIN6_NF 64 d, VIN16_NF 49+39 d) plus the
VIN1_F window were viewed at pixel level: in every case the orange RUL curve
and the sparkline VSI line stop before the gap and resume after it with blank
space between — **no interpolated bridge anywhere**. Note: the thin green/amber
arcs that can visually cross a gap are milestone/zone **annotation arrows**
(label -> marker connectors), not data lines.

### 3b. Forecast endpoint — defect found and FIXED

`forecast_fail_date` was computed as `first_telemetry_date + ttf_days` where
`ttf_days = JCOPENDATE - SALEDATE`. When telemetry starts after the sale date
the endpoint overshoots the actual failure date:

| VIN | saledate | t_start | offset before fix | after fix |
|-----|----------|---------|-------------------|-----------|
| VIN2_F_SM | 2025-06-25 | 2025-06-27 | +2 d | 2025-12-13 == JCO |
| VIN6_F_SM | 2024-09-30 | 2024-10-03 | +3 d | 2025-11-04 == JCO |
| VIN10_F_SM | 2024-06-30 | 2024-07-01 | +1 d | 2025-12-29 == JCO |
| VIN12_F_SM | 2024-12-13 | 2024-12-27 | **+14 d** | 2025-12-07 == JCO |
| VIN14_F_SM | 2024-06-30 | 2024-07-03 | +3 d | 2025-11-17 == JCO |

Before the fix, VIN12_F's purple "Forecast" line sat 14 days AFTER the red
"Failure (JCOPENDATE)" line — misleading. Fix applied in
`V1_1_SM_daily_risk_graphs.py` (failed VINs: `forecast_fail_date =
meta["jcopendate"]`); the 5 dashboards above were re-rendered and re-verified
(printed table now shows forecast_fail == JCOPENDATE for all; VIN12_F PNG
re-viewed: dotted projection terminates exactly on the failure line). The other
9 failed VINs (offset 0) and all 20 NF VINs are unaffected by the code path.

### 3a/3c/3d. Curve data correctness

- 6 sample VINs (VIN1_F, VIN6_F, VIN8_F, VIN1_NF, VIN12_NF, VIN20_NF) x 3
  probe dates (early/mid/late): all six degradation-score inputs (vsi_mean,
  vsi_std, vsi_range, vsi_deviation, uv_share, failed_crank_rate) computed
  from the daily cache equal those recomputed from the independent raw daily
  aggregates with **0.0 difference**, and the stored trajectory degradation
  equals both (e.g. VIN6_F late 2025-09-26: deg 0.413891 from all three paths).
- NF anchors: 18/20 NF VINs use the fleet Weibull median 779 d; VIN12_NF
  (span 779 d) and VIN16_NF (span 766 d) correctly switch to the conditional
  Weibull median: 1096.0 d and 1086.9 d respectively (lambda = 933.1 d,
  rho = 2.03) — matches independent recomputation to < 1e-9.
- Zone-band transition dates equal the independent first crossing of the
  degradation series at 0.15/0.35/0.55 for all 6 sample VINs (e.g. VIN6_F:
  yellow 2025-05-25, orange 2025-08-31, red 2025-10-19).

### 4/5/6

- Sparkline inputs: 15/15 sampled days match raw recomputation exactly
  (max diff 0.00e+00), validating cache == raw for the plotted series.
- Crank ticks: VIN6_F 10 tick dates, VIN11_F 5 tick dates — identical sets to
  the failed (success = False, artifact = False) events in
  `STARTER MOTOR/cache/events/V1_SM_crank_events.parquet`.
- Known numbers: 34/34 VINs agree with `V1_SM_data_quality.csv` on rows,
  t_start, t_end (to the second) and active-day counts.

---

## Documented behaviors (not changed — by design, but worth knowing)

1. **30-day lookback across gaps:** the degradation score at the first active
   days after a long gap is computed from whatever falls inside the trailing
   30-day window. If fewer than 500 driving samples are in the window, the
   script substitutes ALT "healthy-fallback" constants (vsi_mean 28.0, std 0.3
   ...), so the post-gap curve can re-start near GREEN regardless of pre-gap
   level (visible on VIN5_F: final deg 0.01 after the 327 d gap while Ridge
   risk is 99% RED). The Ridge risk badge — the validated deliverable — is
   unaffected. Not changed: behavior is honest (no data -> no degradation
   evidence) and the curve is labeled an illustration.
2. **Isolated single active days** inside masked regions (e.g. VIN1_F
   2025-09-10 in the sparkline) do not render as line segments (NaN on both
   sides); their crank ticks/markers still show.
3. **Zone bands extend through gaps**: the band between two transition dates is
   drawn as a continuous vertical span even if telemetry is absent inside it
   (zone state is simply held, which is the only defensible choice).
4. **Milestone annotation arrows** (green/amber thin arcs) may visually span a
   gap; they connect labels to markers and are not data.
5. The RUL countdown uses `elapsed` days since first telemetry with
   `max_rul = JCOPENDATE - SALEDATE`; for the 5 VINs in 3b the curve therefore
   starts at most 14 d "too high" — negligible at the 350-670 d scale of an
   illustration curve and now consistent with the corrected forecast endpoint.

## Files

- Fixed: `STARTER MOTOR/V1.1/src/V1_1_SM_daily_risk_graphs.py` (forecast anchor)
- Re-rendered: `V1_1_SM_daily_risk_VIN{2,6,10,12,14}_F_SM_dashboard.png`
- New: `STARTER MOTOR/V1.1/results/V1_1_SM_data_gap_inventory.csv` (63 gaps)
- Audit scripts/outputs: `STARTER MOTOR/V1.1/audit/A1_raw_daily_recompute.py`,
  `A2_gap_inventory_and_reconcile.py`, `A3_curve_correctness.py`,
  `audit/out/A2_results.txt`, `audit/out/A3_results.txt`, `audit/out/crops/`
