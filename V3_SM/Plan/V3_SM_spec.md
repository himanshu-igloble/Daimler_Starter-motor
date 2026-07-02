---
title: "V3 Starter Motor — Feature Engineering & Research Iteration (Design Spec)"
status: "draft"
created: "2026-07-01"
program: "SM V3"
supersedes_context: "V1 (v1-sm), V1.1 (0.9321 nested), V2_program (ceiling confirmed + v2_system), V2.1 (NO_IMPROVEMENT / all HOLD)"
accept_bar: "ADD a candidate feature iff E2 fixed-subset LOVO ΔAUROC ≥ +0.01 over the modal-4 baseline (0.9357 non-nested); E3 nested rerun is confirmatory and EXPLORATORY. Report all outcomes, including all-HOLD."
posture: "Rigorous investigate-and-report. Honest accept/reject. Negatives are results."
---

# V3 Starter Motor — Feature Engineering & Research Iteration

## 1. Objective

Discover, engineer, and **honestly adjudicate** new predictive features for the Starter
Motor (SM) predictive-maintenance system, concentrating effort on the parts of the
feature space that prior iterations left genuinely untested — chiefly **interaction /
cross features** and a small set of **restart-clustering / usage** features — and run
every candidate through the pre-locked V1.1/V2.1 feature gate.

This is a **feature-value investigation**, not an AUROC chase. A candidate ships only if
it clears the pre-registered incremental bar; the expected and fully acceptable outcome
is a rigorous **mostly-negative result** that (a) closes off families cleanly with
evidence, (b) tests the interaction/usage surface for the first time under the locked
protocol, and (c) leaves behind a reusable feature dictionary + a new-data roadmap. If an
interaction feature *does* clear the bar, that is a genuine, defensible win.

**Primary evaluation target:** the established binary **failure-risk classifier at the
10-week horizon**, scored by **leave-one-VIN-out (LOVO) AUROC**, apples-to-apples with
the frozen baseline. RUL regression and unsupervised anomaly detection are **not** V3
targets — both were already shown to fail on this fleet (RUL cannot beat the fleet clock;
unsupervised anomaly runs 80–100% FP at n=34). Any feature that genuinely encodes
degradation will manifest as classifier lift, which is the cleanest single arbiter.

## 2. Background & binding constraints

The SM program is mature. Four established facts bound this iteration and **must not be
re-litigated**:

1. **Data ceiling, not method ceiling.** Nested-LOVO AUROC = **0.9321** at a **10-week**
   (~70 d) horizon, triple-evidenced (prequential decay-to-chance at k=11; density audit
   r(failed, n_weeks) = −0.771; X4 reconciliation 4.4e-16 / 0.9357). With **n=14 failed /
   20 non-failed** trucks, honest probes saturate ~0.89–0.93 ("one degree of freedom").
2. **More features degrade this model.** The best two prior candidates
   (`cold_dip_delta90`, `rpm_rise_lag_delta90`) scored **+0.0000** incremental lift; a
   12-feature pool expansion dropped nested AUROC to **0.875** (−0.057). The production
   set stays at **4 features**: `vsi_withinwk_std_ratio_30d_w`, `rest_vsi_p05_delta90`,
   `vsi_range_trend`, `dip_depth_last90_delta`.
3. **The 6-signal / 5-second frame is fixed.** Available signals are CSP, RPM, ANR, GED,
   VSI, SMA + `timestamp`. There is **no location/GPS**, no current channel, no
   temperature channel, no SoC. The 5-second cadence destroys sub-second crank waveform
   physics (inrush, true dip shape, sub-5-s duration deltas, solenoid chatter).
4. **A strict, pre-registered gate already rejected the obvious candidates** (see §2.1).
   V3 must not re-run them; it must find and test what they did **not** cover.

### 2.1 Already settled — do NOT re-run

Consolidated from `V1.1/discovery/`, `V2_program/probes/`, and
`V2.1/features/out/V2_1_gate_summary.json`:

