---
title: "Agent A — Data Quality & Signal Integrity Audit (Starter Motor V1.1)"
status: complete
created: "2026-06-10"
---

# Agent A — Data Quality & Signal Integrity Audit (SM V1.1)

Independent audit run 2026-06-10 against the raw SM parquets (30.9M failed / 76.3M non-failed rows),
the 34 V1 weekly caches, and the V1 crank-events parquet (20,471 events). All numbers below were
computed by the probe scripts in `STARTER MOTOR/V1.1/audit/scripts/` (probe1–probe7); intermediate
CSVs sit next to this report. Read-only on V1 artifacts and `Data/`.

---

## 1. Failure labeling quality (probe1) — Failure_type is USELESS for mode separation

- `Failure_type` contains exactly **one distinct value, "Starter Motor", across all 30,925,573 rows**
  (1 unique value per VIN, 0 nulls). V1 lost nothing by ignoring it; V1.1 cannot get failure modes
  from it. Mode separation must come from signal behavior (see §7) or external KT input.
- `SALEDATE`/`JCOPENDATE` are 1 value per VIN (consistent). **0 rows after JCOPENDATE for every
  VIN** — the failed file is right-censored at the failure date by construction (no post-repair
  contamination, but also no recovery data).
- 9/14 VINs transmit on the JCO day itself (410–12,636 rows on that day); the other 5 are the known
  silent-gap VINs (32–142 d). First telemetry is 0–14 d after SALEDATE for all failed VINs.
- Sale→JCO life: 171 d (VIN2_F) to 671 d (VIN8_F). All failures inside ~2 years of sale.

## 2. Missing-value structure (probe2) — structured, not random; 3 distinct layers

Per-VIN × month × regime null rates (`probe2_null_by_vin_month.csv`, `probe2_null_summary_per_vin.csv`):

1. **Hardware/config cohort ("SMA-dead"), 7 VINs**: VIN8_F, VIN9_F (2/14 failed = 14%) and
   VIN10/11/12/13/20_NF (5/20 NF = 25%) have SMA null 99.74–99.92% and VSI null 74–82%
   (VIN13_NF: SMA dead 99.90% but VSI mostly alive, 17.8% null — mixed config). This is per-VIN
   and stable across months (month-min SMA null 96.7–99.3%), i.e., a telematics configuration,
   not sensor degradation.
2. **Regime structure (all other VINs)**: SMA/VSI null rates are **~0% engine-on**
   (max 6.4e-5 across all 27 SMA-alive VINs) **vs 13–86% engine-off** (e.g., VIN4_F 13.2%,
   VIN18_NF 85.7%). "Null rate" therefore mostly measures key-off duty cycle, not data quality.
3. **Cohort asymmetry is mild and points the safe way**: mean VSI null 13.3% (F) vs 18.6% (NF);
   SMA 16.5% (F) vs 27.0% (NF). NF is *more* missing, so nulls do not fabricate failed-side signal,
   but any feature whose availability depends on SMA/VSI silently reweights cohorts (12F/15NF
   effective for clean crank features).
- VSI rescale (raw > 36 V) affects **≤7 rows per VIN in the entire dataset** — a non-issue.
- GED nulls are independent of the SMA cohort (0.02–0.99 across VINs) and `ged3_rate` carries no
  label signal (AUROC 0.543).

**Config landmine found**: in the SMA-dead config, SMA appears to be event-triggered — those VINs
show 0.66–8.45 crank events/active-day (VIN11_NF 8.4/d, VIN8_F 3.5/d) vs 0.20–1.2/d for
continuous-broadcast VINs. **`events_per_active_day` and `sma1_per_active_day` are config artifacts,
not behavior**, and must never be pooled across the two configs.

## 3. Sampling consistency & gaps (probe3) — two transmit configs; gap counts leak; taper before silence

- Median Δt = 5 s for all 34 VINs. `dt_p99` splits the fleet into a **continuous-transmit family
  (p99 = 6 s: VIN4_F, VIN8_F, VIN9_F, VIN10/11/13_NF)** and a **rest-heartbeat family
  (p99 ≈ 900 s)**, overlapping but not identical to the SMA-dead cohort.
- **Gap counts leak the label**: NF mean 22.4 gaps of 1 h–1 d and 11.7 gaps >1 d vs failed 7.6 / 4.3
  (AUROC 0.875 / 0.868) — purely because NF were observed ~616 active days vs ~371. Any gap-count
  or downtime-count feature is a volume proxy.
- **No fleet-level density precursor**: rows/day in final 30 d ÷ baseline = 0.979 (F) vs 0.997 (NF).
  BUT 2 of the 5 silent-gap VINs **taper before going silent**: VIN1_F 129 rows/day in final 30 d
  vs 4,751 baseline (ratio 0.027, only 3 transmitting days); VIN5_F 659 vs 5,850 (0.113, 1 day).
  VIN4_F (0.85), VIN8_F (0.97), VIN9_F (1.02) cut off abruptly. Telemetry-health itself is a
  partial (2/5) early-warning channel for the silent-gap failure pattern.

