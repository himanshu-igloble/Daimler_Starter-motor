---
title: "SM V2 Program — D3: Data Discovery & Pattern Analysis Report"
status: "complete"
created: "2026-06-12"
---

# Deliverable 3 — Data Discovery & Pattern Analysis Report

> Basis: V1.1 audit/discovery layer (A/B audits, E1–E5, F, G probes) + the V2 probe wave
> (`STARTER MOTOR/V2_program/probes/` P1–P6, run 2026-06-12, full report in
> `V2_program/intake/03_data_discovery_intake.md`). All effects quoted are Failed-vs-NF unless noted.

## 1. The raw material

107.2M rows (30.9M failed / 76.3M non-failed), 6 signals, ~5 s nominal cadence with 16–24% VSI
nulls, heavy gap structure. Derived assets: 34 weekly parquets, 20,471-event crank catalog
(13 artifact-flagged), daily caches, 2,636-row causal truck-week table.

Data-quality facts that bound everything (`A_data_quality_audit.md`):
- **Leak ceilings**: n_weeks AUROC 0.952, active_days 0.946, t_start 0.893 — observation structure
  out-predicts any honest model; every discovery below had to clear density/length controls.
- **SMA-dead cohort** (7 trucks, SMA null >99.7%): a telematics *configuration* split, not sensor
  failure; crank analyses exclude or mask these trucks.
- **VSI quantization 0.2 V + per-truck setpoint offsets** (27.6–28.2 V): only within-truck
  ratios/deltas are meaningful; cross-truck absolute levels smear calibration.
- **16/20 NF end at the extraction wall** (2026-02-09/16): NF censoring is administrative.

## 2. Temporal patterns

| Question | Answer | Evidence |
|---|---|---|
| Long-term aging trend in crank quality? | **No usable one.** All lifetime-trend metrics (Theil-Sen slopes of VSI std, fleet-rank drift; raw AUROC 0.839–0.954) are observation-length artifacts: r(failed, n_weeks) = −0.771; partial-r after control ≈ 0.06–0.19 | P5 (`V2_program/probes/out/P5_*`) |
| Short-term degradation signature? | **Yes — the core signal.** Within-week VSI noise ratio + range trend + rest-VSI sag + dip widening, moving in the final ~10 weeks | B2 screen; X2 modal subset |
| How early does the signal exist? | **k\* = 10 weeks** before last transmission; AUROC decays 0.93 → ~0.59 (chance) past k≈20. Triple-confirmed (G3 screening features, X4 frozen model, P5 fixed-window control) | `V1_1_SM_alerts_horizon.md §5` |
| Drift shape | 10/14 failed = months-scale MONOTONE_DRIFT of volatility (not step); 16/20 NF flat | E3 trajectories |
| Silence as a pattern | 5/14 failed have 32–142 d terminal silence; 2 taper first (97%/89% row-count drop), 3 cut off abruptly. Silence is *outcome*, not usable feature (leak), but is an operational trigger | A audit §3; D11 register |

## 3. Statistical patterns (what was tried, with verdicts)

- **Variance evolution — the one family that works**: `vsi_withinwk_std_ratio_30d` raw 0.968 /
  windowed 0.921; weekly std-ratio is the workhorse in every model and the persistence channel.
- **Entropy/shape — closed**: weekly entropy 0.525, spectral entropy 0.539, dip-depth skew 0.543,
  crank-duration CV 0.639, kurtosis/tail ratios 0.48–0.56 (P6) — all ≈ chance at n=34.
- **Spectral — closed and cautionary**: `vsi_dominant_freq` 0.748 was a 1/n_weeks artifact (0.525
  after L40 control);真 spectral content on fixed windows ≈ 0.59.
- **Gradient/acceleration — closed**: 0.55–0.59 across formulations (B2).

## 4. Operational patterns

- **Start frequency / duty**: sma_duty_last90 0.645 (p=0.16) — weak, closed (B2). Duty-cycle k=2
  clusters show no failure alignment (E5).
- **Seasonality**: no month effect on VSI levels (KW p=0.90/0.95); NF *trending-flag* rate is mildly
  seasonal (monsoon 9.1% vs winter 4.3%) but cannot explain V1's NF FP rate (E4). Calendar features
  on end-anchored windows are banned anyway (D12: t_end month ≈ label).
