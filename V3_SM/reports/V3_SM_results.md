---
title: "V3 Starter Motor — Full Quantitative Results"
status: "complete"
created: "2026-07-01"
program: "SM V3"
sources: "V3_gate_summary.json, V3_validation.json"
---

# V3 Starter Motor — Full Quantitative Results

All numbers in this document are cited directly from `V3_gate_summary.json` and
`V3_validation.json`. No rounding beyond the precision in the source artifacts.

---

## 0. Reconciliation Gate

The pre-registered non-nested LOVO AUROC (modal-4 feature set) was reproduced exactly
before any candidate work began.

| Metric | Expected | Computed | |Δ| | Pass |
|---|---|---|---|---|
| Modal-4 non-nested LOVO AUROC | 0.9357 | 0.9357 | 0.0000 | YES |
| Modal-4 nested LOVO AUROC (baseline for E3) | — | 0.9321 | — | — |

Reconciliation passed. All candidate results are valid relative to this baseline.

---

## 1. E1 Admissibility Gate

E1 criteria (all must hold for a candidate to advance):
- Mann–Whitney U test on failed (n=14) vs non-failed (n=20) feature values: **p ≤ 0.10**
- Single-feature oriented AUROC **≥ 0.60**
- Proxy-leak audit: Spearman |r| ≤ 0.50 vs {n_weeks, t_start, span}
- Redundancy audit: Pearson |r| < 0.85 vs each of the 4 modal production features

All 7 candidates FAILED E1. No candidate advanced to E2 formally; E2 was computed for
all candidates as soft-signal intelligence and is reported below.

### E1 Full Table

| Feature | n_nonnull | MW p | Oriented AUROC | max |r_proxy| | max |r_vs_modal| | Proxy flag | Redund. flag | E1 pass |
|---|---|---|---|---|---|---|---|---|
| dose_dip_x_starts | 27 | 0.2515 | 0.6143 | 0.158 | 0.752 | No | No | **No** |
| weakbat_cold_load | 27 | 0.4208 | 0.5500 | 0.299 | 0.338 | No | No | **No** |
| reg_instab_x_usage | 27 | 0.1643 | 0.6536 | 0.430 | 0.587 | No | No | **No** |
| sag_under_load | 26 | 0.3502 | 0.5946 | 0.211 | 0.299 | No | No | **No** |
| cold_start_fraction_delta90 | 27 | 1.0000 | 0.5107 | 0.094 | 0.132 | No | No | **No** |
| ged3_rate_delta90 | 34 | 1.0000 | 0.5000 | null | null | No | No | **No** |
| night_start_fraction_delta90 | 27 | 0.9029 | 0.5000 | 0.106 | 0.246 | No | No | **No** |

Notes:
- `ged3_rate_delta90`: n_nonnull = 34 (computes for all VINs) but is a zero-variance null
  (GED state-3 near-absent fleet-wide); all correlation values are null as a consequence.
- `dose_dip_x_starts`: max |r_vs_modal| = 0.752 is r vs `dip_depth_last90_delta`. This is
  partial overlap but below the 0.85 redundancy cut — no flag fired. Documented for
  transparency.
- `reg_instab_x_usage`: max |r_proxy| = 0.430 (r vs n_weeks). Below the 0.50 proxy-leak
  cut — no flag fired. However, the exposure correlation is non-negligible and is the
  reason the marginal AUROC (0.6536) is not interpreted as a clean degradation signal.

### Per-Candidate E1 Detail

| Feature | MW p fails? | AUROC fails? | First failing criterion |
|---|---|---|---|
| dose_dip_x_starts | Yes (0.2515) | No (0.6143 ≥ 0.60) | MW p |
| weakbat_cold_load | Yes (0.4208) | Yes (0.5500 < 0.60) | MW p (AUROC also fails) |
| reg_instab_x_usage | Yes (0.1643) | No (0.6536 ≥ 0.60) | MW p |
| sag_under_load | Yes (0.3502) | Yes (0.5946 < 0.60) | MW p (AUROC also fails) |
| cold_start_fraction_delta90 | Yes (1.000) | Yes (0.5107 < 0.60) | MW p (AUROC also fails) |
| ged3_rate_delta90 | Yes (1.000) | Yes (0.5000 < 0.60) | MW p (AUROC also fails) |
| night_start_fraction_delta90 | Yes (0.9029) | Yes (0.5000 < 0.60) | MW p (AUROC also fails) |

No candidate reached the proxy-leak or redundancy check — all failed at the MW p or
AUROC criterion first.

---

## 2. E2 Fixed-Subset LOVO Increment

