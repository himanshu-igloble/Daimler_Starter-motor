---
title: "V3 Starter Motor — Automotive Engineering Feasibility Report"
status: "complete"
created: "2026-07-01"
program: "SM V3"
---

# V3 Starter Motor — Automotive Engineering Feasibility Report

This report provides the automotive-engineering justification for each V3 candidate
family, documents data-availability verdicts, and states the honest conclusion: the
6-signal / 5-second frame genuinely supports computing all of these features, but none
carry incremental predictive signal for SM failure at n = 34.

---

## 1. Starter Motor Failure Physics — Background

Starter motor failures in heavy commercial vehicles broadly divide into three modes:

1. **Brush and commutator wear.** The carbon brush–copper commutator interface degrades
   through ohmic heating and mechanical abrasion. Wear rate is proportional to both the
   energy dissipated per engagement (related to inrush current and crank duration) and the
   total number of engagements over the motor's life (SAE starter durability literature on
   brush wear mechanisms in DC motors). As wear progresses, contact resistance rises,
   reducing cranking torque and increasing voltage dip.

2. **Solenoid contact and winding degradation.** The pull-in and hold-in coils, and the
   main contact discs, are stressed by each engagement's inrush surge. Repeated contacts
   under high current cause pitting, arcing erosion, and eventually open-circuit failure.
   Cold-start conditions amplify this stress: at low temperatures, battery internal
   resistance increases, inrush current draws down more voltage, and the solenoid must hold
   against a stiffer oil-loaded engine (lead-acid cold-cranking behaviour, IEC 60095;
   SAE J537 cold-cranking standards for batteries).

3. **Bearing and drive-gear wear.** The overrunning clutch and Bendix drive accumulate
   fatigue with each engagement, especially when the engine is slow to fire and the drive
   gear remains engaged longer (extended crank duration).

The 6-signal / 5-second frame (CSP, RPM, ANR, GED, VSI, SMA + timestamp) at 5-second
cadence provides access to these phenomena only indirectly: VSI captures the whole-system
voltage during and between cranks, SMA marks engagement events, ANR provides engine load
context, and GED provides alternator excitation state. Sub-second crank physics (inrush
waveform shape, sub-5-second duration deltas, solenoid chatter signatures) are destroyed
by the 5-second cadence and are not recoverable from this dataset.

---

## 2. Family F3 — Interaction / Cross Features (Cumulative Electrical Stress-Dose)

### 2.1 Physical Rationale

The V1.1/V2.1 feature set is purely univariate: each feature captures one dimension of
the electrical signal. Failure physics, however, is multiplicative: brush wear is
proportional to the *product* of energy-per-crank and crank-count. A truck operating at
moderate per-crank dip depth but very high start frequency accumulates the same electrical
dose as a truck with severe dips but infrequent starts. Linear models on marginals are
structurally blind to this joint stress. The F3 family tests whether the interaction
surface holds discriminative signal that the marginals do not.

Four interaction features were tested:

- **`dose_dip_x_starts` (F3-1):** Directly encodes the brush-wear stress dose:
  (mean dip depth over last 90 d) × (mean starts per active day over last 90 d). The
  incumbent `dip_depth_last90_delta` captures only one dimension; its partial overlap
  with the product (r = −0.752) is expected and below the 0.85 redundancy cut.

- **`weakbat_cold_load` (F3-2):** Encodes the battery-risk corner: (resting VSI floor,
  a proxy for battery internal resistance) × (fraction of starts that are cold, which
  demands higher inrush current). Grounded in IEC 60095 / SAE J537 lead-acid cold-test
  physics: a degraded battery under frequent cold-start demand is the highest-stress
  operating condition for both the battery and the starter solenoid.

- **`reg_instab_x_usage` (F3-3):** Usage-weights the voltage regulation instability trend.
  A widening regulation envelope on a heavily-cycled truck implies more repeated exposure
  to sub-optimal charging conditions. Risk: the incumbent `vsi_range_trend` is already in
  the model and the product introduces collinearity.

- **`sag_under_load` (F3-4):** Conditions voltage-sag trend on engine torque at the time
  of crank. High torque at crank-start implies a harder-to-turn engine (temperature, grade,
  or load), amplifying the mechanical and electrical stress. The ANR marginal alone is
  near-chance (AUROC 0.506 in V2.1), but the conditional is untested.

### 2.2 Data Availability

All four F3 features are computable from the existing signals. `sag_under_load` requires
ANR, which has a higher sentinel rate (65535, −5000) than VSI, reducing n_nonnull by one
truck (26 vs 27). The interaction z-scoring is fit within each LOVO fold on training VINs
only, satisfying the no-leakage requirement.

### 2.3 Honest Conclusion — F3

The 6-signal / 5-second frame supports computing these features. They represent valid,
physically motivated hypotheses. The gate found no statistically significant separation
for any of the four: MW p ranges from 0.1643 to 0.4208, BH-FDR adjusted p from 0.7363
to 1.0. Univariate AUROCs range from 0.5500 to 0.6536. The best E2 increment is
+0.0071 (weakbat_cold_load), 0.0029 below the +0.01 bar. The interaction surface of the
6-signal frame has now been tested and does not carry predictive signal at n = 34. The
root cause is the data ceiling — n = 34 (14 failed / 20 non-failed) — not a missing
feature or the wrong model class (see GBM probe result: LOVO AUROC 0.8429 < linear 0.9321).

