---
title: "V2.1 Starter Motor — Richer Heuristics & Feature Screen Iteration (Design Spec)"
status: "draft"
created: "2026-06-22"
program: "SM V2.1"
supersedes_context: "V1 (v1-sm), V1.1 (0.9321 nested), V2_program (ceiling confirmed + v2_system)"
accept_bar: "Lower NF false-alarms (< 0.19 ep/truck-yr) while holding recall >= 10/14 and lead ~>= 116 d"
---

# V2.1 Starter Motor — Richer Heuristics & Feature Screen Iteration

## 1. Objective

Enrich the **operational heuristic layer** and run a final **exploratory feature screen**
for the Starter Motor (SM) predictive-maintenance system, then deliver one honest
ship / no-ship verdict.

**Primary success criterion (the accept-bar, pre-registered):** a new rule ships only
if it **beats H2's specificity — NF false-alarm rate < 0.19 episodes/truck-yr — while
holding recall >= 10/14 and median lead time ~>= 116 days.** This is a *specificity hunt*,
not an AUROC chase.

## 2. Background & binding constraints

The SM program is mature; three established facts bound this iteration and must not be
re-litigated:

1. **Data ceiling, not method ceiling.** Nested-LOVO AUROC = **0.9321** at a **10-week**
   horizon, triple-evidenced (prequential decay-to-chance at k=11; density audit
   r(failed,n_weeks)=-0.771; X4 reconciliation 4.4e-16 / 0.9357). With **n=14 failed**
   trucks, honest probes saturate ~0.89-0.93 ("one degree of freedom").
2. **More features degrade this model.** Best two prior candidates (`cold_dip_delta90`,
   `rpm_rise_lag_delta90`) scored **+0.0000** incremental lift; the 12-feature pool
   expansion dropped nested AUROC to **0.875** (-0.057). Production set stays at 4
   features (`vsi_withinwk_std_ratio_30d_w`, `rest_vsi_p05_delta90`, `vsi_range_trend`,
   `dip_depth_last90_delta`).
3. **The wins live in the heuristic/economics layer.** V2's deployable pager is H2
   (persistent-RED dwell): **10/14 recall, 116 d median lead, 0.19 NF ep/truck-yr**.

### 2.1 Recon: what is already done (do NOT re-run)

A reconnaissance pass over the `V2_program/probes/` and `V1.1/discovery/` suites
established that several intuitive candidates are already settled:

| Candidate | Prior artifact | Verdict / numbers |
|---|---|---|
| Post-crank VSI **recovery slope** | P2_vsi_recovery_dynamics | WEAK — AUROC 0.552, p=0.678 (alternator/regulator property, not starter) |
| **Duty-cycle** (cranks/day + trend) | E5_maintenance, P5_aging_drift | WEAK — no cluster/trend separation; retry-slope AUROC 0.500, p=1.0 |
| Walking-curve **trajectory shape** | E3_trajectories | KNOWN — already the production baseline (10/14 monotone-drift; persistence catches 13/14) |
| Crank **session anatomy** | P1_crank_session_anatomy | WEAK — all metrics p>0.1, AUROC 0.54-0.68 |
| Lifetime aging trends | P5_aging_drift | ARTIFACT — n_weeks confound (LOO 0.936); fixed-window = known G3 |

These are **out of scope** for V2.1.

### 2.2 Recon: what is genuinely untouched (in scope)

| Item | Why novel |
|---|---|
| **A1** CUSUM/EWMA control-chart change-point on rest-VSI | E5 only did a one-shot step-scan + SNR; no statistical control chart, no directional rejection of NF up-steps |
| **A2** conjunction pagers | V2 recommended H2∧A2 / H2∧H5 but never backtested them as composite rules |
| **A3** H4 with terminal-state persistence | Documented bug: H4's 100% NF-fire came from "first-ever-fire" inflation; never re-run with terminal episode state |
| **B2** inter-crank-interval CV | P1 did session anatomy but never inter-crank *timing variance* |
| **B4** >=8h cold-start dip, per-VIN z-scored | P3 used 6h + raw delta; the >=8h + per-VIN z-score variant is untested |
| **B5** ANR engine-torque / load-context | ANR present in cache but never evaluated as a failure predictor |

## 3. Scope

**In scope:** A1, A2, A3 (heuristics, shippable core); A5 (graded-RUL productization,
deliverable); B2, B4, B5 (exploratory feature screens, expect HOLD); C1-C3 (new-data
appendix, documentation only).

**Out of scope (YAGNI / closed):** headline-AUROC chase (data ceiling); re-running
P1/P2/P5/E3/E5; new production plumbing (`v2_system/` already exists — integrating a
winner is a *follow-on, only if A1 ships*); day-precision RUL; deep/sequence models;
SSL crank-encoder (all previously closed with numbers).

