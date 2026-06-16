---
title: "V1.1 Agent E — Hidden Pattern Discovery (clustering, failure archetypes, trajectories, seasonality, maintenance fingerprints)"
status: "complete"
created: "2026-06-10"
---

# Agent E — Pattern Discovery (Starter Motor fleet, n=34)

All numbers from read-only V1 artifacts: `STARTER MOTOR/results/V1_SM_feature_matrix.csv`, `cache/weekly/*.parquet` (34), `cache/events/V1_SM_crank_events.parquet` (non-artifact events only). Scripts in `V1.1/discovery/scripts/E1–E5`, data in `V1.1/discovery/out/`. **n=34: every clustering result below is suggestive, not inferential.** umap-learn/hdbscan are not installed; sklearn PCA/Ward/DBSCAN/Spectral used (no t-SNE — at n=34 it adds nothing over PCA).

Anti-leakage protocol applied throughout: `vsi_dominant_freq` excluded everywhere; every embedding axis and cluster partition checked against `n_weeks` (leak AUROC 0.952) and `t_start` ordinal (leak AUROC 0.893); SMA-rate comparisons conditioned on the telematics-config cohort (SMA-dead = VIN8_F, VIN9_F, VIN10/11/12/13/20_NF — confirmed from `sma_obs_rows`, all <1% SMA coverage).

---

## 1. VIN-level clustering (E1) — weak structure, partially leakage-contaminated

22 artifact-free features, median-imputed, standardized.

**PCA** (`E1_pca_loadings.csv`, `E1_pc_vs_axes.csv`): PC1 28.8%, PC2 21.5%, PC3 7.4%, PC4 6.8% (cum 64.6% at 4 PCs — diffuse, no dominant axis).
- PC1 = battery/rest-VSI decline block (bat_charge_delta_trend +0.36, vsi_rest_median_trend −0.35, vsi_rest_p05_last90 −0.34, dip_depth_trend +0.31). r(failed)=0.21, r(n_weeks)=−0.17 — mildly failure-tilted, mostly clean.
- PC2 = crank-quality block (retry_rate 0.44, crank_dur_mean 0.40, failed_crank_rate 0.37). r(failed)=0.16, r(n_weeks)=−0.25.
- **PC4 is the telematics config**: r(sma_dead)=0.567 via crank_per_active_day (0.60) and rate_vsi_below_21 (0.46). Even with vsi_dominant_freq banned, the config cohort re-enters through event-rate features — confirms audit A's "never pool SMA-rate features across configs".
- No PC strongly tracks failed (max |r|=0.21), n_weeks (max 0.25 on PC1–3) or t_start.

**Hierarchical (Ward)** (`E1_cluster_results.csv`, `E1_cluster_membership.csv`): merge heights jump 9.8→15.4→18.1 at the last two merges — a 2–3 cluster cut at best. ward_k2 = [4, 30]: the 4-cluster is **all failed** (VIN2_F, VIN3_F, VIN6_F, VIN13_F; ARI vs failed only 0.144), driven by the battery block (mean |z| diff: bat_charge_delta_trend 2.47, dip_depth_trend 2.44, vsi_rest_median_trend 2.31). **Leakage check: the same partition separates on n_weeks (KW p=0.014) and t_start (KW p=0.0035)** — these 4 VINs are also short-history/late-start, so the cluster is label-tilted but length-confounded. It is NOT the silent-gap set (ARI −0.11) and NOT the config cohort (ARI −0.11). Section 2 shows the battery interpretation survives on within-VIN (length-free) evidence.

**DBSCAN**: degenerate at all eps (one blob + 2–13 noise points; noise ARI vs failed ≤0.20). **Spectral k=2/3**: no alignment with failed (ARI −0.02/0.00), config (−0.01/0.01) or leakage axes (KW p=0.31/0.24). Honest negative: **there is no global cluster structure separating failed from NF** — the failure signal lives in within-VIN temporal deltas, not in cross-sectional position.

## 2. Failure archetypes (E2 + E5) — the key deliverable

Per-VIN final-120-day signature card vs own >120d baseline; "elevated" judged against the 20-VIN NF reference distribution computed identically at each NF truck's own history end (NF p90: fcr_120 0.126, retry_120 0.091, max_daily_failed 7, vsi_drive_std_ratio 1.137, dip_depth_delta 1.466; NF p10: rest_vsi_delta −0.645 V, rest_vsi_slope −0.028 V/wk). Full cards: `E2_signature_cards_all34.csv`; final table: **`E2_failed_vin_archetypes.csv`**.