- **Maintenance events**: rest-VSI step detection (E5) found 5 NF battery replacements (+0.59 to
  +1.40 V) — now an asset: the A2 detector's sign logic provably rejects them (0/20 NF FP).
- **Geography**: no location channel exists in the data. Not assessable.

## 5. Vehicle clustering — do degradation pathways exist?

E1 ran PCA, Ward hierarchical, DBSCAN, and Spectral on 22 artifact-free features:
- **No global failed/NF cluster structure** (spectral k=2/3 ARI ≈ 0). The only all-failed Ward
  cluster {VIN2/3/6/13_F} is confounded with n_weeks (p=0.014) and t_start (p=0.0035).
- PC1 = battery/rest-VSI block, PC2 = crank-quality block, PC4 = telematics config (r=0.567 with
  SMA-dead) — components recover *signal families and config*, not failure pathways.
- UMAP/t-SNE/HDBSCAN were not run and should not be: at n=34 with 14 events, neighbor-graph
  embeddings are dominated by the same density/config axes PCA already exposed, with added
  stochasticity and no validation degrees of freedom (G1's EPV arithmetic applies to manifold
  methods too).
- **What works instead**: supervised, physics-anchored signature cards (E2) yield the A1/A2/A3/A4
  archetypes with per-VIN evidence — the program's most decision-useful taxonomy. Verdict:
  *distinct degradation pathways exist (A1 solenoid, A2 battery-cascade, A3 volatility), but they
  are found by physics priors + evidence cards, not by unsupervised geometry at this n.*

## 6. The V2 probe wave — was anything left unexploited?

Six probes ran against the event catalog and raw parquets with mandatory density-confound checks:

| Probe | Best metric | Effect | Verdict |
|---|---|---|---|
| P1 Crank-session anatomy (multi-attempt sessions, inter-attempt gaps) | session metrics | AUROC 0.54–0.68, p>0.13 | WEAK — weekly rates already absorb it |
| P2 VSI dip-recovery dynamics (charge acceptance) | recovery slope deltas | AUROC 0.40–0.55 | WEAK — recovery is alternator/regulator physics, not SM |
| P3 Cold-start dip (first start after ≥6 h rest) | **cold_dip_delta90** | raw 0.739, LOO 0.648, d=0.872, p=0.043, density-safe (r=−0.127) | **PROMISING (weak)** — carried to incremental evaluation (D5) |
| P4 Event-level separability at matched age | very-deep-dip rate | d=0.978 but AUROC 0.667, p=0.16 | WEAK — 2–3 A2 VINs drive it |
| P5 Aging/fleet-rank drift | lifetime trends | confound r=−0.771 | **ARTIFACT — definitive negative** |
| P6 Serendipity (drive-mean decline, duration tails, weekend ratio, silence-before-storm) | drive_mean delta | 0.457–0.561 | WEAK — incl. a true null: drive voltage does NOT decline pre-failure (regulator pushes it UP in A2) |

Honest bound: at n=14 events, the CI on even the best probe (0.739) is ≈ [0.55, 0.90]; nothing
here is definitive. The cold-start dip is physics-consistent (cold internal resistance) and
A2-specific; its incremental value over the production `dip_depth_last90_delta` is evaluated under
the frozen protocol in Deliverable 5.

## 7. Verdict — hidden information assessment

1. **The weekly-resolution dataset is mined out.** Three independent lines (B2's 24-candidate
   screen, the E/F/G discovery layer, this probe wave) converge: the exploitable signal lives in
   VSI-derived volatility/sag/dip features in the final ~10 weeks, plus crank-burst events for the
   solenoid archetype. New weekly features now yield ≤ +0.02 AUROC candidates at best.
2. **The remaining information is sub-5-second** (inrush shape, true dip profile, chatter) — it
   exists in the trucks but not in the telemetry. Instrumentation (D2 §7), not analytics, unlocks it.
3. **One new operational telltale**: crank-while-running events (SMA=1 ∧ RPM>400) — never computed
   in V1/V1.1; being screened in the heuristics wave as an abuse/duty metric.
4. **The density confound is the permanent guardrail**: any V2+ feature must pass the P5-style
   partial-correlation test against observation structure before it is believed.
