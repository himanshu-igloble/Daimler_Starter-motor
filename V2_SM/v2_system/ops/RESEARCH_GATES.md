---
title: "SM V2 — Research Gates Register"
status: "complete"
created: "2026-06-12"
owner: "Model Owner"
version: "1.0.0"
---

# SM V2 Research Gates Register

This is the formal do-not-enter-until register for research directions that
were evaluated, found premature, and closed with explicit re-entry criteria.
Each entry states the claim, the evidence, the entry criteria, and what would
change our mind.

Opening a closed gate requires a dated protocol deviation note signed by the
model owner, stating which entry criterion has been met and citing the
supporting evidence.

---

## Gate 1: Survival / Hazard Layer for RUL or Truck-Level Ranking

**Claim that motivated the investigation:** Discrete-time hazard or Cox
regression on truck-week telemetry could provide (a) a meaningful RUL estimate
or (b) a truck-level risk ranker superior to the static Ridge classifier.

**Evidence (closed):**

| Metric | Hazard model | Baseline | Verdict |
|---|---|---|---|
| Median RUL MAE | 576 days | Constant predictor 44 days; Weibull fleet clock 462 days | Demolished by constant |
| Truck-level ranking AUROC | 0.586 | Static Ridge 0.893 (V1.1 nested LOVO) | 34% relative shortfall |
| Weekly P(fail≤30d) AUROC | 0.744 (0.849 under JCOPENDATE) | — | Marginal; driven by vsi_std_ratio already in V2 feature pool |

Source files:
- `STARTER MOTOR/V1.1/discovery/F_survival_analysis.md` (verdict section)
- `STARTER MOTOR/V1.1/discovery/out/F_fleetclock_horizon_eval.csv` (RUL MAE table)
- `STARTER MOTOR/V1.1/discovery/out/F_hazard_lovo_preds.parquet` (fold-level ranker AUROCs)
- `STARTER MOTOR/V1.1/discovery/out/F_truck_week.parquet` (2,636 truck-weeks × 34 trucks)

Additional context: saledate is available only for failed VINs (NF all NaN in
`STARTER MOTOR/results/V1_SM_data_quality.csv`), so age-since-sale is not a
valid covariate for the full fleet. EPV budget at 14 events supports ≈3–4
parameters; 3 covariates were used and the model still failed to beat the constant.

**Re-entry criteria (ALL must be met):**
1. n_failed ≥ 30–50 with confirmed failure dates (not just JCOPENDATE lag).
2. At least one new predictive channel (signal not in the current 4-feature VSI pool)
   that shows truck-level AUROC improvement over the static model in prospective
   data (not retrospective).
3. A clean prospective shadow quarter with ≥5 confirmed failure labels in the
   label registry providing a calibration slope estimate.

**What would change our mind:** A new sensor (e.g., crank current magnitude or
AC ripple on the DC bus) that provides earlier failure signal, combined with a
larger prospective failure cohort. The VSI-based features are already in V2; the
hazard model needs something beyond what V2 already captures.

---

## Gate 2: SSL Crank-Encoder Pretraining

**Claim that motivated the investigation:** Self-supervised pretraining on the
106M unlabelled crank-event rows in `STARTER MOTOR/cache/events/` could learn
useful representations that reduce the label requirement.

**Evidence (closed):**

- The raw SM crank event dataset contains ~106M rows (source: Agent G, Section 1,
  `STARTER MOTOR/V1.1/discovery/G_sequence_representation.md`).
- EPV budget at 14 failed trucks: 1.4 parameters. Even after pretraining, the
  fine-tuning head must be evaluated on 34 labelled sequences. The downstream
  classifier is still constrained to the same EPV budget as all other methods.
- SSL pretraining does not add failure labels. The representations must still be
  validated by LOVO on 34 trucks. An SSL encoder adds parameter overhead to the
  evaluation head without resolving the fundamental label shortage.
- The 2-coefficient trend summary (linear slope + intercept on weekly vsi_std_ratio)
  matches but does not beat the V1 AUROC 0.893 baseline (`G_sequence_representation.md`
  Section 2b) — establishing that the sequence structure is fully captured by
  engineered features at this n.

Source files:
- `STARTER MOTOR/V1.1/discovery/G_sequence_representation.md` (§1 EPV budget, §2b trend result)
- `STARTER MOTOR/V1.1/discovery/out/G1_param_budget.csv` (parameter counts per architecture)

