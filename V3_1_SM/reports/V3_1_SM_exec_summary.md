---
title: "V3.1 Starter Motor — Executive Summary"
status: "complete"
created: "2026-07-02"
program: "SM V3.1"
sources: "V3_1_gate_summary.json, V3_1_validation.json, V3_1_sv_gates.json, T1/T2/T3 outputs"
---

# V3.1 Starter Motor — Executive Summary

## What was built

V3.1 re-opened the (previously closed) SM feature line under one specific justification: V3
had tested only cache-derived candidates, but **no operational-state layer existed** for the
SM fleet — so usage features carried wrong denominators, soak was unmeasured, and telemetry
dropout was conflated with ignition-off. V3.1 built that layer first, then ran a small
pre-registered confirmatory gate on top of it.

Delivered:
- **An SM operational-state engine** (row states → episodes → trips/soak/engine-hours/dropout)
  for all 34 trucks (14 failed / 20 non-failed). Fleet: 130,842.9 engine-hours, 3,552,966.9
  km, 20,877 crank episodes. All validation gates pass (SV-1 0.9785, SV-3 0.936, SV-5 exact;
  soak measurable for 0.7102 of cranks).
- **A 33-feature usage & exposure catalog**, confidence-classified.
- **7 pre-registered candidates** through the frozen gate, unlocked by the new state layer
  (correct engine-hours normalization, soak context, dropout-as-signal, a decorrelated
  starter-side dip trend).
- **T1/T2/T3 channels** and **two forward annexes** (temperature closure, 500-truck
  instrumentation v2).

## The gate outcome

**All 7 candidates REJECTED — the pre-registered expected result. The data ceiling holds.**

| Metric | Value |
|---|---|
| Reconciliation — modal-4 non-nested LOVO AUROC | 0.9357 (reproduced exactly, Δ 0.0000) |
| Frozen nested baseline | 0.9321 |
| Sole E1 pass | `dip_resid_trend_12w` (p 0.0679, AUROC 0.6786) — but E2 Δ −0.0179 (hurts champion) |
| Sole positive E2 Δ | `hard_start_goodv_rate_delta90` (+0.0179) — but E1 fail (p 0.2104); refused by ordering |
| BH-FDR smallest adjusted p (7 tests) | 0.4753 — nothing significant |
| E3 nested rerun | not triggered (no E2 survivor) |

The two near-misses are wins for the protocol: one signal was redundant with the champion dip
channel, the other was a small-n overfit lift with no univariate support. Pre-registration
refused both. This is the **fourth consecutive iteration** (V1.1 → V2 → V2.1/V3 → V3.1) to
re-confirm the ceiling; the cap is the data (n = 34, 5-second 6-signal frame), not the method.

## The business deliverable — T1 battery-first routing

Independent of any AUROC movement, T1 ships an actionable triage: **route a cheap battery
service before an expensive starter inspection.** It converges with V1.1 archetypes on 9/11
scored failed trucks (82 %, SCREEN-GRADE — a consistency check, not accuracy), flags **6 of 14
failed trucks BATTERY_FIRST** (with A2 battery-cascade firing on 4), and produces **zero false
attributions on the 20 healthy trucks**. This extends the shipped A2→battery-first routing (A6)
to the whole fleet. T2 assigns battery-first trucks the earlier 28–91-day service window; T3
tracks dropout escalation (638 elevated weeks across 32/34 trucks) as a data-health monitor
(not a pager). Disclosed limit: the STARTER arm is unvalidated (n = 2) and never fires
fleet-wide because the registered 26.0 V low-voltage threshold sits above the typical
under-load baseline — a fixable calibration, below.

## Priority-ranked next actions

1. **Re-register the low-voltage threshold from the fleet distribution** (cheapest, in-house).
   The 26.0 V cut gated the STARTER attribution arm off entirely (fleet `lowv_crank_share`
   median 0.4953). Re-deriving it empirically is a V3.2 pre-registration that could activate the
   starter-side triage.
2. **Pre-register the top exploratory catalog leads for V3.2** (do not promote within V3.1).
   Strongest raw separators: `monsoon_start_share` (AUROC 0.7357), `hard_start_goodv_rate` in
   LEVEL form (0.6875 — distinct from its REJECTed Δ90 delta), `consecutive_high_crank_days_max90`
   (0.6946), `dropout_hours_per_week` (0.6857). All BH-unsafe post-hoc; each needs a fresh gate.
3. **Add a T3 unknown-gap channel.** VIN4_F's 97-day blackout was missed because it is
   `UNKNOWN_GAP`, not `DROPOUT_RUNNING`; an unknown-gap escalation rule would catch the
   blackout failure mode.
4. **Instrumentation asks for the 500-truck program** (`appendix/instrumentation_v2.md`):
   battery current sensor (true crank-current I²t), 1 Hz VSI burst around SMA events (recovers
   the sub-second dip physics the 5 s cadence destroys), SPN 110 coolant-at-key-on (best crank
   thermal proxy), SPN 171 ambient, per-VIN region mapping, and maintenance/parts records (turns
   T1 archetypes into supervised labels).

## Bottom line

The SM failure-risk classifier is **feature-complete on the current data** at AUROC 0.9321
nested / 0.9357 non-nested. V3.1 built the operational-state foundation, tested the last
structurally-new feature surface, and confirmed no incremental signal at n = 34. The durable
wins are the **state engine** (promotable to `src/`), the **T1 battery-first routing**, and a
clear, evidence-backed instrumentation roadmap.

*All numbers cited from the V3.1 gate, validation, SV, and channel artifacts. Fleet: SM,
n = 34. SCREEN-GRADE caveat applies throughout.*
