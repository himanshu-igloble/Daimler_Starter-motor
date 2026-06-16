# Starter Motor — Version Comparison: V1 → V1.1 → V2

> Identical on the `v1-sm`, `v1.1-sm`, `v2-sm`, and `main` branches. All numbers are
> citation-backed from the shipped reports (see *Provenance*); none are from memory.

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

---

## Performance ceiling (consistent across all three versions)

Nested LOVO **AUROC ≈ 0.932**, detection horizon **10 weeks**, alerting recall capped at **~10–11/14**
— **4/14 failures are structurally invisible** (silent/abrupt mode: SMA-dead, long telemetry gaps).
Breaking this ceiling needs **new signals** (≥1 Hz crank logging, cranking current / battery SoC-SoH,
maintenance-record labels, more failures n≥30–50), **not** new models.

---

## Provenance

- **V1** — `V1_SM/reports/V1_SM_final_report.md` (AUROC 0.9214, CI, recall/spec 13/14 & 18/20, lead-time
  control 18/20 NF, KT reconciliation, risk bands). On `v1-sm` (and `main`).
- **V1.1** — `V1.1_SM/reports/V1_1_SM_RESULTS_MASTER.md` + `V1.1_SM/Plan/V1_1_SM_spec.md` §0 (nested
  0.9321, restatement of V1 to 0.893, horizon k\*=10, alert channels, leak ceilings). On `v1.1-sm` (and `main`).
- **V2** — `docs/2026-06-12-…-sm-v2-d09-performance-improvement-matrix.md`, `…-d10-executive-recommendation.md`,
  `…-d04-heuristic-framework.md`, `…-d01-technical-audit.md` (AUROC unchanged, H2 0.19 ep/yr, Youden-queue
  43% vs RED-only 34%, window matrix). The V2 system lives under `V2_SM/`.
