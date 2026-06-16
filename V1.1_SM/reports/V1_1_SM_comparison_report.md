---
title: "V1 vs V1.1 Starter Motor — Comparison Study"
status: "complete"
created: "2026-06-10"
---

# V1 vs V1.1 Starter Motor — Comparison Study

Fleet: 34 independent SM trucks (14 failed + 20 non-failed). All V1.1 artifacts under `STARTER MOTOR/V1.1/`. V1 artifacts under `STARTER MOTOR/` (tag `v1-sm`), untouched.

## 1. Executive Summary

**Key improvements**
1. **V1's headline number was restated before being beaten.** Nested LOVO (feature screening + subset selection redone inside every fold) shows V1's true out-of-sample AUROC is **0.893**, not the reported 0.9214 (+0.029 selection optimism, plus one recall point bought by a post-hoc pooled threshold). V1.1's headline — **nested AUROC 0.9321, CI [0.811, 0.986], permutation p = 0.005** — is measured under the stricter protocol and still beats both numbers. V1.1's own selection optimism is +0.0036.
2. **The gain is real feature engineering, not protocol arithmetic**: the same nested protocol on V1's de-artifacted feature set scores 0.8429; V1.1's new features add +0.089.
3. **V1's worst error is fixed**: VIN8_F_SM (V1's missed failure, P = 0.303) is now caught at P = 0.521 (recalibrated 0.716, RED), via the within-week volatility and battery-floor features.
4. **A validated early-warning capability now exists** — V1 had none (its trend battery fired on 90% of healthy trucks). V1.1 ships three LOVO/physics-validated channels with a measured **10-week detection horizon** and a decay-to-chance proof that the signal is failure-locked, not leakage.
5. **Probabilities are now shippable** (calibration slope 0.86, Brier 0.124 vs V1's slope 4.72 — V1 scores were rank-only).
6. **Explainability went from a permutation-importance table to**: exact per-truck linear attributions (= SHAP for a linear model), 34 explanation cards with raw-unit counterfactuals, a 4-archetype failure taxonomy mapped to physics, and a governance-grade model card.

**Key limitations (unchanged or newly exposed)**
- VIN9_F_SM is now missed and is **structurally invisible** (SMA-dead config + 142-day silent gap + abrupt mode). The honest recall ceiling for any lead-time claim is ~10–11/14 (4 silent/abrupt A4 failures).
- At the Youden operating point V1.1 trades specificity (15/20) for recall (13/14); the RED tier restores 18/20 at 10/14. There is no operating point that dominates V1 on both axes simultaneously — V1.1 wins on ranking (AUROC), calibration, and alert coverage, not on every confusion-matrix cell.
- Day-precision RUL remains impossible — now with proof (§4): a calibrated hazard model's median RUL is off by 576 days; a constant beats every survival formulation.

**Business impact**: V1.1 turns a static annual-snapshot classifier into a monitored fleet program — weekly-scoreable risk tiers with calibrated probabilities, a ~2.5-month early-warning window on flagged trucks, battery-vs-starter triage routing (the single largest avoidable-cost lever per DICV A6), and per-truck explanations a depot engineer can act on.

## 2. Performance Comparison

| Metric | V1 (reported) | V1 (restated, honest) | V1.1 | Improvement (vs honest V1) |
|--------|---------------|----------------------|------|----------------------------|
| AUROC (headline) | 0.9214 (non-nested) | **0.8929** (nested) | **0.9321** (nested) | **+0.039** |
| Bootstrap 95% CI | [0.765, 1.000] | [0.746, 1.000] | [0.811, 0.986] | tighter, higher floor |
| Permutation p | 0.001 (non-nested pipeline) | — | 0.005 (full nested pipeline, N=200 floor) | honest test |
| Selection optimism | +0.0285 (hidden) | disclosed | +0.0036 | −0.025 |
| Recall @ honest threshold | 13/14 (post-hoc pooled Youden) | 12/14 (per-fold) | **13/14** (per-fold) | +1, incl. VIN8_F_SM |
| Specificity @ same point | 18/20 | 18/20 | 15/20 | −3 (see RED tier) |
| RED-tier operating point | n/a (0 RED in NF fleet) | n/a | 10/14 recall @ 18/20 spec | matched-specificity option |
| F1 / MCC @ honest threshold | 0.897 / 0.821 | — | 0.812 / 0.669 | mixed (recall-weighted) |
| Calibration slope / Brier | 4.72 / 0.149 (uncalibrated) | — | **0.86 / 0.124** | probabilities shippable |
| Validated lead-time channel | none (NF FP 90%) | none | 3 channels, LOVO/physics-validated | new capability |
| Early-detection rate (any validated channel) | 0/14 | 0/14 | **13/14** (median first-fire lead 168 d; 10/20 NF fully clean) | new capability |
| Detection horizon (sustained AUROC ≥ 0.75) | not measured | not measured | **k\* = 10 weeks**, decay-to-chance verified | new capability |
| RUL error | not shipped (ALT precedent) | — | not shipped — now with SM-specific proof (hazard MAE 576 d vs constant 44 d) | honest closure |
| False-alarm burden (shipped alert set) | — | — | RED tier 2/20; A2 detector 0/20; persistence flag 4/20 (tier-gated) | quantified |
| Features | 4 (1 artifact: `vsi_dominant_freq` = 1/n_weeks) | 3 sound | 4, all admissibility-audited | artifact removed |

## 3. Technical Improvements

**New features (X1, all L40/window-anchored, cohort-masked, battery-step re-baselined):** `vsi_withinwk_std_ratio_30d_w` (within-week volatility ratio — the workhorse, coef +0.886), `rest_vsi_p05_delta90` (battery-floor sag vs own segment baseline), `dip_depth_last90_delta` (crank dip widening), plus carried-over `vsi_range_trend` (flagged as a collinearity suppressor in attribution outputs). Two physics candidates (retry-burst, extended-crank-tail) were admissible but fleet-weak — rejected by in-fold screening in 34/34 folds; they live on inside the A1 alert channel instead.

**New validation protocol (X2):** fully nested LOVO; fixed-40-week-window control (zero drop by construction — all features window-anchored); per-feature admissibility audit vs the measured leak ceilings (`n_weeks` AUROC 0.952, `t_start` 0.893); pre-registered per-fold threshold rule; per-fold Platt recalibration; full-pipeline permutation test; jackknife (0.927–0.951); prequential time-locking proof.

**New alerting layer (X3, LOVO-validated):** persistence terminal flag (13/14 recall, 4/20 NF, tier-gated only — as a raw walking alarm it visits all 20 NF trucks and is explicitly NOT shipped that way); A2 battery-cascade triple detector (4/5 battery-archetype trucks, **0/20 NF**, immune to battery replacements, median lead 66.5 d); A1 crank-burst corroborator (tier-gated only — 1.52 FP episodes/truck-year standalone). Combined policy: 13/14 failed trucks fire ≥1 channel.

**New explainability (X5):** exact coef×z attributions summing to decision values; 34 per-VIN cards with raw-unit counterfactuals; archetype taxonomy (A1 solenoid intermittency ×3, A2 battery cascade ×4–5, A3 volatility drift ×3, A4 silent/abrupt ×4) mapped to failure physics; physics-sign verification per coefficient with the suppressor honestly flagged; model card with banned-feature registry and governance rules.

**Knowledge artifacts:** failure-physics research report (17 sources; per-mode observability verdicts at 5 s sampling), survival-analysis closure (discrete-time hazard, Cox, Weibull AFT — all documented dead ends with numbers), sequence/representation closure (parameter-budget math + tiny-LSTM empirical demo; one shelved future SSL path).

## 4. Honest Assessment

**What improved:** ranking power (+0.039 nested AUROC) under a strictly harder protocol; recall including the V1 miss; calibration; early warning (none → 13/14 with a measured horizon); explainability; leakage governance; and the evidence base (every shelved method now has numbers attached, not vibes).

**What did not improve:**
- Specificity at the Youden point (15/20 vs 18/20). Operations must choose the operating point; the comparison is honest only as a pair.
- VIN9_F_SM: V1 nominally caught it (P = 0.4825, barely over a post-hoc threshold); V1.1 misses it on every layer. It is the limiting case of the A4 archetype — SMA-dead config, 142-day silent gap, abrupt mode. No defensible pipeline catches it with this data.
- RUL: survival modeling made things *worse*, quantifiably (truck ranking 0.586 vs 0.893; RUL MAE 576 d vs 44 d for a constant). Calibrated weekly hazard (~0.005/wk) and day-precision RUL are mathematically incompatible at 14 events.
- Deep learning: every architecture requested (LSTM/BiLSTM/TCN/Transformer/TFT/Informer/PatchTST/TimeXer, DeepSurv/DeepHit/DSM, VAE/contrastive/Siamese) is 235×–6,275× over the parameter budget at 14 events; a 43-parameter LSTM's seed variance exceeds any signal difference. Honest probes (PCA, trend coefficients, distance methods) all saturate at the same ~0.89–0.93 single degree of freedom the engineered features already capture.

**Failure modes still not detectable:** A4 silent/abrupt (4/14 — windings, seizure, relay/control losses, telemetry death); brush/commutator wear as a 60–120-day channel (physically real, destroyed by 5 s / 0.2 V sampling); anything requiring cranking current.

**Residual risks:** n = 34 — the CI floor is 0.811 and a handful of trucks decide every threshold; archetypes were derived in-sample (suggestive, not inferential); OOF scores correlate with leak axes (r = −0.64 n_weeks, +0.51 t_start) — defended by the L40 zero-drop control and the prequential decay-to-chance argument, but a larger fleet is the only definitive cure; the persistence rule's NF FPs (4/20) may be right-censored degraders — or may be drift.

**Additional data for future gains (ranked):** (1) high-frequency crank logging (≥1 Hz during SMA=1 — post-2026 architecture) revives the brush-wear channel and true dip/duration physics; (2) cranking current or battery SoC/SoH ends the battery-vs-starter ambiguity; (3) maintenance/parts records turn archetypes into labels; (4) more failures (n_failed ≥ 30–50) unlocks the shelved SSL crank-encoder path and meaningful survival modeling; (5) ambient temperature for cold-start conditioning.
