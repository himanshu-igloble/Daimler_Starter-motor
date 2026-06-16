---
title: "SM V2 Program — D7: Starter Motor V2 Production Architecture"
status: "complete"
created: "2026-06-12"
---

# Deliverable 7 — Starter Motor V2 Production Architecture

> Design constraint honored throughout: every component below is either already validated in
> V1.1/V2 analysis (cited) or is pure engineering with no statistical claim. Nothing in this
> architecture presumes a capability the data has refuted (day-precision RUL, >10-week warning,
> sub-5s physics).

## 0. System overview

```
 Raw telematics (6 signals, ~5s)                       [per truck, streaming/batch]
   │
   ▼
 L0 DATA & QUALITY ───────────── gap/silence detector ── 72h ops trigger (P0)
   │  weekly + daily + event caches; artifact flags;        │
   │  sentinel/VSI-scaling guards; density monitor          │
   ▼                                                        │
 L1 FLEET RISK ASSESSMENT (weekly)                          │
   │  frozen Ridge-4 walking score (LOVO-calibrated),       │
   │  tiers G/A/R · H1 momentum ranker · H5 fleet pctile    │
   ▼                                                        │
 L2 VEHICLE FAILURE PREDICTION ── calibrated P(fail-class), │
   │  tier + 10-wk validity statement + CI                  │
   ▼                                                        │
 L3 FAILURE-WINDOW ESTIMATION ── evidence-state machine ←── channels (A2, persistence, A1)
   │  window matrix lookup + CI + n (D6)                    │
   ▼                                                        ▼
 L5 HEURISTIC INTELLIGENCE ──────────────── composite alert policy (D4):
   │  A2 → battery-first 14–30d · H2 dwell → inspect 2–4wk · RED → ranked queue
   ▼
 L4 EXPLAINABILITY ENGINE ── evidence card on every alert
   │
   ▼
 Outputs: fleet ranking · alert queue with windows · evidence cards · governance dashboard
```

Cadence: scores weekly (features need 30–90 d windows); fleet review monthly; alerts evaluated on
every weekly run. All thresholds pre-registered; all outputs carry their validation provenance.

## 1. Layer 0 — Data & quality (the part that caught V1's worst bugs)

- Caches: weekly (34→N parquets), daily (A1 channel), crank-event catalog (gap-aware ≤10 s episode
  splitting, >60 s artifact flag, RPM≥550 success rule) — exact V1 definitions retained.
- Guards (all existing, now mandatory gates): sentinel filtering (65535/−5000/0/255), VSI ×0.2
  scaling check, per-VIN setpoint baselining, battery-step re-baseline (E5 detector), SMA-dead
  cohort masking, stuck-value screens.
- **Density monitor**: rows/day trend per truck; taper alarm. **Silence detector**: >30 d quiet
  while AMBER/RED → 72 h operational check (the VIN9_F countermeasure — a telemetry-architecture
  fix, not a model).
- New-truck onboarding: no L40 history → fleet-prior score only, tier capped at AMBER, "immature"
  badge until 12 masked weeks accrue.

## 2. Layer 1 — Fleet risk assessment

- Engine: frozen 4-feature RidgeClassifier (nested AUROC 0.9321, CI [0.811, 0.986], perm p=0.005),
  Platt-calibrated; walking weekly scores via the X4 causal recomputation (reconciled to 4.4e-16).
- Outputs: full-fleet ranked table (calibrated prob, tier, Δ4wk momentum, fleet percentile),
  top-N high-risk list, inspection-queue ordering = tier → H1 momentum → H5 co-fire (D4 §3).
- Feature pool changes only via the admissibility pipeline (MW p, AUROC, L40 control, proxy-corr
  gates, density partial-correlation per P5) — candidates currently in evaluation: cold_dip_delta90,
  rpm_rise_lag_delta90 (verdicts in D5).

## 3. Layer 2 — Vehicle failure prediction

- Per truck: calibrated failure-class probability + tier + **validity statement**: "score valid
  ~10 weeks out; a clean GREEN is not a guarantee beyond ~2.5 months" (X4-validated).
- Confidence reporting: calibration slope 0.86 / Brier 0.124 on file; tier error rates quoted from
  OOF (RED: 10/14 recall @ 18/20 spec; Youden alternative 13/14 @ 15/20 — operating point per D6
  economics, default = Youden-queue with RED-priority, since breakdown:inspection ≈ 31:1).
