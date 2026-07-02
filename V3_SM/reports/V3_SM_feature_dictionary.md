---
title: "V3 Starter Motor — Feature Dictionary"
status: "complete"
created: "2026-07-01"
program: "SM V3"
sources: "V3_gate_summary.json, V3_validation.json, V3_SM_spec.md §4, V3_candidates.json"
---

# V3 Starter Motor — Feature Dictionary

Seven candidates were pre-registered, engineered, and adjudicated through the locked
V1.1/V2.1 gate. All 7 received a REJECT verdict. This dictionary is the permanent record
of what was built, why it was physically motivated, and exactly why it did not ship.

Interaction features use within-fold z-scoring before multiplication:
z(A) = (A − μ_train) / σ_train, computed separately per fold on training VINs only.
The product z(A)·z(B) encodes genuine multiplicative interaction rather than a rescaled
marginal, avoids raw-voltage scale domination, and keeps both factors orthogonal to
their own marginals. Orientation of the predictive sign is resolved empirically by
oriented AUROC in E1 (AUROC reported as the larger of the two directions).

---

## F3-1 — `dose_dip_x_starts`

**Physical justification.** Starter brush, commutator, and contact wear accumulate as a
cumulative electrical dose: the energy drawn per crank event (proportional to the voltage
dip depth) multiplied by the total number of cranks. A truck with moderate per-crank dips
but very high start frequency, or with severe dips but infrequent starts, is invisible to
either marginal signal alone. The product captures the joint "high energy × high count"
stress corner that drives thermal and mechanical degradation in the solenoid winding and
the brush-ring interface (per SAE starter durability literature on brush wear mechanisms).

**Mathematical definition.**
```
dose_dip_x_starts = z(dip_depth_last90_level) · z(starts_per_active_day_last90)
```
where `dip_depth_last90_level` is the mean voltage dip depth (pre-crank baseline VSI −
minimum VSI during crank) over the last 90 days, `starts_per_active_day_last90` is the
mean number of crank sessions per active day over the same window, and z(·) is the
within-fold standardizer fit on training VINs only.

**Required raw signals.** VSI, SMA, timestamp.

**Data availability.** Computable; n_nonnull = 27 / 34 (7 VINs excluded via SMA-null or
insufficient window, consistent with the established SMA-dead cohort convention).

**Pre-registered expected power.** M (Medium) — the headline interaction candidate;
primary risk flagged as partial redundancy with incumbent `dip_depth_last90_delta`.

**Realized result.**
- E1: MW p = 0.2515 (threshold ≤ 0.10 → FAIL); oriented AUROC = 0.6143 (≥ 0.60 → pass).
- Proxy audit: max |r| vs {n_weeks, t_start, span} = 0.158 (r(n_weeks) = 0.158) → no flag.
- Redundancy audit: max |r| vs modal-4 = 0.752 (r vs dip_depth_last90_delta = −0.752).
  Below the 0.85 cut → no flag; partial overlap documented.
- E2: AUROC = 0.9321, Δ = −0.0036 → below +0.01 bar.

**Screened verdict. REJECT** — E1 failed on MW p (0.2515 > 0.10); the univariate
separation is not statistically significant on this fleet. E2 confirmed no incremental
value (Δ = −0.0036).

---

## F3-2 — `weakbat_cold_load`

**Physical justification.** A battery with a low resting-voltage floor (high internal
resistance, partial sulfation) poses heightened risk only when it is also frequently called
upon to deliver cold-start current. Cold cranking draws substantially higher current than
warm cranking due to increased oil viscosity and reduced battery capacity at low
temperatures (lead-acid cold-cranking physics, per IEC 60095 cold-test standards and SAE
J537). The product captures the "weak AND worked-hard" operating corner; neither marginal
alone identifies it.

**Mathematical definition.**
```
weakbat_cold_load = z(rest_vsi_p05_last90) · z(cold_start_fraction_last90)
```
where `rest_vsi_p05_last90` is the 5th-percentile of resting-state VSI over the last 90
days, `cold_start_fraction_last90` is the fraction of crank sessions preceded by ≥ 6 h of
inactivity, and z(·) is the within-fold standardizer.

