---
title: "V3 Starter Motor — Synthesis and Verdict"
status: "complete"
created: "2026-07-01"
program: "SM V3"
---

# V3 Starter Motor — Synthesis and Verdict

## 1. Outcome Statement

**V3 result: NO IMPROVEMENT / ALL HOLD.**

All 7 candidates REJECTED. The frozen modal-4 feature set remains the production
configuration. The data ceiling holds at non-nested LOVO AUROC = 0.9357 / nested = 0.9321.

This is the correct, expected result. The V3 spec (§10) pre-registered this as the
most-likely outcome. A rigorous negative on the interaction/usage surface is a legitimate
and valuable scientific result — it closes off a branch of the feature space with evidence
and strengthens the ceiling argument.

---

## 2. Comparison Table — All V3 Candidates vs Frozen Baseline

Frozen baseline: modal-4, non-nested LOVO AUROC = **0.9357**, nested = **0.9321**.
E2 add-bar: Δ ≥ **+0.01**. All candidates REJECT.

| Feature | Family | Oriented AUROC (E1) | MW p | E2 AUROC | Δ vs 0.9357 | ≥ +0.01? | Verdict |
|---|---|---|---|---|---|---|---|
| dose_dip_x_starts | F3 interaction | 0.6143 | 0.2515 | 0.9321 | −0.0036 | No | **REJECT** |
| weakbat_cold_load | F3 interaction | 0.5500 | 0.4208 | 0.9429 | +0.0071 | No | **REJECT** |
| reg_instab_x_usage | F3 interaction | 0.6536 | 0.1643 | 0.9393 | +0.0036 | No | **REJECT** |
| sag_under_load | F3 interaction | 0.5946 | 0.3502 | 0.9357 | 0.0000 | No | **REJECT** |
| cold_start_fraction_delta90 | F1 usage | 0.5107 | 1.0000 | 0.9286 | −0.0071 | No | **REJECT** |
| ged3_rate_delta90 | F4 probe | 0.5000 | 1.0000 | 0.9357 | 0.0000 | No | **REJECT** |
| night_start_fraction_delta90 | F4 probe | 0.5000 | 0.9029 | 0.9393 | +0.0036 | No | **REJECT** |
| **Frozen modal-4 baseline** | — | — | — | — | **0.0000** | — | **KEEP** |

Key observations:
- No REJECT is anywhere close to the +0.01 bar. Best increment: +0.0071 (weakbat_cold_load),
  which is also univariately insignificant.
- Two candidates (dose_dip_x_starts −0.0036, cold_start_fraction_delta90 −0.0071) actively
  harm held-out AUROC when added.
- No redundancy or proxy-leak flag fired on any candidate. The REJECTs are genuine
  discriminative failures, not artifacts filtered by the audit steps.
- BH-FDR smallest adjusted p = 0.7363. Nothing approaches significance under multiplicity
  correction.

---

## 3. The Ceiling Holds

The data ceiling was established across three prior iterations:
- V1.1: nested 0.9321; prequential AUROC decays to ~0.5 at k = 11 weeks.
- V2: density audit r(failed, n_weeks) = −0.771; feature-pool expansion to 12 features
  dropped nested AUROC to 0.875 (−0.057).
- V2.1: strict gate rejected best prior candidates; ceiling re-confirmed.

V3 adds a fourth line of evidence: **the interaction/usage surface of the 6-signal frame
carries no additional signal.** Specifically:

1. The 4 interaction features (F3-1 through F3-4) test the multiplicative stress-dose
   hypotheses that linear marginals structurally cannot see. All 4 REJECT.
2. The usage features (cold-start rate, night-start fraction) test duty-cycle dimensions
   never previously screened. Both REJECT.
3. The GED cross-system probe tests the only remaining signal channel (GED) as an SM
   covariate. REJECT (zero-variance null).

**The ceiling is not the model class.** The GBM model-class probe (SCREEN-GRADE, n = 34,
wide variance) scored LOVO AUROC = 0.8429 on the full 11-feature pool — lower than the
linear Ridge on the 4-feature set (0.9321). A regularized nonlinear model does NOT beat
the linear model at n = 34. The cap is the data, not the linear Ridge architecture.

**The ceiling is not missing feature engineering.** V3 has now exhaustively screened:
- All obvious univariate VSI/crank-session features (V1.1/V2).
- The ANR load marginal (V2.1).
- The cold-start depth family (V2.1).
- All interaction products of the available signals (V3).
- Cold-start rate, night-start rate (V3).
- GED as SM covariate (V3).

What remains untested requires *new instrumentation* — see §6 and `appendix/new_data_roadmap.md`.

