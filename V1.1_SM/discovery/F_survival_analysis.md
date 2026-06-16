---
title: "Agent F — Survival Analysis for SM V1.1: Discrete-Time Hazard vs Fleet Clock"
status: "complete"
created: "2026-06-10"
---

# Agent F — Survival Analysis (SM fleet, n=34, 14 events)

**Question.** Does survival reframing (discrete-time hazard / Cox / Weibull on
truck-weeks) beat (a) the fleet-clock baseline and (b) the V1 static classifier
(nested-LOVO AUROC 0.893)? ALT prior: per-truck day-precision RUL lost to the
fleet clock (MAE 142d vs 50d).

**Verdict (up front): NO for RUL, NO as a truck-level risk score.** The hazard
model's median-RUL MAE is 576 d — *worse* than the Weibull fleet clock (462 d),
and both are demolished by a trivial constant (44 d). As a truck-level ranker
it scores 0.586 vs the static model's 0.893. Its only non-trivial output is a
weekly P(fail≤30d) signal at AUROC 0.744 (0.849 under JCOPENDATE event timing),
driven almost entirely by `vsi_std_ratio`. Recommendation: **do not ship a
hazard layer**; at most, feed `vsi_std_ratio` into the static score as a weekly
trend covariate.

Scripts: `STARTER MOTOR/V1.1/discovery/scripts/F1_build_truck_week.py`,
`F2_fleet_clock.py`, `F3_hazard_lovo.py`, `F4_cox_weibull.py`.
Outputs: `STARTER MOTOR/V1.1/discovery/out/F_*.{parquet,csv}`.

---

## 1. Truck-week table & anti-leakage protocol

**2,636 truck-weeks × 34 trucks, 14 events** (`out/F_truck_week.parquet`).

- **Time axis**: `age_week` = integer weeks since first telemetry (`t_start`).
  Calendar-true: silent-gap weeks are absent (not-at-risk), so age advances
  through gaps but contributes no person-time. Weeks-since-sale was not usable —
  `saledate` exists only for failed VINs (NF all NaN in
  `results/V1_SM_data_quality.csv`); for failed VINs `t_start` ≈ saledate
  (0–14 d apart), so the axes nearly coincide where both exist.
- **Event** = 1 at the last observed week of each failed VIN (t_end-anchored).
  JCOPENDATE sensitivity for the 5 silent-gap VINs (VIN1/4/5/8/9_F, +32…142 d)
  reported throughout.
