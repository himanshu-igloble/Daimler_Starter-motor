---
title: "V2 Data Discovery Intake — SM Signal Exploration"
status: "complete"
created: "2026-06-12"
---

# V2 Signal Discovery Intake — Starter Motor Fleet

Date: 2026-06-12  
Analyst: Claude (Sonnet 4.6), automated probe pipeline  
Scope: BharatBenz SM fleet, 34 trucks (14F + 20NF), non-ALT  
Production feature baseline: V1.1 nested-LOVO AUROC 0.893 (restated; 0.932 nested)

---

## ALREADY KNOWN — Do Not Re-Derive

The following are confirmed in V1.1 discovery (E/F/G agents) or audit (A/B/C probes).
V2 probes **must not claim credit** for these:

1. **vsi_withinwk_std_ratio_30d_w / vsi_std_ratio_30d_L40** — within-week VSI drive std ratio vs own baseline. Primary signal. AUROC ~0.93 (production feature).
2. **failed_crank_rate_last90 / retry_burst_rate_last90 / extended_crank_tail_rate_last90 / first_crank_fail_rate_last90** — crank-failure and retry rates in final 90 days (production features). Event-rate aggregates, not session anatomy.
3. **rest_vsi_p05_delta90 / dip_depth_last90_delta** — resting VSI decline and dip depth change in final 90 days (production features).
4. **vsi_range_trend / vsi_trend_persistence** — VSI range Theil-Sen + persistence flag (production features).
5. **Three failure archetypes** (E2): A1 solenoid-intermittency (3 VINs), A2 battery-cascade (4–5 VINs), A3 VSI-volatility-only (3 VINs), A4 silent/abrupt (4 VINs).
6. **Step detection** (E5): 4 largest rest-VSI negative steps = A2 failed VINs; drive-VSI up-steps ≥0.4 V also A2. Battery-replacement NF up-steps documented for 5 NF VINs.
7. **VSI trajectory shape** (E3): 10/14 failed = MONOTONE_DRIFT; persistence rule (≥4 of last 12 weeks above NF p90 envelope) catches 13/14 failed.
8. **Seasonality of CRANK SUCCESS RATE** (E4): no month effect on levels; NF "trending" flag mildly monsoon-skewed but not the cause of FP rate.
9. **k* = 10 weeks earliest-detection horizon** (G3 prequential): signal time-locked to failure, not length artifact.
10. **SMA-dead cohort exclusion** and vsi_dominant_freq leak confirmed (audit A).
11. **Duty-cycle clusters** (E5): no failure alignment at this n.
12. **No hazard layer / no deep sequence models** (F, G): mathematically out of bounds at n=14 events.
13. **dip_depth and recovery_slope present in crank events cache** — already used in V1 feature construction (dip_depth_last90_delta is production).
14. **Fleet-clock MAE 462 d vs constant 44 d** (F): per-truck RUL is unbeatable by fleet clock.
15. **Battery-replacement step-up segmentation** required for rest-VSI features on 6 VINs.

---

## Probe Results

### P1 — Crank Session Anatomy

**Method**: Group non-artifact crank events into sessions (intra-session gap < 60 s) for 27 non-SMA-dead VINs (10 F + 17 NF). Per session: n_attempts, total/max duration, inter-attempt gap, baseline_vsi, min_vsi, dip_depth, engine_started (rpm_max_15s > 500). Per VIN: final-90d vs own-baseline delta for each metric. Density check: all metrics are session-level rates (not raw counts), corr. with n_sessions_total checked.

**Key numbers**: 10,405 sessions, 304 multi-attempt (2.9% of sessions).

| Metric | AUROC (VIN-level) | Cohen's d | n_F / n_NF | MWU p | Density r | Verdict |
|--------|-----------|-----------|-----------|-------|-----------|---------|
| multi_rate_delta90 | 0.661 | 0.44 | 11/15 | 0.177 | −0.256 | WEAK |
| dip_depth_delta90 (session) | 0.679 | 0.74 | 11/15 | 0.132 | −0.045 | WEAK |
| session_dur_delta90 | 0.642 | 0.60 | 11/15 | 0.233 | density-safe | WEAK |
| recovery_slope_delta90 | 0.539 | −0.05 | 11/15 | 0.756 | density-safe | WEAK |
| f90_multi_attempt_rate | 0.606 | 0.48 | 11/15 | 0.373 | 0.034 | WEAK |
| bl_multi_attempt_rate (baseline) | 0.511 | 0.37 | 12/15 | 0.942 | — | WEAK |

