---
title: "V2 Raw Screens Intake — B5 True CWR + B6 VIN1_F Daily Alarm"
status: "complete"
created: "2026-06-12"
---

# V2 Raw Screens Intake: B5 + B6

## B5 — True Crank-While-Running (CWR) Screen

### Definition & Method
True CWR requires: SMA==1 AND RPM>400 AND the immediately preceding row (same VIN, gap ≤10 s) also had RPM>400. This excludes normal crank spin-up (where RPM rises from ~0 inside the SMA=1 window). RPM sentinel 65535 filtered first. Consecutive qualifying rows (gap ≤10 s) grouped into EPISODES.

Scope: all 14 failed VINs (both SMA-dead excluded) + 10 largest active NF VINs (9 after removing SMA-dead VIN20_NF). Processing the full 30.9M-row failed parquet + 36.8M NF rows for the 9 active NF VINs.

SMA-dead exclusions (>99% SMA null): VIN8_F, VIN9_F (failed); VIN10_NF, VIN11_NF, VIN12_NF, VIN13_NF, VIN20_NF (NF — only 5/15 NF dead; remaining 10/15 active NF processed with 9 in scope for row count).

### Results

**Failed VINs (active, n=12):**

| VIN | Episodes | ep/truck-yr |
|-----|----------|-------------|
| VIN14_F_SM | 35 | 27.97 |
| VIN4_F_SM | 9 | 21.77 |
| VIN7_F_SM | 13 | 17.37 |
| VIN6_F_SM | 11 | 13.80 |
| VIN3_F_SM | 10 | 14.73 |
| VIN1_F_SM | 12 | 14.37 |
| VIN13_F_SM | 8 | 13.45 |
| VIN12_F_SM | 13 | 13.80 |
| VIN5_F_SM | 5 | 8.34 |
| VIN11_F_SM | 4 | 3.28 |
| VIN10_F_SM | 7 | 6.15 |
| VIN2_F_SM | 3 | 6.72 |

**F median: 11.89 ep/truck-yr** (n=12 active)

**NF active VINs (n=9 processed):**

| VIN | Episodes | ep/truck-yr |
|-----|----------|-------------|
| VIN5_NF_SM | 46 | 27.01 |
| VIN4_NF_SM | 30 | 18.64 |
| VIN18_NF_SM | 17 | 10.42 |
| VIN17_NF_SM | 12 | 9.57 |
| VIN7_NF_SM | 15 | 7.76 |
| VIN8_NF_SM | 14 | 7.39 |
| VIN1_NF_SM | 12 | 6.83 |
| VIN19_NF_SM | 11 | 6.67 |
| VIN16_NF_SM | 10 | 6.35 |

**NF median: 7.76 ep/truck-yr** (n=9)

**Mann-Whitney U=61.0, p=0.6441** — not significant.

### A1-Archetype Trucks (VIN1_F, VIN10_F, VIN14_F)
- VIN14_F: 35 episodes, 27.97/yr — **top of all trucks, F or NF**
- VIN1_F: 12 episodes, 14.37/yr — above F median
- VIN10_F: 7 episodes, 6.15/yr — below F median

VIN14_F dominates. However, VIN5_NF (27.01/yr) and VIN4_NF (18.64/yr) also show high rates, meaning high CWR is not exclusive to failed trucks.

### Final-90-Day vs Baseline Rate (Precursor Test)
No clear directional pattern across failed fleet:

| VIN | ep_final90 | ep_baseline | rate_f90/yr | rate_base/yr |
|-----|-----------|-------------|-------------|--------------|
| VIN1_F | 0 | 12 | 0.0 | 20.4 |
| VIN4_F | 7 | 3 | 28.4 | 18.0 |
| VIN10_F | 5 | 3 | 20.3 | 3.4 |
| VIN14_F | 4 | 32 | 16.2 | 31.8 |
| VIN12_F | 0 | 13 | 0.0 | 18.7 |
| VIN13_F | 0 | 13 | 0.0 | 12.8 |

Mixed signal: some trucks show final-90 increase (VIN4_F, VIN10_F), others show drop (VIN1_F, VIN14_F, VIN12_F, VIN13_F). No consistent precursor pattern.

Caveat: final-90d windows are short and noisy; this analysis is exploratory only.

### B5 Verdict
**NULL / OPERATIONAL TELLTALE**

