# SM Frozen Champion — V1.1 Ridge — Deployable Artifact

Loadable packaging of the frozen starter-motor champion: modal winner of the
V1.1 nested-LOVO RidgeClassifier protocol (4 features, alpha=1.0), on 34 trucks
(14 failed / 20 non-failed). Nested AUROC **0.9321** (validation estimate);
this packaged modal-subset model scores LOVO AUROC **0.9357** (non-nested).
Tiers on **recalibrated** prob: GREEN < 0.35 ≤ AMBER < 0.55 ≤ RED.

**Version lineage:** V1.1 (2026-06-10) is the champion iteration. Its ceiling was
re-confirmed by V2.1, V3 and V3.1 — each re-derived exactly 0.9357 and accepted
no candidate (see `SM_last5_iteration_comparison.md` in this folder).

## Files
| File | What it is |
|---|---|
| `V1_1_SM_champion_bundle.joblib` | dict: fitted sklearn Pipeline (fit on all 34 trucks) + Platt calibrator (fit on modal-subset LOVO OOF decision values) + tier bands + auxiliary OOF-Youden threshold + metadata. No custom classes. |
| `V1_1_SM_predict.py` | loader + CLI (`py -3 V1_1_SM_predict.py <features_csv>`) |
| `V1_1_SM_training_matrix.csv` | provenance copy of the 34-truck feature matrix |
| `V1_1_SM_model_spec.json` | provenance copy of the frozen nested-protocol spec |
| `V1_1_SM_nested_lovo_predictions.csv` | provenance copy of archived nested OOF predictions |
| `SM_last5_iteration_comparison.csv` / `.md` | evidence table: why V1.1 is the champion |
| `V1_1_SM_verification.json` | parity-gate results from packaging (P1–P4) |
| `V1_1_SM_MANIFEST.json` | SHA256 of every file + inputs + env + git commit |

## Quick start
```
py -3 V1_1_SM_predict.py V1_1_SM_training_matrix.csv
```

## Honesty notes
- 0.9321 is the **nested** cross-validation estimate in which each fold picked its
  own subset/threshold/calibrator. A deployable model must be ONE model, so this
  artifact ships the modal winner subset with a pooled-OOF Platt calibrator.
  Its resubstitution outputs on the 34 training trucks will NOT reproduce the
  archived nested OOF probabilities — expected, not a bug.
- Tier bands 0.35/0.55 are frozen from the spec. The binary `predicted_class`
  uses an auxiliary Youden threshold derived from OOF probs (see
  `V1_1_SM_verification.json`); the tier is the primary decision output.
- The Platt calibrator and auxiliary Youden threshold were fit on the
  modal-subset **LOVO out-of-fold** decision values, but at inference they are
  applied to the **production (all-34) model's** decision output — a mild
  train/inference scale approximation (the honest trade; calibrating on
  resubstitution scores would be leaky). Tier remains the primary decision output.
- Loading under a different sklearn minor version may emit
  `InconsistentVersionWarning`; re-run the packaging script to rebuild in-place.
- Rebuild + re-verify: `py -3 "STARTER MOTOR/V1.1/src/V1_1_SM_package_model.py"`,
  then `py -3 "STARTER MOTOR/V1.1/src/V1_1_SM_bundle_smoketest.py"`.