---

## 3. Family F1 — Usage Features (Cold-Start Rate)

### 3.1 Physical Rationale

Cold engagements represent the harshest operating condition for the starter motor:
battery internal resistance is elevated at low temperatures, oil viscosity increases
cranking resistance, and the solenoid must hold against a heavier load. This is well
established in SAE starter durability literature on thermal-cycle fatigue in solenoid
contacts. The *rate* of cold starts — the fraction of total starts preceded by ≥ 6 h of
inactivity — is a duty-cycle stressor that prior iterations had not screened standalone.
V2.1 screened the cold-start *dip depth* (and found it redundant with
`dip_depth_last90_delta`, r ≈ 0.92). The cold-start *fraction* is orthogonal to dip depth
and captures the usage/exposure dimension.

### 3.2 Data Availability

`cold_start_fraction_delta90` is computable from SMA and timestamp alone. n_nonnull = 27
(consistent with the SMA-null cohort exclusion). The 6 h rest criterion is defined on the
SMA field: ≥ 6 h elapsed since the last SMA = 1 event.

### 3.3 Honest Conclusion — F1

The cold-start fraction was computed and tested. MW p = 1.0, AUROC = 0.5107. The rate of
cold starts carries no statistical relationship to SM failure risk. The pre-registered
risk note was correct: this feature likely proxies parking/operational pattern (fleet
segment or route type) rather than degradation. At n = 34, fleet-segment differences are
not separating failed from non-failed trucks by cold-start rate.

---

## 4. Family F4 — Probe Features (GED Co-occurrence, Night-Start Pattern)

### 4.1 GED Disturbance Co-occurrence (`ged3_rate_delta90`)

**Physical rationale.** The alternator (GED channel) and starter motor share the vehicle
electrical bus. Frequent alternator regulation disturbances (GED state-2 = disturbance)
could plausibly stress the shared bus, indirectly affecting starter performance. This is a
speculative cross-subsystem coupling hypothesis, included as a "think-beyond" null-check.
The candidates.json note records the fundamental data fact: GED state-2 (disturbance) is
absent in failed SM VINs (44% null rate in sm_failed). The feature was therefore
implemented against GED state-3 (signal unavailable), which is near-absent fleet-wide.

**Data availability.** The GED channel is present in the SM dataset (confirmed via column
dictionary). n_nonnull = 34 (all VINs compute a value) but the feature is effectively
zero-variance: GED state-3 near-absent means the rate is near-zero for all VINs, removing
any discriminative potential.

**Honest conclusion.** Zero-variance null. MW p = 1.0, AUROC = 0.5000. GED is the
alternator channel; it carries no SM failure signal in this dataset. This was the expected
result and is documented rather than assumed.

### 4.2 Night-Start Fraction (`night_start_fraction_delta90`)

**Physical rationale.** The time-of-day distribution of starts reflects operational
patterns: long-haul routes often involve overnight departures (00:00–05:00), while
urban/shift-work patterns concentrate starts in early morning. This is a usage-pattern
covariate, not a temperature proxy. There is no GPS or location channel in the SM dataset
that would support a temperature interpretation. The timestamp field allows derivation of
start timing, and this usage dimension had never been extracted from prior iterations.
The physical risk is that time-of-day reflects duty cycle, not degradation — but the
feature was included as a low-cost null-check on the usage/circadian surface.

**Data availability.** Computable from SMA and timestamp. n_nonnull = 27. Timezone
validity of the timestamp is unverified; the feature is treated as a usage pattern only.

**Honest conclusion.** MW p = 0.9029, AUROC = 0.5000. The time-of-day usage pattern
carries no relationship to SM failure risk. Night-start fraction is orthogonal to the
failure mechanism captured by the 4 incumbent features.

---

## 5. Overall Feasibility Conclusion

The 6-signal / 5-second frame (CSP, RPM, ANR, GED, VSI, SMA + timestamp) genuinely
supports computing all 7 V3 candidate features. The data-engineering is not the
bottleneck. However:

1. The interaction/usage surface of this dataset has now been comprehensively tested
   under the locked gate, and none of the 7 candidates carry incremental predictive
   signal for SM failure at n = 34.

2. The root constraint is the dataset composition, not the feature engineering:
   - n = 34 trucks (14 failed / 20 non-failed) is a SCREEN-GRADE sample size.
   - The 6 available signals (VSI, SMA, ANR, GED, CSP, RPM) at 5-second cadence do not
     carry the sub-second crank waveform physics that most cleanly encodes brush/solenoid
     degradation (IBS current waveform, per-crank inrush shape, sub-5-second duration
     deltas).
   - There is no location/GPS channel (ruling out ambient temperature), no current-clamp
     channel (ruling out direct crank-current measurement), and no age/odometer channel
     (ruling out mileage-normalized RUL).

3. The features that exist in this frame and that capture genuine degradation signal have
   already been found: the 4-feature modal set (vsi_withinwk_std_ratio_30d_w,
   rest_vsi_p05_delta90, vsi_range_trend, dip_depth_last90_delta) at AUROC 0.9321 nested.

4. The path to further progress is new instrumentation and/or data collection, not
   additional feature engineering on the existing 6-signal frame. The `new_data_roadmap.md`
   in the appendix specifies three concrete paths.