## 4. Sensor reliability (probe4) — 0.2 V quantization, per-truck setpoints, stuck episodes

- VSI is quantized at **0.2 V** (168 distinct values, 8.0–51.0 V; top value 28.0 V at 31.7M rows).
  A single outlier level (51.0 V) exists in trace amounts (≤7 rows/VIN).
- **Per-truck regulation setpoint offsets**: drive-regime (RPM>700) median VSI ranges
  **27.6–28.2 V** across trucks (fleet std 0.18 V ≈ 1 quantization step). VIN2_F/VIN5_F/VIN12_F
  and VIN9_NF sit at 27.6; others at 28.0–28.2. Fleet-pooled *level* features (e.g., mean drive VSI)
  smear a ±0.3 V calibration term that is as large as most degradation effects; V1.1 should
  baseline-correct VSI per VIN.
- **Stuck-value episodes**: longest run of identical consecutive drive-regime VSI readings is
  42,133 samples for VIN7_NF (~58 h of drive samples), 2,545 for VIN7_F; 13 VINs have ≥10 runs over
  30 min. Caveat: runs were counted on the drive-row sequence (can span key-off gaps), so they
  overstate contiguous wall-clock time; still, VIN7_NF/VIN16_NF/VIN4_NF warrant a stuck-sensor mask
  before any VSI-variance feature is trusted. Note failed cohort does NOT have more stuck runs
  (mean max-run 776 F vs 3,272 NF) — stuckness does not explain §7's variance signal (stuck runs
  *reduce* variance and are more common on the NF side).

## 5. Underutilized signals (probe5/probe6) — VIN-level single-feature AUROC screen (14F vs 20NF, Mann-Whitney)

Full table: `probe6_single_feature_auroc.csv` (45 features). Non-volume highlights:

| Feature (per-VIN aggregate) | AUROC (dir.) | p | mean F | mean NF |
|---|---|---|---|---|
| `vsi_drive_std_med` (weekly drive-VSI std, median) | **0.732** | 0.024 | 0.223 | 0.137 |
| `vsi_settled_p05` (rest-bout voltage ≥2 h after engine-off, p05) | **0.734** | 0.036 | 23.40 V | 23.96 V |
| `vsi_rest_p05_med` (weekly rest p05, median) | **0.729** | 0.024 | 24.01 V | 24.29 V |
| `vsi_settled_median` | 0.715 | 0.054 | 24.05 V | 24.89 V |
| `rest_slope_vph_median` (V/h decay within ≥3 h rest bouts) | 0.608 | 0.34 | −0.211 | −0.125 |
| `min_vsi_crank_med` | 0.630 | 0.20 | 21.48 V | 21.70 V |

Dead ends (honest negatives): **RPM-during-crank profile carries nothing** (`rpm_max15_med`
AUROC 0.500; p10 0.512), crank duration nothing (0.507), dip depth 0.575, success rate 0.543,
recovery slope 0.541; **ANR/CSP/RPM usage levels nothing** (0.536/0.507/0.575). Rest-bout decay
slope is directionally right (failed batteries lose voltage ~70% faster at rest) but weak at
VIN level (0.608, n = 11F/19NF with ≥1 bout ≥3 h; VIN5_F/VIN9_F/VIN14_F have none).

## 6. Leakage risks beyond V1's calendar-truncation control (probe6/probe7)

1. **Volume features outperform the V1 model**: `n_weeks` AUROC **0.952**, `active_days_total`
   **0.946**, `total_rows` 0.889, gap counts 0.868–0.875 — all pure observation-length artifacts,
   and all *higher than V1's Ridge 0.921*. Any V1.1 feature must be benchmarked against this
   0.95 leakage ceiling; beating 0.921 is meaningless if the feature correlates with volume.
2. **Recruitment epoch**: `t_start` ordinal alone gives AUROC **0.893** (p = 1.2e-4) — 17/20 NF
   started telemetry Jan–Jul 2024, while failed trucks enter at sale through 2025 (VIN2_F
   2025-06, VIN3_F 2025-04, VIN4_F 2025-03). Failed trucks are systematically *younger/later-sold*.
   Any calendar-correlated feature (season, firmware rollout, route changes) partially encodes the
   label. The calendar-truncation control handles t_end, **not t_start**.
3. **Extraction-date wall**: 16/20 NF end exactly 2026-02-09/16 (extraction date); the 4 NF ending
   earlier are all SMA-dead-cohort trucks. So "ends before 2026-02" ≈ failed ∪ SMA-dead-NF.
