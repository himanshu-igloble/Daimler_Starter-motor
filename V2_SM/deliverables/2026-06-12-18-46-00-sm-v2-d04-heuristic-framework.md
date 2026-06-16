---
title: "SM V2 Program — D4: Heuristic Engineering Framework"
status: "complete"
created: "2026-06-12"
---

# Deliverable 4 — Heuristic Engineering Framework

> Every heuristic below is **backtested on causal walking risk scores** (the frozen V1.1 4-feature
> model, recomputed at weekly cuts k=0..26 per truck, scored leave-one-VIN-out — machinery
> reconciled exactly to X4: k=0 AUROC 0.9357, feature diffs ≤ 4.4e-16). Rule parameters were frozen
> a priori in the run spec, not tuned on outcomes. Status of all results: **SCREEN-GRADE**
> (n=34, retrospective) — pre-register before deployment. Full method + per-VIN fires:
> `STARTER MOTOR/V2_program/intake/06_heuristics_intake.md`, outputs in
> `V2_program/analysis/heuristics/out/`.

## 1. Design philosophy

The V2 system pairs the calibrated ML risk score with rule-based intelligence for three reasons:
(1) rules capture *dynamics* (dwell, momentum, escalation) that a per-week static score cannot;
(2) rules are explainable to a workshop foreman in one sentence; (3) the validated channels (A2
cascade) encode physics the 4-feature model does not see. The V1.1 lesson stands: a rule that looks
clean in-sample (persistence: 2/20 NF) can flood out-of-fold as a walking alarm (20/20 NF ever-fire,
31% of weeks) — every V2 heuristic was therefore evaluated as a *deployed weekly walking alarm*,
the harshest honest test.

## 2. Validated ranked table

| Rank | Heuristic | Definition (frozen) | Validated value | FP burden (NF) | Complexity | Explainability | Priority |
|---|---|---|---|---|---|---|---|
| 1 | **A2 battery-cascade** (X3, ships from V1.1) | rest-VSI step ≤ −0.5 V ∧ drive-VSI step ≥ +0.3 V (±8 wk) ∧ dip widening > +1 V | 4/5 of battery archetype; median lead 66.5 d; the only short-fuse channel | **0/20 ever; 0.00 ep/yr** | Medium | High (3 physical conditions) | **P0 — ship** |
| 2 | **H2 persistent-RED dwell** | ≥3 consecutive weekly cuts in RED tier | **10/14 recall; median lead 116 d** | **5/20 ever; 0.19 ep/truck-yr** | Low | High ("RED three weeks running") | **P0 — the new walking pager** |
| 3 | **H1 risk momentum** | Δ(recal. prob) ≥ +0.15 over trailing 4 wk | 13/14 recall; median lead 126 d | 19/20 ever; 0.75 ep/yr — ranker, not pager | Low | High ("risk climbing fast") | **P1 — severity ranker inside AMBER/RED** |
| 4 | **H5 fleet-percentile persistence** | ≥ p85 of fleet same-week scores in ≥4 of 6 wk | 7/14 recall; median lead 119 d | **3/20 ever; 0.11 ep/yr** (cleanest) | Medium | Medium ("worst 15% of fleet for a month") | **P1 — confidence booster when co-firing with H2** |
| 5 | **Persistence flag** (X3) | weekly vsi-std ratio > NF p90 envelope ≥4 of 12 wk | 13/14 terminal recall; median lead 168 d | 4/20 end-state but **20/20 ever-fire** | Medium | Medium | **P2 — terminal-state condition flag only, gated on AMBER/RED** |
| 6 | **H3 escalation ladder** | GREEN→AMBER→RED climb within 8 wk ∧ any channel active | 9/14; median lead 77 d | 8/20; 0.24 ep/yr | Medium | High | P2 — adds little over H2; keep as tie-breaker |
| 7 | **A1 crank-burst** (X3) | 7-d failed-crank+retry sum > own baseline+3σ, ≥2 d | 4/12 applicable; rescued GREEN-tier VIN1_F | 8/15 applicable; 1.52 ep/yr | Medium | High | P2 — tier-gated corroborator only |
| 8 | **H4 multi-channel agreement** | ≥2 of {tier≥AMBER, persistence, A1, A2} | 14/14 — but flooded by persistence | 20/20 ever | Low | Medium | P3 — internal composite score only, never a trigger |
| 9 | **H6 crank-while-running counter** | SMA=1 ∧ RPM>400 same sample (engine already running) | **RESOLVED NOT PREDICTIVE** — true per-sample raw scan: F median 11.9 vs NF 7.8 episodes/truck-yr, MW p=0.64, heavy overlap (`V2_program/intake/07_raw_screens_intake.md`) | n/a | Low | High | P3 — operational duty/abuse telltale only; make no failure claim |

Rejected by prior evidence (do not revisit without new data): anomaly-detection standalone
(80–100% FP at this n), GED=2 channel (absent in all 14 failed SM), entropy/spectral/gradient
families (B2: 0.48–0.64), lifetime-trend heuristics (P5: density artifacts).

## 3. Recommended V2 composite alert policy

Weekly evaluation per truck, strict precedence; each alert carries its evidence card (D7 Layer 4):

1. **A2 fires** → P0 alert: battery-first inspection within 14–30 d (window matrix D6). Zero
   false-alarm history; never suppress.
2. **H2 fires** (3-wk RED dwell) → P0 alert: planned electrical inspection within 2–4 wk. Expected
   burden ~0.19 NF episodes/truck-yr.
3. **RED single week** → P1: queue inspection within 4–8 wk; rank the queue by H1 momentum, break
   ties with H5 co-fire.
4. **AMBER** → P2: bundle into next scheduled service; promote if H1+H5 both fire.
5. **Persistence terminal-state / A1** → corroborators: attach to any open P0–P2 as confidence
   evidence; alone they trigger nothing.
6. **Telemetry silence >30 d while AMBER/RED** → P0 ops check within 72 h (the VIN8/9_F lesson —
   a quiet truck is itself a signal).

Estimated combined paging burden (retrospective): ~0.2–0.3 shop-grade alerts per truck-year from
H2+A2, vs 1.5+ for V1.1's channel set used naively. Recall path: A2∪H2 catches 11/14 outright;
+VIN1_F via A1 corroboration on its AMBER/RED weeks; VIN2_F via H1-in-RED; VIN9_F remains the
documented blind spot (no instrument sees it).

## 4. Caveats and governance

- All numbers are 34-truck retrospective screens; the H1–H5 parameter set must be **pre-registered**
  (it already is, in the run spec) and held fixed through the first prospective quarter.
- Walking probabilities at k>10 use the k=0 Platt map (per-cut recalibration was skipped for
  runtime) — tier boundaries are reliable, raw probability values at deep truncations less so.
- The 4 chronic NF firers (VIN2/5/8/15_NF) drive most residual FP burden across every rule family —
  they are right-censored degradation candidates, tracked as the prospective watchlist (D8).
- Heuristic thresholds (0.15 momentum, 3-wk dwell, p85/4-of-6) should be re-derived only when ≥5
  new failure labels accrue, under the same nested discipline as the model refit.