**Re-entry criteria (ALL must be met):** Same as Gate 1 (n_failed ≥ 30–50; new
channel; clean prospective quarter). Additionally: a published evaluation
protocol for SSL pretraining + fine-tuning on fleets of this size that has been
validated on an external dataset.

**What would change our mind:** Evidence that SSL pretraining on crank events
from a different (larger) fleet transfers meaningfully to the SM fleet — i.e.,
cross-fleet transfer learning that bypasses the local label shortage. This would
require access to a third-party fleet with ≥50 confirmed starter failures and
compatible telemetry.

---

## Gate 3: Deep Tabular and Sequence Models (LSTM, TCN, Transformer, TFT, PatchTST, TimeXer)

**Claim that motivated the investigation:** Modern deep learning on tabular or
sequential data might extract patterns that Ridge regression misses.

**Evidence (closed):**

EPV (events-per-variable) budget: 14 failed trucks → ≈1.4 parameters at EPV=10
(Peduzzi et al. 1996), ≈0.7 at EPV=20 (Riley et al. BMJ 2020). The table below
shows the overrun for the smallest feasible configuration of each architecture:

| Architecture | Min params | Overrun vs EPV-10 |
|---|---|---|
| LSTM h=8 | 329 | 235x |
| BiLSTM h=8 | 657 | 469x |
| TCN (2 blocks, 8 ch, k=3) | 489 | 349x |
| Transformer (1 layer, d=16) | 2,273 | 1,624x |
| TFT (minimal d=16) | 8,785 | 6,275x |
| V1 Ridge (4 features) | 5 | 4x (within budget) |

Empirical confirmation: a 43-parameter LSTM (h=2, minimal config) showed
seed-unstable results — spread of 0.064 AUROC across seeds with no mean
improvement over the 0.893 baseline. Seed spread of 0.064 is larger than the
optimism delta (0.0036) of the current V1.1 model.

Source files:
- `STARTER MOTOR/V1.1/discovery/G_sequence_representation.md` (§1 EPV budget table, §2e seed instability)
- `STARTER MOTOR/V1.1/discovery/out/G1_param_budget.csv`
- `STARTER MOTOR/V1.1/discovery/out/G2_probe_results.csv` (h=2 LSTM seed spread)

**Re-entry criteria:** Same as Gate 1. Additionally: EPV ≥ 10 for the minimum
feasible architecture of the proposed model (i.e., n_failed ≥ 32.9 × min_params / 10).
For a minimal LSTM (329 params), this requires n_failed ≥ 330 — substantially
beyond the current fleet.

**What would change our mind:** A fundamental reduction in the minimum viable
parameter count for sequential models on this type of data, or a much larger
fleet. Neither is plausible within the current project scope.

---

## Gate 4: Unsupervised Anomaly Detection

**Claim that motivated the investigation:** Unsupervised methods (isolation
forest, autoencoder, OCSVM, LOF) might detect starter-motor failures without
requiring labels.

**Evidence (closed):**

All unsupervised methods evaluated on the SM fleet (n=34) produced false-positive
rates of 80–100% on non-failed trucks. This finding mirrors the alternator
analysis result documented in project memory (feedback_anomaly_detection_fails_small_n.md).
The fundamental issue is that at n=34 with only 4 VSI-based signal dimensions,
there is no reliable boundary between "unusual NF behaviour" and "pre-failure
degradation" that an unsupervised method can learn without labels. NF trucks
naturally spread across the feature space, and the anomaly scores pick up
NF outliers as frequently as they pick up failed trucks.

Source files:
- Project memory: `feedback_anomaly_detection_fails_small_n.md` (SM + ALT evidence)
- `STARTER MOTOR/V1.1/discovery/E_pattern_discovery.md` (§1, cluster structure analysis:
  no global cluster separating failed from NF; `E1_cluster_results.csv` ARI = 0.144 for
  best-case Ward clustering, effectively chance after leakage correction)

**Re-entry criteria:**
1. n_nonfailed ≥ 100 (enough NF diversity to define a reliable "normal" envelope).
2. A new signal channel with demonstrated NF baseline stability (NF coefficient of
   variation < 0.1 in the prospective quarter) — this is the pre-condition for any
   anomaly threshold to be interpretable.
3. Prospective validation on a held-out fleet (not the SM training fleet).