**Required raw signals.** VSI, SMA, timestamp.

**Data availability.** Computable; n_nonnull = 27 / 34.

**Pre-registered expected power.** L-M — risk flagged as cold-start rate sparsity per VIN.

**Realized result.**
- E1: MW p = 0.4208 (FAIL); oriented AUROC = 0.5500 (FAIL — below 0.60).
- Proxy audit: max |r| vs {n_weeks, t_start, span} = 0.299 → no flag.
- Redundancy audit: max |r| vs modal-4 = 0.338 (vs vsi_range_trend) → no flag.
- E2: AUROC = 0.9429, Δ = +0.0071 → best incremental candidate, but below +0.01 bar.
- BH-FDR adjusted p = 0.7363 (smallest in the cohort — still far from significance).
- GBM in-sample signal: SHAP mean abs = 0.785, permutation importance = 0.1049 — moderate
  in-sample weight. Zero held-out gain (E2 Δ = +0.0071). Classic small-n overfit signature.

**Screened verdict. REJECT** — E1 failed on both MW p (0.4208) and oriented AUROC (0.5500);
E2 increment (+0.0071) below the pre-registered +0.01 bar; GBM in-sample weight without
held-out gain is an overfit artifact, not a signal.

---

## F3-3 — `reg_instab_x_usage`

**Physical justification.** A widening voltage-regulation envelope (increasing trend in
the intra-week VSI range) is a candidate marker of alternator or regulator degradation
affecting the charging circuit. Its relevance to starter wear should scale with the
number of start events: a heavily-cycled truck is exposed more often to any regulation
anomaly. The interaction usage-weights the instability trend, providing a feature that
may separate degraded-and-busy trucks from degraded-but-lightly-used ones. Risk: the
incumbent `vsi_range_trend` is already in the modal-4 set, so the product may add only
collinearity.

**Mathematical definition.**
```
reg_instab_x_usage = z(vsi_range_trend) · z(starts_per_active_day_last90)
```
where `vsi_range_trend` is the Theil–Sen slope of the weekly intra-week VSI range over
the observation window, and `starts_per_active_day_last90` is as defined in F3-1.

**Required raw signals.** VSI, SMA, timestamp.

**Data availability.** Computable; n_nonnull = 27 / 34.

**Pre-registered expected power.** L — collinearity with incumbent flagged as primary risk.

**Realized result.**
- E1: MW p = 0.1643 (best raw p in the cohort, but FAIL — threshold ≤ 0.10); oriented
  AUROC = 0.6536 (best univariate AUROC in the cohort; passes ≥ 0.60).
- Proxy audit: r(n_weeks) = 0.430 — the faint signal is partially correlated with
  observation length; max |r| vs {n_weeks, t_start, span} = 0.430. Below 0.50 flag cut,
  but the exposure confound is real and noted.
- Redundancy audit: max |r| vs modal-4 = 0.587 (vs vsi_range_trend, as expected) → no flag.
- E2: AUROC = 0.9393, Δ = +0.0036 → below +0.01 bar.

**Screened verdict. REJECT** — E1 failed on MW p (0.1643 > 0.10); the modest univariate
AUROC (0.6536) is partly driven by exposure length (r(n_weeks) = 0.430), not demonstrated
degradation physics. E2 confirmed no actionable increment.

---

## F3-4 — `sag_under_load`

**Physical justification.** The ANR marginal (mean pre-crank engine torque) was screened
in V2.1 and is near-chance (AUROC 0.506, MW p = 0.981). However, the crank voltage sag
conditioned on high engine load — i.e., situations where the engine is harder to turn
over — is a sharper mechanical-stress proxy. Under high resistive load, a starter with
worn brushes or a weakened solenoid contact will exhibit a greater proportional voltage
collapse. The product z(dip_depth_delta90) · z(ANR_pre_crank_60s) is the untested
interaction that the ANR marginal failure cannot rule out.

