---
title: "V2 Incremental Feature Evaluation — cold_dip_delta90 & rpm_rise_lag_delta90"
status: complete
created: 2026-06-12
program: SM V2
protocol: V1.1 frozen nested LOVO Ridge (alpha=1.0, seeds boot=42/perm=43)
---

# V2 Program: Incremental Feature Intake Report

**Date:** 2026-06-12
**Scope:** Two candidates evaluated against the frozen V1.1 production model.  
**Baseline:** V1.1 nested AUROC = 0.9321; modal-4 non-nested LOVO = 0.9357.  
**Fleet:** 34 SM trucks (14F + 20NF). SMA-dead cohort (7 VINs) forced NaN on both candidates; fold-internal median imputation per production protocol.

---

## STOP-CONDITION CHECK

Reconciliation PASSED: modal-4 non-nested LOVO AUROC = **0.9357** (expected 0.9357, diff = 0.0000 ≤ 0.002). Proceeding to E1–E4.

---

## E1 — Admissibility Screen

| Feature | n non-NaN | MW p | AUROC | r_nwk | r_tstart | r_span | proxy_flag | r_dip_depth | r_rest_vsi_p05 |
|---------|-----------|------|-------|-------|----------|--------|------------|-------------|----------------|
| cold_dip_delta90 | 26/34 | 0.0430 | 0.739 | −0.444 | +0.302 | −0.300 | NONE | **+0.923** | −0.701 |
| rpm_rise_lag_delta90 | 27/34 | 0.0539 | 0.722 | −0.204 | +0.267 | −0.263 | NONE | +0.501 | −0.498 |

**Key findings:**
- Neither candidate triggers the proxy-leakage flag (|r| ≤ 0.5 for all three proxies).
- `cold_dip_delta90` is **near-perfectly redundant** with the modal feature `dip_depth_last90_delta` (Pearson r = +0.923). Both measure crank-induced voltage dip in the last 90 days vs. baseline — cold_dip restricts to post-6h-rest events, dip_depth uses all non-artifact events. The additional variance is minimal.
- `cold_dip_delta90` also correlates r = −0.701 with `rest_vsi_p05_delta90` (another modal feature).
- `rpm_rise_lag_delta90` MW p = 0.054 (above the 0.05 significance threshold but within the 0.10 production screening threshold). Single-feature AUROC = 0.722 (oriented), which is adequate.
- `rpm_rise_lag_delta90` shows moderate redundancy with `dip_depth_last90_delta` (r = +0.501, borderline).
- **rpm_rise_lag_delta90 computation:** Successfully derived from raw parquet (lazy scan, ±60 s window, first sample RPM ≥ 550 in 5 s samples), 27 non-SMA-dead VINs, runtime 51.6 s. No fallback restriction needed (all 27 VINs had adequate event counts).

---

## E2 — Fixed-Subset LOVO Increment

Plain 34-fold LOVO (no re-screening) on modal-4 and expansions.

| Subset | LOVO AUROC | Delta vs modal-4 |
|--------|-----------|-----------------|
| modal-4 baseline | 0.9357 | — |
| modal-4 + cold_dip_delta90 | 0.9357 | **+0.0000** |
| modal-4 + rpm_rise_lag_delta90 | 0.9357 | **+0.0000** |
| modal-4 + both | 0.9393 | +0.0036 |

**Neither candidate individually provides any incremental lift** on the fixed subset. The joint addition yields +0.0036 (below the +0.01 ADD threshold).

### Per-VIN Probability Changes (Green-tier failed + Youden FPs)

| VIN | modal_p | d_cold | d_rpm | d_both | Note |
|-----|---------|--------|-------|--------|------|
| VIN1_F_SM (F) | 0.406 | +0.010 | +0.013 | +0.022 | Modest lift |
| VIN3_F_SM (F) | 0.420 | +0.005 | −0.006 | −0.001 | No meaningful change |
| VIN4_F_SM (F) | 0.431 | +0.010 | −0.010 | −0.001 | Cancels out |
| VIN9_F_SM (F) | 0.405 | −0.001 | +0.004 | +0.003 | Negligible |
| VIN5_NF_SM (FP) | 0.595 | −0.002 | −0.010 | −0.011 | Small FP reduction |
| VIN20_NF_SM (FP) | 0.492 | +0.001 | +0.006 | +0.006 | Negligible |
| VIN2_NF_SM (FP) | 0.456 | −0.003 | −0.010 | −0.012 | Small FP reduction |
| VIN10_NF_SM (FP) | 0.433 | −0.003 | −0.003 | −0.006 | Negligible |
| VIN15_NF_SM (FP) | 0.345 | −0.017 | −0.001 | −0.016 | Minor FP reduction |