**What would change our mind:** A clearly bimodal signal — one where NF trucks
cluster tightly and failed trucks are visibly separated — identified in prospective
data. The current VSI features are ratio/delta-based and deliberately normalised
for cross-truck compatibility, which also narrows the separation margin for
anomaly methods.

---

## Gate 5: Manifold Clustering for Failure Sub-Type Discovery

**Claim that motivated the investigation:** Unsupervised manifold methods (PCA
projection, hierarchical clustering, spectral clustering, DBSCAN) on the
cross-sectional feature matrix could reveal distinct failure sub-types or NF
clusters that a linear model misses.

**Evidence (closed):**

- Ward k=2/3/4: ARI vs failed = 0.144 best case. The best-case 4-cluster (isolating
  VIN2_F, VIN3_F, VIN6_F, VIN13_F) is confounded by observation-length leakage:
  KW p=0.014 vs n_weeks, p=0.0035 vs t_start ordinal. Battery-archetype
  interpretation survives on within-VIN evidence (E5 step-change analysis), but
  the clustering itself is length-contaminated.
- DBSCAN: degenerate at all eps (one blob + noise). NF ARI ≤ 0.20.
- Spectral k=2/3: ARI vs failed = −0.02/0.00. No alignment with failed, config
  cohort, or leakage axes (KW p = 0.24–0.31).
- PCA: no dominant axis (PC1 28.8%, PC2 21.5%; 4 PCs explain 64.6% — diffuse).
  Max |r| with failed = 0.21 (PC1). PC4 tracks telematics config (SMA-dead cohort)
  through event-rate features even after vsi_dominant_freq is banned.

The failure archetypes (A1/A2/A3/A4) in `E2_failed_vin_archetypes.csv` are
rule-based (NF-quantile threshold flags on within-VIN temporal deltas), not
cluster-discovered. They are useful for failure-mode attribution in work orders
but do not represent a latent structure that clustering can recover.

Source files:
- `STARTER MOTOR/V1.1/discovery/E_pattern_discovery.md` (§1 Ward/DBSCAN/Spectral results)
- `STARTER MOTOR/V1.1/discovery/out/E1_cluster_results.csv`
- `STARTER MOTOR/V1.1/discovery/out/E1_cluster_membership.csv`
- `STARTER MOTOR/V1.1/discovery/out/E2_failed_vin_archetypes.csv`

**Re-entry criteria:**
1. n_total ≥ 100 with at least 30 failed trucks (current 34/14 produces ARI ≈ chance
   after leakage correction).
2. New features with genuine cross-sectional variance not contaminated by observation
   length or telematics config cohort.
3. External validation: cluster structure must replicate on a held-out fleet.

**What would change our mind:** A stable cluster solution (ARI > 0.5 vs failed,
KW p > 0.1 vs n_weeks and t_start) on cross-sectional data from a substantially
larger fleet. The failure archetypes are mechanistically interesting but
statistically underpowered as a basis for structural modelling at current n.

---

## Cross-Reference: Gate Evidence Files

| Path | Exists? | Gate(s) |
|---|---|---|
| `STARTER MOTOR/V1.1/discovery/F_survival_analysis.md` | Verify below | 1 |
| `STARTER MOTOR/V1.1/discovery/G_sequence_representation.md` | Verify below | 2, 3 |
| `STARTER MOTOR/V1.1/discovery/E_pattern_discovery.md` | Verify below | 4, 5 |
| `STARTER MOTOR/V1.1/discovery/out/F_fleetclock_horizon_eval.csv` | Verify below | 1 |
| `STARTER MOTOR/V1.1/discovery/out/F_hazard_lovo_preds.parquet` | Verify below | 1 |
| `STARTER MOTOR/V1.1/discovery/out/G1_param_budget.csv` | Verify below | 2, 3 |
| `STARTER MOTOR/V1.1/discovery/out/E1_cluster_results.csv` | Verify below | 5 |
| `STARTER MOTOR/V1.1/discovery/out/E2_failed_vin_archetypes.csv` | Verify below | 4, 5 |
| `STARTER MOTOR/results/V1_SM_data_quality.csv` | Verify below | 1 |

---

*End of Research Gates Register. For governance questions see
ops/GOVERNANCE_CHARTER.md. For the current model specification see
v2_config.json (config_version 2.1.0-B).*