| Candidate | Prior verdict / numbers | Source |
|---|---|---|
| Duty-cycle: **cranks/day + trend** | **WEAK** — no cluster/trend separation; retry-slope AUROC 0.500, p=1.0 | E5_maintenance, P5_aging_drift |
| **Inter-crank-interval CV** (`intercrank_cv_delta90`) | **REJECT** — E1 AUROC 0.589, MW p=0.449; E2 +0.0000 | V2.1 B2 |
| Post-crank VSI **recovery slope** | **WEAK** — AUROC 0.552, p=0.678 (regulator property, not starter) | P2_vsi_recovery_dynamics |
| **≥6/≥8 h cold-start dip depth** (`cold_dip_delta90`, `z_cold_dip_delta90`) | **REJECT/HOLD** — r=0.923 / 0.938 redundant with `dip_depth_last90_delta`; E2 +0.0000 / −0.0036 | V2 P3, V2.1 B4 |
| **ANR load** marginal (`anr_pos_mean_delta90`) | **REJECT** — AUROC 0.506, MW p=0.981; E2 −0.0429 | V2.1 B5 |
| **RPM rise lag** (`rpm_rise_lag_delta90`) | **HOLD** — E2 +0.0000, MW p=0.054 | V2 |
| Crank **session anatomy** (per-session metrics) | **WEAK** — all p>0.1, AUROC 0.54–0.68 | P1_crank_session_anatomy |
| Lifetime **aging drift** / spectral | **ARTIFACT** — n_weeks confound; `vsi_dominant_freq` = 1/n_weeks (**BANNED**) | P5, V1.1 B_feature_audit §1.4 |
| Seasonality (month effect on VSI) | **NULL** — KW p=0.90 (drive-std), p=0.95 (rest) | V1.1 E4 |

### 2.2 Genuinely untouched — in scope for V3

