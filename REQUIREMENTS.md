# Requirements — Daimler / BharatBenz Starter Motor RUL & Risk

Functional, data, technical, and acceptance requirements for the starter-motor predictive-maintenance
project. Applies to all three versions (`V1_SM/`, `V1.1_SM/`, `V2_SM/`). See [`README.md`](./README.md)
for navigation and [`VERSION_COMPARISON_SM.md`](./VERSION_COMPARISON_SM.md) for what differs between versions.

---

## 1. Problem statement

Predict and prioritise starter-motor maintenance for a fleet of BharatBenz 5528T heavy-duty trucks from
on-board CAN-bus telemetry, so a service operation can (a) rank trucks by failure risk, (b) get the
earliest honest warning the data supports, and (c) act on it cost-effectively — **without promising a
per-truck failure date the data cannot support**.

---

## 2. Functional requirements

| # | Requirement | Delivered as | Status |
|---|---|---|---|
| FR-1 | Separate failed vs healthy starter motors (**WHICH**) | RidgeClassifier, 4 features, nested 34-fold LOVO **AUROC 0.9321** | ✅ V1.1 (V1 0.921→restated 0.893) |
| FR-2 | Ship **calibrated** risk probabilities, not just ranks | Platt recalibration inside each fold → slope 0.86 / Brier 0.124 | ✅ V1.1 |
| FR-3 | Provide a measured **detection horizon** | Prequential validation → **k\* = 10 weeks** (~70 d) | ✅ V1.1, ✅ V2 (triple-confirmed) |
| FR-4 | Emit **validated lead-time alerts** with controlled false alarms | A2 battery-cascade (0/20 NF, ~66 d) + **H2 dwell pager (10/14 @ 0.19 NF ep/truck-yr)** | ✅ V1.1 channels, ✅ V2 deployable pager |
| FR-5 | Provide an honest **maintenance window**, not a date | Evidence-conditional **window matrix** + 95% CI + n-per-state | ✅ V2 (replaces RUL) |
| FR-6 | Model the **economics** of the operating point | Youden-queue policy saves ~43% vs run-to-failure (break-even cost ratio R≈30.7) | ✅ V2 |
| FR-7 | Ship a deployable **production system** | `V2_SM/v2_system/`: pipeline, monitors, registry, refit gates, shadow quarter, ops runbooks | ✅ V2 |
| FR-8 | Be reproducible and **honestly self-audited** | nested-CV protocol; V1's optimism (+0.0285) and a `1/n_weeks` artifact feature were caught and removed | ✅ V1.1 audit |

**Explicit non-goal (out of scope):** day-precision per-truck RUL. Hazard-model RUL MAE is 576 d vs a
constant-prediction baseline of 44 d — mathematically closed at n=34. RUL is shipped as an
evidence-conditional window, never a countdown.

---

## 3. Data requirements

- **Source:** ~204 M rows / ~14.5 GB of CAN telemetry (**not** stored in this repo, `.gitignore`d).
  Downstream stages consume committed per-VIN weekly/daily caches under `*/cache/`, so reports and
  figures reproduce offline.
- **SM fleet:** **34 trucks = 14 failed (`_F_SM`) + 20 non-failed (`_NF_SM`).** All labels carry `_SM`.
- **VIN independence (hard rule):** starter-motor and alternator VINs are **different physical trucks**
  reusing the same numbering. `VIN1_SM ≠ VIN1_ALT`. **No cross-dataset VIN-level analysis is valid.**
- **Key signals:** `VSI` supply voltage (0–36 V), `SMA` starter-motor active {0,1}, `RPM` engine speed,
  `CSP` vehicle speed; crank events derived from SMA/RPM/VSI transitions.

---

## 4. Technical / runtime requirements

- **Python** 3.11+.
- **Libraries:** `numpy`, `pandas`, `scipy`, `scikit-learn` (RidgeClassifier), `matplotlib`,
  `lifelines` (survival); `openpyxl` (xlsx), `python-pptx` (decks).
  ```bash
  pip install numpy pandas scipy scikit-learn matplotlib lifelines openpyxl python-pptx
  ```
- **Run:** execute each version's stage scripts in dependency order (see README §3); V2 deploys via
  `V2_SM/v2_system/V2_weekly_pipeline.py` and `deployment_kit/DEPLOYMENT_RUNBOOK.md`.

---

## 5. Constraints & honest-assessment principles

- **No over-promising.** Every published number is backed by a shipped report; conservative verdicts
  are preferred over flattering ones the sample size cannot support.
- **Nested validation is mandatory.** Screening, subset search, threshold, and calibration are redone
  inside every LOVO fold — this is what restated V1's 0.921 to 0.893.
- **Artifact discipline.** Features whose signal is an artifact of observation length (e.g. the banned
  `vsi_dominant_freq` ≈ `1/n_weeks`) are removed.
- **Detect-vs-decide.** Once the model is at its ceiling, value comes from the decision layer (alerts,
  economics, governance), not from chasing AUROC.

---

## 6. Acceptance criteria

- FR-1 reproduces **nested AUROC 0.9321**.
- FR-3 reproduces the **10-week** horizon (prequential AUROC ≥ 0.75 to k=10, chance by k=11).
- FR-4 alerts keep non-failed false alarms controlled (A2 **0/20**; H2 **0.19 ep/truck-yr**).
- FR-6 Youden-queue beats run-to-failure (~43% saving) and the FP-averse RED-only policy (34%).
- FR-7 the V2 pipeline + governance + shadow-quarter sim run green end-to-end from the committed cache.
