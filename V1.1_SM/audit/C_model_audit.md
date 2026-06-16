---
title: "Agent C — V1 SM Model Architecture Audit (adversarial, with reruns)"
status: "complete"
created: "2026-06-10"
---

# Agent C — Adversarial Audit of the V1 Starter Motor Modeling Stack

Audited artefacts (read-only): `STARTER MOTOR/src/V1_SM_ridge_classifier.py`,
`V1_SM_feature_selection.py`, `STARTER MOTOR/results/*.csv|json`,
`STARTER MOTOR/reports/V1_SM_final_report.md`.
Rerun script: `STARTER MOTOR/V1.1/audit/scripts/C1_model_audit.py`.
Numeric outputs: `STARTER MOTOR/V1.1/audit/results/C1_audit_results.json`,
`C1_nested_lovo_folds.csv`, `C1_jackknife.csv`.

**Reproduction check (gate for everything below):** the V1 winner LOVO was
re-executed from the feature matrix — AUROC 0.9214 exactly, max per-VIN
probability difference vs `V1_SM_lovo_predictions.csv` = 4.8e-05 (CSV rounding
only). The audit reruns are therefore on the same footing as V1.

---

## 1. Selection-bias audit — NESTED LOVO (the headline number)

**Problem.** V1's screening (23 -> 5 pool: MW p<0.10, AUROC>=0.60, Spearman
filter, LOVO-stability filter) and the exhaustive k=4–5 subset search both
consumed **all 34 labels** before the LOVO that produced AUROC 0.9214. The
held-out VIN in each fold had already voted on which features the model would
use. This is textbook selection leakage; the reported 0.9214 is optimistic by
construction.

**Rerun.** Full nested LOVO: inside each of the 34 folds, the complete
screening pipeline (MW + AUROC floor + correlation filter + leave-one-out
stability at ceil(0.8x33)=27/33 + pool cap 12) and the complete exhaustive
subset search (inner 33-fold LOVO per subset, identical tie-breaking) were
redone on the 33 training VINs only; the held-out VIN was scored by that
fold's own winning pipeline and classified at that fold's own inner-OOF Youden
threshold.

| Quantity | V1 reported | Nested (honest) |
|---|---|---|
| AUROC | **0.9214** | **0.8929** |
| Optimism | — | **+0.0285** |
| Bootstrap 95% CI | [0.765, 1.000] | [0.746, 1.000] |
| Recall @ threshold | 13/14 (pooled post-hoc Youden) | 12/14 (per-fold Youden) |
| Specificity @ threshold | 18/20 | 18/20 |

**Selection stability (why the optimism is modest):** 27/34 folds picked
exactly the V1 winner 4-set. `vsi_std_ratio_30d` and `vsi_dominant_freq`
appeared in 34/34 fold winners, `vsi_range_trend` 31/34,
`failed_crank_rate_last90` 28/34; interlopers were `crank_dur_trend` (7 folds)
and `vsi_rest_p05_last90` (2 folds). Fold pools ranged 4–6 features. The
signal is real and the selection is fairly stable — but the honest baseline
for V1.1 to beat is **0.893, not 0.921**.

Note the diagnostic V1 itself recorded: in-sample permutation importance of
`failed_crank_rate_last90` is 0.0002 ± 0.011 — it contributes ~nothing to the
fitted model, yet survived subset selection (and was dropped by 6/34 nested
folds). It is a selection-noise passenger, and it is also the feature that is
missing for VIN5_F_SM and near-zero for the silent-gap VIN8_F_SM (see §6).

## 2. Threshold honesty

The 0.4382 Youden threshold was computed on the pooled OOF predictions — i.e.
after seeing all 34 outcomes. Rerun with the 4 features fixed: each fold's
threshold from an inner 33-fold LOVO on its training VINs.

- Per-fold thresholds: min 0.4203, median 0.4398, max 0.4929 (pooled: 0.4382).
- Pooled post-hoc threshold: recall 13/14, specificity 18/20.
- Honest per-fold thresholds: **recall 12/14, specificity 18/20**.

The pooled choice buys exactly one TP — and it is VIN12_F_SM, whose
probability (0.4382) **equals the threshold to 4 decimals**. That detection is
an artifact of computing the cutoff on the same pooled predictions
(`roc_curve` returns observed scores as candidate thresholds, and `>=` then
includes the boundary case). Honest operating point: **12/14 recall, 18/20
specificity**. The effect is small (one truck) but the reported confusion
matrix should not survive into V1.1 unmodified.

## 3. Calibration of the 34 OOF probabilities