**Mathematical definition.**
```
sag_under_load = z(dip_depth_delta90) · z(ANR_pre_crank_60s)
```
where `dip_depth_delta90` is the Δ90 trend in voltage dip depth and `ANR_pre_crank_60s`
is the mean engine torque in the 60 s preceding each crank event. z(·) is within-fold.

**Required raw signals.** VSI, SMA, ANR, timestamp.

**Data availability.** Computable; n_nonnull = 26 / 34 — one extra missing VIN relative to
VSI-only features, attributable to ANR sentinel (65535 / −5000) sparsity in some VINs.

**Pre-registered expected power.** L-M — risks: ANR pre-crank sparsity; ANR marginal is
near-chance suggesting mechanical load may not discriminate.

**Realized result.**
- E1: MW p = 0.3502 (FAIL); oriented AUROC = 0.5946 (FAIL — below 0.60).
- Proxy audit: max |r| vs {n_weeks, t_start, span} = 0.211 → no flag.
- Redundancy audit: max |r| vs modal-4 = 0.299 (vs rest_vsi_p05_delta90) → no flag.
- E2: AUROC = 0.9357, Δ = 0.0000.

**Screened verdict. REJECT** — E1 failed on both MW p and oriented AUROC; conditioning
crank sag on ANR load provides no discriminative information beyond the incumbent features.

---

## F1b — `cold_start_fraction_delta90`

**Physical justification.** Cold-start engagements (preceded by ≥ 6 h rest) draw
substantially higher current than warm restarts due to increased oil viscosity and reduced
battery capacity, stressing starter motor windings, brushes, and solenoid contacts (SAE
starter durability literature on thermal cycling and brush wear). Prior iterations (V2.1
B3/B4) screened the cold-start voltage dip depth and found it redundant with the incumbent
`dip_depth_last90_delta` (r ≈ 0.92). The *rate* of cold starts — fraction of all starts
that are cold — is a distinct usage-stressor covariate and was never screened standalone.

**Mathematical definition.**
```
cold_start_fraction_delta90 = mean(cold_frac, last-90d) − mean(cold_frac, per-VIN baseline)
```
where `cold_frac` is the fraction of crank sessions on a given active day preceded by ≥ 6 h
of SMA-inactive time. Δ90 = (last-90-day mean) − (per-VIN baseline mean).

**Required raw signals.** SMA, timestamp.

**Data availability.** Computable; n_nonnull = 27 / 34.

**Pre-registered expected power.** L — risk: fraction proxies parking/exposure pattern,
not starter degradation.

**Realized result.**
- E1: MW p = 1.0000 (FAIL); oriented AUROC = 0.5107 (FAIL — at chance).
- Proxy audit: max |r| vs {n_weeks, t_start, span} = 0.094 → no flag.
- Redundancy audit: max |r| vs modal-4 = 0.132 → no flag.
- E2: AUROC = 0.9286, Δ = −0.0071 → negative increment.

**Screened verdict. REJECT** — E1 failed completely (MW p = 1.0, AUROC at chance);
the rate of cold starts has no relationship to SM failure risk at n = 34.

---

## F4a — `ged3_rate_delta90`

**Physical justification.** GED (alternator excitation state) is a cross-subsystem
"think-beyond" null-check. A truck experiencing frequent alternator regulation disturbances
might simultaneously stress the electrical system that the starter shares (shared bus
voltage, battery state). GED state-2 (disturbance) is the signal of interest; however,
this state is absent from failed SM VINs in this dataset (44% null rate in sm_failed). The
feature was therefore implemented as a delta of GED state-3 (signal unavailable) rate,
which is near-absent fleet-wide. Expected result was VL (very low) / null, and that is
what was observed — a zero-variance feature.

**Mathematical definition.**
```
ged3_rate_delta90 = mean(ged3_rate, last-90d) − mean(ged3_rate, per-VIN baseline)
```
where `ged3_rate` is the fraction of timesteps per active day with GED = 3 (signal
unavailable). GED state-2 (disturbance) was confirmed absent in failed SM VINs.

**Required raw signals.** GED, timestamp.

**Data availability.** n_nonnull = 34 / 34 (feature computes for all VINs; effectively
zero-variance fleet-wide due to near-absence of GED state-3).

