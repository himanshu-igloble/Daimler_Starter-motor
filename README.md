# Daimler / BharatBenz Starter Motor — RUL & Risk Prediction

**Branches:**
[![main](https://img.shields.io/badge/main-all_6_versions-2ea44f?logo=github)](https://github.com/himanshu-igloble/Daimler_Starter-motor/tree/main)
[![v1-sm](https://img.shields.io/badge/v1--sm-baseline-1f6feb?logo=github)](https://github.com/himanshu-igloble/Daimler_Starter-motor/tree/v1-sm)
[![v1.1-sm](https://img.shields.io/badge/v1.1--sm-audited_redesign-1f6feb?logo=github)](https://github.com/himanshu-igloble/Daimler_Starter-motor/tree/v1.1-sm)
[![v2-sm](https://img.shields.io/badge/v2--sm-decision_layer-1f6feb?logo=github)](https://github.com/himanshu-igloble/Daimler_Starter-motor/tree/v2-sm)
[![v2.1-sm](https://img.shields.io/badge/v2.1--sm-improvement_hunt-8250df?logo=github)](https://github.com/himanshu-igloble/Daimler_Starter-motor/tree/v2.1-sm)
[![v3-sm](https://img.shields.io/badge/v3--sm-interaction_closure-8250df?logo=github)](https://github.com/himanshu-igloble/Daimler_Starter-motor/tree/v3-sm)
[![v3.1-sm](https://img.shields.io/badge/v3.1--sm-state_engine-8250df?logo=github)](https://github.com/himanshu-igloble/Daimler_Starter-motor/tree/v3.1-sm)

Predictive-maintenance pipeline for the **starter motor** of the BharatBenz 5528T heavy-duty truck.
From on-board CAN-bus telemetry it answers: **which** trucks are at risk, **how early** a failure can be
detected, and **what to do** about it operationally.

## ▶ Start here — **V2** is the current, deployable version

[![recommended](https://img.shields.io/badge/recommended-v2--sm-2ea44f?logo=github)](https://github.com/himanshu-igloble/Daimler_Starter-motor/tree/v2-sm)

The model is **frozen at its ceiling** (nested AUROC **0.9321**, **10-week** horizon); **V2 turns that
into operations** — this is what to deploy:

- **H2 dwell pager** — catches **10/14** failures at **0.19 false episodes/truck-year** (median **116-day** lead).
- **Youden-queue policy** — saves **~43%** vs run-to-failure (beats the FP-averse RED-only policy).
- **Window matrix** — evidence-conditional maintenance windows (+95% CI) instead of fake day-precision RUL.
- **Production system** (`V2_SM/v2_system/`) — weekly pipeline, monitors, registry, refit gates, a
  prospective shadow quarter, and ops runbooks; plus 10 deliverable docs in `V2_SM/deliverables/`.

📂 Branch [`v2-sm`](https://github.com/himanshu-igloble/Daimler_Starter-motor/tree/v2-sm) · folder `V2_SM/` ·
start reading `V2_SM/deliverables/…-d10-executive-recommendation.md`.
**V1 → V1.1 below are the lineage** that established and honestly validated the model.

> **Honest-engineering project.** Every metric here is backed by a shipped report (no numbers from
> memory). The standing finding is conservative: the classifier is strong (**nested AUROC ≈ 0.932**)
> and gives a validated **10-week** warning, but ~4 of 14 failures are structurally invisible and
> day-precision RUL is mathematically closed at this sample size — so we ship **risk tiers + validated
> alerts + evidence-conditional windows**, not a per-truck countdown.

> **Validated & frozen (V2.1 · V3 · V3.1).** Three pre-registered improvement hunts stress-tested the
> frozen model — **17 candidate features/rules in total, all REJECT**; the baseline reproduced to the
> 4th decimal every time (**0.9357 non-nested / 0.9321 nested**). They confirm the ceiling is a *data*
> limit, not a method limit, and each shipped a durable operational asset: **V2.1** — a recall-lever
> pager (A3: non-failed false alarms **20/20 → 7/20** at held recall 13/14) plus A5 graded maintenance
> windows; **V3** — the interaction/usage-feature closure (GBM probe **0.843 < 0.932** = data-not-method);
> **V3.1** — an operational-state engine (all SV gates pass), battery-vs-starter triage (**9/11**
> archetype convergence, **0/20** false attributions on healthy trucks), maintenance-window validation
> (**9/11** failures inside the predicted window), and the DICV management validation dossier under
> `V1.1_SM/reports/`. Full detail in [`VERSION_COMPARISON_SM.md`](./VERSION_COMPARISON_SM.md).

---

## 1. Repository & branch map

Each version lives on its own branch (so you can roll back to any version at any time); `main` carries
**all six** versions merged together. V1 → V2 are the delivery lineage; V2.1 / V3 / V3.1 are frozen,
pre-registered validation hunts that re-confirmed the ceiling.

| Branch | What's on it | Use it to… |
|---|---|---|
| **`main`** | All six versions (`V1_SM/` + `V1.1_SM/` + `V2_SM/` + `V2_1_SM/` + `V3_SM/` + `V3_1_SM/`) + this README + requirements + comparison | Browse everything in one place |
| **`v1-sm`** | **Only** the V1 deliverable (baseline classifier) | Check out / roll back to V1 in isolation |
| **`v1.1-sm`** | **Only** the V1.1 deliverable (audited nested redesign) | Check out / roll back to V1.1 in isolation |
| **`v2-sm`** | **Only** the V2 deliverable (decision layer + deployment system) | Check out / roll back to V2 in isolation |
| **`v2.1-sm`** | **Only** the V2.1 hunt (richer heuristics/features; A3 recall lever + A5 windows) | Check out / roll back to V2.1 in isolation |
| **`v3-sm`** | **Only** the V3 hunt (interaction/usage feature closure) | Check out / roll back to V3 in isolation |
| **`v3.1-sm`** | **Only** the V3.1 hunt (state engine + triage + window validation) | Check out / roll back to V3.1 in isolation |

```bash
git clone https://github.com/himanshu-igloble/Daimler_Starter-motor
cd Daimler_Starter-motor
git switch v1-sm     # see ONLY V1
git switch v1.1-sm   # see ONLY V1.1
git switch v2-sm     # see ONLY V2  (deployable)
git switch v2.1-sm   # see ONLY V2.1 validation hunt
git switch v3-sm     # see ONLY V3  validation hunt
git switch v3.1-sm   # see ONLY V3.1 validation hunt
git switch main      # see ALL SIX
```

---

## 2. Version comparison

The model is **frozen from V1.1 onward** (nested AUROC 0.9321, 10-week horizon); the differences are in
honesty/calibration (V1 → V1.1) and in the operational decision layer (V1.1 → V2). V2.1 / V3 / V3.1 are
three pre-registered hunts that tried and failed to beat it (17 candidates, all REJECT) — see
[`VERSION_COMPARISON_SM.md`](./VERSION_COMPARISON_SM.md) for their full head-to-head.

| Dimension | **V1** — Baseline | **V1.1** — Audited Redesign | **V2** — Decision Layer |
|---|---|---|---|
| Branch | [`v1-sm`](https://github.com/himanshu-igloble/Daimler_Starter-motor/tree/v1-sm) | [`v1.1-sm`](https://github.com/himanshu-igloble/Daimler_Starter-motor/tree/v1.1-sm) | [`v2-sm`](https://github.com/himanshu-igloble/Daimler_Starter-motor/tree/v2-sm) |
| Question | classifier + lead-time channel? | was 0.921 honest? add calibration, alerts, horizon | detect earlier, cut FPs, ship ops — find the ceiling |
| Classifier AUROC | **0.9214** (non-nested) → restated **0.893** | **0.9321** nested (CI [0.811, 0.986]) | **0.9321 — unchanged** (ceiling) |
| Validation | 34-fold LOVO, non-nested | **fully nested** 34-fold LOVO | re-audited, pool selection-complete |
| Calibration | slope 4.72 — not shippable | **slope 0.86 / Brier 0.124 — shippable** | unchanged |
| Detection horizon | not measured | **k\* = 10 weeks** validated | 10 weeks — triple-confirmed |
| Lead-time / pager | **none** (90% NF false-positive) | 3 validated channels; A2 **0/20 NF**, ~66 d lead | **H2 dwell pager: 10/14 @ 0.19 NF ep/truck-yr** |
| RUL | risk bands only | risk bands + ~10-wk window | **window matrix** (+ 95% CI) replaces RUL |
| Economics | not modeled | tiers by Youden (FP-averse) | **Youden-queue saves ~43%** vs run-to-failure |
| Verdict | classifier works, lead-time doesn't | the honest ceiling: 0.932 + 10-wk warning | model finished; the win is the **decision layer** |

**Full head-to-head (incl. V2.1 / V3 / V3.1):** [`VERSION_COMPARISON_SM.md`](./VERSION_COMPARISON_SM.md).
**Performance ceiling** (all six versions, re-confirmed four consecutive times through V3.1): nested
AUROC ≈ 0.932 · 10-week horizon · alert recall ~10–11/14 (4/14 silent/abrupt failures are structurally
invisible). Breaking it needs **new signals**, not new models.

---

## 3. How to navigate the project

| Version | Lives in | Key reports | Pipeline (run in order) |
|---|---|---|---|
| **V1** | `V1_SM/` | `reports/V1_SM_final_report.md` | `src/V1_SM_build_weekly_cache → crank_events → features → feature_selection → ridge_classifier → lead_time → final_report → production_graphs` |
| **V1.1** | `V1.1_SM/` | `reports/V1_1_SM_RESULTS_MASTER.md`, `Plan/V1_1_SM_spec.md` | `src/V1_1_SM_build_daily_cache → features → nested_ridge → horizon → alerts → explainability → daily_risk_graphs` |
| **V2** | `V2_SM/` | `deliverables/…-sm-v2-d01..d10-*.md` (10 deliverables) | `v2_system/V2_weekly_pipeline.py`; deploy via `v2_system/deployment_kit/DEPLOYMENT_RUNBOOK.md` |
| **V2.1** | `V2_1_SM/` | `reports/V2_1_SM_exec_summary.md`, `_verdict.md` | `params/` gate → `features/` → `heuristics/` → `reports/build_comparison.py` |
| **V3** | `V3_SM/` | `reports/V3_SM_exec_summary.md`, `_verdict.md` | `params/` gate → `features/` (incl. `out/`, `tests/`) → `analysis/` → `reports/` |
| **V3.1** | `V3_1_SM/` | `reports/V3_1_SM_exec_summary.md`, `_verdict.md`, `_state_engine_report.md` | `params/` → `state/` engine (→ `state/out/`) → `features/` → `heuristics/` (T1/T2/T3) → `analysis/` → `reports/` |

Each version dir also has `cache/` or `state/out/` (committed intermediates — pipelines reproduce
**without** the raw data), `results/`/`analysis/out/` (machine-readable CSV/JSON),
`graphs/`/`visualizations`, and `presentation/` (decks). V2 additionally ships a full `v2_system/`
(monitors, registry, refit gates, shadow-quarter sim, ops runbooks). V2.1 / V3 / V3.1 each carry a
pre-registered `Plan/…_spec.md` and a one-verdict `reports/…_verdict.md`.

**Where to start:** `V2_SM/deliverables/…-d10-executive-recommendation.md` (the final word) →
`VERSION_COMPARISON_SM.md` (what changed) → each version's report above.

---

## 4. Requirements & how to run

- **Python 3.11+** with `numpy`, `pandas`, `scipy`, `scikit-learn` (RidgeClassifier), `matplotlib`,
  `lifelines` (survival), `openpyxl` (xlsx), `python-pptx` (decks).
  ```bash
  pip install numpy pandas scipy scikit-learn matplotlib lifelines openpyxl python-pptx
  ```
- Run a version by executing its stage scripts in the order in the table above (each reads the previous
  stage's cache). The committed `*/cache/` lets reports and figures reproduce **without** the raw data.

See [`REQUIREMENTS.md`](./REQUIREMENTS.md) for the full functional + data + technical requirements.

---

## 5. Data & domain notes (read before interpreting results)

- **Raw data is NOT in this repo.** The source is ~204 M rows / ~14.5 GB of CAN telemetry (`.gitignore`d).
  The committed per-VIN weekly/daily caches under `*/cache/` are what the downstream stages consume.
- **SM fleet = 34 trucks** (14 failed `_F_SM` + 20 non-failed `_NF_SM`). All labels carry an `_SM` suffix.
- **VIN independence (hard rule):** starter-motor and alternator VINs are **different physical trucks**
  that reuse the same numbering. `VIN1_SM ≠ VIN1_ALT`. **No cross-dataset VIN-level analysis is valid.**
- **Key CAN signals:** `VSI` supply voltage (0–36 V), `SMA` starter-motor active {0,1}, `RPM` engine
  speed, `CSP` vehicle speed; crank events are derived from SMA/RPM/VSI transitions.

---

## 6. Bottom line

The starter-motor classifier is **finished** at nested **AUROC 0.9321** with a validated **10-week**
detection horizon — confirmed three times over. **V1** established the baseline (and exposed that its
own headline was optimistic). **V1.1** restated it honestly (0.893), beat it cleanly (0.9321), and added
calibration + validated alerts + the horizon. **V2** built the **decision layer**: a deployable dwell
pager (0.19 false episodes/truck-year), a cost-optimal **Youden-queue** policy (~43% saving), honest
evidence-conditional windows instead of RUL, and a production system with governance and a shadow
quarter. The next gain requires **new sensors**, not new models. Ship **tiers + alerts + windows**.

---

## 7. Loadable model artifact (deployable)

The frozen V1.1 champion classifier is packaged as a **load-and-predict** joblib bundle — no re-fit needed.

**Path (this branch):** [`V1.1_SM/models/V1_1_ridge_champion/`](./V1.1_SM/models/V1_1_ridge_champion)

| File | What it is |
|---|---|
| [`V1_1_SM_champion_bundle.joblib`](./V1.1_SM/models/V1_1_ridge_champion/V1_1_SM_champion_bundle.joblib) | fitted sklearn `Pipeline` (median-impute → `StandardScaler` → `RidgeClassifier(α=1.0)`, fit on all 34 trucks) + **Platt calibrator** (`LogisticRegression`, fit on modal-subset LOVO out-of-fold decision values) + tier bands + auxiliary Youden threshold + metadata. Plain dict of standard sklearn objects. |
| [`V1_1_SM_predict.py`](./V1.1_SM/models/V1_1_ridge_champion/V1_1_SM_predict.py) | loader + CLI — `py -3 V1_1_SM_predict.py <features_csv>` |
| `V1_1_SM_training_matrix.csv` | provenance: the 34-truck feature matrix |
| `V1_1_SM_model_spec.json` | provenance: the frozen nested-protocol spec |
| `V1_1_SM_nested_lovo_predictions.csv` | provenance: archived nested OOF predictions |
| `V1_1_SM_verification.json` | packaging parity gates P1–P4 (real numbers) |
| `V1_1_SM_MANIFEST.json` | SHA256 of every file + inputs + build env |
| `README.md` | artifact usage + honesty notes |

**Model:** modal 4-feature subset of the V1.1 nested-LOVO `RidgeClassifier(alpha=1.0)` + Platt calibrator,
**nested AUROC 0.9321 / modal-subset LOVO AUROC 0.9357** (recall 13/14); alert tiers on the *recalibrated*
prob `GREEN < 0.35 ≤ AMBER < 0.55 ≤ RED`; auxiliary binary Youden threshold 0.405 (OOF).
Build + verify scripts: [`V1.1_SM/src/V1_1_SM_package_model.py`](./V1.1_SM/src/V1_1_SM_package_model.py),
`V1_1_SM_iteration_comparison.py`, `V1_1_SM_bundle_smoketest.py`.

```bash
# score trucks from a features CSV (the bundle imputes NaNs with training medians)
py -3 V1.1_SM/models/V1_1_ridge_champion/V1_1_SM_predict.py \
      V1.1_SM/models/V1_1_ridge_champion/V1_1_SM_training_matrix.csv
```

> 0.9321 is the **nested** cross-validation estimate (each fold picked its own subset/threshold). A single
> deployable model must be one model, so the bundle ships the **modal winner subset** + a pooled-OOF Platt
> calibrator; its resubstitution scores on the 34 training trucks do not reproduce the nested OOF numbers
> (expected, documented in the artifact README). The tier is the primary decision output.

### 7b. Horizon + window rules (the RUL replacement — rule-based, not a model)

Per-truck day-precision RUL is mathematically closed at n=34, so SM ships a **deterministic** detection-horizon
+ alert-channel wrapper (`is_ml_model=False`) in
[`V1.1_SM/models/horizon_window_rules/`](./V1.1_SM/models/horizon_window_rules):

| File | What it is |
|---|---|
| [`V1_1_SM_horizon_window_bundle.joblib`](./V1.1_SM/models/horizon_window_rules/V1_1_SM_horizon_window_bundle.joblib) | frozen rules: **k\*=10-week** detection window, AUROC(k) decay table, 3 alert channels + validated 34-truck policy, validated leads |
| [`V1_1_SM_predict.py`](./V1.1_SM/models/horizon_window_rules/V1_1_SM_predict.py) | loader/CLI — `maintenance_window(tier)`, `horizon_auroc(k)`, `channel_lead_summary()` |
| provenance | `V1_1_SM_horizon_curve.csv`, `V1_1_SM_alert_policy.csv`, verification + MANIFEST |

**Rule:** classifier RED → schedule maintenance within the **k\*=10-week (~70-day)** window (AUROC 0.9357 at k=0,
in-spec through week 16). Validated first-fire leads across **13/14** failed trucks: median **168 d** (min 28, max 392);
1 silent failure. Leads are historical validation observations, not forward guarantees.
