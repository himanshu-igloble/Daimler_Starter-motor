---
title: "SM V2 Program — D5: Alternative Model Evaluation Report"
status: "complete"
created: "2026-06-12"
---

# Deliverable 5 — Alternative Model Evaluation Report

> Question: did V1/V1.1 choose the right model class, and does any alternative beat it? Method:
> exhaustive use of the program's own controlled comparisons (`C_model_audit.md §4` nine-class
> sweep, `G_sequence_representation.md` parameter-budget + probes, `F_survival_analysis.md`
> survival suite) plus the V2 incremental run (`V2_program/intake/05_incremental_features_intake.md`).
> Evidence tiers: **MEASURED** (run on this fleet, LOVO), **ARITHMETIC** (ruled out by parameter
> budget — would be malpractice to "try"), **INHERITED** (measured in the ALT program, same data
> regime). The binding constraint everywhere: **14 failure events** (EPV-10 budget ≈ 1.4 params).

## 1. Classification models

| Model | Evidence | Result | Verdict |
|---|---|---|---|
| RidgeClassifier(α=1.0), 4 feats | MEASURED | **0.9321 nested** (CI [0.811, 0.986], perm p=0.005); optimism +0.0036 | **KEEP — production** |
| Logistic (C=1) | MEASURED | 0.9143 (same features) | No gain |
| Linear/smooth class (LDA etc.) | MEASURED | 0.89–0.92 band | Equivalent, no gain |
| Random Forest | MEASURED | 0.9214 tie with V1 ridge but 6 FPs and no interpretability gain | Rejected |
| XGBoost / LightGBM / CatBoost (boosted trees) | MEASURED (class) | **0.67–0.78** — splits memorize 34 rows; LOVO punishes | Rejected |
| Balanced RF | — | Class balance (14:20) is not the failure mode; RF already showed no gain | Not warranted |
| TabNet | ARITHMETIC | ~10⁴–10⁵ params vs 1.4-param budget (G1 logic) | Ruled out |
| Explainable Boosting Machine | ARITHMETIC | Per-feature splines ≈ 10–50 params each ≫ budget; the 4-feature linear model already IS fully glass-box | Ruled out; need not arise |

## 2. Survival / time-to-event models

| Model | Evidence | Result | Verdict |
|---|---|---|---|
| Weibull fleet clock (LOVO cond. median) | MEASURED | RUL MAE **461.9 d** vs constant-91d at **44.4 d** | Closed |
| Discrete-time hazard (3 lagged covariates, truck-LOVO) | MEASURED | RUL MAE **576.1 d**; ranking AUROC 0.586 vs static 0.893; weekly P(fail≤30d) 0.744 | Closed (one salvage: vsi_std_ratio HR confirmed) |
| Cox PH time-varying | MEASURED | vsi_std_ratio HR 1.74 (naive p=0.002, anti-conservative SEs) | Sanity only |
| Weibull AFT (early-life covariate) | MEASURED | Covariate NS (p=0.176); early life does not predict lifetime | Closed |
| Random Survival Forest | ARITHMETIC | 14 events → 0–3 events/node beyond depth 1–2; degenerate Nelson–Aalen | Ruled out |
| DeepSurv / DeepHit / DSM | ARITHMETIC | EPV < 0.5–1; DeepHit has ~6× more output bins than events | Ruled out |

## 3. Time-series / sequence models

| Model | Evidence | Result | Verdict |
|---|---|---|---|
| LSTM/BiLSTM/TCN/Transformer/TFT/Informer/PatchTST/TimeXer | ARITHMETIC (G1, formula-counted per architecture) | **235×–6,275× over EPV-10 budget** | Ruled out as a family |
| Tiny-LSTM (h=2, 43 params) — the smallest possible | MEASURED | Seed spread 0.854/0.882/0.918 — seed variance exceeds any probe-vs-baseline difference | Demonstrates the instability empirically |
| Linear sequence probes (PCA3+logit, trend-coeffs, 1-NN, kPCA) | MEASURED | Saturate 0.89–0.925, with leak-flagged components; no probe beats the static features | The sequence contains no extra extractable signal at this n |

## 4. Anomaly detection (novel-failure discovery)

| Model | Evidence | Result | Verdict |
|---|---|---|---|
| Isolation Forest / OC-SVM / LOF / autoencoder family | INHERITED (ALT program, n=25; SM plan §1.3 carries it) | 80–100% false-positive rates standalone at this fleet size | Closed standalone |
| Supervised-physics alternative | MEASURED | The A2 cascade detector is the working "anomaly" channel: 4/5 archetype, 0/20 NF | This is what shipped instead |
| VAE / DeepSVDD | ARITHMETIC | Same parameter wall + no validation degrees of freedom | Ruled out |

## 5. Representation learning

| Approach | Evidence | Verdict |
|---|---|---|
| Contrastive / Siamese / generic SSL on 34 weekly series | ARITHMETIC + G2 probes | The encoder can be fit, but any classifier head re-enters the 14-event wall; probes already saturate |
| **SSL crank-encoder pretraining on the 106M raw rows** (masked VSI reconstruction → frozen encoder → ≤3-dim head) | DESIGNED, gated | The only defensible deep path (G §3). **Entry gate: n_failed ≥ 30–50 + current/high-rate channel + prospective quarter** (D8 Phase D) |
| Foundation TS models (zero-shot embeddings) | Judgment | Embeddings face the same n=34 evaluation wall the G2 probes hit; revisit at the same gate as SSL |

## 6. V2 incremental candidates (new evidence, this program)

Both physics-motivated candidates were built and evaluated under the exact frozen protocol
(reconciliation 0.9357 ± 0.0000):

| Candidate | Standalone | Fixed-subset Δ | Expanded nested pool | Verdict |
|---|---|---|---|---|
| cold_dip_delta90 | 0.739 raw / 0.648 LOO | **+0.0000** | selected 22/34 folds but displaces dip_depth | **HOLD** — r = 0.923 with `dip_depth_last90_delta`: a restricted-subset duplicate |
| rpm_rise_lag_delta90 (built from raw, 27 VINs, 51.6 s) | 0.722, MW p=0.054 | **+0.0000** | selected 10/34 folds | **HOLD** — real but non-additive |
| Both jointly | — | +0.0036 | **nested 0.8750 (−0.057 vs 0.9321)** | Pool expansion actively harms nested selection |

The expanded-pool regression is itself a finding: under honest in-fold selection, adding redundant
candidates costs real AUROC. The 10-feature pool + 4-feature modal subset is selection-complete.

## 7. Verdict

**V1.1 chose correctly.** RidgeClassifier(α=1.0) on 4 audited features is the measured optimum at
n=34/14 events across every feasible class; every requested alternative is either measured-worse,
arithmetically unfittable, or inherited-closed. The model is not the bottleneck — events and
instrumentation are. V2 therefore freezes the classifier, ships the decision/heuristic layers
(D4/D6/D7), and gates all deep/survival research behind the explicit data conditions in D8. The
honest expected discrimination improvement from any modeling change today: **+0.00 AUROC**.
