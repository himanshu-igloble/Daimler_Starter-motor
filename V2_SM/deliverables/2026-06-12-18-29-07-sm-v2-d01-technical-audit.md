---
title: "SM V2 Program — D1: Starter Motor V1/V1.1 Technical Audit"
status: "complete"
created: "2026-06-12"
---

# Deliverable 1 — Starter Motor V1/V1.1 Technical Audit

> Audit basis: full read of `STARTER MOTOR/` (V1 + V1.1 trees), agent-distilled intake
> (`STARTER MOTOR/V2_program/intake/01_v1_v11_audit_intake.md`) with Fable spot-verification of all
> load-bearing claims against source files. SM fleet = 34 trucks (14 F + 20 NF), `_SM` suffix,
> fully independent of the ALT fleet.

## 1. What was audited

| Layer | Artifacts |
|---|---|
| Data ingestion | `src/V1_SM_build_weekly_cache.py`, `V1_SM_crank_events.py` → 34 weekly parquets, 20,471-event crank catalog |
| Features | `src/V1_SM_features.py` (34×23), `V1.1/src/V1_1_SM_features.py` (34×10 clean pool + admissibility + L40 control matrix) |
| Labels | t_end = last telemetry; JCOPENDATE for lead-time dual reporting only |
| Models | V1 Ridge (k=4), V1.1 fully nested 34-fold LOVO Ridge (`V1_1_SM_nested_ridge.py`) |
| Alerts | `V1_1_SM_alerts.py` — persistence / A1 crank-burst / A2 battery-cascade, all LOVO-validated |
| Horizon | `V1_1_SM_horizon.py` — prequential k=0..26 walk-back, exact k=0 reconciliation |
| Audits | `V1.1/audit/` A (data quality), B (features), C (model), D (physics) + 12 probe/audit scripts |
| Discovery | `V1.1/discovery/` E1–E5 (patterns), F1–F4 (survival), G1–G3 (sequence) |
| Reports | 10 reports incl. model card, executive recommendation, explanation cards |

## 2. Headline results (verified against canonical files)

| Quantity | V1 (as reported) | V1 (restated, honest) | V1.1 | Source |
|---|---|---|---|---|
| LOVO AUROC | 0.9214 | 0.8929 (nested) | **0.9321 (nested)** | `C_model_audit.md §1`, `V1_1_SM_model_spec.json` |
| Selection optimism | +0.0285 | — | **+0.0036** | same |
| Recall / specificity | 13/14, 18/20 | 12/14, 18/20 | 13/14, 15/20 (Youden); **10/14, 18/20 (RED tier)** | same |
| Permutation p | 0.001 (non-nested) | — | 0.005 (full nested pipeline, N=200) | same |
| Calibration | slope 4.72 (probs invalid) | — | slope 0.86, Brier 0.124 — **probabilities shippable** | `V1_1_SM_gates.json G3` |
| Detection horizon | unvalidated | — | **k\* = 10 weeks**, decay-to-chance confirmed | `V1_1_SM_alerts_horizon.md §5` |

## 3. What is working (strengths)

1. **Validation discipline is genuinely industrial-grade.** Screening, subset search, threshold and
   recalibration are all re-done inside each of 34 LOVO folds; the optimism gap collapsed from
   +0.029 (V1) to +0.0036. The permutation test shuffles labels through the *entire* nested
   pipeline (p=0.005, the floor at N=200). Few production PdM systems are validated this honestly.
2. **Leak defense is structural, not cosmetic.** Every V1.1 feature is window/L40-anchored by
   construction; the L40 control matrix is bit-identical (G1 drop = 0.0000). The program found and
   banned its own V1 headline feature (`vsi_dominant_freq` = a 1/n_weeks artifact, L40 AUROC
   0.748→0.525) — `B_feature_audit.md §1.4`.
3. **The artifact register is a model practice.** 12 catalogued artifacts (silent gaps, SMA-dead
   telematics config, density drift, VSI setpoint offsets, battery-replacement steps, pooled-Youden
   threshold artifact...) each with mitigation and residual risk.
4. **Alert channels were validated out-of-fold, and the honest negatives were published.**
   Persistence: recall holds 13/14 LOVO but NF FP doubles (2→4/20) and *every* NF truck visits the
   fire state as a walking alarm (31.4% of weeks) — demoted to terminal-state condition flag. A2
   battery-cascade: 4/5 of the battery archetype, **0/20 NF**, replacement-step immune — the only
   short-fuse (~1–3 month) channel. A1: too noisy standalone (1.52 ep/truck-yr), kept as corroborator.
5. **The horizon claim is mechanically verified.** X4 recomputes features causally at every cut with
   exact k=0 reconciliation (max|diff| ≤ 4.4e-16) and shows AUROC ≥0.75 sustained to k=10 weeks,
   decaying to chance past ~k=20 — the score is failure-locked, not epoch-locked.
6. **Physics-grounded archetypes (A1 solenoid / A2 battery-cascade / A3 volatility / A4 silent)**
   connect every failed VIN to a mechanism and to the channel that should catch it
   (`E_pattern_discovery.md §2`).

## 4. What is not working (weaknesses), and why

