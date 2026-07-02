# Starter Motor — Version Comparison: V1 → V1.1 → V2 → V2.1 → V3 → V3.1

> Identical on the `v1-sm`, `v1.1-sm`, `v2-sm`, `v2.1-sm`, `v3-sm`, `v3.1-sm`, and `main` branches. All
> numbers are citation-backed from the shipped reports (see *Provenance*); none are from memory.
>
> **V1 → V2 are the delivery lineage** (baseline → honest ceiling → decision layer). **V2.1 · V3 · V3.1
> are three frozen, pre-registered improvement hunts** that each failed to beat the ceiling (17
> candidates, all REJECT) and are compared in their own section below.

**SM fleet = 34 independent trucks (14 failed `_F_SM` + 20 non-failed `_NF_SM`).** Completely
separate from the alternator fleet — the `_SM` suffix is mandatory and **no cross-dataset VIN
analysis is valid** (`VIN1_SM ≠ VIN1_ALT`).

---

## TL;DR

| Dimension | **V1** — Baseline | **V1.1** — Audited Redesign | **V2** — Decision Layer |
|---|---|---|---|
| Question | Does a classifier separate failed vs healthy SMs? Is there a lead-time channel? | Was V1's 0.921 honest? Add calibration, validated alerts, a measured horizon. | Detect earlier, cut false positives, ship RUL/ops — what's the ceiling? |
| Classifier AUROC | **0.9214** (non-nested LOVO) → **restated 0.893** under nesting | **0.9321** nested LOVO (95% CI [0.811, 0.986]) | **0.9321 — unchanged** (ceiling confirmed) |
| Model | Ridge, 4 features (incl. 1 artifact) | Ridge, 4 features (all audited) | same 4; 2 new candidates rejected (Δ +0.0000) |
| Validation | 34-fold LOVO, **non-nested** (hidden +0.0285 optimism) | **fully nested** 34-fold LOVO (+0.0036 optimism) | re-audited; pool proven selection-complete |
| Calibration | slope 4.72 — rank-only, **not shippable** | slope 0.86 / Brier 0.124 — **shippable** | unchanged |
| Detection horizon | not measured | **k\* = 10 weeks** (~70 d), validated | **10 weeks — triple-confirmed ceiling** |
| Lead-time / pager | **none** (12/14 trend, but 90% NF false-positive) | 3 validated channels; A2 battery-cascade **0/20 NF**, ~66 d lead; no deployable pager | **H2 dwell pager: 10/14 @ 0.19 NF episodes/truck-yr** (median lead 116 d) |
| RUL | risk bands only (no dates) | risk bands + ~10-wk window statement | **window matrix** (evidence-conditional + 95% CI) replaces RUL |
| Economics | not modeled | tiers by Youden (FP-averse) | **Youden-queue saves ~43%** vs run-to-failure (beats RED-only 34%) |
| Verdict | classifier works, lead-time doesn't — ship risk bands | the honest ceiling: 0.932 + validated 10-wk warning | model is finished; the win is the **decision layer** |

---

## The validation hunts — V2.1 · V3 · V3.1

After V2 froze the model, three **pre-registered** hunts each attacked the ceiling from a different,
previously-untested angle. All three reproduced the frozen baseline to the 4th decimal (**non-nested
LOVO 0.9357 / nested 0.9321**) and **rejected every candidate — 17 in total**. This is the load-bearing
evidence that the cap is the **data** (n = 34, 5-second 6-signal frame), not the method or the linear
model class. Each hunt still shipped a durable operational asset, which is why they were worth running.