**Pre-registered expected power.** VL (Very Low) — GED is the alternator channel; expected
null documented pre-registration.

**Realized result.**
- E1: MW p = 1.0000 (FAIL); oriented AUROC = 0.5000 (FAIL — at chance).
- Proxy audit: all proxy/redundancy correlations = null (zero-variance prevents computation).
- E2: AUROC = 0.9357, Δ = 0.0000.

**Screened verdict. REJECT** — zero-variance null; GED state-3 is near-absent fleet-wide
and state-2 is absent in failed SM VINs; AUROC = 0.5000, MW p = 1.0. The null was
expected and is documented.

---

## F4b — `night_start_fraction_delta90`

**Physical justification.** The time-of-day distribution of starts is a usage/circadian
signature that distinguishes long-haul operations (overnight starts, warm idling) from
urban shift-work patterns (early-morning cold starts). This is a usage covariate, not a
temperature proxy — there is no GPS or location channel in this dataset to support a
temperature interpretation. Starts in the 00:00–05:00 window were never derived from the
timestamp field in prior iterations. Expected to be a weak or null discriminator as it
captures duty-cycle pattern rather than degradation physics.

**Mathematical definition.**
```
night_start_fraction_delta90 = mean(night_frac, last-90d) − mean(night_frac, per-VIN baseline)
```
where `night_frac` is the fraction of crank sessions initiated in the fixed 00:00–05:00
window on each active day. Δ90 = (last-90-day mean) − (per-VIN baseline mean).
Note: timestamp timezone is unverified; the feature is treated as a usage pattern only.

**Required raw signals.** SMA, timestamp.

**Data availability.** Computable; n_nonnull = 27 / 34.

**Pre-registered expected power.** L — usage pattern, not damage signal.

**Realized result.**
- E1: MW p = 0.9029 (FAIL); oriented AUROC = 0.5000 (FAIL — at chance).
- Proxy audit: max |r| vs {n_weeks, t_start, span} = 0.106 → no flag.
- Redundancy audit: max |r| vs modal-4 = 0.246 (vs dip_depth_last90_delta) → no flag.
- E2: AUROC = 0.9393, Δ = +0.0036 → below +0.01 bar.

**Screened verdict. REJECT** — E1 failed completely (MW p = 0.9029, AUROC at chance);
time-of-day usage pattern carries no relationship to SM failure risk at n = 34.

---

## Summary Table

| Feature | Family | Exp. Power | n_nonnull | MW p | Oriented AUROC | E2 Δ | BH-FDR adj-p | Verdict |
|---|---|---|---|---|---|---|---|---|
| dose_dip_x_starts | F3 interaction | M | 27 | 0.2515 | 0.6143 | −0.0036 | 0.8803 | REJECT |
| weakbat_cold_load | F3 interaction | L-M | 27 | 0.4208 | 0.5500 | +0.0071 | 0.7363 | REJECT |
| reg_instab_x_usage | F3 interaction | L | 27 | 0.1643 | 0.6536 | +0.0036 | 1.0000 | REJECT |
| sag_under_load | F3 interaction | L-M | 26 | 0.3502 | 0.5946 | 0.0000 | 0.8171 | REJECT |
| cold_start_fraction_delta90 | F1 usage | L | 27 | 1.0000 | 0.5107 | −0.0071 | 1.0000 | REJECT |
| ged3_rate_delta90 | F4 probe | VL | 34 | 1.0000 | 0.5000 | 0.0000 | 1.0000 | REJECT |
| night_start_fraction_delta90 | F4 probe | L | 27 | 0.9029 | 0.5000 | +0.0036 | 1.0000 | REJECT |

E1 threshold: MW p ≤ 0.10 AND oriented AUROC ≥ 0.60 (both required).
E2 threshold: Δ AUROC ≥ +0.01 over modal-4 non-nested baseline (0.9357).
BH-FDR: Benjamini–Hochberg correction on 7 simultaneous tests. Smallest adjusted p = 0.7363
(weakbat_cold_load). Nothing is significant under any reasonable FDR control.
