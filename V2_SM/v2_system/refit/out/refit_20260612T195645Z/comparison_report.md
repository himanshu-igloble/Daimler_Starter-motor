# SM V2 Refit Comparison Report

**Generated:** 2026-06-12T19:56:45.202822+00:00
**Mode:** self-test (identity check)

## 1. Headline Metrics

| Metric | Baseline (V1.1) | Refit Candidate | Delta |
|--------|----------------|-----------------|-------|
| Nested AUROC | 0.9321 | 0.9321 | +0.0000 |
| Bootstrap 95% CI (N=200) | [0.8107, 0.9861] | [0.8107, 0.9861] | — |
| Permutation p (N=20) | 0.005 | 0.0476 | — |
| Calibration slope | 0.86 | 0.860 | +0.000 |
| Brier score | 0.1240 | 0.1240 | +0.0000 |

## 2. Winner Subset

**Baseline:** `['dip_depth_last90_delta', 'rest_vsi_p05_delta90', 'vsi_range_trend', 'vsi_withinwk_std_ratio_30d_w']`
**Refit modal subset (14/34 folds):** `['dip_depth_last90_delta', 'rest_vsi_p05_delta90', 'vsi_range_trend', 'vsi_withinwk_std_ratio_30d_w']`
**Subset UNCHANGED** (same modal winner as baseline).

## 3. Gates Summary

- G1_fixed_L40_control: **True**
- G2_oof_proxy_audit: **report-only**
- G3_calibration: **report-only**
- G4_winner_stability: **False**
- G5_jackknife: **report-only**
- G6_token_scan: **True**

## 4. Per-VIN Top Movers (|Δ prob_recal| largest first)

| VIN | Failed | Baseline prob | Refit prob | Δ |
|-----|--------|--------------|------------|---|
| VIN10_F_SM | 1 | 0.9953 | 0.9953 | -0.0000 |
| VIN10_NF_SM | 0 | 0.4349 | 0.4349 | -0.0000 |
| VIN11_F_SM | 1 | 0.9578 | 0.9578 | +0.0000 |
| VIN11_NF_SM | 0 | 0.1211 | 0.1211 | +0.0000 |
| VIN12_F_SM | 1 | 0.9549 | 0.9549 | -0.0000 |
| VIN12_NF_SM | 0 | 0.0909 | 0.0909 | +0.0000 |
| VIN13_F_SM | 1 | 0.654 | 0.654 | +0.0000 |
| VIN13_NF_SM | 0 | 0.146 | 0.146 | +0.0000 |
| VIN14_F_SM | 1 | 0.9977 | 0.9977 | +0.0000 |
| VIN14_NF_SM | 0 | 0.0412 | 0.0412 | +0.0000 |
| VIN15_NF_SM | 0 | 0.2542 | 0.2542 | +0.0000 |
| VIN16_NF_SM | 0 | 0.0433 | 0.0433 | +0.0000 |
| VIN17_NF_SM | 0 | 0.0961 | 0.0961 | -0.0000 |
| VIN18_NF_SM | 0 | 0.2352 | 0.2352 | -0.0000 |
| VIN19_NF_SM | 0 | 0.1968 | 0.1968 | +0.0000 |
*(showing top 15 of 34 VINs)*

## 5. Review Checklist

- [ ] Nested AUROC >= baseline or delta within CI overlap
- [ ] G1 drop <= 0.05 (PASS)
- [ ] G6 zero banned tokens (PASS)
- [ ] G3 calibration slope in [0.5, 2.0]
- [ ] Top movers reviewed — no systematic direction bias on NF trucks
- [ ] Subset change (if any) has domain-level justification
- [ ] Restatement note drafted (see worked example: V1 -> V1.1 in REFIT_RUNBOOK.md)

## 6. Promotion Decision

**THIS CANDIDATE HAS NOT BEEN DEPLOYED.**
Manual review required. If promoting:
1. Bump `config_version` and `model.features` in `v2_config.json`
2. Update `validation_of_record` block with refit metrics
3. Recompute `config_hash` and update it
4. Publish restatement note in `docs/` (see V1->V1.1 template in runbook)
5. Retag: `git tag v2.x-sm-refit-<date>`
