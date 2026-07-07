# Daimler_Starter-motor — V1.1 (audited nested redesign)

**V1.1 SM** — the honestly-restated, fully-nested champion of the starter-motor program
(nested AUROC **0.9321** / modal-subset LOVO **0.9357**, 34 trucks: 14 failed / 20 non-failed).

- Deliverable: `V1.1_SM/`
- Full program comparison: `VERSION_COMPARISON_SM.md`

## Loadable model artifact (deployable)

The frozen V1.1 champion classifier is packaged as a load-and-predict joblib bundle:

- **Bundle:** `V1.1_SM/models/V1_1_ridge_champion/V1_1_SM_champion_bundle.joblib`
- **Loader / CLI:** `V1.1_SM/models/V1_1_ridge_champion/V1_1_SM_predict.py`
- **Provenance + verification + manifest:** alongside the bundle in the same folder
- **Build / verify scripts:** `V1.1_SM/src/V1_1_SM_package_model.py` · `..._iteration_comparison.py` · `..._bundle_smoketest.py`

Model: modal 4-feature subset of the nested-LOVO `RidgeClassifier(alpha=1.0)` + Platt calibrator,
**nested AUROC 0.9321 / modal-subset LOVO 0.9357**; alert tiers on the recalibrated prob
GREEN < 0.35 ≤ AMBER < 0.55 ≤ RED; auxiliary binary Youden threshold 0.405 (OOF).

```bash
py -3 V1.1_SM/models/V1_1_ridge_champion/V1_1_SM_predict.py \
      V1.1_SM/models/V1_1_ridge_champion/V1_1_SM_training_matrix.csv
```

### Horizon + window rules (RUL replacement — rule-based, not a model)

Per-truck day-precision RUL is mathematically closed at n=34, so SM ships a deterministic detection-horizon +
alert wrapper (`is_ml_model=False`) in `V1.1_SM/models/horizon_window_rules/`:

- **Bundle:** `V1_1_SM_horizon_window_bundle.joblib` — k*=10-week window, AUROC(k) decay table, 3 alert channels + validated 34-truck policy
- **Loader / CLI:** `V1_1_SM_predict.py` — `maintenance_window(tier)`, `horizon_auroc(k)`, `channel_lead_summary()`

Classifier RED → schedule within the **k*=10-week (~70-day)** window (AUROC 0.9357 at k=0). Validated first-fire leads across **13/14** failed trucks: median **168 d** (min 28, max 392); 1 silent failure. Historical validation, not guarantees.