| VIN | Archetype | Evidence (final 120 d vs own baseline) |
|---|---|---|
| VIN10_F | **A1 solenoid intermittency** | fcr 0.100→0.433 (4.3x; last-30d 0.564), retry 0.038→0.283 (7.5x), 8 failed cranks in one day, drive-VSI std ratio 2.56 |
| VIN14_F | **A1+A2 mixed** | fcr 0.252→0.449, retry 0.298, 12 failed cranks/day, rest-VSI −2.45 V + step −2.31 V (2025-09-01, SNR 5.8), drive-VSI step +0.65 V, std ratio 5.36 |
| VIN1_F | **A1 then silent** | fcr 0.080→0.198 (2.5x), 9 failed cranks on 2025-06-24, last telemetered crank failed (n=1 in final 30 d — quote with care), then 72 d gap |
| VIN2_F | **A2 battery cascade** | rest-VSI step −1.59 V (2025-09-22, SNR 5.3), rest delta −0.73 V, 8 failed cranks/day, dip_depth +1.66 V. Caveat: 25-wk history, baseline = 43 events |
| VIN3_F | **A2 battery cascade** | rest delta −1.00 V, rest step −1.70 V (2025-06-16), drive-VSI step +0.47 V, std ratio 1.98; fcr flat (clean crank) |
| VIN6_F | **A2 battery cascade** (strongest) | dip_depth +3.65 V, rest delta −2.12 V, rest step −2.71 V (2025-08-04, SNR 4.2), drive-VSI step +0.67 V, std ratio 3.85 |
| VIN13_F | **A2 battery cascade** | rest delta −0.66 V, drive-VSI step +0.75 V (2025-09-01, SNR 3.8), std ratio 2.80, dip_depth +1.09 V |
| VIN7_F | **A3 VSI-volatility only** | std ratio 2.57; fcr/retry/rest all NF-like |
| VIN11_F | **A3 VSI-volatility only** | std ratio 1.82; fcr 0.68x (improved) |
| VIN12_F | **A3 VSI-volatility only** | std ratio 2.32; everything else NF-like |
| VIN4_F | **A4 silent/abrupt** | 97 d gap; std ratio 1.17 (marginal); fcr flat |
| VIN5_F | **A4 silent/abrupt** | 32 d gap; **0 events and no VSI in final 120 d** — card empty, honest unknown |
| VIN8_F | **A4 silent/abrupt** (the V1 miss) | 37 d gap; fcr **improved** 0.103→0.005; only signal std ratio 1.33 (mild) |
| VIN9_F | **A4 silent/abrupt** | 142 d gap; std ratio 1.02, all metrics NF-like |

Ward clustering of the cards (k=3/4, `E2_failed_cards_flags.csv`) isolates {VIN10, VIN14} (burst), VIN1 (burst+gap) and lumps the rest — the A2/A3/A4 split is rule-based (NF-quantile flags), not blind clustering; labelled accordingly.

**Physics mapping**: A1 = solenoid-contact intermittency prior (retry/failed-start bursts, days–weeks horizon) — 3 VINs. A2 = battery-cascade prior (resting-VSI decline + deeper dips + regulator pushing drive voltage UP) — 4–5 VINs; **independently corroborated by step detection (E5): the 4 largest negative rest-VSI steps in the whole fleet are VIN6_F/VIN14_F/VIN3_F/VIN2_F (−2.71/−2.31/−1.70/−1.59 V, all in the final 1–4 months), and the only 4 sustained drive-VSI up-steps ≥0.4 V are VIN13_F/VIN6_F/VIN14_F/VIN3_F (+0.47..+0.75 V, same period)**. A3 = regulation instability without crank/battery signature (could be early A2 or a distinct mode — unresolved at this n). A4 = abrupt/no-precursor prior; A4 = exactly the silent-gap set minus VIN1. Brush wear: invisible, as physics predicted (5 s sampling).

## 3. Degradation trajectories (E3, `E3_trajectory_shapes.csv`)

Causal per-week features (no future or full-history dependence): trailing-4-wk mean of vsi_drive_std / expanding mean (≥8 wk history), and rolling-4-wk failed-crank rate; aligned on the last 40 observed weeks; NF envelope = per-position NF median/p90.

