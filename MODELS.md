# Model Registry — Daimler / BharatBenz Starter Motor

Every **deployable, verified** model artifact shipped in this repo, in one place. Each artifact is
self-contained — a `joblib` bundle + a `predict.py` loader/CLI + provenance copies + a
`verification.json` (parity gates, real numbers) + a SHA256 `MANIFEST.json`. Bundles load with only
`joblib` + `numpy` + `pandas` + `scikit-learn 1.8.x`.

> **Honest-engineering note.** The classifier AUROC is a **nested LOVO** estimate at n=34 (not field
> accuracy). Per-truck day-precision RUL is **mathematically closed** at this sample size, so instead of a
> countdown the repo ships a **validated detection window + alert channels** (a deterministic rule set,
> explicitly *not* an ML model). Every artifact folder carries its own README with the full caveats.

## Deployable models

| # | Model | Answers | Type | Path | Headline |
|---|---|---|---|---|---|
| 1 | **Failure classifier** (frozen champion) | WHICH trucks are at risk | modal 4-feature nested-ridge `Pipeline` (impute→scale→ridge) + Platt calibrator | [`V1.1_SM/models/V1_1_ridge_champion/`](./V1.1_SM/models/V1_1_ridge_champion) | nested **AUROC 0.9321** / modal-subset LOVO 0.9357; recall 13/14 |
| 2 | **Horizon + window rules** (RUL replacement) | WHEN to act | deterministic rules (`is_ml_model=False`) | [`V1.1_SM/models/horizon_window_rules/`](./V1.1_SM/models/horizon_window_rules) | **k\*=10-week** window; validated leads median **168 d** (13/14) |

## Quick start

```bash
# 1. Failure classifier — score a feature CSV (bundle imputes NaNs with training medians)
py -3 V1.1_SM/models/V1_1_ridge_champion/V1_1_SM_predict.py \
      V1.1_SM/models/V1_1_ridge_champion/V1_1_SM_training_matrix.csv

# 2. Horizon + window rules — maintenance window + validated alert leads
py -3 V1.1_SM/models/horizon_window_rules/V1_1_SM_predict.py
```

## What is (and isn't) inside a bundle

- **Inside** the classifier bundle: the fitted `SimpleImputer` (medians), `StandardScaler` (mean/scale),
  and `RidgeClassifier` (coefficients) — all in one `Pipeline` — **plus** a `LogisticRegression` Platt
  calibrator (fit on the modal-subset LOVO out-of-fold decision values), the exact feature-column list,
  tier bands, an auxiliary Youden threshold, frozen metrics, and the build environment. Tiers are applied
  to the **recalibrated** probability.
- **Not inside**: the **feature engineering** that turns raw CAN telemetry into the model's input columns
  (that lives in `V1.1_SM/src/`). The provenance `*_training_matrix.csv` documents the exact input schema.
- The **horizon/window** artifact is a *rule* wrapper, not a fitted model: it encodes the frozen 10-week
  detection horizon, the AUROC-by-week decay table, and the three validated alert channels.

## Provenance & verification

Each folder's `MANIFEST.json` records a SHA256 for every file and input; `verification.json` records the
packaging parity gates (classifier: closed-form vs sklearn < 1e-8, modal-subset LOVO AUROC 0.935714;
rules: AUROC(k=0)=0.9357, k\*=10 reconciled against the frozen horizon/alert CSVs). Rebuild scripts live in
`V1.1_SM/src/` (`V1_1_SM_package_model.py`, `V1_1_SM_package_rules.py`, and their smoke tests).