`sigmoid(decision_function)` of a RidgeClassifier is a monotone score, not a
probability. Quantified on the V1 OOF predictions:

- Brier score **0.1491** vs constant-base-rate reference 0.2422 — informative.
- Calibration-in-the-large: mean predicted 0.456 vs base rate 0.412 — mild
  over-prediction (logit gap −0.18); acceptable.
- **Recalibration slope 4.72** (intercept 0.85): scores are severely
  compressed — the whole fleet lives in [0.24, 0.95], non-failed mean 0.347,
  failed mean 0.610. A "0.55 RED" is in reality far more than 55% likely to
  fail; a "0.30 GREEN" far less than 30%.
- Consequence: the GREEN/AMBER/RED cutoffs (0.35/0.55) and the Youden value
  are tier boundaries on an uncalibrated score. They rank correctly but their
  numeric values must not be communicated as failure probabilities. 12/20
  non-failed trucks sit in 0.26–0.46 — within 0.10 of the threshold — so small
  score shifts move tiers; with 34 points, fitted recalibration (Platt inside
  LOVO) would itself be high-variance, so V1.1 should either recalibrate
  inside folds and report it as such, or present ranks/tiers only.

## 4. Model-class sensitivity (same 4 features, same LOVO protocol)

| Model | AUROC | Recall | Spec |
|---|---|---|---|
| **RidgeClassifier(alpha=1.0)** | **0.9214** | 0.929 | 0.900 |
| RandomForest(300) | 0.9214 | 1.000 | 0.700 |
| LogisticRegression(L2, C=1) | 0.9143 | 0.929 | 0.900 |
| GaussianNB | 0.9125 | 1.000 | 0.800 |
| kNN(k=7) | 0.9089 | 0.786 | 0.900 |
| LogisticRegression(L2, C=0.1) | 0.9036 | 0.929 | 0.900 |
| LinearSVM(C=1) | 0.9000 | 0.857 | 0.850 |
| kNN(k=5) | 0.8946 | 0.929 | 0.750 |
| GradientBoosting(d2, 100) | 0.7786 | 0.714 | 0.950 |
| DecisionTree(depth=2) | 0.6679 | 0.714 | 0.750 |

**Verdict: Ridge confirmed.** Every linear/smooth model lands 0.89–0.92 (the
ranking differences are ~1 swapped pair among 280 — not meaningful at n=34);
axis-split trees and boosting collapse (0.67–0.78), exactly replicating the
ALT lesson. RandomForest ties on AUROC but with 6 FPs at its Youden point and
no interpretability gain. There is no model-class headroom on a static
4-feature matrix; V1.1 gains must come from the data representation, not the
classifier.

## 5. Stability

**Jackknife (drop one VIN, recompute AUROC on remaining 33 OOF preds):**
range [0.9154, 0.9731], i.e. ±0.05 around 0.9214 — no single VIN creates the
result. The structure of the errors:

- Removing **VIN8_F_SM** (the missed failure, prob 0.303) lifts AUROC to
  0.9731 (+0.052) — the single biggest sensitivity, and it is a *miss*, not a
  support: the headline would be higher without it, so it is not propping up
  the result.
- Removing **VIN9_NF_SM** (worst FP, 0.541) gives 0.9436 (+0.022).
- Removing any single correctly-ranked failed VIN costs at most −0.006.

**Invariance:** 5 random fold-order shuffles -> AUROC 0.921429 identical each
time; RidgeClassifier `random_state` in {0, 7, 1234} -> max probability
difference 0.00e+00. The pipeline is exactly deterministic; no seed-hacking
surface exists. (The bootstrap CI and permutation p do depend on their seeds,
but N=200/1000 resamples make that immaterial.)

## 6. What a linear-static snapshot model structurally cannot learn

Evidence from the OOF errors (all three V1 errors have a temporal story the
static matrix cannot encode):

- **VIN8_F_SM (FN, prob 0.303):** a silent-gap VIN — telemetry ends **37 days
  before** JCOPENDATE. Its `failed_crank_rate_last90` is 0.006 (window
  overlaps the gap) and its `vsi_range_trend` is *negative* (−0.044). The
  snapshot cannot represent "observation ended early"; a survival formulation
  treats this correctly as censoring of the covariate stream. VIN5_F_SM's
  `failed_crank_rate_last90` is outright NaN and gets median-imputed toward
  the healthy fleet — same defect.
- **VIN8_NF_SM (FP, 0.456):** `failed_crank_rate_last90` = 0.323 — higher
  than 13 of the 14 failed trucks. A chronically hard-starting but
  non-deteriorating truck is indistinguishable from a deteriorating one in a
  single window; only *within-truck change over time* separates them.