- **Causal std-ratio shape**: failed = 10/14 MONOTONE_DRIFT + 1 LATE_SPIKE + 3 FLAT (VIN1, VIN2, VIN3); NF = 16/20 FLAT, 4/20 drift. The dominant failed trajectory is a **gradual months-scale drift, not a late spike**.
- **Persistence rule** (≥4 of last 12 aligned weeks above the NF p90 envelope): **13/14 failed qualify (all except VIN9_F, 3 wks) vs 2/20 NF (VIN2_NF, VIN5_NF)** — including VIN8_F (12/12 wks) and VIN5_F. Caveats: NF p90 envelope is in-sample (~10% per-position exceedance by construction; the VIN-level 2/20 reflects persistence, not magnitude), and alignment-at-end means failed windows abut failure while NF windows abut an arbitrary cutoff. As a candidate V1.1 alert rule it must be re-validated inside LOVO. Consistent with audit B's `vsi_withinwk_std_ratio_30d` (AUROC 0.968, survives L40 control).
- **Failed-crank-rate shape**: only 4/14 failed show drift/spike (VIN10, VIN1, VIN6, VIN13) — the crank channel is an A1-only channel, 11 wks above-envelope for VIN14, ≤2 for A3/A4. NF: 17/20 flat.

## 4. Seasonality (E4) — levels are not seasonal; the *trend flag* is mildly monsoon-skewed; the V1 FP problem is NOT seasonal

- Raw monthly levels, VIN-month medians, cohort-conditioned: **no month effect** on vsi_drive_std (KW p=0.90 alive / 0.63 dead), vsi_rest_median (p=0.95/0.67), NF crank success (p=0.61; monthly medians 0.94–1.00).
- The causal std-ratio>1.30 "trending" flag on NF weeks IS seasonal: monsoon 9.1% of weeks vs winter 4.3% (chi2 p=0.0072; June peak 14.3%) — a ~2x modulation, plausibly monsoon electrics (humidity/wet starts).
- **But this cannot explain V1's 90% NF lead-time FP rate**: 17/20 NF histories end in February (winter, the *lowest*-flag season) and the overall NF flag rate is only ~6% of weeks. V1's FP problem was the trend criterion (any positive slope), not seasonality. Side finding (leakage warning): t_end month is itself nearly a label — failed ends scatter Jun–Dec, NF ends pile at Feb — so **any calendar-month or season feature computed on a last-N-days window would leak** and is banned for V1.1.

## 5. Maintenance / operational fingerprints (E5, `E5_step_changes_all.csv`, `E5_duty_cycle.csv`)

- **Battery-replacement candidates** (sustained rest-VSI step UP ≥0.5 V, SNR≥2): 5 NF trucks — VIN18_NF +1.40 V (2024-05), VIN12_NF +0.70, VIN3_NF +0.61, VIN5_NF +0.61, VIN17_NF +0.59 — plus VIN8_F +0.60 V in 2024-06 (16 months pre-failure; early battery service, unrelated to the end). These steps reset rest-VSI baselines; V1.1 battery features should be segment-aware.
- Negative steps: dominated by the A2 failed VINs (section 2). VIN10_NF/VIN13_NF show −3.0/−4.2 V "steps" at 2024-02-26 = earliest allowed split in the SMA-dead/VSI-sparse cohort — artifact-suspect, not counted.
- **Duty-cycle clusters** (cohort-conditioned, k=2 on cranks/day, active days, RPM, CSP): a high-crank/low-speed cluster (1.26 cranks/day, CSP 22.9, 7F/7NF) vs low-crank/highway (0.36, CSP 27.1, 5F/8NF) — **no failure alignment**; duty cycle is operational texture, not a risk factor at this n.

## 6. Verdict — how many failure pathways?

**Three observable pathways plus one unobservable class** (suggestive, n=14): **A1 solenoid-intermittency (3)**, **A2 battery-cascade (4 + 1 overlap)**, **A3 VSI-volatility-only (3)**, **A4 silent/abrupt (4)** — i.e., ~10/14 failures have a months-scale electrical precursor, ~4 have none in this telemetry.

V1.1 implications:
1. The single best causal channel is the within-week VSI-volatility drift (catches A1+A2+A3, 13/14 incl. VIN8 under the persistence rule, NF FP 2/20) — implement as a fixed-window LOVO-validated feature + weekly persistence alert.
2. Add a battery-cascade detector: rest-VSI down-step/slope + drive-VSI up-step + dip-depth delta (A2's triple signature, 4/4 corroborated) — also the natural "battery vs starter" triage output, with battery-replacement step-up segmentation to avoid NF false alarms.
3. Keep failed-crank/retry burst as a high-precision short-horizon alert (A1 only; days–weeks lead).
4. A4 (4/14, ~29%) is irreducible with current telemetry — state it as the recall ceiling (~10–11/14) for any honest V1.1 lead-time claim; VIN9_F is the likely permanent miss even for the risk score.
5. Ban calendar/season features on end-anchored windows (t_end month ≈ label); no de-seasonalization needed for levels.