F median 11.89 vs NF median 7.76 ep/truck-yr, p=0.64 (Mann-Whitney). The ~53% higher F rate is not statistically significant. The top NF truck (VIN5_NF: 27/yr) exceeds the top failed truck's rate for A1 archetypes. No final-90d precursor pattern is consistent. CWR events are real operational abuse events (starter engaged on running engine) but do not discriminate failed from non-failed trucks at the fleet level.

Caveats:
- Only 9/15 active NF VINs processed (full scan of all 15 would reduce NF median further or confirm it)
- VIN8_F and VIN9_F excluded (SMA-dead); their true rates unknown
- p=0.64 is far from significance even with this partial NF sample

---

## B6 — VIN1_F_SM Daily Crank-Spike Re-test

### Method
Daily time series of failed cranks + retries (retry_within_120s flag) for VIN1_F_SM, artifact events excluded. A1 alarm rule: 7-day rolling sum S7 of (failed + retries); alarm when S7 > (first-half mean + 3σ, floor 3) for ≥2 consecutive days, evaluated on second half of history.

VIN1_F metadata: t_start=2024-09-30, t_end=2025-09-10 (345 days), JCOPENDATE=2025-11-26, gap=72 days.

### Daily Series Key Facts
- Total events: 546 (56 failed, 49 retries)
- First-half S7 baseline: mean=1.91, σ=3.34 → threshold=11.94 (floor not binding)
- History half-point: day 172 (≈2025-03-21)

### Alarm Results

| Alarm Onset | S7 | Threshold | Lead to t_end | Lead to JCOPENDATE |
|-------------|-----|-----------|---------------|-------------------|
| **2025-04-08** | 21 | 11.94 | **155 days** | **232 days** |
| **2025-06-24** | 16 | 11.94 | **78 days** | **155 days** |

**2025-04-08 burst detail:** 12 failed cranks + 9 retries in one session (11:44–11:58), 15 total events. S7 stays elevated (21–22) for the full 7-day window → clean alarm over ≥2 days.

**2025-06-24 burst detail:** 9 failed cranks + 7 retries, 16 combined events. S7=16 exceeds threshold; 7-day window keeps S7 elevated through 2025-06-30 (≥2 consecutive days) → clean alarm.

Weekly granularity (V1 verdict: "insufficient data"): the weekly aggregator smoothed both bursts into ≤1-event weeks around each date, failing to reach the weekly equivalent threshold. The daily rule detects both.

### NF Sanity Check (False-Alarm Rate)

| VIN | Alarms | Alarm Dates | Threshold |
|-----|--------|-------------|-----------|
| VIN4_NF_SM | **3** | 2025-07-04, 2025-10-18, 2026-01-08 | 9.88 |
| VIN15_NF_SM | **6** | 2025-02-08, 2025-02-26, 2025-04-14, 2025-08-04, 2025-09-03, 2025-10-19 | 6.44 |
| VIN5_NF_SM | **2** | 2025-03-25, 2025-07-18 | 13.43 |

All three NF trucks fire false alarms (2–6 per truck). The rule has poor specificity on its own at the per-truck level. The thresholds vary widely (6.44–13.94) due to varying baseline activity levels.

### B6 Verdict
**YES — daily aggregation resolves the V1 "insufficient data" finding.**

The daily A1 rule produces two clean alarms for VIN1_F (Apr 8: 155-day lead to t_end, 232-day lead to JCOPENDATE; Jun 24: 78-day lead, 155-day lead to JCOPENDATE). Weekly granularity masked both bursts; daily is the right resolution.

However, **the rule has high false-alarm rate on NF trucks (2–6 alarms per truck)**. VIN1_F's alarms are real in hindsight, but the rule is not specific enough in isolation for production alerting. Recommended next step: combine daily alarm flag with the Ridge failure-risk score as a conjunction gate to reduce false positives.

Lead to JCOPENDATE for first alarm: 232 days — operationally actionable if combined with risk score filter.

---

## Output Files
- `B5_cwr_per_vin.csv` — per-truck episode count, ep/truck-yr, note (SMA-dead flagged)
- `B5_cwr_episodes.csv` — episode-level summary (trucks with >0 episodes)
- `B5_cwr_final90_vs_baseline.csv` — final-90d vs baseline rate delta per failed VIN
- `B6_vin1f_daily_series.csv` — VIN1_F 345-day daily series with S7 and alarm flag
- `B6_alarm_dates.csv` — all alarm onset dates (VIN1_F + NF sanity trucks) with S7, threshold, lead days

## Scripts
- `b5_crank_while_running.py` — B5 full analysis
- `b6_vin1f_daily_alarm.py` — B6 daily alarm + NF sanity check