- **VIN9_NF_SM (FP, 0.541):** `vsi_dominant_freq` 0.040 (97th pct of fleet) —
  a persistently noisy-voltage healthy truck. Same failure mode of the
  representation: level vs trajectory confusion.

The static model also cannot express time-varying risk (one number per truck
forever), cannot produce a "risk this month" statement, and averages over
failure-mode heterogeneity (the project's own failure-mode work showed
abrupt vs gradual modes).

**Could the data support richer formulations?**

- **(a) Discrete-time hazard on truck-weeks: YES — this is the V1.1 move.**
  The weekly cache holds **2,636 truck-weeks** (22–108 per VIN, 34 VINs). A
  pooled logistic hazard P(fail in week t | alive, x_t) with time-varying
  covariates reframes the rows from 34 to ~2.6k, handles the 5 silent-gap
  VINs as censored, and yields a calibrated weekly hazard. **Honest caveat:
  the events-per-variable budget is still 14** — each truck fails once;
  truck-weeks are clustered, not independent. EPV>=10 allows ~1 covariate,
  EPV>=5 allows ~2–3. So: <=3 covariates, baseline-hazard spline kept rigid,
  inference by truck-level LOVO + truck-level permutation (never row-level),
  cluster-robust everything. The win is *time-varying, calibrated risk*, not
  more discrimination headroom.
- **(b) Cox PH at n=34/14 events: marginal.** lifelines 0.30.0 is installed.
  Same EPV arithmetic (14/10 = 1.4 covariates at the standard rule). Usable
  only as a 1–2 covariate sanity check on (a); it adds nothing (a) does not,
  and the discrete-time version handles tied weeks and time-varying x more
  naturally. Do not build the deliverable on it.
- **(c) Sequence models: NO.** 14 positive sequences total. The smallest
  useful GRU/TCN has O(10^3–10^4) parameters against 14 event labels; even
  with truck-week windowing the effective independent units remain 34 trucks.
  Per-truck day-precision RUL already lost to the fleet clock on the ALT side
  (MAE 142d vs 50d) for the same reason. Revisit at fleet n >= ~150–200
  failed units, not before.

## 7. Verdict — should V1's numbers be restated in V1.1?

**Yes. Three restatements, one confirmation:**

1. **AUROC: report 0.893 (nested, selection-honest) as the baseline V1.1 must
   beat.** 0.9214 may remain in the table only if labeled "non-nested
   (feature selection saw all labels); optimism +0.029". The CIs overlap
   heavily ([0.746, 1.000] nested) — the model is genuinely good; the point
   estimate was simply flattered.
2. **Operating point: 12/14 recall, 18/20 specificity** with a fold-honest
   threshold. The 13th TP (VIN12_F_SM) is a threshold-equals-score artifact.
3. **Probabilities: declare uncalibrated** (slope 4.7). Tier labels are fine;
   the numeric values 0.35/0.55 must not be presented as probabilities.
4. **Model class: Ridge stands.** Confirmed against 9 alternatives; no
   restatement needed, and V1.1 should not spend effort on classifiers.

### Ranked recommendations for V1.1 modeling

| # | Recommendation | Feasibility at n=34 |
|---|---|---|
| 1 | Restate baseline: nested AUROC 0.893, recall 12/14, spec 18/20; pin the V1.1 comparison table to these | Done (this audit) |
| 2 | Discrete-time hazard on 2,636 truck-weeks, <=3 time-varying covariates, truck-level LOVO + cluster-aware permutation inference; deliverable = calibrated weekly risk + censoring-correct handling of the 5 gap VINs | **Feasible — highest expected value** |
| 3 | In-fold recalibration (Platt) or rank/tier-only reporting of scores | Trivial |
| 4 | Pre-register the threshold rule (inner-fold Youden or fixed 0.44) before any V1.1 LOVO is run | Trivial |
| 5 | Replace/augment `failed_crank_rate_last90` with a gap-aware coverage feature (it is a selection passenger: importance 0.0002, NaN for VIN5_F, misleading on gap VINs) | Feasible, small |
| 6 | Cox PH (lifelines) 1–2 covariate sanity check on #2 only | Marginal — EPV 1.4 |
| 7 | Sequence/deep models | Not at n=34 (14 event sequences); document and skip |

All numbers in this report regenerate from
`STARTER MOTOR/V1.1/audit/scripts/C1_model_audit.py` (deterministic, ~4 min).