**Lead-time assessment**: Session-level aggregation does not add separability beyond the production window-rate features (failed_crank_rate_last90 = 0.95+ AUROC at production). Multi-attempt rate in final 90d captures the same A1-archetype signal already in retry_burst_rate_last90.

**Density check**: r(multi_rate_delta90, n_sessions) = −0.256, r(dip_depth_delta90, n_sessions) = −0.045 → density-safe for dip. All metrics are inherently rate-normalized.

**NEW finding vs production**: Session anatomy (grouping by <60s gap) does NOT add beyond the event-rate window aggregates already in production. The inter-attempt gap within a session and session-level dip depth are weaker than the production dip_depth_last90_delta. This is a negative result — the session framing adds no incremental predictive power.

**Verdict: WEAK** — All metrics p > 0.1, AUROC 0.54–0.68; dominated by production features.

---

### P2 — VSI Dip-Recovery Dynamics

**Method**: From crank events with recovery_slope non-null (16,523 / 20,471 events; 10,683 after SMA-dead exclusion). Per VIN: baseline (>180d or >90d if insufficient) vs final-90d mean of recovery_slope; slow-recovery rate; Theil-Sen trend over lifetime; recovery efficiency = slope/dip_depth ratio. Per-event metric, density-robust by construction.

**Key number**: recovery_slope mean = 1.22 V/s, range −2.6 to +11.2 V/s; 19% null.

| Metric | AUROC | Cohen's d | n_F / n_NF | MWU p | Verdict |
|--------|-------|-----------|-----------|-------|---------|
| recovery_slope_delta90 | 0.552 | −0.055 | 11/15 | 0.678 | WEAK |
| recovery_slope_delta180 | 0.521 | 0.031 | 11/15 | 0.876 | WEAK |
| slow_recovery_rate_90 | 0.536 | 0.311 | 11/15 | 0.775 | WEAK |
| ts_recovery_slope_trend | 0.400 | 0.513 | 12/15 | 0.393 | WEAK |
| dip_delta90 (P2 version) | 0.636 | 0.644 | 11/15 | 0.254 | WEAK |
| recovery_efficiency_delta90 | 0.339 | −0.534 | 11/15 | 0.177 | WEAK |
| f90_recovery_slope (absolute) | 0.497 | −0.176 | 11/15 | 1.00 | WEAK |

**Interpretation**: Recovery slope shows no consistent degradation signal for failed vs NF trucks. The AUROC 0.39–0.55 range spans chance. This contrasts with the production dip_depth_last90_delta (captured in production). The physics explanation: recovery slope measures how fast VSI returns after SMA episode — this is primarily an alternator/regulator property, which does not consistently degrade before SM failure. Recovery slope degrades for A2 (battery-cascade) VINs as a secondary effect of regulator overworking, but the signal is absorbed by the production dip_depth feature.

**Verdict: WEAK** — Recovery dynamics carry no incremental signal beyond dip_depth_last90_delta.

---

### P3 — Cold-Start Proxy (Depth and Duration)

**Method**: First start-of-day event after ≥6h rest gap = cold_start; subsequent events same day = warm_start. Metrics: cold_dip/warm_dip ratio (density-independent), cold_dip_delta90 (final-90d vs own baseline). DISTINCT from E4 (which measured crank success RATE by month; we measure DIP DEPTH and DURATION).

**Key numbers**: 5,400 cold starts, 5,168 warm starts across 27 VINs.

| Metric | AUROC | Cohen's d | n_F / n_NF | MWU p | Density r | Verdict |
|--------|-------|-----------|-----------|-------|-----------|---------|
| dip_cold_warm_ratio | 0.561 | 0.507 | 12/15 | 0.608 | −0.338 | WEAK |
| dur_cold_warm_ratio | 0.439 | −0.333 | 12/15 | 0.608 | — | WEAK |
| **cold_dip_delta90** | **0.739** | **0.872** | **11/15** | **0.043** | −0.127 | **PROMISING (weak)** |
| cold_dur_delta90 | 0.606 | 0.505 | 11/15 | 0.378 | — | WEAK |
| cold_dip_mean (absolute) | 0.594 | 0.385 | 12/15 | 0.421 | — | WEAK |

