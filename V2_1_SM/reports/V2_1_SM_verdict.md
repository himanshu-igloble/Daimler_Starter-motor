---
title: "V2.1 Starter Motor — Ship Verdict"
status: complete
created: 2026-06-22
---

# V2.1 Starter Motor — Ship Verdict

**NO new rule clears the accept-bar; H2 remains the recommended pager.**

---

## Accept-Bar (Pre-registered)

A new rule ships only if **all three** conditions hold simultaneously:

| Criterion | Threshold | H2 Baseline |
|-----------|-----------|-------------|
| NF eps/truck-yr | < 0.19 | 0.19 (exactly at bar) |
| Recall | >= 10/14 | 10/14 |
| Median lead | >= 116 d | 116 d |

No rule tested in V2.1 clears all three simultaneously.

---

## Full Comparison Table

| Heuristic | Recall (n/14) | Med Lead (d) | NF ever-fire (n/20) | NF eps/yr | Clears bar? |
|-----------|:---:|:---:|:---:|:---:|:---:|
| **H2_baseline** (recommended) | **10** | **116** | **5** | **0.190** | **—** (baseline) |
| A1_cusum | 7 | 148 | 14 | 0.592 | NO |
| A1_ewma | 7 | 148 | 14 | 0.377 | NO |
| H2 & A2 | 4 | 49 | 0 | 0.000 | NO (recall 4 < 10) |
| H2 & H5 | 7 | 119 | 3 | 0.108 | NO (recall 7 < 10) |
| A1 & H2 | 5 | 133 | 3 | 0.108 | NO (recall 5 < 10) |
| A3_h4_terminal | 13 | 168 | 7 | 0.430 | NO (NF eps 0.43 > 0.19) |

The table confirms the tradeoff is structural: driving NF eps below 0.19 requires recall ≤ 7; achieving recall ≥ 10 requires NF eps ≥ 0.43. H2 sits on the Pareto frontier at the chosen operating point.

---

## Verdict: NO_IMPROVEMENT — H2 Stays

**H2 (persistent-RED dwell) is confirmed as the recommended single deployable pager** at the current operating point (recall 10/14, 0.19 eps/yr, 116 d median lead).

The three reasons no V2.1 candidate supersedes H2:

1. **Recall-FP tradeoff is Pareto-binding.** All conjunctions (A2 family) achieve lower NF eps only by dropping recall well below 10/14. There is no operating point in the tested rule space that beats H2 on both axes simultaneously.

2. **A3 raises recall to 13/14 but at 0.43 eps/yr.** This is a genuine improvement in recall direction, but it exceeds the accepted FP budget by 2.3×. It does not displace H2 at the strict bar.

3. **All three features REJECT.** No new feature adds incremental signal above the modal-4 supervised baseline (AUROC 0.9357). The supervised data ceiling is re-confirmed.

---

## Two Genuine V2.1 Takeaways Worth Shipping

### Takeaway 1 — A3's terminal-state fix: the lever for a "more-recall" operating point

The A3 terminal-state persistence fix reduced NF ever-fire from 20/20 (original H4) to 7/20 while holding recall at 13/14. This is the most promising direction if the organisation ever decides to accept a higher FP budget in exchange for catching 3 additional trucks (recall 13/14 vs H2's 10/14).

**Recommendation:** If the FP budget is revisited, A3_h4_terminal should be the first candidate re-evaluated — it dominates the recall side of the Pareto frontier. The one irreducible miss (VIN9_F_SM) is structurally invisible across all channels and cannot be recovered without new sensor data.

### Takeaway 2 — A5 graded-RUL policy: deployable now

A5 is a triage policy, not a go/no-go detector, so the accept-bar does not gate it. It is deployable now:

- **GREEN (18 trucks):** No near-term action required.
- **persistence_AND_RED (9 trucks):** 126–284 d window (median 206 d) — schedule inspection.
- **A2_battery_cascade (4 trucks):** 28–91 d window — near-term inspection.
- **AMBER_only (3 trucks):** No actionable window (empirically empty).

---

## Feature Verdicts (Work-stream B)

Reconciliation PERFECT: modal-4 nested AUROC = 0.9357, diff = 0.0000.

| Feature | E2 Delta | Verdict |
|---------|----------|---------|
| intercrank_cv_delta90 | +0.0000 | **REJECT** — zero incremental lift |
| z_cold_dip_delta90 | -0.0036 | **REJECT** — marginal negative delta |
| anr_pos_mean_delta90 | -0.0429 | **REJECT** — clear negative delta |

E3 was skipped — no candidate cleared E2. All three REJECTs are consistent with the data ceiling. The supervised model is already extracting the available signal from the 34-truck dataset.

---

## Path Forward

The data ceiling (0.932 AUROC, 10/14 recall at 0.19 eps/yr) is real and will not be broken by additional heuristic or feature engineering on the current data. The real lever is new data:

- **C1:** IBS / current-clamp (direct alternator current measurement)
- **C2:** Hi-rate VSI firmware (sub-second crank resolution)
- **C3:** Full CWR + sale-date (true time-to-failure labels)

See `appendix/C_new_data_appendix.md`.

---

## Caveats

- **SCREEN-GRADE (n=34):** Wide CIs throughout; ±10–15 pp at 80% CI.
- **Multiplicity:** ~7 tests in V2.1; no single result survives Benjamini-Hochberg at q=0.10 on its own.
- **A1 conservative-bias:** Hair-trigger on 3 low-σ NF VINs inflates NF eps slightly.
- **B4 conservative-bias:** z_cold_dip cross-period z-score shrinks estimates for short-span trucks.