- **Causality**: every covariate at week *t* uses only weeks ≤ *t−1* (strictly
  lagged — the event week's own telemetry never feeds its covariates). No
  whole-life statistics, no observation length, no t_start/epoch, no
  `vsi_dominant_freq`.
- **Validation**: leave-one-VIN-out at truck level (34 folds); imputation means
  and scalers fit inside each fold.
- **Clustering**: weekly rows within a truck are correlated. No SEs are quoted
  from pooled logistic; Cox naive SEs are flagged anti-conservative (lifelines
  `CoxTimeVaryingFitter` raises `NotImplementedError` for `robust=True` in
  0.30.0).

### Covariates (3, per Agent C's EPV budget: 14 events / 4 params ≈ 3.5)

| Covariate | Definition (all lagged to ≤ t−1) | Rationale |
|---|---|---|
| `vsi_std_ratio` | mean(`vsi_drive_std`, wk t−4…t−1) ÷ expanding mean over wk 0…t−5 (≥4 wk), clipped [0.2, 5] | charging-ripple instability vs the truck's own past |
| `crank_fail_rate` | failed cranks ÷ cranks (success==False, artifacts/None excluded), wk t−4…t−1, ≥5 cranks; **masked (NaN) for the 7 SMA-dead trucks**, fold-mean imputed | direct starter health |
| `rest_delta` | mean(`vsi_rest_p05`, wk t−4…t−1) − median of first 8 observed wk (causal part only), clipped ±6 V | battery/charging rest-voltage sag |

**SMA-dead handling**: cohort = `sma_null_pct > 0.99` → VIN8_F, VIN9_F +
VIN10/11/12/13/20_NF (7 trucks). These trucks *do* have rows in the crank-events
parquet (fallback detection path), but per protocol their crank covariate is
masked and imputed with the **training-fold mean** (zero signal, zero
group-level bias after centering). No cohort indicator was spent — it would be
a 4th covariate and would partially encode failure-class composition (2/14 F vs
5/20 NF).

Sanity (direction): failed VINs' last-26-wk means vs all NF weeks —
`vsi_std_ratio` 1.78 vs 1.01; `crank_fail_rate` 0.096 vs 0.058; `rest_delta`
−0.90 V vs −0.26 V. All three move the expected way.

Event ages: failed 21–90 wk (median 69); NF censored at 60–111 wk (median 101).

## 2. Fleet-clock baseline (KM / Weibull)

- **KM median: undefined (∞)** — with 14/34 events, S(t) never crosses 0.5
  within support; 95% CI for the median is [78 wk, ∞). KM 25th percentile of
  failure: 73 wk. This alone disqualifies KM as an RUL engine here.
- **Weibull** (all 34): λ=133.3 wk, ρ=2.03 (wear-out shape), **median 111.3 wk
  (779 d)**, IQR 72.1–156.6 wk. JCOPENDATE sensitivity: median 110.3 wk —
  negligible shift.
- **Marginal weekly hazard** (baseline b): 14/2,636 = **0.0053/wk** (~0.28/yr).

**Conditional-median RUL** (med(T−t | T>t), Weibull, LOVO — held-out failed VIN
excluded from each fit), MAE on failed VINs:

| eval point (actual RUL) | n | Weibull fleet-clock MAE | KM |
|---|---|---|---|
| 28 d | 14 | 485.5 d | undefined (0/14) |
| 63 d | 14 | 471.0 d | undefined |
| 91 d | 14 | 460.5 d | undefined |
| 182 d | 12 | 396.7 d | undefined |

Last-26-weeks trajectory (323 truck-weeks, 13/14 failed VINs — VIN5_F_SM has no
observed weeks in its final 26 calendar weeks due to silent gaps): Weibull MAE
**461.9 d**. A constant 91-d prediction scores **44.4 d** (this is near the
structural floor: actuals are ~uniform over 7–182 d, so any constant ≈ 13 wk
lands ~45 d). The survival conditional median is honest about *population*
residual life but useless for *about-to-fail* trucks — heavy censoring pushes
it to 400–700 d while the evaluated trucks die within 182 d.

## 3. Discrete-time hazard model (logistic, truck-level LOVO)

`logit h(t) = β₀ + β₁·log1p(age) + β·covariates`, ridge (C=1), 34 folds.

**Coefficient stability across folds** (per-unit): log_age +0.71±0.06,
`vsi_std_ratio` **+0.69±0.04** (the workhorse), `crank_fail_rate` +0.40±0.45
(sign-unstable — flips when VIN14_F, the high-crank-failure truck, is held
out), `rest_delta` −0.15±0.05.

- **Pooled weekly-hazard AUROC** (14 event-weeks vs 2,622 at-risk weeks):
  **0.747**.
- **Age-matched concordance** (event week vs other trucks at-risk at the same
  age — a discrete Uno-style time-dependent C, 332 comparable pairs): **0.654**.
- **Horizon classification** (P(fail≤H), covariates frozen, age advanced;
  positives = held-out failed VINs' weeks within H of t_end, negatives = all NF
  weeks + failed early weeks):

| H | AUROC | age-only ablation | JCOPENDATE-shifted labels |
|---|---|---|---|
| 30 d | **0.744** (64 pos) | 0.646 | 0.849 (45 pos) |
| 60 d | 0.708 (127 pos) | 0.622 | 0.810 (95 pos) |
| 90 d | 0.688 (179 pos) | 0.601 | 0.791 (138 pos) |

  Covariates add ~0.09–0.10 over age alone. The JCOPENDATE improvement is real
  but **not deployable lead time**: it relabels the gap VINs' last observed
  weeks as >H-from-failure, and those trucks transmit nothing during the gap —
  the model cannot be queried when it matters.
- **Calibration**: in-the-large excellent — Σ predicted events 14.9 vs 14
  observed (ratio 1.06); recalibration slope 0.77 (mildly overconfident
  spread); decile table noisy (obs 0 in 5/10 deciles — only 14 events) but the
  top decile is honest: predicted 0.0275/wk vs observed 0.0303/wk. Verdict:
  *adequately calibrated, weakly discriminating.*
- **Truck-level ranking** (held-out hazard, mean of last 4 observed weeks):
  AUROC **0.586**; peak hazard: 0.425. The static V1 classifier (0.893) is not
  remotely threatened. (And "last 4 weeks" is itself leakage-adjacent for
  ranking — shown only to bound the best case.)

## 4. Cox PH & Weibull AFT sanity checks

**Cox time-varying** (2 covariates available for all 34 trucks, EPV=7;
penalizer 0.01; intervals [age, age+1), gap weeks not-at-risk):
`vsi_std_ratio` HR **1.74** per unit (coef 0.553, naive se 0.183, naive
p=0.002); `rest_delta` HR 0.888 (p=0.33, NS). LR vs null 10.84, naive
χ²₂ p=0.0044. **Naive SEs are anti-conservative under within-truck
correlation** (no cluster-robust option in lifelines CTV) — read as "consistent
with the discrete-time model", not as confirmatory inference.

**Weibull AFT** (static, one causal early-life covariate = mean `vsi_drive_std`
wk 0–7; EPV=14): covariate NS (coef 4.30, p=0.176); shape ρ=2.02 → wear-out
hazard, agreeing with the discrete model's positive log-age term. In-sample
concordance 0.635. Early-life telemetry does not predict lifetime.

## 5. RUL framing — the answer

Median RUL from the LOVO hazard model (smallest k with Ŝ(t+k)≤0.5, covariates
frozen, cap 260 wk), failed VINs' last 26 weeks (323 truck-weeks, 13 VINs):

| Predictor | MAE (days) |
|---|---|
| **Constant 91 d** (≈ what V1-static implies: no time dimension, fleet-median prior) | **44.4** |
| Weibull fleet clock, conditional median, LOVO | 461.9 |
| Discrete-time hazard model, median RUL, LOVO | **576.1** |

The hazard model predicts median RUL ≈ 700 d for trucks dying within 182 d:
correct *average* weekly hazard (calibrated at 0.005/wk) mathematically forces
long survival medians — calibration and day-precision RUL are incompatible at
this event rate. Per-VIN hazard MAE ranges 76 d (VIN14_F, strong crank signal)
to 1,012 d (VIN9_F, SMA-dead, masked covariate). **This replicates the ALT
finding** (fleet clock unbeatable for day-precision RUL) and is *worse* here
because SM survival is barely covariate-predictable at truck level.

## 6. Why RSF / DeepSurv / DeepHit / DSM are out

**Random Survival Forest** — `scikit-survival` is not installed (probed;
per instructions not pip-installed). Mathematically it was near-pointless
anyway: RSF needs enough events per terminal node (≥10–15 events total per
effective split path) to estimate node-level Nelson–Aalen curves; with 14
events across 34 trucks, any tree deeper than 1–2 splits places 0–3 events per
node, yielding degenerate cumulative-hazard estimates, and the LOVO variance of
the ensemble ranking would swamp any signal a 4-parameter logistic already
captures.

**DeepSurv** — a Cox partial-likelihood neural net with even one 8-unit hidden
layer has >30 free parameters against 14 events (EPV < 0.5, vs the ≥10 rule of
thumb); the partial likelihood has 14 informative terms total. It cannot be fit
without the prior dominating entirely, i.e., it reduces to an expensively
regularized linear Cox — which we already ran.

**DeepHit** — estimates a full discrete distribution over time bins via a
softmax over (bins × subjects) plus a ranking loss; with ~90 weekly bins and 14
events there are ~6× more output bins than events. The model's likelihood is
unidentified and its concordance on LOVO folds would be driven by initialization
noise.

**DSM (Deep Survival Machines)** — a mixture of k Weibull/log-normal experts
with neural gating; even k=2 with a linear gate is ~12+ parameters and requires
estimating mixture responsibilities from censored likelihood — at 14 events the
posterior over mixture assignments is essentially the prior. The single-Weibull
AFT (Section 4) is the identified special case, and its covariate is already NS.

## 7. Limitations (stated, not hidden)

1. **NF age ≈ observation length**: NF trucks lack saledate; their `t_start` is
   the extraction-window start, so true vehicle age is understated by an
   unknown amount → fleet hazard-vs-age is biased toward early ages. This hurts
   all fleet-clock variants equally; it cannot rescue the hazard model.
2. **14 events** bound everything: decile calibration is noise, horizon-AUROC
   CIs (cluster-aware) would be wide (~±0.10).
3. **Silent gaps**: 5 failed VINs are unobservable for their final 32–142 d;
   any weekly risk product is structurally blind exactly when those trucks
   approach failure.

## 8. Recommendation for V1.1

**Do not ship a hazard layer** — not as an RUL estimator (loses to a constant
by 13×), not as a maintenance-window estimator (median-RUL output is 700 d for
trucks dying in <182 d), not as a truck-level risk score (0.586 vs static
0.893). The single reusable finding: **`vsi_std_ratio` (4-wk drive-VSI-std vs
own past baseline) is the only temporally informative signal** (Cox HR 1.74;
+0.10 AUROC over age at 30 d). Carry it into the V1.1 static feature
discussion as a candidate *weekly trend covariate*, clearly labeled with its
modest standalone discrimination (weekly P(fail≤30d) AUROC 0.744).