| Dimension | **V2.1** — Richer Heuristics/Features | **V3** — Interaction & Usage | **V3.1** — Operational State |
|---|---|---|---|
| Branch | [`v2.1-sm`](https://github.com/himanshu-igloble/Daimler_Starter-motor/tree/v2.1-sm) | [`v3-sm`](https://github.com/himanshu-igloble/Daimler_Starter-motor/tree/v3-sm) | [`v3.1-sm`](https://github.com/himanshu-igloble/Daimler_Starter-motor/tree/v3.1-sm) |
| Aim | Can richer rules (CUSUM/EWMA drift, conjunctions, terminal-state fix) or new features (inter-crank CV, cold-dip depth, torque trend) beat H2 / the modal-4 set? | Test the last untouched feature surface: interaction/cross terms + usage/probe features a linear model on marginals cannot see. | Build the missing operational-state layer (trips/soak/engine-hours/dropout), then gate usage features on **correct denominators**. |
| Candidates tested | 7 rule variants + **3 features** | **7 features** (4 interaction, 1 usage, 2 probe) | **7 features** (state-unlocked: engine-hour-normalized, soak, dropout-as-signal, decorrelated dip trend) |
| Protocol | V1.1/V2 strict accept-bar (recall ≥ 10/14 ∧ NF eps < 0.19/yr ∧ lead ≥ 116 d); features on the locked gate | Locked V1.1 gate (MW p ≤ 0.10 ∧ oriented AUROC ≥ 0.60 ∧ ΔAUROC ≥ +0.01); BH-FDR over 7 | Same locked gate **+ 5 state-validation (SV) gates** before any feature; BH-FDR over 7 |
| Baseline reproduced | modal-4 **0.9357** (Δ 0.0000) | modal-4 **0.9357** (Δ 0.0000) | modal-4 **0.9357** (Δ 0.0000) |
| Verdict | **All 3 features REJECT**; no rule beats H2 — every FP cut loses recall, every recall gain ~doubles FPs | **All 7 REJECT**; best incremental +0.0071 < +0.01; GBM probe **0.843 < 0.932** ⇒ data-not-method | **All 7 REJECT**; the two near-misses were one redundant (E1 pass, E2 −0.0179) + one small-n overfit (E2 +0.0179, E1 fail), both refused by pre-registration |
| What shipped | **A3 recall lever** — terminal-state fix cuts NF false alarms **20/20 → 7/20** at held recall 13/14; **A5 graded windows** (9 trucks 126–284 d · 4 near-term 28–91 d · 18 GREEN) | Interaction/usage **feature-space closure** + **temperature-infeasibility** appendix (no GPS/ambient ⇒ no thermal proxy on the current frame) + new-data roadmap | **State engine** (SV-1 0.9785, SV-3 0.936, SV-5 exact; 130.8k engine-hrs · 3.55M km · 20.9k cranks) · **T1** battery-vs-starter triage (**9/11** convergence, **0/20** NF false attributions) · **T2** windows · **T3** dropout monitor · **heartbeat REFUTED** (P0-1) · **DICV validation dossier** (**9/11** failures inside the predicted window) |

**How to read it.** The *Verdict* row is the headline — nothing beat the frozen model, four iterations
running. The *What shipped* row is the payoff — each hunt either closed a branch of the search space
with exact numbers or produced a deployable operational asset (recall lever, graded windows, state
engine, battery-first triage). V3.1 additionally promoted the state engine as reusable infrastructure
and produced the DICV management validation dossier (under `V1.1_SM/reports/`).

---

## What changed at each step

- **V1 → V1.1 — the honesty audit.** V1's `0.9214` was non-nested; restated to **0.893** once the
  Youden threshold and feature selection were moved *inside* every fold (the +0.0285 gap was selection
  optimism plus one artifact feature, `vsi_dominant_freq`, exposed as a `1/n_weeks` leak). A fully
  nested redesign with new feature engineering then **beat** the honest baseline → **0.9321**, added
  shippable calibrated probabilities, **3 validated alert channels**, and the first measured detection
  horizon (**10 weeks**).
- **V1.1 → V2 — the decision layer.** No model gain was available (boosted trees 0.67–0.78, survival
  RUL MAE 576 d, deep models far over budget, anomaly 80–100% FP; pool-expansion *degraded* to 0.875).
  V2's value is operational: a clean deployable **pager** (H2 persistent-RED dwell, 0.19 ep/truck-yr),
  a cost-optimal operating point (**Youden-queue, 43% saving** at India HD cost ratios), honest
  VIN-specific **windows** instead of RUL, production governance, a prospective **shadow quarter**, and
  a funded instrumentation path past the ceiling.
- **V2 → V2.1 → V3 → V3.1 — the pre-registered stress tests.** Three independent hunts (richer
  heuristics/features; interaction/usage; operational state) reproduced the baseline exactly
  (0.9357 / 0.9321) and **rejected all 17 candidates**. They did not change the model — they *hardened*
  it, ruled out the last structurally-new feature surfaces, and shipped operational assets (A3 recall
  lever, A5 graded windows, the state engine, and T1 battery-first triage). See the dedicated
  *validation hunts* section above.

---

## Performance ceiling (consistent across all six versions, re-confirmed four times)

Nested LOVO **AUROC ≈ 0.932** (non-nested 0.9357), detection horizon **10 weeks**, alerting recall
capped at **~10–11/14** — **4/14 failures are structurally invisible** (silent/abrupt mode: SMA-dead,
long telemetry gaps). The ceiling has now survived four consecutive pre-registered attacks
(V1.1 → V2 → V2.1/V3 → V3.1), including a nonlinear GBM probe (0.843 < 0.932) and a full
operational-state feature surface. Breaking it needs **new signals** (≥1 Hz crank logging, cranking
current / battery SoC-SoH, coolant-at-key-on thermal proxy, maintenance-record labels, more failures
n ≥ 30–50), **not** new models.

---

## Provenance

- **V1** — `V1_SM/reports/V1_SM_final_report.md` (AUROC 0.9214, CI, recall/spec 13/14 & 18/20, lead-time
  control 18/20 NF, KT reconciliation, risk bands). On `v1-sm` (and `main`).
- **V1.1** — `V1.1_SM/reports/V1_1_SM_RESULTS_MASTER.md` + `V1.1_SM/Plan/V1_1_SM_spec.md` §0 (nested
  0.9321, restatement of V1 to 0.893, horizon k\*=10, alert channels, leak ceilings). On `v1.1-sm` (and `main`).
- **V2** — `docs/2026-06-12-…-sm-v2-d09-performance-improvement-matrix.md`, `…-d10-executive-recommendation.md`,
  `…-d04-heuristic-framework.md`, `…-d01-technical-audit.md` (AUROC unchanged, H2 0.19 ep/yr, Youden-queue
  43% vs RED-only 34%, window matrix). The V2 system lives under `V2_SM/`.
- **V2.1** — `V2_1_SM/reports/V2_1_SM_exec_summary.md` + `_verdict.md` + `V2_1_comparison.csv` (7 rules +
  3 features, all REJECT; H2 stays best pager; A3 terminal-fix NF 20/20→7/20; A5 graded bands in
  `heuristics/out/A5_graded_rul_policy.csv`, `A5_per_truck_bands.csv`; ceiling-break paths in
  `appendix/C_new_data_appendix.md`). On `v2.1-sm` (and `main`).
- **V3** — `V3_SM/reports/V3_SM_exec_summary.md` + `_verdict.md` + `_results.md` (7 interaction/usage
  candidates all REJECT; modal-4 reproduced 0.9357; best incremental +0.0071; BH-FDR min p 0.7363; GBM
  probe 0.8429; temperature infeasible — `appendix/temperature_infeasibility.md`, `new_data_roadmap.md`).
  On `v3-sm` (and `main`).
- **V3.1** — `V3_1_SM/reports/V3_1_SM_exec_summary.md` + `_verdict.md` + `_state_engine_report.md` +
  `_results.md` (state engine SV-1 0.9785 / SV-3 0.936 / SV-5 exact; 7 state-unlocked candidates all
  REJECT; heartbeat P0-1 REFUTED; T1/T2/T3 in `heuristics/out/{T1_attribution.csv, T1_convergence.json,
  T2_windows.csv, T3_data_health.csv}`; state cache in `state/out/*.parquet`; instrumentation v2 +
  temperature closure in `appendix/`). The DICV validation dossier (window validation 9/11) is
  `V1.1_SM/reports/2026-07-02_DICV_StarterMotor_Validation_Report.pdf` + `…_Brief.pdf`. On `v3.1-sm` (and `main`).
