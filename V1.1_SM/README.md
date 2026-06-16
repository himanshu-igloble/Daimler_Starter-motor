# Starter Motor V1.1 — Deliverables Index

Program executed 2026-06-10. Seven deliverables, mapped to files:

| # | Deliverable | Location |
|---|-------------|----------|
| 1 | V1 Technical Audit Report | `audit/A_data_quality_audit.md` (data/signal integrity), `audit/B_feature_audit.md` (features), `audit/C_model_audit.md` (model/validation — incl. the nested-LOVO restatement of V1 to AUROC 0.893) |
| 2 | Failure Physics Research Report | `audit/D_failure_physics.md` (17 sources; per-mode observability at 5 s sampling) |
| 3 | Hidden Pattern Discovery Report | `discovery/E_pattern_discovery.md` (clustering, 4 failure archetypes, seasonality), `discovery/F_survival_analysis.md` (hazard/Cox/Weibull — closed negative), `discovery/G_sequence_representation.md` (deep-model math, prequential 10-week horizon) |
| 4 | V1.1 Architecture Specification | `Plan/V1_1_SM_spec.md` |
| 5 | V1.1 Experimental Results | `reports/V1_1_SM_experiment_results.md` (X1 features + X2 nested model), `reports/V1_1_SM_alerts_horizon.md` (X3 alerts + X4 horizon), `reports/V1_1_SM_explanation_cards.md` + `reports/V1_1_SM_model_card.md` (X5) |
| 6 | V1 vs V1.1 Comparison Report | `reports/V1_1_SM_comparison_report.md` |
| 7 | Final Executive Recommendation | `reports/V1_1_SM_executive_recommendation.md` |

Headline: nested-LOVO AUROC **0.9321** (V1 restated honest baseline: 0.893), recall 13/14 incl. V1's miss VIN8_F_SM, calibrated probabilities, validated ~10-week detection horizon, 3 tier-gated alert channels, 34 explanation cards. Sole miss VIN9_F_SM (structurally invisible: SMA-dead + 142 d silent gap + abrupt mode).

Code: `src/` (features, nested ridge, alerts, horizon, explainability). Results: `results/`. Graph: `graphs/V1_1_SM_fleet_risk.png`. Audit/discovery probe scripts under `audit/scripts/`, `discovery/scripts/`.

## VIN display renumbering (2026-06-11)

Graphs and presentations now use **sequential fleet numbering**: failed trucks first
(VIN1_F_SM … VIN14_F_SM, unchanged), then non-failed continue the sequence
(old VIN{k}_NF_SM → new VIN{k+14}_NF_SM; e.g. old VIN1_NF → VIN15_NF, old VIN20_NF → VIN34_NF).
This removes the confusing reuse of the same numbers across cohorts (old VIN1_F and
old VIN1_NF were different physical trucks).

- **Mapping module**: `src/V1_1_SM_vin_display_map.py` (imported by all graph/deck scripts;
  mapping is applied at render time only).
- **Traceability CSV**: `results/V1_1_SM_vin_naming_map.csv` (old_label, new_label, cohort,
  raw_file_vin — 34 rows).
- **Scope**: this is a **display-only** change. All results CSVs/JSON (`results/`), reports
  (`reports/`), caches and audit artifacts **retain the original labels** — the audit trail
  references them. Each per-VIN graph carries a footer note with its raw-file label
  (e.g. "raw NF-file label: VIN1" on VIN15_NF_SM).
- **Collision warning**: new names VIN15_NF…VIN20_NF denote *different trucks* than the same
  old names (new VIN15–20_NF = raw NF-file VIN1–6). Always resolve via the mapping CSV when
  cross-referencing graphs/decks against results artifacts.