No per-VIN change exceeds 0.022. The four Green-tier failed trucks are not materially better separated.

---

## E3 — Full Nested Rerun with Expanded Pool (12 features) [EXPLORATORY]

> **MULTIPLICITY CAVEAT:** Post-hoc pool expansion constitutes a new selection event. This run is EXPLORATORY and does NOT constitute independent validation of the candidates.

**Expanded pool:** 10 V1.1 features + cold_dip_delta90 + rpm_rise_lag_delta90 = 12 candidates.  
**Expanded nested AUROC = 0.8750** (V1.1 baseline = 0.9321, delta = **−0.0571**).

The expanded pool yields a 5.7% AUROC drop vs. the frozen V1.1 model. This is not a signal about the candidates themselves but reflects that adding 2 redundant/correlated features disrupts the per-fold screening and subset search — candidates compete with and partially displace the existing informative features.

### Feature Frequency (outer-fold selection counts)

| Feature | Folds selected (of 34) |
|---------|------------------------|
| vsi_withinwk_std_ratio_30d_w | 34/34 |
| vsi_range_trend | 29/34 |
| rest_vsi_p05_delta90 | 26/34 |
| **cold_dip_delta90** | **22/34** |
| vsi_trend_persistence | 14/34 |
| **rpm_rise_lag_delta90** | **10/34** |
| dip_depth_last90_delta | 6/34 |

- `cold_dip_delta90` enters the winner subset in 22/34 folds — it partially **displaces** `dip_depth_last90_delta` (6/34 folds, down from 34/34 in the modal set). This is consistent with high redundancy: the two features compete and neither adds independent signal.
- `rpm_rise_lag_delta90` enters in 10/34 folds (at the ADD threshold, but nested AUROC regression overrides).
- Pool entry counts: cold_dip 24/34 folds, rpm_rise 20/34 folds (both frequently pass screening but don't survive subset selection or produce gains).

---

## E4 — Honest Verdict

| Candidate | E2 delta | E3 folds | Verdict | Reason |
|-----------|----------|----------|---------|--------|
| cold_dip_delta90 | +0.0000 | 22/34 | **HOLD** | Zero incremental lift on fixed subset; near-perfect redundancy with dip_depth_last90_delta (r=0.923); displaces rather than augments modal features. |
| rpm_rise_lag_delta90 | +0.0000 | 10/34 | **HOLD** | Zero incremental lift on fixed subset; MW p=0.054 (marginal); moderate redundancy with dip_depth (r=0.501); nested pool expansion degrades overall AUROC. |

**ADD criteria not met for either candidate:** E2 delta < +0.01 (both = 0.000). Both fail the E2 gate regardless of E3.

---

## Recommendations

1. **Do not add either candidate to the production V1.1 feature set at this time.** Both HOLD: the signal is real (both pass single-feature screening) but there is no incremental predictive value beyond the existing modal subset.

2. **cold_dip_delta90 root cause:** The cold-start restriction (≥6 h rest) provides no unique information because `dip_depth_last90_delta` already captures the same underlying degradation signal across all (non-artifact) events. The correlation r = 0.923 leaves no room for independent contribution.

3. **rpm_rise_lag_delta90 root cause:** The time-to-RPM-550 lag (in 5 s sample counts) is largely determined by baseline VSI health (same root cause as dip_depth). The marginal MW p = 0.054 confirms the signal exists but is noisier than existing features. Feature engineering refinement (e.g., only the first cold-start crank per day, higher RPM threshold, continuous time-to-RPM in seconds) could be explored in a V2.1 probe.

4. **V2.1 path:** If RPM-rise is to be reconsidered, compute it in continuous seconds (not sample index), restrict to post-overnight rest events only (≥8 h), and use per-VIN z-score normalization to reduce confounding from drive cycle variation.

---

## Outputs

| File | Description |
|------|-------------|
| `out/admissibility.csv` | E1 admissibility screen: MW p, AUROC, proxy Spearman r, modal Pearson r |
| `out/increment_lovo.csv` | E2 LOVO AUROCs for 4 subset configurations, per-VIN probabilities |
| `out/nested_expanded_summary.csv` | E3 per-VIN expanded-pool predictions, winner subset indicators |
| `out/rpm_rise_per_vin_cache.csv` | Computed rpm_rise_lag_delta90 values (cache for reproducibility) |
| `out/eval_summary.json` | Machine-readable summary of all four evaluation stages |
| `V2_incremental_feature_eval.py` | Full evaluation script (replicates V1.1 protocol exactly) |