---

## 4. Model-Class Finding

| Model | Configuration | LOVO AUROC |
|---|---|---|
| Linear Ridge | modal-4 (nested) | **0.9321** |
| Linear Ridge | modal-4 (non-nested) | **0.9357** |
| GBM (SCREEN-GRADE) | modal-4 + all 7 V3 candidates | **0.8429** |

The GBM was a diligence probe to test whether the performance ceiling is model-class
(i.e., the Ridge cannot see nonlinear interactions). The result is decisive at this sample
size: the nonlinear model underperforms the linear model by 0.0892 AUROC points under
LOVO evaluation. At n = 34, the GBM cannot generalize its in-sample fits across folds.
The GBM result is consistent with the wide-CI / high-variance regime expected at SCREEN-GRADE.

This does not mean GBMs are inferior to Ridge models for starter motor prediction in
general — at n = 500+ it may perform differently. At n = 34, the conclusion is unambiguous.

---

## 5. Recommendations

### 5.1 Feature Set — FREEZE at Modal-4

Do NOT add any V3 candidate to the production feature set. The 4 production features are:
1. `vsi_withinwk_std_ratio_30d_w`
2. `rest_vsi_p05_delta90`
3. `vsi_range_trend`
4. `dip_depth_last90_delta`

AUROC: 0.9357 non-nested / 0.9321 nested. This is the correct configuration.

### 5.2 Feature Engineering — CLOSED

Feature engineering on the existing 6-signal / 5-second dataset is complete. The
interaction/usage surface has been tested under the locked gate. No further engineering
iterations on this data are warranted. A new iteration makes sense only upon receipt of
new sensor channels (see §6).

### 5.3 Next Step — New Instrumentation

The single highest-ROI action is to specify the sensor additions that would unlock the
next performance tier. See `appendix/new_data_roadmap.md` for three concrete paths:
(a) IBS / current-clamp for crank-current waveform;
(b) high-rate VSI firmware trigger during SMA = 1;
(c) full warranty + odometer + SALEDATE ingest.

---

## 6. Limitations

**Sample size (binding constraint).** n = 34 (14 failed / 20 non-failed) is SCREEN-GRADE.
A single truck change moves recall by approximately 7 percentage points. Bootstrap CIs on
AUROC are wide. Results should not be extrapolated to the full DICV fleet without
re-evaluation at larger n.

**Retrospective, observational data.** No controlled experiment. Failure label derives
from warranty/workshop records; timing uncertainty is inherent. Retrospective bias cannot
be ruled out at this sample size.

**Interaction z-scoring assumes global standardization.** The within-fold z-scoring is
correct for leakage, but at n = 14 failed / 20 non-failed VINs per fold, the standardizer
is noisy. The interaction features are therefore moot rather than conclusively zero — they
are moot because none survived E1, and at n = 34 the fold variance would have made any
borderline signal unreliable in production anyway.

**Multiplicity.** 7 simultaneous tests. Handled by Benjamini–Hochberg FDR correction;
smallest adjusted p = 0.7363. No significance claim is warranted.

**Temperature.** Ambient temperature is infeasible (no GPS / location channel). The two
derivable proxies were already null (seasonality KW p = 0.90; cold-dip rejected for
redundancy). See `appendix/temperature_infeasibility.md`.

**Feature scope vs. prior work.** F1a (`restart_burst_rate`) was scoped in the spec (§2.2)
but dropped before execution: the frozen V1.1 feature matrix already contains
`retry_burst_rate_last90` — a pooled V1.1 candidate that did not make the modal-4 winner —
so restart-burst clustering is already represented and settled. V3 therefore tested the 7
genuinely-novel candidates rather than re-screening an already-covered feature. This
refinement (and the F4c-optional / F4a-reframe) is recorded in the implementation plan
under "Refinements vs committed spec."

---

## 7. Future Work

The durable contribution of V3 is not a new feature — it is a tested, closed feature
space and a clear roadmap. See `appendix/new_data_roadmap.md` for the three paths that
would break the ceiling. The most important:

1. **IBS / current-clamp** — would unlock direct brush/solenoid health estimation from
   the crank-current waveform, which is what the 5-second VSI frame cannot reconstruct.
2. **High-rate VSI firmware trigger** — 1 Hz or faster during SMA = 1 windows would
   partially restore sub-second crank voltage physics within the existing data pipeline.
3. **Larger failure cohort** — every 10 additional failed examples reduces LOVO variance
   by ~√(n/n+10). At n = 50 failed VINs the SCREEN-GRADE caveat relaxes substantially.