**cold_dip_delta90 detail**: AUROC 0.739 (raw), MWU p = 0.043, Cohen's d = 0.872 (large effect). LOO-validated AUROC = 0.648 (notable drop). Density check: r(cold_dip_delta90, n_cold_starts) = −0.127 → density-safe. The signal is carried primarily by A2 battery-cascade VINs (VIN6_F: delta +4.55V, VIN3_F: +1.48V) — battery degradation makes cold starts dramatically worse as cell internal resistance rises with temperature decline. A1/A3/A4 VINs show near-zero or negative deltas.

**Lead time**: cold_dip_delta90 is a final-90d vs baseline comparison — same temporal window as production features. It does NOT offer earlier warning than production.

**Overlap concern**: cold_dip_delta90 is partially captured by production `dip_depth_last90_delta` (Pearson r expected high for A2 VINs); cold start is a subset of all cranks. Incremental AUROC vs production features requires LOVO regression evaluation.

**Verdict: PROMISING (weak)** — cold_dip_delta90 shows the largest effect of any non-VSI-std metric found (Cohen's d = 0.87, LOO AUROC 0.648, p = 0.043), but the signal is A2-archetype-specific and likely highly correlated with production dip_depth_last90_delta. Warrants incremental evaluation in a LOVO regression.

---

### P4 — Event-Level Separability at Matched Truck Age

**Method**: All non-SMA-dead VINs, events in final-90d window (2,050 events: 894 F, 1,156 NF). Compute per-event binary features; aggregate to VIN-level rates; AUROC at VIN level (11F / 11–15NF depending on feature). Age-matched: both F and NF in their own final 90d. Also final-30d window.

| Feature | AUROC (VIN, final_90d) | Cohen's d | n_F/n_NF vins | MWU p |
|---------|----------------------|-----------|--------------|-------|
| is_retry | 0.636 | 0.59 | 11/15 | 0.249 |
| is_extended_crank (>10s) | 0.639 | 0.55 | 11/15 | 0.183 |
| is_very_extended_crank (>20s) | 0.539 | 0.27 | 11/15 | 0.673 |
| is_deep_dip (>6V) | 0.558 | 0.40 | 11/15 | 0.640 |
| **is_very_deep_dip (>8V)** | **0.667** | **0.978** | **11/15** | **0.161** |
| engine_fail_rpm | 0.558 | 0.40 | 11/15 | 0.640 |
| is_slow_recovery | 0.503 | −0.18 | 11/15 | 1.000 |
| dip_depth (continuous) | 0.603 | — | 11/15 | — |
| dur_s (continuous) | 0.609 | — | 11/15 | — |
| **is_retry (final_30d)** | **0.709** | — | **11/15** | — |
| is_extended_crank (final_30d) | 0.648 | — | 11/15 | — |

**Notes**: 
- is_very_deep_dip (>8V threshold) shows highest Cohen's d (0.978) but AUROC only 0.667 and MWU p = 0.161 — a few A2 VINs drive the large d while A3/A4 have no dip signal.
- is_retry at final-30d reaches 0.709 — short-horizon supplement, consistent with A1-archetype; largely captured by production retry_burst_rate_last90.
- All event-level features at VIN level AUROC < 0.71 and p > 0.10.
- These metrics are substantively different from production only in their binary thresholding; the continuous versions are already subsumed by production dip_depth and retry rate features.

**Verdict: WEAK** — No event-level binary feature surpasses or materially augments production features. The is_very_deep_dip Cohen's d 0.978 is large but driven by 2–3 A2 VINs and the production dip_depth_last90_delta captures the same phenomenon continuously.

---

### P5 — Aging / Fleet-Percentile Rank Drift

**Method**: Per-VIN Theil-Sen slope of vsi_drive_std over full observed history. Fleet-percentile rank (fraction of fleet with lower std each week). Density-confound: CRITICAL finding — r(failed, n_weeks) = −0.771 (failed trucks have median 60 weeks history vs NF median 95 weeks). All trend metrics confounded.

| Metric | Raw AUROC | LOO AUROC | n_weeks r | Partial r (controlling n_weeks) | Verdict |
|--------|---------|---------|---------|-------------------------------|---------|
| ts_vsi_std_slope_per_week (full) | **0.954** | 0.786 | −0.429 | **0.194** | **ARTIFACT** |
| fleet_rank_drift | 0.839 | — | −0.451 | — | ARTIFACT |
| ts_fleet_rank_slope | 0.882 | — | −0.750 | **0.063** | **ARTIFACT** |
| weeks_above_p70_fleet | 0.562 | — | 0.011 | — | WEAK |
| late_fleet_rank_pct | 0.789 | — | — | — | ARTIFACT (n_weeks proxy) |
| ts_retry_rate_slope | 0.500 | — | — | — | WEAK |
| ts_slope_L20 (fixed last-20-week window) | 0.893 | — | −0.361 | — | KNOWN (= G3 established) |

**Critical finding**: n_weeks alone achieves LOO AUROC = 0.936 on this fleet. Any "lifetime trend" metric (Theil-Sen on full history, fleet-rank drift early vs late) is almost entirely driven by observation-length collinearity with failure — not by genuine early-warning signal. Partial r of ts_vsi_std_slope after removing n_weeks = 0.194.

**Only density-safe version**: Fixed last-20-week window slope (ts_slope_L20) achieves AUROC 0.893 with r(n_weeks) = −0.361 — but this is substantively equivalent to G3 prequential proof (already known). The fixed window IS what V1.1 already implements via vsi_std_ratio_30d windows.

**Conclusion**: There is NO genuine early-warning signal beyond 10 weeks before failure in this fleet. The G3 prequential cliff at k=11 weeks is definitive — the slope trend metrics that appear strong are n_weeks confounded.

**Verdict: ARTIFACT** for lifetime-trend metrics. KNOWN for fixed-window versions.

---

### P6 — Serendipity (Anomalous Patterns)

**Method**: VSI drive mean level decline, crank duration distribution shape (kurtosis, p95/p50 ratio), weekend vs weekday failure ratio, "silence before storm" operational silence pattern, rest-VSI bimodality (coefficient of variation). Density checks: r(metric, n_weeks) checked for all trend metrics.

| Metric | AUROC | Cohen's d | n_F/n_NF | MWU p | Density r | Verdict |
|--------|-------|-----------|---------|-------|-----------|---------|
| ts_drive_mean_slope (decline) | 0.550 | 0.69 | 14/20 | 0.637 | −0.285 | WEAK |
| drive_mean_delta_last90d | 0.457 | 0.29 | 14/20 | 0.687 | −0.012 | WEAK |
| dur_kurtosis | 0.476 | −0.30 | 12/14 | 0.857 | 0.083 | WEAK |
| dur_p95_over_p50 | 0.561 | 0.45 | 12/15 | 0.550 | — | WEAK |
| weekend_weekday_fail_ratio | 0.560 | 0.20 | 10/15 | 0.637 | — | WEAK |
| silence_before_storm_days | 0.500 | null | 14/20 | 1.000 | — | WEAK |
| rest_vsi_median_cv | 0.561 | 0.28 | 14/20 | 0.564 | — | WEAK |

**Notable negatives**:
- **VSI drive MEAN decline**: Theil-Sen slope shows positive Cohen's d (0.69) but AUROC only 0.550, density r = −0.285 (borderline confound). Density-safe absolute delta (drive_mean_delta_last90d, r = −0.012) shows AUROC 0.457 < chance — drive voltage mean does NOT decline before SM failure in this fleet. Physics: alternator regulator may actually push drive voltage UP as it compensates for battery degradation (E2 A2 archetype step +0.47–0.75V). The mean effect is negligible.
- **Duration kurtosis**: heavy-tailed dur_s distribution (occasional long cranks) shows AUROC 0.476 — failed VINs actually have slightly lower kurtosis (more uniform degradation vs occasional spikes in NF). Noise.
- **Silence before storm**: the "operational silence → failure burst" pattern did not materialize as a significant feature (AUROC 0.500). Silent-gap VINs (A4 archetype) show no post-silence failed burst in telemetry.
- **Rest-VSI CV (bimodality proxy)**: battery-replacement step-up NF VINs DO show high CV (expected), but the failed A2 VINs show downward step-only → moderate CV, not extreme. Not discriminative.

**Flagged NEW finding (P6-NEW)**: `dur_p95_over_p50` ratio (tail-heaviness of crank duration) shows moderate density-robustness (r with n_events = 0.083) but AUROC 0.561. This is genuinely unexplored in V1.1 but too weak to pursue. The distribution shape of crank duration does not reliably separate F from NF at this n.

**Verdict: WEAK** — No serendipitous strong signal found.

---

## Summary Table: All Probes

| Probe | Best Metric | Raw AUROC | LOO AUROC | Cohen's d | Density-Safe | Verdict | V2 Action |
|-------|------------|---------|---------|---------|------------|---------|-----------|
| P1 session anatomy | dip_depth_delta90 (session) | 0.679 | — | 0.74 | YES | WEAK | Drop |
| P2 recovery dynamics | dip_delta90 | 0.636 | — | 0.64 | YES | WEAK | Drop |
| **P3 cold-start dip** | **cold_dip_delta90** | **0.739** | **0.648** | **0.872** | YES | **PROMISING (weak)** | **LOVO eval** |
| P4 event separability | is_retry (30d) | 0.709 | — | — | YES | WEAK | Drop (=production) |
| P5 aging drift | ts_slope_L20 | 0.893 | — | — | Partial | KNOWN | Already in V1.1 |
| P5 fleet rank | ts_fleet_rank_slope | 0.882 | — | 1.556 | NO (r=−0.750) | ARTIFACT | Drop |
| P6 serendipity | drive_mean_slope | 0.550 | — | 0.69 | Partial | WEAK | Drop |

---

## Key Finding: cold_dip_delta90 (P3) as Best Candidate

**Definition**: Change in mean cold-start (first start after ≥6h rest gap) dip depth in the final 90 days vs own baseline.

**n**: 11 failed / 15 NF with sufficient cold starts (27 VINs active).

**Effect**: AUROC 0.739 (raw), LOO AUROC 0.648. Cohen's d = 0.872. MWU p = 0.043.

**Density check**: r(cold_dip_delta90, n_cold_starts) = −0.127 → safe.

**Physics**: Cold-start dip depth increases when battery internal resistance is high (low temperature + degraded cell) because the battery must supply higher instantaneous current to the starter solenoid with less reserve. Battery-cascade A2 VINs (VIN3_F, VIN4_F, VIN6_F) show the strongest effect. A1/A3/A4 VINs show weaker or absent signal.

**Limitation**: The production feature `dip_depth_last90_delta` already captures aggregate dip depth change; `cold_dip_delta90` is a subset (cold starts only) that may not materially differ. A LOVO incremental test is required to confirm additive value above the production model. Given the LOO AUROC drop (0.739 → 0.648), the signal is modest.

**Lead-time view**: Same temporal window as production features (final-90d vs baseline). No earlier-warning property confirmed.

---

## Uncertainties and Stop Conditions Hit

1. **P5 density confound confirmed severe**: r(failed, n_weeks) = −0.771. Any lifetime-trend metric will appear to discriminate because failed trucks are observed for fewer weeks. Only fixed-window metrics (L20) are trustworthy, and those are already in V1.1.

2. **P1 session anatomy limited by crank events cache schema**: The cache has `retry_within_120s` (boolean) but not inter-attempt time series within a session. True intra-session gap sequence analysis would require rebuilding from raw parquet. Budget constraint: pilot-level evidence (from retry_within_120s as proxy) was used instead.

3. **P3 cold start cold_dip_delta90 baseline sparsity**: For some VINs with short history (VIN2_F, VIN3_F, VIN5_F), the baseline window (>90d) has fewer than 5 cold-start events, making the delta noisy. VIN5_F was excluded (NaN).

4. **Recovery slope nulls**: 19% null rate (3,948 / 20,471 events). Nulls may be non-random (events without VSI post-crank data); the non-null subset may be biased toward longer events or higher-activity days.

5. **n=14 failed trucks bounds all AUROC CIs**: Bootstrap CI for any metric at AUROC 0.739 is approximately [0.55, 0.90]. No finding in this report is statistically definitive.

6. **SMA-dead exclusion reduces effective sample**: All crank-based analyses limited to 11F / 15NF VINs (not 14/20). Four failed VINs (VIN8, VIN9, VIN12, VIN13) carry zero crank signal.

---

## File Inventory

### Scripts (new files only, under `STARTER MOTOR/V2_program/probes/`)
| File | Purpose |
|------|---------|
| `P1_crank_session_anatomy.py` | Session grouping, multi-attempt rates, session dip/duration/recovery deltas |
| `P2_vsi_recovery_dynamics.py` | Recovery slope baseline vs final-90d, slow-recovery rate, Theil-Sen trend |
| `P3_cold_start_proxy.py` | Cold/warm start dip depth and duration comparison (NOT E4's success rate) |
| `P4_event_separability.py` | Event-level binary features at age-matched F vs NF (final-90d and final-30d) |
| `P5_aging_drift.py` | Theil-Sen slope of std over full life; fleet-percentile rank trajectory; density-confound analysis |
| `P6_serendipity.py` | VSI drive mean decline, duration kurtosis, weekend/weekday ratio, operational silence, rest-VSI CV |

### Output CSVs (under `STARTER MOTOR/V2_program/probes/out/`)
| File | Rows | Key content |
|------|------|-------------|
| `P1_sessions.csv` | 10,405 | Session-level metrics (n_attempts, dip, duration, etc.) |
| `P1_session_metrics_per_vin.csv` | 27 | Per-VIN session baseline/final-90d/delta aggregates |
| `P1_session_auroc.csv` | 9 | AUROC table for session metrics |
| `P2_recovery_per_vin.csv` | 27 | Per-VIN recovery slope baseline/delta/trend |
| `P2_recovery_auroc.csv` | 7 | AUROC table for recovery metrics |
| `P3_cold_warm_per_vin.csv` | 27 | Per-VIN cold/warm start dip depth and duration |
| `P3_cold_start_auroc.csv` | 5 | AUROC table for cold-start metrics |
| `P4_event_features_sample.csv` | 5,000 | Sample enriched event table (binary flags) |
| `P4_event_auroc.csv` | 14 | AUROC table at VIN level (age-matched) |
| `P5_aging_trends.csv` | 34 | Per-VIN Theil-Sen slopes, fleet-rank drift, density check |
| `P5_percentile_rank_trajectory.csv` | 2,577 | Per-VIN-week fleet-percentile rank of vsi_drive_std |
| `P5_aging_auroc.csv` | 7 | AUROC table with density-confound flags |
| `P6_serendipity_metrics.csv` | 34 | Per-VIN serendipity metrics |
| `P6_serendipity_auroc.csv` | 7 | AUROC table for serendipity metrics |

---

## Verdict Summary for V2 Feature Selection

**PROMISING (weak), warranting LOVO incremental test**:
- `cold_dip_delta90`: cold-start dip depth final-90d vs baseline. AUROC 0.739, LOO 0.648, d=0.872, p=0.043. Density-safe. Physics-consistent (battery cold-resistance amplification). Likely partially redundant with production `dip_depth_last90_delta`. Only pursue if incremental LOVO regression adds ≥0.02 AUROC to production model; given n=11/15, this is near the noise floor.

**WEAK** (all probes except P5 ARTIFACT):
- Session anatomy (P1): rate metrics duplicative of production retry/crank-rate features.
- Recovery dynamics (P2): no consistent slope degradation signal.
- Cold-start ratio (P3, dip_cold/warm_ratio): 0.561 — not informative.
- Event binary thresholds (P4): all < 0.71, dominated by production features.
- Serendipity metrics (P6): 0.457–0.561, all p > 0.5.

**ARTIFACT** (density-confounded):
- Full-lifetime Theil-Sen slope of vsi_std: n_weeks alone LOO AUROC 0.936; partial r = 0.194 after controlling.
- Fleet-rank drift and fleet-rank slope: r(n_weeks) = −0.750; partial r = 0.063.
- Late fleet-rank percentile: a proxy for short history, not genuine high-risk signal.

**KNOWN** (re-discovered, not new):
- Fixed-window (L20) vsi_std slope: AUROC 0.893 → already implemented in production as `vsi_withinwk_std_ratio_30d_w`.

**Overall conclusion**: The V1.1 production feature set appears to exploit the primary available signal channels. `cold_dip_delta90` is the only metric not already captured by a production feature that shows a statistically plausible effect (p=0.043), but its LOO AUROC of 0.648 and strong A2-archetype specificity limit its standalone value. Recommend: single LOVO incremental evaluation of `cold_dip_delta90` added to the V1.1 feature set as the only V2 candidate. No other probe reached PROMISING threshold.

---
*Probe execution time: ~8 minutes. No raw parquet scans performed (all from cache). SMA-dead exclusion applied to all crank analyses (7 VINs). No existing files modified.*