E2 criterion: modal-4 + candidate LOVO AUROC achieves Δ ≥ +0.01 over the 0.9357 baseline.

E2 was computed for all 7 candidates as informational soft-signal analysis. All 7 fail.

| Feature | E2 AUROC (modal-4 + cand.) | Δ vs 0.9357 | Pass (≥ +0.01) |
|---|---|---|---|
| dose_dip_x_starts | 0.9321 | −0.0036 | No |
| weakbat_cold_load | **0.9429** | **+0.0071** | No |
| reg_instab_x_usage | 0.9393 | +0.0036 | No |
| sag_under_load | 0.9357 | 0.0000 | No |
| cold_start_fraction_delta90 | 0.9286 | −0.0071 | No |
| ged3_rate_delta90 | 0.9357 | 0.0000 | No |
| night_start_fraction_delta90 | 0.9393 | +0.0036 | No |

Best incremental candidate: `weakbat_cold_load` at +0.0071 — 0.0029 below the +0.01 bar.
This candidate was also univariately insignificant (E1 MW p = 0.4208, AUROC = 0.5500).
The positive E2 delta without E1 discriminative merit is consistent with overfitting noise
on the n = 34 fold structure (see §4 GBM probe for confirmatory in-sample overfit evidence).

Three candidates (dose_dip_x_starts, cold_start_fraction_delta90) show negative E2 deltas,
confirming they actively harm held-out performance when added.

---

## 3. E3 Nested Rerun

E3 was not triggered. Protocol: E3 runs only for candidates that pass E2.
No candidate passed E2.

```
fold_safe_reverify: "n/a - no E1 survivors"
```

E3 result: null.

---

## 4. Multiplicity Control — Benjamini–Hochberg FDR

7 simultaneous Mann–Whitney tests. BH-FDR adjusted p-values (from `V3_validation.json`):

| Feature | Raw MW p | BH-FDR adjusted p |
|---|---|---|
| reg_instab_x_usage | 0.1643 | 1.0000 |
| dose_dip_x_starts | 0.2515 | 0.8803 |
| sag_under_load | 0.3502 | 0.8171 |
| weakbat_cold_load | 0.4208 | **0.7363** |
| night_start_fraction_delta90 | 0.9029 | 1.0000 |
| cold_start_fraction_delta90 | 1.0000 | 1.0000 |
| ged3_rate_delta90 | 1.0000 | 1.0000 |

Smallest BH-FDR adjusted p = **0.7363** (weakbat_cold_load). Nothing is significant under
any reasonable FDR level. There is no candidate with even suggestive statistical evidence
after multiplicity correction.

---

## 5. Analytics — Mutual Information, Permutation Importance, SHAP

All analytics from the GBM model-class probe (§4 probe). All incumbent features are
fit on the full 11-feature pool (modal-4 + 7 V3 candidates). Rankings below.

### 5.1 Mutual Information with Failure Label

| Feature | MI (discrete estimate) | Rank |
|---|---|---|
| vsi_withinwk_std_ratio_30d_w | **0.3658** | 1 (incumbent) |
| vsi_range_trend | 0.2091 | 2 (incumbent) |
| rest_vsi_p05_delta90 | 0.0774 | 3 (incumbent) |
| dip_depth_last90_delta | 0.0590 | 4 (incumbent) |
| weakbat_cold_load | 0.0450 | 5 (V3 candidate) |
| reg_instab_x_usage | 0.0099 | 6 (V3 candidate) |
| dose_dip_x_starts | 0.0000 | 7 (V3 candidate) |
| sag_under_load | 0.0000 | 7 (V3 candidate) |
| cold_start_fraction_delta90 | 0.0000 | 7 (V3 candidate) |
| ged3_rate_delta90 | 0.0000 | 7 (V3 candidate) |
| night_start_fraction_delta90 | 0.0000 | 7 (V3 candidate) |

The 4 incumbent features dominate MI. Five V3 candidates score exactly 0.0000.
`weakbat_cold_load` and `reg_instab_x_usage` show marginal MI (0.045 and 0.010
respectively) — insufficient for discriminative value.

### 5.2 GBM Permutation Importance