| # | Weakness | Why it behaves that way | Severity |
|---|---|---|---|
| W1 | G4 winner-stability gate FAILS (modal subset 14/34 folds) | A 14/14 tie between k=3/k=4 nestings of the same 2-feature core; substantive stability is fine (core pair 34/34) but the strict criterion is honest to report | Low |
| W2 | Youden operating point gives 15/20 specificity | Youden is recall-greedy at this class balance; the RED-tier point (18/20 @ 10/14) is the deployable one | Low — choice of operating point, not a defect |
| W3 | 4 failed trucks are GREEN-tier (VIN1/3/4/9_F) | Three are A4-silent or solenoid-then-silent: the failure transient was never telemetered | Structural; channels recover 3 of 4 |
| W4 | VIN9_F_SM invisible on every layer | SMA-dead config + 142-day silent gap + A4 abrupt mode | Irreducible with current telemetry |
| W5 | No prospective validation | Entire program is retrospective; 16/20 NF end at the extraction wall (2026-02) | The single biggest open validation risk |
| W6 | No cost/economics layer | Tier thresholds chosen by Youden, not by maintenance economics | Addressed in V2 (D6/D7) |
| W7 | NF true age unknown | NF trucks lack SALEDATE; t_start = extraction-window start understates age | Biases fleet-clock age axis; cannot be fixed in-data |
| W8 | Bootstrap CI [0.811, 0.986] is wide | n=34, 14 events — irreducible at this fleet size | Permanent until more failures accrue |
| W9 | Repeat-offender NF trucks (VIN2/5/8/15_NF) dominate FP counts | Plausibly genuinely degrading, right-censored at extraction | Reframe as prospective watchlist, not FPs |

## 5. Hidden assumptions (the ones that matter)

- **t_end anchoring** (C1): all features end at last telemetry, not failure date. Correct for
  causality, but it means the model predicts "truck approaching its last transmission," and the 5
  gap VINs' final 32–142 days are invisible by construction.
- **Crank success = RPM ≥ 550 within event+15 s** (C7) at 5-second sampling: ~93% of cranks are
  single-sample; duration is quantized at 5 s. All crank-duration claims inherit this.
- **SMA-dead masking + fold-internal imputation** (C11): 7 trucks contribute no crank signal;
  their crank features are train-fold means. The model is structurally VSI-only for that cohort.
- **Event ≠ failure mode**: `Failure_type` is constant ("Starter Motor") on all 30.9M failed rows;
  archetypes are data-derived, not warranty-verified.

## 6. Leakage risks — status

Leak ceilings measured in `A_data_quality_audit.md §6`: n_weeks AUROC **0.952**, active_days
**0.946**, t_start **0.893** — all above any honest model. Defenses: admissibility rules (no
counts/lengths/dates), L40 anchoring, G1 zero-drop control, G2 proxy audit (OOF r vs n_weeks
−0.640 — above tripwire, justified as label-mediated via the G3 k-decay curve), G6 token scan.
**Residual risk**: any future feature touching history length, calendar position, or transmission
density must clear the same gates; the V2 probe wave (P5) re-confirmed that all lifetime-trend
metrics are density artifacts (r(failed, n_weeks) = −0.771).

## 7. Component verdict table

| Component | Works? | Why | Business value |
|---|---|---|---|
| Weekly + event caches | Yes | Gap-aware, artifact-flagged, regime-masked | Foundation for everything |
| 10-feature clean pool | Yes | All admissible, L40-anchored; 2 crank features admissible-but-weak | Risk tiers |
| Nested Ridge (Layer 1) | Yes — ceiling | 0.932 nested; model-class sweep shows trees/boosting 0.67–0.78, RF ties but no gain (`C_model_audit.md §4`) | Monthly fleet triage |
| Tiers + calibration | Yes | Slope 0.86; RED = 10/14 @ 18/20 | Actionable priorities |
| Persistence channel | Conditionally | Terminal-state flag only; walking use floods (20/20 NF) | Condition confirmation on AMBER/RED |
| A1 crank-burst | Corroborator only | 1.52 FP ep/truck-yr standalone | Rescued GREEN-tier VIN1_F |
| A2 battery-cascade | Yes — best channel | 4/5 archetype, 0/20 NF, ~66 d median lead | Battery-first intervention (cheapest save) |
| Survival/hazard layer | **No — closed** | Hazard RUL MAE 576 d vs constant 44 d; ranking 0.586 vs static 0.893 (`F_survival_analysis.md`) | None as RUL; vsi_std_ratio retained as trend covariate |
| Deep/sequence models | **No — closed** | 235×–6,275× over EPV-10 parameter budget; 43-param LSTM seed-unstable (`G_sequence_representation.md §1–2`) | Revisit at n_failed ≥ 30–50 |
| Explainability | Partial | `V1_1_SM_explanations.json` + cards exist; not yet wired into alert routing | Audit trail per alert |
| Economics layer | **Missing** | Never built | V2 closes this (D6) |
| Prospective validation | **Missing** | Retrospective only | V2 governance closes this (D8) |

## 8. Audit verdict

V1.1 is **feature-complete and honest at the discrimination layer**: 0.932 nested AUROC with a
10-week validated horizon is the ceiling of this dataset, triple-confirmed by physics
(`D_failure_physics.md`), prequential decay (G3/X4), and the V2 probe wave (P5 density audit).
The genuine V2 upside is **not a better classifier** — it is the decision layer (economics,
evidence-conditional windows), the never-built physics features with honest incremental bounds
(cold-start dip, RPM-rise lag), a validated heuristic/escalation layer, productization
(monitoring, governance, cold-start onboarding), and instrumentation (current/high-rate VSI).
Those are quantified in D4–D10 of this program.
