---
title: "SM V2 Program — D10: Executive Recommendation Report"
status: "complete"
created: "2026-06-12"
---

# Deliverable 10 — Executive Recommendation: Starter Motor V2

## Bottom line

The V2 deep review confirms V1.1's statistical core is the **honest ceiling of this dataset**
(nested AUROC 0.932, 10-week validated horizon) — and then finds the improvement V1.1 left on the
table: it was never the model, it was the **decision layer**. V2 delivers an order-of-magnitude
cleaner alert pager, a cost-optimized operating policy worth ~43% of run-to-failure cost, an honest
per-truck failure-window product with confidence intervals, a production architecture with
governance, and a funded path (instrumentation) to the next physics. Recommendation: **ship V2 as
specified in D7/D8, run the prospective shadow quarter, and put the sensor pilot in front of DICV.**

## What the program established (with evidence grade)

1. **The classifier is finished.** Every alternative — boosted trees (0.67–0.78), survival models
   (RUL MAE 576 d vs constant 44 d), deep sequence models (235×–6,275× over parameter budget),
   anomaly detectors (80–100% FP), and two new physics features (both Δ +0.0000, one r=0.92 with an
   existing feature) — was measured, arithmetically excluded, or duplicates existing signal.
   Pool-expansion under honest nested selection *degraded* AUROC to 0.875. [VALIDATED]
2. **Earlier warning does not exist in this data.** Physics (5 s sampling destroys the 60–120 d
   brush-wear channel), prequential decay (k\*=10 wk), and the density audit (all longer trends are
   observation-length artifacts, r=−0.771) agree independently. [VALIDATED]
3. **But the alerting layer had real headroom.** The new persistent-RED dwell rule (H2) achieves
   10/14 recall at **0.19 NF episodes/truck-year** — V1.1 had no deployable walking pager at all
   (its persistence rule floods 20/20 NF; A1 burns 1.52 ep/yr). With A2 (0/20 NF, ~66 d fuse) the
   composite policy pages ~0.2–0.3 times per truck-year and still covers 13/14 failures. [SCREEN]
4. **Economics reverses a V1.1 default.** At India HD cost ratios (breakdown ≈ 31× inspection),
   the recall-greedy Youden queue saves ~43% vs run-to-failure — beating the conservative RED-only
   policy (34%) everywhere above ratio 11.5. FP-aversion was costing money. At 5,000 trucks and a
   4%/yr failure rate this is ≈ ₹23 lakh/yr with break-even at ratio 30.7. [ECON, swept]
5. **RUL ships in its only honest form.** Day-precision RUL is mathematically closed at 14 events
   (calibration ⊥ precision). The replacement: evidence-conditional windows — "A2 fired → failures
   historically 28–91 d later (n=4)" — with CIs, n, and a NOT-a-countdown contract. [VALIDATED inputs]
6. **The blind spot is operational, not statistical.** VIN9_F-class (SMA-dead + terminal silence)
   is invisible to any model; the fix is a 72-hour ops check on telemetry silence — now part of the
   architecture. [ENG]

## Five decisions requested

| # | Decision | Basis |
|---|---|---|
| 1 | Adopt the **Youden-queue + RED-priority operating point** (inspection queue economics) | D6/D9; flip threshold R=11.5 vs actual ~31 |
| 2 | Ship the **composite alert policy (A2 + H2 + queue + silence trigger) in shadow mode** for one quarter with pass/fail KPIs | D4/D8-C1 |
| 3 | Fund the **instrumentation pilot**: current clamp/IBS (₹2–15k/truck) + trigger-based high-rate VSI (firmware-only) on 20–50 trucks | D2 §7, D8-C2; the only path past the 10-wk ceiling |
| 4 | Institutionalize **governance**: pre-registration registry, drift monitors, refit gates, watchlist (VIN2/5/8/15_NF), restatement policy | D7 §7 |
| 5 | Keep deep/survival research **gated** (n_failed ≥ 30–50 + new channel + clean prospective quarter) — gates, not aspirations | D5/D8-D |

## The success-criteria questions, answered straight

- **Can failures be detected earlier?** Not with this telemetry. 10 weeks is the validated ceiling;
  trigger-sampled VSI or a current channel reopens the question (brush-wear physics offers 60–120 d).
- **Can false positives be reduced?** Yes — done: the pager level drops to 0.19 ep/truck-yr (H2)
  with A2 at zero; and the economics shows residual FPs cost far less than the breakdowns avoided.
- **Can RUL become truly VIN-specific?** As windows conditioned on the truck's own evidence state —
  yes, shipped. As day-counts — no, and pretending otherwise loses to a constant by 10×.
- **Which failure modes are detectable?** Battery-cascade (A2 — best channel), solenoid
  intermittency (crank bursts), volatility/regulation modes (model), thermal/abuse events (direct
  counters). **Which are not?** Silent/abrupt (A4), sub-5-second physics, mechanical wear without a
  vibration channel, anything on a truck that stops transmitting.
- **What additional signals unlock the next level?** (1) starter/battery current, (2) trigger-based
  high-rate VSI (near-free), (3) battery temperature, (4) maintenance-record labels, (5)
  transmission-health monitoring as a first-class alert.
- **Highest-ROI path to production?** D8 as sequenced: shadow quarter (validates honestly) →
  workshop integration → instrumentation pilot → scale-out with per-fleet baselines.

## What this costs and returns (base case)

Phase A+B ≈ 4–6 engineer-weeks (mostly orchestration/UI; the statistics is done). Shadow quarter:
no fleet-ops cost (logging only). Pilot hardware: ₹0.7–7.5 lakh for 20–50 trucks. Return at current
fleet scale is modest in rupees but decisive in evidence; at 5,000-truck scale the modeled saving
is ₹23 lakh/yr against ~19 inspector-hours/week — and the prospective quarter converts every number
above from "retrospective" to "validated in deployment", which is what DICV will actually buy.

## Risks worth naming

Shadow-quarter FP burden may exceed the retrospective 0.19 (expected direction; one documented
re-registration is budgeted). DICV may decline the pilot (V2 still ships; ceiling stands). New
failures during rollout trigger a full-protocol refit (planned, not feared). The watchlist trucks
may fail — which would be the system's first prospective saves if alerts are heeded.

## Closing

V1.1 proved what this data can know. V2's contribution is to make that knowledge **decide things**:
which truck, which week, which intervention, at what cost, with what confidence, and with its
limits printed on every card. That — not another model — is what an industrial-grade predictive
maintenance system looks like at 14 failure events. The program should be judged by the shadow
quarter, and we have made that test impossible to game.
