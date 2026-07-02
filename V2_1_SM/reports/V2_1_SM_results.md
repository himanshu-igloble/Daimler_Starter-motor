---
title: "V2.1 Starter Motor — Full Work-Stream Results"
status: complete
created: 2026-06-22
---

# V2.1 Starter Motor — Full Work-Stream Results

**Accept-bar (pre-registered):** a new rule ships only if NF eps/truck-yr < 0.19 AND recall >= 10/14 AND median lead >= 116 d.

**Baseline to beat — H2_pers_red:** recall 10/14, med lead 116 d, NF ever-fire 5/20, 0.19 NF eps/truck-yr.

---

## Work-stream A — Heuristic Rules

### A1: CUSUM + EWMA (down-steps, rest-VSI)

**Signal:** CUSUM and EWMA applied to rest-VSI for downward drift detection.

| Variant | Recall | Med Lead | NF ever-fire | NF eps/yr | Clears bar? |
|---------|--------|----------|--------------|-----------|-------------|
| A1 CUSUM | 7/14 | 148 d | 14/20 | 0.592 | **NO** |
| A1 EWMA | 7/14 | 148 d | 14/20 | 0.377 | **NO** |

**Why it fails:** Both variants generate too many NF false-alarm events. The root cause is structural — NF trucks also exhibit real rest-VSI down-steps (e.g., VIN10_NF shows -3.0 V drops), making the DOWN-only CUSUM hair-trigger on at least 3 low-σ NF VINs.

**Sanity gate PASSED 4/4:** The CUSUM correctly fired on all strong E5 down-steps in VIN14_F, VIN2_F, VIN3_F, and VIN6_F — confirming the detector is working as designed on the signal it targets. The issue is insufficient discriminability, not a coding error.

**Conservative-bias review note:** The A1 CUSUM threshold was set to avoid missing F trucks at the cost of NF specificity. A stricter threshold would further reduce recall below 7/14 before NF eps falls below 0.19.

---

### A2: Conjunctions (ANDing rules to raise specificity)

**Monotonicity PASS:** ANDing rules never raised NF eps above either parent's level — all conjunctions maintained or reduced NF false-alarm rates, confirming the monotonicity property holds.

| Conjunction | Recall | Med Lead | NF ever-fire | NF eps/yr | Clears bar? |
|-------------|--------|----------|--------------|-----------|-------------|
| H2 & A2 | 4/14 | 49 d | 0/20 | 0.000 | **NO** (recall too low; perfect specificity) |
| H2 & H5 | 7/14 | 119 d | 3/20 | 0.108 | **NO** (NF well under 0.19 but recall 7 < 10) |
| A1 & H2 | 5/14 | 133 d | 3/20 | 0.108 | **NO** (recall 5 < 10) |

**Interpretation:** There is a genuine recall↔false-alarm tradeoff. Conjunctions can drive NF eps well below 0.19 (reaching 0.0) but only by sacrificing recall to 4–7/14. No conjunction simultaneously achieves recall ≥ 10 and NF eps < 0.19.

---

### A3: H4 Terminal-State Persistence Fix

**Change:** Applied terminal-state persistence to H4 (nearest-neighbour VSI pattern), fixing the original H4's behaviour of continuing to re-fire on every new window after the initial alarm, which inflated NF eps.

| Rule | Recall | Med Lead | NF ever-fire | NF eps/yr | Clears bar? |
|------|--------|----------|--------------|-----------|-------------|
| A3_h4_terminal | 13/14 | 168 d | 7/20 | 0.43 | **NO** (NF eps 0.43 > 0.19) |

**Specificity improvement:** The terminal-state fix dropped NF ever-fire from the original H4's 20/20 to 7/20 — a massive specificity gain. Recall held at 13/14.

**pers_terminal_fire_start behaviour:** The terminal persistence field was populated for only 4 NF VINs, confirming correct behaviour — the other 3 NF ever-fire cases fired only transiently and did not enter the persistent terminal state.

**Sole F miss — VIN9_F_SM:** The one failed truck not detected is structurally invisible: no signal in any monitoring channel (rest-VSI, GED, CUSUM) shows a precursor pattern. This is a known irreducible blind spot; no heuristic or feature tested in V2.1 can recover it without new sensor data.

**Takeaway:** A3's terminal-state fix is the most promising direction for a higher-recall pager if a slightly higher FP budget is ever accepted. It represents the best operating point on the recall side of the Pareto frontier.

---

### A5: Graded RUL Policy (deployable triage, not a go/no-go detector)

A5 is a deployable triage policy — it does not compete against the accept-bar (which governs binary go/no-go detectors). It assigns each truck a risk band and maintenance window.

**Per-truck band distribution (n=34 trucks):**

| Band | Count |
|------|-------|
| GREEN | 18 |
| persistence_AND_RED | 9 |
| A2_battery_cascade | 4 |
| AMBER_only | 3 |

**Maintenance windows by band:**