## 4. Architecture — parallel fan-out + synthesis gate

Three work-streams run as independent, parallel work-orders (<=3 concurrent agents, per
the Stay-Within-Limits throttle). They share only **read-only frozen inputs** and never
mutate them. Nothing auto-promotes; everything funnels through one synthesis gate that
applies the accept-bar.

```
FROZEN SHARED INPUTS (read-only)
  walking_scores.csv (27 cuts x 34 VIN)            -> A1, A2, A3
  heuristic_fires.csv / heuristic_summary.csv      -> A2, A3
  V1_1_SM_alert_validation.csv / alert_policy.csv  -> A2, A3
  E5_step_changes_all.csv (ground truth)           -> A1 validation
  V1_1_SM_feature_matrix.csv + nested-LOVO script  -> B2, B4, B5 gate
  raw parquets (sm_failed / sm_non_failed)         -> B2, B4, B5

        Work-stream A          Work-stream B            Work-stream C
        (heuristics)           (feature screens)        (new-data appendix)
        A1 CUSUM/EWMA          B2 inter-crank CV        C1 IBS / current clamp
        A2 conjunctions        B4 z-cold-start          C2 hi-rate VSI firmware
        A3 H4 terminal-fix     B5 ANR load-context      C3 full-CWR + saledate
        A5 graded RUL          (E1 admit -> E2 LOVO)    (doc only, no modeling)
                              \        |        /
                          SYNTHESIS GATE (orchestrator)
        Accept-bar: ship iff NF < 0.19 ep/yr AND recall >= 10/14 AND lead ~>= 116 d.
        Features: ADD iff E2 LOVO delta >= +0.01. -> single V2.1 verdict report.
```

## 5. Work-stream A — Heuristics (shippable core)

### A1 — Directional CUSUM/EWMA change-point on per-VIN rest-VSI  *(headline)*
- **Input:** per-VIN weekly rest-VSI (p05) series, reconstructed **causally** from the
  frozen weekly cache using the same L40-window arithmetic as `H_walking_scores.py`.
- **Method:** one-sided **downward** CUSUM
  `S_t = max(0, S_{t-1} + (mu0 - k*sigma0 - x_t))`, with baseline `mu0, sigma0` from the
  VIN's **first 8 usable weeks** (causal, pre-alarm). EWMA variant
  `z_t = lambda*x_t + (1-lambda)*z_{t-1}` as cross-check.
- **Pre-registered params (frozen before any outcome look):** baseline = 8 weeks;
  CUSUM slack `k = 0.5*sigma`; alarm threshold `h = 4*sigma`; EWMA `lambda = 0.3`,
  `L = 3*sigma`; **direction = DOWN only**; min 8 usable weeks (matches X4 usability).
- **Specificity lever:** DOWN-only ignores NF battery-*replacement* up-steps — the
  mechanism that inflates competing rules' false-alarm rate.
- **Ground-truth sanity check:** must recover the E5 down-steps (VIN14_F -2.3 V/SNR 5.76,
  VIN6_F -2.7 V/SNR 4.15, VIN2_F -1.59 V, VIN3_F -1.70 V) and must NOT fire on NF
  up-steps.
- **Metrics:** recall n/14, NF ever-fire n/20, NF ep/truck-yr, median lead (d).
- **Accept:** NF < 0.19 ep/yr at recall >= 10/14, lead ~>= 116 d.

### A2 — Conjunction pagers
- **Rules:** `H2 AND A2`, `H2 AND H5`, and (once A1 computed) `A1 AND H2`.
- **Method:** AND-combine **terminal-state** fire tables; both channels must be active
  within a **4-week alignment window** (pre-registered).
- **Rationale:** conjunctions can only *lower* FP — a direct accept-bar play.

### A3 — H4 with terminal-state persistence
- Re-run H4 (>=2 of {tier>=AMBER, persistence, A1-burst, A2}) with persistence recomputed
  as **currently-firing episode** (not "ever-fired"). Recover persistence episode
  intervals from `walking_scores.csv` by re-applying the documented persistence rule
  weekly. Tests whether fixing the inflation rescues multichannel voting.

### A5 — Graded RUL escalation  *(deliverable, no new modeling)*
- Lookup table mapping (channel fired, dwell length) -> inspection window, from V2's D6
  evidence-window matrix (A2 -> 28-91 d; persistence AND RED -> 206 d CI[126,284];
  AMBER empirically empty). Output = policy table + per-truck band assignment.

## 6. Work-stream B — Feature screens (exploratory; expect HOLD)

All three run the **frozen V1.1 protocol** (replicates `V2_incremental_feature_eval.py`):

1. **Reconciliation gate:** reproduce modal-4 non-nested LOVO AUROC = **0.9357**
   (diff <= 0.002) before any candidate work.
