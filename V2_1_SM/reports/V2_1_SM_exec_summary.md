---
title: "V2.1 Starter Motor — Executive Summary"
status: complete
created: 2026-06-22
---

# V2.1 Starter Motor — Executive Summary

## The Question

Can richer heuristics (CUSUM drift detection, rule conjunctions, terminal-state fixes) or new predictive features (inter-crank variability, cold-dip depth, torque trend) improve starter motor failure detection beyond the V1.1 baseline?

---

## The Honest Answer

**No — the data ceiling holds. H2 (persistent-RED dwell) remains the best single deployable pager at the strict accept-bar.**

Seven rule variants and three candidate features were tested. None clears the pre-registered accept-bar (recall ≥ 10/14, NF eps < 0.19/yr, median lead ≥ 116 d) while simultaneously improving on H2. The tradeoff is structural: every rule that cuts false alarms below H2 also loses recall; every rule that raises recall above H2 roughly doubles the false-alarm rate.

There are two genuine wins from V2.1 worth acting on, and one clear path to breaking the ceiling.

---

## Comparison Table

| Rule | Recall (n/14) | Med Lead (d) | NF eps/yr | Ships? |
|------|:---:|:---:|:---:|:---:|
| **H2_baseline** (recommended) | **10** | **116** | **0.19** | **Yes (incumbent)** |
| A1 CUSUM | 7 | 148 | 0.592 | No |
| A1 EWMA | 7 | 148 | 0.377 | No |
| H2 & A2 (conjunct) | 4 | 49 | 0.000 | No — recall too low |
| H2 & H5 (conjunct) | 7 | 119 | 0.108 | No — recall too low |
| A1 & H2 (conjunct) | 5 | 133 | 0.108 | No — recall too low |
| A3 terminal-fix | 13 | 168 | 0.430 | No — FP budget exceeded |

All three new features (inter-crank CV, cold-dip z-score, torque trend): **REJECT** — zero or negative incremental lift over the 0.9357 AUROC modal baseline.

---

## The Two Genuine Wins

**Win 1 — A3 terminal-state fix (recall lever):** Fixing H4's terminal-state persistence dropped NF false-alarms from 20/20 to 7/20 while holding recall at 13/14. This is the best operating point available for a "more-recall" pager, and the recommended option if the organisation ever accepts a slightly higher FP budget (~0.43 eps/yr vs 0.19).

**Win 2 — A5 graded-RUL policy (deployable now):** A5 assigns each truck a risk band and maintenance window without triggering the binary accept-bar. 9 trucks have a 126–284 d inspection window; 4 trucks need near-term attention (28–91 d); 18 are GREEN. This policy is ready to deploy.

---

## The Path to Breaking the Ceiling

The 0.932 AUROC / 10/14 recall ceiling is a data-size limit, not a methods limit. Three data investments can break it:

1. **IBS / current-clamp** — direct alternator current measurement (C1)
2. **Hi-rate VSI firmware** — sub-second crank resolution (C2)
3. **Full warranty history + sale date** — true time-to-failure labels (C3)

Any one of these would materially increase discriminability. See `appendix/C_new_data_appendix.md` for detail.

---

*SCREEN-GRADE analysis (n=34). Wide CIs throughout; ±10–15 pp at 80% CI. ~7 tests; treat individual results cautiously under multiplicity.*
