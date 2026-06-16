---
title: "SM V2 Program — D9: Expected Performance Improvement Matrix (V1.1 → V2)"
status: "complete"
created: "2026-06-12"
---

# Deliverable 9 — Expected Performance Improvement Matrix

> Every "V2 expected" cell states its evidence grade: **VALIDATED** (LOVO/OOF on this fleet),
> **SCREEN** (retrospective rule backtest, pre-registered params, needs prospective confirmation),
> **ECON** (assumption-driven cost model, sensitivity-swept), **ENG** (engineering, no statistical
> claim). Claims we refuse to make are listed in §3 — they matter as much as the improvements.

## 1. The matrix

| Dimension | V1.1 baseline | V2 expected | Δ and evidence |
|---|---|---|---|
| Discrimination (nested AUROC) | 0.9321 [0.811, 0.986] | **0.9321 (unchanged)** | +0.00 — pool proven selection-complete; both new candidates HOLD (D5 §6). VALIDATED |
| Failure coverage (any validated alert before failure) | 13/14 retrospective | 13/14 (A2∪H2∪corroborators) | Unchanged; VIN9_F-class remains the documented blind spot. VALIDATED/SCREEN |
| **Deployable pager FP burden** | No usable walking pager (persistence floods: 20/20 NF ever-fire, 31% of weeks; A1 1.52 ep/truck-yr) | **H2 dwell: 0.19 NF ep/truck-yr at 10/14 recall; A2: 0.00** | **~8× cleaner than A1, and converts "no pager" → "pager"**. SCREEN |
| Short-fuse warning | A2 only (median 66.5 d, 0/20 NF) | A2 unchanged + H2 at median 116 d | No earlier warning claimed — ceiling is physics. VALIDATED |
| Detection horizon | k\*=10 wk | 10 wk (unchanged) | Triple-confirmed ceiling (G3, X4, P5). VALIDATED |
| RUL output | None (validity statement only) | **Evidence-conditional windows + 95% CI + n per state** | New capability in honest form (D6). VALIDATED inputs, retrospective windows |
| Maintenance economics | Not modeled; tier thresholds by Youden | **Cost-optimal operating point: Youden-queue saves 43% vs run-to-failure at base costs (vs 34% RED-only); flip threshold R=11.5, actual R≈31** | New decision layer. ECON (low/base/high swept; p_convert 0.5–0.9) |
| Fleet-scale value | — | N=5000 @ 4%/yr: ~₹23.4 lakh/yr saving, 76 alerts/wk, 19 inspector-h/wk, break-even R=30.7 | ECON, enrichment bias disclosed (this fleet is 41% failed by construction) |
| Explainability | explanations.json + cards (static) | Evidence card on every alert: archetype, raw-unit drivers, channel history, counterfactual, confidence block | ENG (model is linear — attributions exact) |
| Governance | Manual discipline | Registry + PSI/calibration/alert-volume monitors + refit gates + watchlist + replayable audit trail | ENG |
| Validation status | Retrospective only | + Prospective shadow quarter with pass/fail KPIs (D8 C1) | The single biggest credibility upgrade. PROCESS |
| Blind spots | Documented in reports | Surfaced in product (SMA-dead badges, silence ops-trigger ≤72 h, GREEN caveat) | ENG — turns a known limitation into an operational loop |
| Path beyond ceiling | Listed in exec rec | Funded instrumentation proposal: current clamp/IBS ₹2–15k/truck + trigger high-rate VSI (firmware-only), with break-even case | ECON + SOURCED hardware costs |

## 2. Recall/precision at the recommended operating points (retrospective, n=34)

| Policy | Failed caught | NF burden | Use |
|---|---|---|---|
| A2 (P0) | 4/5 of battery archetype | 0/20 | Battery-first, never suppress |
| H2 dwell (P0 pager) | 10/14 | 5/20 ever; 0.19 ep/truck-yr | The walking pager |
| Youden queue (P1) | 13/14 | 5/20 at threshold | Inspection queue (economics-optimal) |
| Combined policy | 13/14 ≥1 signal | 10/20 fully clean; 4 chronic firers → watchlist | System-level |

## 3. Claims V2 explicitly does NOT make (and why)

1. **No earlier warning than 10 weeks** — physics + prequential decay + density audit all agree;
   the 60–120 d brush-wear channel is destroyed by 5 s sampling (D2 §3).
2. **No day-precision RUL** — calibration and precision are incompatible at 0.0053/wk hazard
   (hazard MAE 576 d vs constant 44 d; D6 §2).
3. **No AUROC improvement from modeling** — every alternative measured-worse or unfittable (D5).
4. **No VIN9_F-class catch** — SMA-dead + terminal silence is invisible to any model on this
   telemetry; the countermeasure is operational (silence trigger), not statistical.
5. **No transfer of these exact numbers to the population fleet** — this 34-truck fleet is
   failure-enriched 41% vs ~2–8%/yr population rates; all fleet-scale figures are parameterized.

## 4. Where the next real improvement comes from

In order of expected value per rupee (D2 §7, D8 C2): (1) current/IBS channel — separates
battery vs cable vs motor, revives mode-specific prognosis; (2) trigger-based high-rate VSI —
near-free, restores the brush-wear lead-time channel; (3) maintenance-record labels — converts
archetypes to supervised failure modes; (4) accumulating failures to n≥30–50 — unlocks the gated
survival/SSL paths. Until then, V2's gains are decision-quality gains, deliberately.
