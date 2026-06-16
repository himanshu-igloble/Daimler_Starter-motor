---
title: "V1.1 Starter Motor — Experiments X1 & X2 Results (feature matrix + nested-LOVO Ridge)"
status: "complete"
created: "2026-06-10"
updated: "2026-06-10"
---

# V1.1 SM — X1/X2 Experiment Results

Scripts: `V1.1/src/V1_1_SM_features.py` (X1), `V1.1/src/V1_1_SM_nested_ridge.py` (X2).
Outputs: `V1.1/results/V1_1_SM_feature_matrix.csv`, `V1_1_SM_feature_admissibility.csv`,
`V1_1_SM_nested_lovo_predictions.csv`, `V1_1_SM_nested_fold_winners.csv`,
`V1_1_SM_model_spec.json`, `V1_1_SM_gates.json`.
Seeds: bootstrap 42, permutation 43. Closed-form ridge verified vs sklearn
`RidgeClassifier(alpha=1.0)` to max |z diff| = 1.6e-15.

**Headline: fully nested 34-fold LOVO AUROC = 0.9321** (V1 restated baseline 0.893).

---

## 1. X1 — Feature matrix + admissibility audit

Candidate pool: 10 features, every one **window-anchored by construction** (L40 = each
VIN's last 40 masked weeks, or last-90-day event windows inside it). The L40-control
matrix is **bit-identical** to the production matrix (max diff 0.0 on all 10 features,
zero NaN mismatches) — the V1 failure mode (full-history denominators laundering the
n_weeks label signal) is structurally impossible in this pool.

Cohort masking: SMA-dead trucks (sma_obs_rows/n_rows <= 1%: VIN8_F, VIN9_F, VIN10_NF,
VIN11_NF, VIN12_NF, VIN13_NF, VIN20_NF) are NaN on all 5 crank/event features;
imputation is fold-internal in X2 (F's approach), never zeros.
Battery-step re-baseline (E5, rest-VSI step >= +0.5 V, SNR >= 2): VIN8_F + 5 NF
(VIN3/5/12/17/18_NF) — `rest_vsi_p05_delta90` baselines exclude pre-step weeks.

### Admissibility table (spec §2.3; full CSV in results/)

| feature | n | MW p | AUROC raw | AUROC L40 | drop | r n_wks | r t_start | r span | verdict |
|---|---|---|---|---|---|---|---|---|---|
| vsi_std_ratio_30d_L40 | 34 | .0044 | 0.793 | 0.793 | 0.000 | -.29 | +.21 | -.37 | PASS |
| vsi_withinwk_std_ratio_30d_w | 34 | .00004 | **0.921** | 0.921 | 0.000 | -.55 | +.46 | -.58 | watch |
| vsi_range_trend | 34 | .0115 | 0.732 | 0.732 | 0.000 | -.41 | +.33 | -.40 | watch |
| vsi_trend_persistence | 34 | .0141 | 0.739 | 0.739 | 0.000 | -.09 | +.10 | -.12 | PASS |
| failed_crank_rate_last90 | 26 | .0573 | 0.724 | 0.724 | 0.000 | -.26 | +.31 | -.32 | PASS |
| retry_burst_rate_last90 | 27 | .4219 | 0.589 | 0.589 | 0.000 | -.11 | +.24 | -.23 | PASS |
| extended_crank_tail_rate_last90 | 26 | .3502 | 0.612 | 0.612 | 0.000 | -.18 | +.21 | -.17 | PASS |
| first_crank_fail_rate_last90 | 26 | .0777 | 0.706 | 0.706 | 0.000 | -.19 | +.22 | -.24 | PASS |
| rest_vsi_p05_delta90 | 34 | .0124 | 0.757 | 0.757 | 0.000 | +.54 | -.49 | +.61 | watch |
| dip_depth_last90_delta | 26 | .0430 | 0.739 | 0.739 | 0.000 | -.35 | +.26 | -.25 | PASS |

**Admitted: 10/10. Dropped: none.** The §2.3 rejection rule (|r|>0.5 with a proxy AND
>0.05 L40 drop) fires for nobody — all L40 drops are exactly 0. Three features sit in
the watch band (|r|>0.4–0.65 with span/n_weeks); these correlations are label-mediated
(failed trucks have shorter telemetry *because they failed*), and the time-locking
evidence is on file (G3 k-curve: prequential AUROC 0.836–0.921 for k=0..10 weeks,
collapse to 0.536 at k=11 — failure-locked, not epoch-locked). The two new crank
candidates (`retry_burst_rate_last90` 0.589, `extended_crank_tail_rate_last90` 0.612)
are admissible but fleet-weak; per-fold screening in X2 rejects them in every fold.

Note on `vsi_std_ratio_30d_L40`: implemented as Agent B's B3 `vsi_std_ratio_30d_w`
(between-week volatility: std of `vsi_drive_mean` last 4 wks / std over L40), the spec
§1 "fixed-basis redefinition" of the V1 winner — the literal task wording would have
duplicated feature #2. Carry-over checks: `vsi_range_trend` and
`failed_crank_rate_last90` match the V1 matrix to <1e-16.

---

## 2. X2 — Fully nested 34-fold LOVO Ridge

Protocol per spec §3 / C1's recipe: inside each of 34 training folds — V1-faithful
screening (MW p<0.10, AUROC>=0.60, |Spearman|<0.85 dedup, stability >=27/33 re-screens,
pool cap 10), exhaustive subsets k=3..6, winner by 33-fold inner-LOVO AUROC (tie-break
smaller k, then MCC), per-fold median-impute -> StandardScaler -> RidgeClassifier(1.0),
per-fold inner-OOF Youden threshold (pre-registered), per-fold Platt recalibration on
inner-OOF decision values.

### Headline

| quantity | V1.1 nested | V1 restated (C audit) |
|---|---|---|
| **AUROC** | **0.9321** | 0.8929 |
| bootstrap 95% CI (N=200, seed 42) | [0.811, 0.986] | [0.746, 1.000] |
| permutation p (full nested pipeline) | **0.0050** (N=200, seed 43) | — |
| recall @ per-fold Youden | **13/14** | 12/14 |
| specificity @ per-fold Youden | 15/20 | 18/20 |
| F1 / MCC | 0.812 / 0.669 | — |

**V1.1 beats the restated V1 baseline by +0.039 AUROC** and the CI lower bound (0.811)
clears chance decisively. Permutation: 0/200 label shuffles of the *entire* nested
pipeline (screening + subset search + threshold redone per shuffle) reached 0.9321;
null mean 0.374, null p95 0.690 — p = 1/201 = 0.0050, the minimum resolvable at N=200.

### Honest classification detail

- Per-fold Youden point: TP 13, FN 1, TN 15, FP 5. The miss is **VIN9_F_SM** (prob
  0.401 vs thr 0.406) — A4 silent/abrupt, 142-day silent gap, SMA-dead, mid-fleet on
  every live feature. Physics says this truck is unobservable (spec §0.6); the model
  agrees.
- **VIN8_F_SM — V1's worst miss (prob 0.303) — is now caught**: prob 0.521, recalibrated
  0.716, tier RED. The within-week noise ratio + battery-step-aware rest-VSI delta
  recover it without a VIN1_F trade-off (VIN1_F prob 0.406 = caught at its fold thr
  0.396).
- False alarms at Youden: VIN5_NF (0.595, RED), VIN20_NF (0.492, RED), VIN2_NF (0.456,
  AMBER), VIN10_NF (0.454, AMBER), VIN15_NF (0.399, GREEN). The Youden rule is
  recall-greedy; the tier rule is the better operating point (below).
- **Tiers on recalibrated scores** (GREEN<0.35<=AMBER<0.55<=RED, pre-registered):

| tier | failed | non-failed |
|---|---|---|
| RED | 10 | 2 |
| AMBER | 0 | 2 |
| GREEN | 4 | 16 |

  RED-only alerting: 10/14 recall at **18/20 specificity** — exactly the honest recall
  ceiling E/D predicted for lead-time-observable archetypes (A1/A2/A3 ~10-11 trucks).
  The 4 GREEN failed are VIN1_F, VIN3_F, VIN4_F, VIN9_F (recal 0.22–0.34; three of the
  four are A4-silent or solenoid-then-silent).

### Winner-subset stability (G4)

Feature frequency across 34 fold winners: `vsi_withinwk_std_ratio_30d_w` 34/34,
`vsi_range_trend` 34/34, `rest_vsi_p05_delta90` 28/34, `dip_depth_last90_delta` 20/34.
No other feature ever selected. Subsets: {withinwk, rest_p05, range_trend, dip_depth}
14 folds, {withinwk, rest_p05, range_trend} 14 folds, {withinwk, dip_depth,
range_trend} 6 folds — a 14/14 modal tie between the k=4 and k=3 nestings of the same
core. Modal subset (first-seen tiebreak, used for G1 and the comparison rows):
**k=4: withinwk + rest_vsi_p05_delta90 + vsi_range_trend + dip_depth_last90_delta**.
Fold pools ranged 5–8 features; inner AUROCs 0.927–0.955.

---

## 3. Gates (V1_1_SM_gates.json)

| gate | result | pass |
|---|---|---|
| G1 fixed-L40 control rerun (modal subset) | LOVO 0.9357 raw vs 0.9357 on L40-control matrix, drop 0.0000 (matrices bit-identical by construction) | **PASS** |
| G2 OOF-score proxy audit | Spearman vs n_weeks -0.640, t_start +0.507, span -0.653 | reported; |r|>0.5 -> time-locking justification attached (G3 k-curve + zero-drop L40 control); label-mediated |
| G3 calibration (pooled recalibrated OOF) | Brier 0.124 (constant-ref 0.242), CITL -0.062, slope 0.860 in [0.5,2] | **PASS — probabilities shippable** |
| G4 winner stability | strict criterion (modal subset in >=17/34 folds) **FAILS at 14/34** — a 14/14 tie between the k=3 and k=4 nestings of the same core; only 3 distinct subsets exist, core pair (withinwk + range_trend) in 34/34 folds, all selected features drawn from a 4-feature union | **FAIL (strict) / stable (substantive)** |
| G5 jackknife AUROC | min 0.927 / max 0.951, range 0.024, std 0.007 | tight (report-only) |
| G6 leakage token scan | 0 banned tokens in selected features | **PASS** |

G2 honesty note: the OOF score *does* correlate with observation-structure proxies
above the 0.5 tripwire. This is expected and label-mediated — the proxies themselves
classify at 0.95 (A audit) because failed trucks stop transmitting when they fail. The
two reasons this is signal rather than leak: (1) every feature is L40/window-anchored
and the full L40-control rerun loses 0.0000 AUROC (a length artifact would collapse,
as vsi_dominant_freq did: 0.748 -> 0.525); (2) the G3 prequential curve holds 0.84–0.92
through k=10 weeks before t_end and collapses to chance at k=11 — an epoch/length leak
would not decay with distance-to-failure.

---

## 4. Comparisons & ablation

| row | AUROC | note |
|---|---|---|
| **V1.1 nested (headline)** | **0.9321** | recall 13/14, spec 15/20 @ fold-Youden |
| V1.1 non-nested (modal subset) | 0.9357 | optimism delta **+0.0036** |
| V1 restated nested baseline | 0.8929 | recall 12/14, spec 18/20 (C audit) |
| V1 as originally reported | 0.9214 | +0.029 selection optimism + domfreq artifact |
| Ablation: nested protocol on V1-era 22 feats (minus domfreq) | **0.8429** | same code, same nesting, old features |
| V1 winner-overlap 3-feat on V1.1 matrix (std_ratio_L40 + fcr90 + range_trend) | 0.7893 | plain LOVO |

**Ablation verdict: the V1.1 gain comes from the new features, not the protocol.**
Honest protocol applied to the old (de-artifacted) feature set yields 0.843 — i.e.
V1's 0.893 nested number was itself partly carried by `vsi_dominant_freq` (a banned
1/n_weeks artifact). The new pool (within-week noise ratio + battery-aware rest-VSI
delta + dip-depth delta) adds +0.089 over that honest floor, and +0.039 over V1's
restated headline. The tiny nesting optimism (+0.0036, vs V1's +0.029) reflects the
near-deterministic subset selection (core pair chosen 34/34).

Trade-off vs V1 restated: +1 recall (13/14 vs 12/14, including the previously-missed
VIN8_F) at -3 specificity (15/20 vs 18/20) at the Youden point; the RED-tier operating
point restores 18/20 specificity at 10/14 recall. Choose per maintenance economics;
both are honest, pre-registered operating points.

---

## 5. Verdict

- **X1 success criterion met**: 10/10 candidates pass §2 gates (2 crank features are
  admissible but too weak to survive in-fold screening — kept in the matrix,
  documented, never selected).
- **X2 success criterion met**: nested AUROC 0.9321 >= 0.893; G1/G3/G6 pass, G2/G5
  reported with justification, G4 fails only on the strict tie-break technicality
  (substantive stability is the best observed in this program: 2 features in 34/34
  folds, 3 total subsets). Permutation p = 0.0050 — the signal is not selection noise.
- VIN9_F_SM (A4, SMA-dead, 142-d silent gap) is the structural miss; no admissible
  feature sees it. The honest recall ceiling for tier-RED alerting remains ~10-11/14
  as predicted by the physics audit.

Runtimes: X1 ~50 s; X2 main nested 133 s; ablation 20 s; permutations 828 s
(N reduced from target 1000 to 200 under the documented runtime-bound rule
`min(1000, max(200, 1500s/t_nested))` — permutations reduced first, nesting never
reduced; p floor at N=200 is 0.005 and the observed p hit that floor).