2. **E1 admissibility:** Mann-Whitney p (screen <= 0.10); single-feature oriented AUROC;
   proxy-leak Spearman |r| <= 0.5 vs {n_weeks, t_start, span}; redundancy Pearson r vs
   the 4 production features.
3. **E2 fixed-subset LOVO increment:** modal-4 + candidate. **ADD iff delta AUROC >= +0.01.**
4. **E3 nested rerun:** only if E2 passes; flagged EXPLORATORY (multiplicity).

| Feat | Computation (raw parquet, `py -3` polars-lazy) |
|---|---|
| **B2** inter-crank CV | session starts (gap > 60 s => new session, per P1); CV = std/mean of inter-session intervals, last90 vs baseline -> `intercrank_cv_delta90` |
| **B4** z-cold-start | cold = first crank after **>= 8 h** rest; per-VIN **z-scored** dip (own mu, sigma); `z_cold_dip_delta90` — distinct from P3's 6h-raw |
| **B5** ANR load | 2-3 candidates: hi-torque time-fraction (ANR > p75); mean ANR in 60 s pre-crank (restart load); idle-quality (ANR var at idle RPM). E1 screen only; promote to E2 only if admissible |

**Stop condition:** if all three fail E1, stop — report HOLD; do not force E2.

## 7. Work-stream C — New-data appendix (documentation only)

DICV-facing. For each path: signal unlocked, why current 6-signal/5 s data cannot reach
it, cost, integration effort, expected payoff.

- **C1 — IBS / current clamp.** Crank-current waveform -> brush / solenoid / contact-
  resistance health (impossible from 5 s voltage). ~Rs 2-15k/truck.
- **C2 — High-rate VSI firmware trigger during SMA=1.** Captures crank voltage waveform
  at > 0.2 Hz -> revives the 60-120 d brush-wear channel. Firmware-only.
- **C3 — Full true-CWR scan (all 15 NF) + SALEDATE/odometer/maintenance ingest.**
  Completes the partial B5 CWR scan; adds age/mileage normalization.

## 8. Synthesis gate & decision logic

1. Collect all A-rule and combo metrics into one **recall / FP / lead comparison table**
   (every rule vs H2 baseline).
2. Apply the accept-bar: **ship iff NF < 0.19 ep/yr AND recall >= 10/14 AND lead ~>= 116 d.**
3. Apply the feature gate: **ADD iff E2 delta >= +0.01** (else HOLD).
4. Write a single honest verdict — explicitly allow a "NO IMPROVEMENT / all HOLD"
   outcome if nothing clears the bar.

## 9. Validation rigor & honesty guardrails

1. **Pre-registration:** all params written to `params/` and committed **before** runs.
2. **Reconciliation gate** opens each work-stream (A reproduces H2 = 10/14, 0.19;
   B reproduces modal-4 LOVO = 0.9357) before new work.
3. **SCREEN-GRADE** labeling throughout (n=34, retrospective; wide CIs).
4. **Multiplicity:** ~7 new tests -> Benjamini-Hochberg note; no claim of significance
   without it.
5. **Leak gates** on every feature: proxy-correlation audit; n_weeks (0.952) and t_start
   (0.893) ceilings stated.
6. **No retrospective tuning** — report pre-registered params as-is.
7. **VIN independence** — `_SM` suffix only; never pool with ALT; never pool SMA event
   rates across the SMA-dead cohort (VIN8_F, VIN9_F + 5 NF).

## 10. Deliverables & layout

```
STARTER MOTOR/V2.1/
  Plan/V2_1_SM_spec.md            (this file)
  params/                          pre-registered param files (committed first)
  heuristics/  A1_cusum.py  A2_conjunctions.py  A3_h4_terminal.py  A5_graded_rul.py  + out/
  features/    B2_intercrank_cv.py  B4_zcold_start.py  B5_anr_load.py  + out/
  appendix/    C_new_data_appendix.md
  reports/     V2_1_SM_results.md           (per-stream detail)
               V2_1_SM_verdict.md           (synthesis + ship decision + comparison table)
               V2_1_SM_exec_summary.md      (1-page)
```

## 11. Risks & open build-notes

- **A1 input availability:** per-VIN weekly rest-VSI series may need reconstruction from
  the weekly cache; the `H_walking_scores.py` machinery already recomputes features per
  cut, so the arithmetic exists — confirm at plan time and reuse verbatim.
- **A3 persistence episodes:** full weekly episode intervals were noted as absent from
  the alert CSVs in V2; recompute from `walking_scores.csv` by re-applying the
  persistence rule weekly.
- **Small-n fragility:** a single truck shifts recall by ~7 points; all conclusions are
  screen-grade.
- **Most-likely outcome:** A1 and/or a conjunction ships a cleaner pager; A3 may rescue
  multichannel; B2/B4/B5 most likely HOLD; C becomes the "what actually breaks the
  ceiling" ask for DICV.