4. **Config confound**: per §2, SMA-rate and event-rate features differ ~10× by telematics config;
   config membership itself is label-correlated (14% F vs 25% NF), so config-sensitive features
   leak cohort composition.

## 7. Latent degradation (probe7) — one strong new channel V1 missed

Within-VIN screen: last-8-observed-weeks median minus own prior baseline, failed vs NF
(`probe7_latent_screen.csv`):

- **Δ`vsi_drive_std` AUROC 0.893, p = 0.0001** (mean ΔF +0.378 V vs ΔNF +0.007 V). Verified with
  a **calendar-matched control** (each NF truncated at a failed VIN's end date, removing the
  Feb-2026 seasonal/endpoint confound): **AUROC 0.889, p = 0.0001** (mean ΔNF +0.009). Per-VIN:
  9/14 failed show Δ ≥ +0.15 (VIN6_F +1.24, VIN14_F +1.15, VIN13_F +1.01, VIN3_F +0.42, VIN10_F
  +0.38, VIN5_F +0.30, VIN12_F +0.30, VIN7_F +0.24, VIN11_F +0.15); max NF Δ is +0.059. The 5
  non-responders (VIN1/2/4/8/9_F, Δ −0.01…+0.06) include 4 of the 5 silent-gap VINs, whose final
  observed weeks are 32–142 d before failure.
- Onset timing (weekly std > NF p99.5 = 0.965): VIN13_F first exceeds **294 d** before last
  telemetry, VIN6_F 280 d, VIN14_F 91 d, VIN3_F 49 d. Absolute thresholds only flag these 4
  (NF weekly max is 3.48 — heavy tail), so the **baseline-relative delta, not an absolute
  threshold, is the deployable form**.
- Supporting deltas: Δ`vsi_drive_p95` AUROC 0.684 (p = 0.041; F +0.86 V vs NF +0.03 V);
  Δrest `vsi_rest_p05` directional 0.696 (p = 0.056; F −0.78 V vs NF −0.18 V); crank-retry-rate
  final-60 d delta AUROC 0.704 (p = 0.053; F +0.010 vs NF −0.007). Deltas of rpm/csp/anr usage:
  nothing (0.43–0.48).
- Physical reading: rising charging-bus voltage variance + sagging rest voltage + more crank
  retries = battery/charging stress preceding starter failure. This contradicts V1's "no
  lead-time channel" conclusion for ~9/14 failed VINs, with zero NF exceedances at the Δ ≥ 0.15
  working point on this screen. Caveat: screening-level result computed at the same endpoint that
  defines the label-time geometry; V1.1 must re-test it in the LOVO/rolling framework before any
  claim.

## Ranked V1.1 impact

1. **Adopt Δ(vsi_drive_std) as the prime V1.1 candidate** (0.889 calendar-matched; lead 49–294 d
   on 4 VINs at absolute threshold; 9/14 sensitivity at delta threshold) — re-validate under LOVO.
2. **Benchmark every feature against the 0.95 volume ceiling** and the 0.893 t_start epoch leak;
   add a recruitment-epoch control (match/stratify on t_start), not just calendar truncation.
3. **Per-VIN VSI baseline correction** (setpoints 27.6–28.2 V) + stuck-run mask before any
   variance/level feature.
4. **Never pool SMA-rate/event-rate features across the two telematics configs** (10× artifact).
5. Failure_type is constant — abandon it; use §7 channels (variance-rise vs silent-gap vs none)
   as a data-driven 3-way mode split: variance-rise (9), silent-gap-with-taper (VIN1/5), abrupt
   (VIN2/4/8/9 overlap).

## Probe scripts and outputs

| Script | Output CSVs |
|---|---|
| `scripts/probe1_labels.py` | `probe1_labels_per_vin.csv` |
| `scripts/probe2_null_structure.py` | `probe2_null_by_vin_month.csv`, `probe2_null_summary_per_vin.csv` |
| `scripts/probe3_sampling_gaps.py` | `probe3_dt_gaps_per_vin.csv`, `probe3_density_drift.csv`, `probe3_rest_gap_vsi_decay.csv` (empty by design — long gaps have null VSI at both edges) |
| `scripts/probe4_vsi_sensor.py` | `probe4_vsi_value_hist.csv`, `probe4_vsi_stuck_baseline_per_vin.csv` |
| `scripts/probe5_rest_decay.py` | `probe5_rest_bout_decay_per_vin.csv` |
| `scripts/probe6_signal_screen.py` | `probe6_vin_feature_matrix.csv`, `probe6_single_feature_auroc.csv` |
| `scripts/probe7_epoch_latent.py` | `probe7_latent_last8wk_delta.csv`, `probe7_latent_screen.csv`, `probe7_crank_final60d_delta.csv` |