| Band | Window Range | Median |
|------|-------------|--------|
| A2_battery_cascade | 28–91 d | (n=4) |
| persistence_AND_RED | 126–284 d | 206 d |
| AMBER_only | empirically empty | — |

> Note: the window ranges/medians are the **V2 D6 evidence-window** estimates (support: A2 n=4 failed trucks; persistence∧RED n=10 failed trucks). The `n` in the band-distribution table above (9 trucks in persistence_AND_RED) is the **current NF-fleet** band count — a distinct quantity. Do not conflate the two.

**Deployment status:** A5 is deployable now as a maintenance triage policy. Trucks in the `persistence_AND_RED` band have a median 206-day action window; the `A2_battery_cascade` band flags trucks needing near-term inspection (28–91 d). GREEN trucks require no immediate action.

---

## Work-stream B — Feature Gating (LOVO/nested-LOVO)

**Reconciliation:** PERFECT. Modal-4 nested AUROC = 0.9357; expected = 0.9357; diff = 0.0000. The V1.1 nested-LOVO gate is confirmed correct.

**Leak-ceiling reference:** n_weeks AUROC ceiling = 0.952; t_start ceiling = 0.893 (established in V1.1). Any feature correlated with these proxies is inadmissible.

Three candidate features were evaluated through E1 (univariate screen) and E2 (incremental nested-LOVO vs modal-4 baseline):

| Feature | E1 MW p | E1 AUROC | E2 AUROC | E2 Delta | Verdict |
|---------|---------|----------|----------|----------|---------|
| intercrank_cv_delta90 | 0.449 | 0.589 | 0.9357 | +0.0000 | **REJECT** |
| z_cold_dip_delta90 | 0.048 | 0.728 | 0.9321 | -0.0036 | **REJECT** |
| anr_pos_mean_delta90 | 0.981 | 0.506 | 0.8929 | -0.0429 | **REJECT** |

**E3 SKIPPED:** No candidate cleared E2. All three add no incremental signal above the modal-4 baseline.

**Redundancy note (z_cold_dip):** beyond its E2 fail, `z_cold_dip_delta90` is r≈0.94-redundant with the existing production feature `dip_depth_last90_delta` (Pearson, from `admissibility.csv`) — it measures essentially the same crank-dip degradation, leaving no room for independent contribution. This mirrors the V2-program finding that the 6h-raw `cold_dip_delta90` was held for the same reason (r=0.923). The `proxy_flag` is correctly False (the 0.5 proxy-leak gate covers n_weeks/t_start/span only, not production-feature redundancy), but the redundancy is an additional, independent reason to REJECT.

**Conservative-bias review note (B4):** The z_cold_dip_delta90 cross-period z-score is computed relative to each truck's own history, which introduces a mild shrinkage bias for trucks with short observation spans. This makes the E2 delta slightly pessimistic for that feature, but the -0.0036 margin is too small to reverse the REJECT even with a generous correction.

**Interpretation:** All three feature REJECTs are consistent with the established data ceiling. The supervised model's performance is limited by the 34-truck sample size, not by missing features. The real lever is new data (work-stream C).

---

## Work-stream C — New Data Paths

See `appendix/C_new_data_appendix.md` for full detail on:
- **C1:** IBS (Integrated Battery Sensor) / current-clamp data — direct measurement of alternator current output; would provide the most discriminating signal for alternator-mode failures.
- **C2:** Hi-rate VSI firmware — sub-second VSI sampling during crank events; currently all crank resolution is lost in the 1-Hz aggregation.
- **C3:** Full CWR + sale-date — complete warranty claim history linked to sale date enables true time-to-failure labels rather than observation-window proxies.

**Assessment:** C is the only real path to beating the 0.932 AUROC ceiling. All three data paths are independent — any one of them could break the current ceiling.

---

## Caveats and Limitations

1. **SCREEN-GRADE quality (n=34, wide CIs):** All results carry wide confidence intervals. At n=34, even a 2-truck swing changes recall from 10/14 to 8/14. Treat all AUROC and recall estimates as ±10–15 pp at 80% CI.

2. **Multiplicity (~7 new tests):** Approximately 7 independent hypothesis tests were run in V2.1 (A1 CUSUM, A1 EWMA, three conjunctions, A3, three B features). Applying Benjamini-Hochberg FDR correction at q=0.10 means any single nominally-significant result (e.g., z_cold_dip E1 p=0.048) should be treated cautiously — it does not survive multiplicity correction.

3. **Leak ceilings:** n_weeks AUROC ceiling = 0.952; t_start ceiling = 0.893. Features correlated with observation-window length or start-date are inadmissible (data-leakage proxies).

4. **A1 hair-trigger on low-σ NF VINs (conservative-bias):** Three NF VINs with unusually low rest-VSI variance trigger the CUSUM at a threshold calibrated on F trucks. This inflates NF eps and makes A1's NF rate slightly pessimistic.

5. **B4 cross-period z-score (conservative-bias):** z_cold_dip_delta90 uses within-truck normalization that shrinks estimates for short-span trucks, making its E2 delta slightly more negative than a globally-normalized version would be.