| ID | Item | Why it is novel (what prior work did NOT cover) |
|---|---|---|
| **F3** | **Interaction / cross features** | No prior iteration tested *products* of features. A linear Ridge on marginals is structurally blind to a multiplicative stress-*dose*; the rejected marginals (ANR load, cranks/day) may carry signal only *conditioned on* another factor. This is the headline gap. |
| **F1a** | **Restart temporal-clustering** (`restart_burst_rate`) | Settled work covered crank *count/day* and inter-crank *interval CV*; neither measures short-window **burst clustering** (≥2 cranks within ~10 min = hard-start / repeated-attempt episodes). |
| **F1b** | **Cold-start *rate*** (`cold_start_fraction`) | B3/B4 tested the cold-start *dip depth* (rejected, redundant). The **frequency** of cold starts (fraction of starts after ≥6 h rest) as a usage covariate was never screened standalone. |
| **F4a** | **GED-disturbance co-occurrence in SM** | GED (alternator excitation state) has never been evaluated as an SM-failure covariate. Expected null (it is the alternator's channel; 44% null in sm_failed), but the brief's "think beyond" ask makes it a cheap, worthwhile null-check. |
| **F4b** | **Night-start fraction** (`night_start_fraction`) | Time-of-day of starts (a circadian/**usage** pattern, explicitly *not* a temperature proxy) has never been derived from `timestamp`. |
| **F4c** | **VSI recovery *time-to-baseline*** | Distinct from the settled recovery *slope* (WEAK): elapsed time (s) for post-crank VSI to return to pre-crank baseline. |

## 3. Scope

**In scope:** F3 (4 interaction features — priority), F1a/F1b (2 restart-usage features),
F4a/F4b/F4c (3 breadth null-checks). **≈9–10 candidates total** — deliberately capped;
at n=34 a wide net manufactures false positives even through the gate. Plus: the full
deliverable set (§9), a per-feature dictionary (§4), validation analytics (correlation,
MI, permutation importance, SHAP, degradation-trend viz, significance tests), and a
new-data roadmap.

**Out of scope (YAGNI / already closed):** everything in §2.1; ambient-temperature /
weather reconstruction (data-blocked — no location channel; one short infeasibility note
only, §8); RUL regression and unsupervised anomaly (closed with numbers); deep/sequence
models and SSL crank-encoders (closed); new production plumbing (`v2_system/` exists —
integrating any V3 winner is a follow-on, *only if something ships*).

## 4. Feature families & pre-registered definitions

> **Post-execution note (2026-07-01):** executed with **7 candidates**, all **REJECTED** (ceiling
> holds at 0.9357/0.9321). Refinements applied *before* running (recorded in the implementation
> plan's "Refinements vs committed spec"): F1a `restart_burst_rate` dropped — already represented
> by the pooled `retry_burst_rate_last90` in the V1.1 matrix; F4a reframed to `ged3_rate_delta90`
> (GED state-2 is absent from failed SM, so a "disturbance" feature is undefined); F4c
> `vsi_recovery_time` left optional/not-run. The pre-registration below is preserved as originally
> written. See `reports/V3_SM_verdict.md`.

All features are **window-anchored** for leakage safety: computed either over the **last
N days before a per-VIN censor point** or as a **delta vs the VIN's own early-history
baseline**. No feature may use `n_weeks`, `t_start`, calendar span, `SALEDATE`,
`JCOPENDATE`, or any post-censor information. Crank events and sessions reuse the existing
`STARTER MOTOR/src/V1_SM_crank_events.py` extraction **verbatim** (SMA==1 grouping;
session gap > 60 s ⇒ new session; duration > 60 s ⇒ artifact, excluded) so definitions
stay identical to prior work.

Notation: `dip_depth` = pre-crank baseline VSI − min VSI during crank; `rest_vsi_p05` =
5th-percentile idle VSI; `starts/day` = crank sessions per active day; `Δ90` = (last-90-d
mean) − (per-VIN baseline mean); `TS-slope` = Theil–Sen slope; `active day` = a day with
≥1 valid crank session. **Interaction factors are standardized (z-scored) within each
training fold before multiplication** — so each product encodes genuine interaction rather
than a rescaled marginal (this also prevents raw-voltage scale-domination and collinearity
with the marginals); the standardizer is fit on training VINs only (no leakage), and the
final predictive sign is resolved by oriented AUROC in E1.

### 4.1 Candidate table (feature dictionary — seed)

| ID | Feature | Mathematical definition | Raw signals | Availability | Exp. power | Primary risk |
|---|---|---|---|---|---|---|
| F3-1 | `dose_dip_x_starts` | `z(dip_depth_last90) · z(starts_per_active_day_last90)` | VSI, SMA, ts | ✅ computable | **M** | redundancy w/ `dip_depth_last90_delta` |
| F3-2 | `weakbat_cold_load` | `z(rest_vsi_p05_last90) · z(cold_start_fraction_last90)` | VSI, SMA, ts | ✅ computable | L–M | cold-start rate sparsity per VIN |
| F3-3 | `reg_instab_x_usage` | `z(vsi_range_trend) · z(starts_per_active_day_last90)` | VSI, SMA, ts | ✅ computable | L | `vsi_range_trend` already a winner (collinearity) |
| F3-4 | `sag_under_load` | `z(dip_depth_delta90) · z(ANR_pre_crank_60s)` | VSI, SMA, ANR, ts | ✅ computable | L–M | ANR pre-crank sparsity; ANR marginal is chance |
| F1a | `restart_burst_rate_delta90` | Δ90 of (episodes with ≥2 crank sessions within a 10-min window, per active day) | SMA, ts | ✅ computable | L | 5-s cadence coarsens 10-min windows; rare |
| F1b | `cold_start_fraction_delta90` | Δ90 of (fraction of starts preceded by ≥6 h rest) | SMA, ts | ✅ computable | L | proxies exposure/parking, not degradation |
| F4a | `ged_disturb_cooccur` | rate of GED∈{2} readings per active day, Δ90 (co-occurrence screen) | GED, ts | ⚠ 44% null (sm_failed) | **VL** | GED is the alternator channel; mostly null |
| F4b | `night_start_fraction_delta90` | Δ90 of (fraction of starts in a fixed 00:00–05:00 window) | SMA, ts | ✅ computable | L | `timestamp` tz unknown; usage not damage |
| F4c | `vsi_recovery_time_delta90` | Δ90 of (median seconds for post-crank VSI to return to ≥ pre-crank baseline) | VSI, SMA, ts | ⚠ 5-s floor | L | quantized to ≥5 s; recovery *slope* already WEAK |

### 4.2 Physical rationale (per candidate)

- **F3-1 `dose_dip_x_starts`** — brush/commutator/contact wear is a *cumulative* electrical
  dose: (energy per crank ∝ dip depth) × (number of cranks). A truck with moderate dips
  but very high start frequency, or vice-versa, is invisible to either marginal alone.
- **F3-2 `weakbat_cold_load`** — a weak battery (low rest-VSI floor) is only *dangerous*
  when frequently asked to deliver cold-start current; the product captures the "weak AND
  worked-hard" corner.
- **F3-3 `reg_instab_x_usage`** — a widening regulation envelope matters more on a
  heavily-cycled truck; usage-weights the regulator-instability trend.
- **F3-4 `sag_under_load`** — the ANR marginal is near-chance (AUROC 0.506), but crank
  voltage sag *conditioned on high engine load* (harder to turn over) is a sharper,
  untested mechanical-stress proxy.
- **F1a `restart_burst_rate`** — repeated hard-start attempts in a short window are a
  classic solenoid/contact failure signature; distinct from calendar-rate cranks/day.
- **F1b `cold_start_fraction`** — cold engagements draw more current (oil viscosity,
  battery IR); the *rate* of them is a duty-cycle stressor not previously screened.
- **F4a `ged_disturb_cooccur`** — cheap "think-beyond" null-check for cross-subsystem
  coupling; documents the expected null rather than assuming it.
- **F4b `night_start_fraction`** — a usage/circadian signature (long-haul vs urban
  shift-work); no temperature claim (no location channel to support one).
- **F4c `vsi_recovery_time`** — recovery *time* (not slope) may separate healthy vs
  sluggish electrical recovery even where slope did not; expected weak given 5-s floor.

## 5. Evaluation protocol (pre-registered, reuses V1.1/V2.1 gate)

Runs the frozen V1.1 protocol (`V2_incremental_feature_eval.py` machinery):

0. **Reconciliation gate (regression check).** Before *any* candidate work, reproduce the
   modal-4 non-nested LOVO AUROC = **0.9357** (accept if |Δ| ≤ 0.002). If it does not
   reproduce, halt and fix the harness — no candidate results are valid until it does.
1. **E1 admissibility (per candidate):**
   - Mann–Whitney U on failed vs non-failed feature values: **screen p ≤ 0.10**.
   - Single-feature **oriented AUROC ≥ 0.60**.
   - **L40 fixed-window control:** recompute on a fixed last-40-week window and confirm the
     signal is not a history-length artifact (guards against the `vsi_dominant_freq` trap).
   - **Proxy-leak audit:** Spearman **|r| ≤ 0.5** vs {`n_weeks`, `t_start`, `span`}
     (stated leak ceilings: n_weeks 0.952, t_start 0.893 — a candidate correlating with
     these is presumed leaky).
   - **Redundancy audit:** Pearson **|r| < 0.85** vs each of the 4 production features
     (kills near-duplicates like the cold-dip family, r≈0.92–0.94).
2. **E2 fixed-subset LOVO increment:** modal-4 + candidate. **ADD iff ΔAUROC ≥ +0.01.**
3. **E3 nested rerun:** only for candidates passing E2; flagged **EXPLORATORY**
   (multiplicity). A nested increment that survives is the sole "genuine win" condition.

**Soft-signal reporting:** any candidate that passes E1 but fails E2 is reported as a
**SOFT SIGNAL** (univariate merit, no incremental value) — an honest negative, not a
silent drop.

## 6. Validation rigor & honesty guardrails

1. **Pre-registration:** all thresholds and feature params written to `params/` and
   committed **before** any candidate is computed. No retrospective tuning.
2. **Reconciliation-first:** §5 step 0 gates the whole iteration.
3. **SCREEN-GRADE labeling** everywhere (n=34, retrospective, wide bootstrap CIs; a single
   truck moves recall ~7 points).
4. **Multiplicity:** ~9–10 tests ⇒ Benjamini–Hochberg FDR note; no significance claim
   without it.
5. **Leak gates** on every feature (proxy-correlation audit; window-anchoring proof).
6. **VIN independence:** `_SM` suffix only; never pool with ALT; never pool SMA event
   rates across the SMA-dead cohort (VIN8_F, VIN9_F + the 5 SMA-null NF trucks) — exclude
   or flag per prior convention.
7. **Determinism:** fixed seeds; cache raw crank-event extraction; record `py -3` +
   library versions.

## 7. Secondary probe — model-class check (caveated, not headline)

One diligence probe, clearly labeled EXPLORATORY: fit a **single regularized nonlinear
model** (shallow gradient-boosted trees, strong depth/leaf regularization) on the modal-4
set and on modal-4 + admissible F3 interactions, under the same LOVO scheme. Purpose: test
whether the cap is **model-class** (linear Ridge cannot see interactions) rather than
features. Expectation at n=34: high variance, likely no robust gain; report as evidence,
never as a shipped model.

## 8. Ambient temperature — infeasibility (closed)

Per-start ambient-temperature reconstruction is **infeasible**: the dataset has **no
GPS/latitude/longitude/depot/region** anywhere (confirmed in the column dictionary and a
repo-wide grep), so weather-API/station interpolation cannot be geo-anchored. The two
derivable proxies were already null: **seasonality** (month effect on VSI) tested null in
V1.1 E4 (KW p=0.90/0.95), and **cold-start voltage dip** was rejected as redundant with
`dip_depth_last90_delta` (r≈0.92). V3 therefore spends **zero modeling effort** on
temperature; `appendix/temperature_infeasibility.md` records the why and the data that
would unlock it (per-vehicle GPS + timestamp → historical daily temperature; or an
onboard ambient/coolant temperature channel). `night_start_fraction` (F4b) is retained as
a **usage** feature only, with no temperature interpretation.

## 9. Deliverables & layout

```
STARTER MOTOR/V3/
  Plan/       V3_SM_spec.md (this file)  ·  V3_SM_implementation_plan.md
  params/     pre-registered JSONs (gate thresholds, per-feature params) — committed first
  features/   feature implementations + _feature_lib.py  ·  out/ (caches, gate_summary.json, admissibility.csv)
  analysis/   EDA + validation scripts (correlation, MI, permutation, SHAP, survival, sig-tests) · out/
  reports/    V3_SM_feasibility_report.md   (automotive justification + literature refs + per-feature availability verdict)
              V3_SM_feature_dictionary.md   (final dictionary: rationale · math · signals · availability · power · risks · verdict)
              V3_SM_results.md              (per-candidate E1/E2/E3 detail)
              V3_SM_verdict.md              (synthesis + accept/reject + comparison table + recommendations + limitations + future work)
              V3_SM_exec_summary.md         (1-page)
  graphs/     feature distributions (F vs NF), degradation-trend overlays, feature-ranking bar, SHAP/permutation plots
  appendix/   temperature_infeasibility.md  ·  new_data_roadmap.md (IBS current clamp / hi-rate VSI firmware / warranty+odometer)
```

Deliverables map 1:1 to the brief: feasibility report, automotive-engineering
justification, literature-backed references, implementation plan, feature-engineering
code, validation analytics, exploratory + ranking visualizations, feature ranking,
recommendations, limitations, and future work.

## 10. Risks & most-likely outcome

- **Interactions may just proxy their parents.** F3 features risk high redundancy with the
  incumbent winners; the |r|<0.85 gate is the guard, and several may die there. That is a
  valid, informative negative.
- **Small-n multiplicity.** ~10 tests at n=34 ⇒ real false-positive risk; BH-FDR + the
  strict +0.01 nested gate are the defense.
- **5-second cadence** caps F1a/F4c resolution; flagged in-line.
- **Most-likely outcome:** ceiling holds at 0.9321; F3-1 (`dose_dip_x_starts`) is the best
  hope and may reach SOFT-SIGNAL (E1-pass, E2-fail); F1/F4 most likely HOLD or null; the
  durable contributions are the tested interaction/usage surface, the feature dictionary,
  and the new-data roadmap. A single F3 feature clearing E2 **and** E3 nested would be the
  genuine win — reported with appropriately wide CIs.

## 11. Definition of done

1. Reconciliation gate reproduces 0.9357 (|Δ| ≤ 0.002).
2. All ≈9–10 candidates pre-registered, computed, and passed through E1 → redundancy →
   E2 (→ E3 if applicable), with a full admissibility table.
3. Every deliverable in §9 written; feature dictionary complete with the brief's per-feature
   schema; temperature infeasibility + new-data roadmap documented.
4. One honest verdict — explicitly permitting "NO IMPROVEMENT / all HOLD" — with SCREEN-GRADE
   caveats and BH-FDR multiplicity note.
5. Spec + params committed to git before results; results committed after.