| Feature | Perm. importance | Rank |
|---|---|---|
| vsi_withinwk_std_ratio_30d_w | **0.3333** | 1 (incumbent) |
| rest_vsi_p05_delta90 | 0.1431 | 2 (incumbent) |
| weakbat_cold_load | 0.1049 | 3 (V3 candidate) |
| vsi_range_trend | 0.0098 | 4 (incumbent) |
| dip_depth_last90_delta | 0.0000 | 5 (incumbent) |
| dose_dip_x_starts | 0.0000 | 5 (V3 candidate) |
| reg_instab_x_usage | 0.0000 | 5 (V3 candidate) |
| sag_under_load | 0.0000 | 5 (V3 candidate) |
| cold_start_fraction_delta90 | 0.0000 | 5 (V3 candidate) |
| ged3_rate_delta90 | 0.0000 | 5 (V3 candidate) |
| night_start_fraction_delta90 | 0.0000 | 5 (V3 candidate) |

### 5.3 GBM SHAP Mean Absolute Value

| Feature | SHAP mean abs | Rank |
|---|---|---|
| vsi_withinwk_std_ratio_30d_w | **2.5228** | 1 (incumbent) |
| rest_vsi_p05_delta90 | 1.2222 | 2 (incumbent) |
| weakbat_cold_load | 0.7850 | 3 (V3 candidate) |
| vsi_range_trend | 0.1718 | 4 (incumbent) |
| dose_dip_x_starts | 0.1520 | 5 (V3 candidate) |
| reg_instab_x_usage | 0.1146 | 6 (V3 candidate) |
| cold_start_fraction_delta90 | 0.0662 | 7 (V3 candidate) |
| dip_depth_last90_delta | 0.0166 | 8 (incumbent) |
| sag_under_load | 0.0000 | 9 (V3 candidate) |
| ged3_rate_delta90 | 0.0000 | 9 (V3 candidate) |
| night_start_fraction_delta90 | 0.0000 | 9 (V3 candidate) |

**Interpretation of `weakbat_cold_load` in-sample signal.** This candidate ranks 3rd in
both GBM permutation importance (0.1049) and SHAP (0.785). However, its LOVO held-out
gain is only +0.0071, and its E1 univariate AUROC is 0.5500 (MW p = 0.4208). Moderate
in-sample importance without held-out discriminative merit is a textbook small-n overfit
signature: the GBM assigned weight to this feature in individual folds despite it carrying
no generalizable signal. This in-sample weight must NOT be interpreted as evidence of real
predictive value.

---

## 6. Model-Class Probe — GBM vs Linear Ridge (SCREEN-GRADE)

**SCREEN-GRADE: n = 34, retrospective, wide bootstrap CIs. Not a shipped model.**

| Model | LOVO AUROC |
|---|---|
| Linear Ridge (modal-4, nested) | **0.9321** |
| GBM on modal-4 + all 7 V3 candidates | **0.8429** |

The GBM LOVO AUROC (0.8429) is substantially below the linear Ridge nested baseline
(0.9321). A regularized nonlinear model does not beat the linear model on these features
and at this sample size.

**Conclusion:** the performance ceiling is the DATA, not the linear model class. Even a
nonlinear GBM with access to all 11 features (modal-4 plus all 7 V3 candidates) cannot
match the linear model trained on the 4-feature set. This rules out the hypothesis that
the Ridge model is leaving exploitable nonlinear interactions on the table. At n = 34,
the GBM has insufficient data to generalize and overfits the training folds, yielding
LOVO AUROC = 0.8429.

This probe is confirmatory and consistent with the data-ceiling finding from V2 and V2.1.

---

## 7. Soft-Signal Inventory

Per protocol, candidates that pass E1 but fail E2 are reported as SOFT SIGNALS. No
candidate passed E1, so there are no soft signals to report.

The closest to a soft signal: `reg_instab_x_usage` passed the AUROC criterion (0.6536)
but failed MW p (0.1643). `dose_dip_x_starts` also passed the AUROC criterion (0.6143)
but failed MW p (0.2515). Neither is a soft signal under the pre-registered protocol
because both criteria must be met for E1 passage.

---

## 8. Verdicts (from `V3_gate_summary.json`)

| Feature | Verdict | Reason (verbatim from gate JSON) |
|---|---|---|
| dose_dip_x_starts | REJECT | E1 fail (mw_p=0.2515, auroc=0.6143) |
| weakbat_cold_load | REJECT | E1 fail (mw_p=0.4208, auroc=0.55) |
| reg_instab_x_usage | REJECT | E1 fail (mw_p=0.1643, auroc=0.6536) |
| sag_under_load | REJECT | E1 fail (mw_p=0.3502, auroc=0.5946) |
| cold_start_fraction_delta90 | REJECT | E1 fail (mw_p=1.0, auroc=0.5107) |
| ged3_rate_delta90 | REJECT | E1 fail (mw_p=1.0, auroc=0.5) |
| night_start_fraction_delta90 | REJECT | E1 fail (mw_p=0.9029, auroc=0.5) |