- Blind-spot disclosure is part of the output contract: SMA-dead trucks carry a "crank channels
  masked" badge; A4-silent risk is stated on every GREEN.

## 4. Layer 3 — Failure-window estimation (RUL, honest form)

- Evidence-state machine per truck-week: {A2 fired} > {H2 dwell} > {persistence-terminal ∧ RED} >
  {RED} > {AMBER} > {GREEN}; + silence overlay.
- Output per truck: state → scheduling window + median lead + 95% CI + n (the D6 lookup card).
  Never a date. UI copy: "Trucks in this state historically failed 28–91 days later (n=4)".
- The state machine is also the **escalation logic**: state transitions (not levels) page humans.

## 5. Layer 4 — Explainability engine

Every alert ships an evidence card (extends `V1_1_SM_explanations.json` + explanation_cards):
- **Archetype** (A1/A2/A3/A4 signature match) and which physics mode it implies (D2 table).
- **Feature drivers** in raw units (e.g., "within-week VSI noise 2.6× own baseline; rest-floor
  down 1.8 V over 90 d"), with fleet percentile per driver.
- **Channel evidence**: which rules fired, when, with their validated FP history (A2: 0/20).
- **Counterfactual**: "returns to GREEN if rest-VSI floor recovers +0.4 V" (linear model → exact).
- **Confidence block**: tier OOF error rates, state n, window CI — auto-attached.
SHAP is unnecessary: the model is 4-feature linear; exact coefficient×z contributions are the SHAP
values. Spend the effort on raw-unit translation instead.

## 6. Layer 5 — Heuristic intelligence (composite alert policy)

Precedence per D4 §3: A2 (P0, battery-first 14–30 d) → H2 dwell (P0, inspect 2–4 wk) → RED queue
(P1, ranked by H1/H5) → AMBER bundling (P2) → corroborators (persistence terminal, A1) attach
evidence but never page → silence overlay (P0 ops, 72 h). Expected paging burden ~0.2–0.3
shop-grade alerts/truck-yr (retrospective; re-measure prospectively).

## 7. Cross-cutting: governance & monitoring (what makes it production, not research)

- **Pre-registration registry**: thresholds (0.35/0.55 tiers; H1 +0.15/4wk; H2 3wk; H5 p85 4-of-6),
  banned-feature list (vsi_dominant_freq class), admissibility gates — versioned, hash-pinned.
- **Drift monitors**: PSI on the 4 modal features (alarm >0.2), calibration slope (refit gate
  outside [0.5, 2]), alert-volume tracker (paging burden vs the 0.19 ep/truck-yr baseline),
  density/null-rate per fleet batch.
- **Refit policy**: only on ≥5 new failure labels or a drift gate, always full nested protocol +
  admissibility + L40 + permutation; restated baselines published (the V1→V1.1 restatement is the
  template).
- **Prospective watchlist**: VIN2/5/8/15_NF tracked explicitly; every future outcome (save or FP)
  is recorded as the system's first prospective validation evidence.
- **Scale-out**: per-fleet NF envelopes (persistence p90) and fleet-percentile baselines recomputed
  per deployment cohort; never transfer absolute VSI levels across fleets (setpoint smear, A audit §4).
- **Audit trail**: every alert stores model hash, feature snapshot, state, card — replayable.

## 8. Build inventory (what exists vs what is engineering)

| Component | Status |
|---|---|
| Caches, features, nested model, calibration, tiers | **Exists, validated** (V1/V1.1 scripts) |
| Walking-score engine | **Exists** (X4 + V2 heuristics rerun; needs packaging as weekly job) |
| Channels A1/A2/persistence | **Exists, validated** |
| H1/H2/H5 heuristics + state machine | **Validated screen-grade** (V2); needs pre-registered config + scheduler |
| Window matrix + econ policy engine | **Exists as analysis** (V2); needs lookup-service wrapper |
| Evidence cards | Partial (explanations.json); needs raw-unit + counterfactual template |
| Drift/PSI/calibration monitors, registry, dashboard | **New engineering** (no statistical risk) |
| Silence/ops trigger | Trivial query; **new** |
Estimated effort split: ~80% orchestration/UI/ops engineering, ~20% statistical (D5 candidate
adjudication + pre-registration freeze).
