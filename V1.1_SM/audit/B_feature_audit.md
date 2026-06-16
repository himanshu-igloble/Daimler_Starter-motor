---
title: "V1.1 Agent B — Feature Engineering Audit (existing 23 features + new candidate scan)"
status: "complete"
created: "2026-06-10"
---

# V1.1 Feature Audit — Agent B

All numbers computed on the frozen V1 artifacts (read-only): `STARTER MOTOR/results/V1_SM_feature_matrix.csv`, `cache/weekly/*.parquet` (34 files), `cache/events/V1_SM_crank_events.parquet` (20,471 events; non-artifact subset used). Baseline LOVO RidgeClassifier (alpha=1.0, train-median impute, StandardScaler) **replicated exactly: AUROC 0.9214**, VIN8_F_SM prob 0.3031.

Scripts: `V1.1/audit/scripts/B1_audit_existing.py`, `B2_candidates.py`, `B3_truncation_control.py`, `B4_model_variants.py`.
Data outputs: `V1.1/audit/out/B1_*.csv`, `B2_*.csv`, `B3_truncation_control.csv`, `B4_model_variants.csv`.

---

## Part 1 — Audit of the existing 23 features

### 1.1 Redundancy structure (Spearman, full 23x23 in `B1_corr_matrix.csv`)

Clusters at |r| >= 0.70 (none involve more than one winner):

| cluster | r |
|---|---|
| crank_dur_mean ~ multi_sample_rate | +0.886 |
| failed_crank_rate ~ retry_rate | +0.883 |
| dip_depth_trend ~ recovery_slope_trend ~ dip_depth_last90_delta | +0.806 / +0.741 / +0.570 |
| bat_charge_delta_trend ~ vsi_rest_median_trend | -0.936 |

The 4 winners are well decorrelated: max pairwise |r| = 0.365 (vsi_std_ratio_30d ~ vsi_range_trend). Feature selection did its job on redundancy.

### 1.2 Jackknife (leave-one-VIN-out) AUROC stability (`B1_jackknife_auroc.csv`)

| winner | full AUROC | jk min | jk max | jk std | worst-case influence |
|---|---|---|---|---|---|
| vsi_std_ratio_30d | 0.8786 | 0.8692 | 0.9077 | 0.0102 | removing VIN1_F_SM gains +0.029 |
| vsi_dominant_freq | 0.7482 | 0.7288 | 0.7865 | 0.0160 | removing VIN8_F_SM gains +0.038 |
| failed_crank_rate_last90 | 0.7404 | 0.7188 | 0.7688 | 0.0154 | removing VIN1_F_SM drops -0.022 |
| vsi_range_trend | 0.7321 | 0.7115 | 0.7885 | 0.0182 | removing VIN13_F_SM gains +0.056 |

**No winner is driven by a few VINs.** vsi_std_ratio_30d's 0.879 is the most stable feature in the matrix (jk floor 0.869). Single-VIN sensitivity is not the problem; history-length confounding is (below).

### 1.3 Time-proxy / epoch check (`B1_time_proxy.csv`)

The observation-structure proxies themselves are near-perfect classifiers — the cohort asymmetry is severe:

| proxy | oriented AUROC | direction | MW p |
|---|---|---|---|
| n_weeks_masked | **0.954** | F shorter | <0.0001 |
| active_days_total | 0.946 | F shorter (371 vs 616 d) | <0.0001 |
| span_days | 0.938 | F shorter | <0.0001 |
| t_start calendar | **0.893** | F start LATER | 0.0001 |
| t_end calendar | 0.816 | F end earlier | 0.0015 |

Failed masked-week counts: min 22 / med 59 / max 81. NF: min 61 / med 93 / max 107. **Any feature whose value depends on total history length can launder this label signal.** Winner correlations with proxies: vsi_std_ratio_30d max |r| = 0.450, vsi_dominant_freq 0.444, vsi_range_trend 0.437, failed_crank_rate_last90 0.466 (vs t_start). All below the 0.5 tripwire but all in the "watch" band. Note: V1's calendar-truncation epoch control (`V1_SM_epoch_control.json`, drop -0.0000, PASS) only removed <= 7 trailing NF weeks — it never equalized history length, so it could not have caught a length artifact.

### 1.4 Fixed-window control (the decisive test, `B3_truncation_control.csv`)

Every feature recomputed using only each VIN's **last 40 masked weeks** (all 20 NF and 10/14 F get an identical 40-week basis; residual length floor inside the window = AUROC 0.643):

| feature | AUROC full history | AUROC L40 window | drop | verdict |
|---|---|---|---|---|
| vsi_std_ratio_30d | 0.8786 | 0.7929 | +0.086 | PARTIAL inflation |
| **vsi_dominant_freq** | 0.7482 | **0.5250** | **+0.223** | **LENGTH ARTIFACT** |
| failed_crank_rate_last90 | 0.7404 | 0.7404 | 0.000 | SURVIVES |
| vsi_range_trend | 0.7321 | 0.7321 | 0.000 | SURVIVES |

**vsi_dominant_freq mechanics:** the periodogram's frequency grid is k/n; for 17/34 VINs the dominant frequency IS the lowest non-zero bin = 1/n_weeks. Spearman r(vsi_dominant_freq, 1/n_weeks_masked) = +0.425, and 1/n alone scores AUROC 0.954. Recomputed on a fixed 24-week window the "spectral" signal is gone (AUROC 0.592, p=0.27). **There is no spectral physics here — it is the failed fleet's shorter telemetry encoded as a frequency.** Verdict: REPLACE.

### 1.5 Physical justification of winners

- **vsi_std_ratio_30d** (recent vs lifetime between-week VSI volatility) — plausible physics: charging/regulation instability rises before failure; survives the L40 control at 0.793. KEEP, but redefine on a fixed window in V1.1 (the full-history denominator borrows ~0.09 AUROC from length asymmetry).
- **vsi_dominant_freq** — statistical accident (above). REPLACE.
- **failed_crank_rate_last90** — direct failure physics (unsuccessful cranks), window-anchored, survives exactly. KEEP. Watch: r=+0.466 with t_start (failed fleet entered service later).
- **vsi_range_trend** (Theil-Sen of weekly p95-p05 drive VSI, last 12 wks) — plausible (widening voltage envelope = degrading regulation), window-limited by construction, survives exactly. KEEP.

### 1.6 Why VIN8_F_SM was missed (P=0.303) (`B1_vin8_profile.csv`)

VIN8_F_SM looks like a healthy long-history truck on 3 of 4 winners:

- failed_crank_rate_last90 = 0.006 (24th pctile; lifetime 0.074 — crank quality **improved** in the last 90 d, n=333 events)
- vsi_range_trend = -0.044 (3rd pctile — envelope narrowing, anti-failure direction)
- vsi_dominant_freq = 0.0123 (15th pctile — it has 81 masked weeks, NF-like, so the length artifact votes "healthy")
- only vsi_std_ratio_30d = 0.739 (82nd pctile) votes "failed"

Telemetry: 82 weeks (2024-01-29 to 2025-10-20), vsi_drive_mean dead-flat 27.8 V (std 0.05) over the final 8 weeks, then a 37-day silent gap to the recorded end. **The failure transient was never telemetered; VIN8 is an abrupt, electrically silent failure.** Partial recovery is possible: vsi_withinwk_std_ratio_30d_w raises its LOVO prob 0.303 -> 0.436-0.447 (variants D/I/J below), and in the honest 3-feature model it crosses the Youden threshold — at the cost of VIN1_F_SM becoming the miss and 5 NF false alarms. Its sma_duty_last90 = 3.87 SMA-active rows/active-day (94th pctile) hints at a duty/wear channel, but that feature is fleet-wide weak (AUROC 0.645). No clean feature catches VIN8 for free.

---

## Part 2 — New candidate scan (24 candidates, `B2_candidate_screening.csv`)

Screening = MW p, oriented AUROC, Cohen's d, jackknife stability (frac of 34 folds with AUROC >= 0.70), Spearman vs 4 winners, Spearman vs 5 obs/epoch proxies. Incremental = LOVO Ridge winners-4 + candidate vs 0.9214 (`B2_incremental_lovo.csv`).

### Top candidates (clean or salvageable)

| rank | candidate | AUROC | MW p | d | max r(winners) | max r(proxy) | L40 AUROC | incr. delta |
|---|---|---|---|---|---|---|---|---|
| 1 | **vsi_withinwk_std_ratio_30d** (mean weekly vsi_drive_std, last 4 wks / all) | 0.9679 | 3e-06 | 1.82 | 0.70 (std_ratio_30d) | 0.60 span | **0.9214 (survives)** | **+0.046 -> 0.9679** |
| 2 | vsi_rollstd4_last_ratio | 0.9357 | 2e-05 | 1.69 | **0.82 (std_ratio_30d)** | 0.60 | 0.886 | -0.004 (redundant) |
| 3 | failed_crank_rate_last30 | 0.7544 | 0.012 | 1.03 | 0.63 (fcr90) | 0.37 | n/a (window-anchored) | +0.004 |
| 4 | vsi_trend_persistence (sign-consistency of rolling 4-wk slopes, last 12 wks) | 0.7393 | 0.014 | 1.13 | 0.63 | 0.21 | 0.7393 (survives) | +0.007; hurts in 5-feat combos (0.846-0.879) |
| 5 | vsi_rest_p05_last90_delta (battery proxy) | 0.7179 | 0.034 | -0.72 | 0.46 | 0.47 (watch) | — | -0.004 |
| 6 | failed_crank_rate_last60 | 0.7192 | 0.034 | 0.64 | 0.92 (fcr90) | 0.30 | — | -0.004 (redundant) |

`vsi_withinwk_std_ratio_30d` is the single real discovery: within-week (intra-day) supply-voltage noise rising in the last 30 d vs lifetime. It is complementary to the winner (between-week volatility), survives the fixed-window control at 0.9214, p=3e-6, d=1.82, jackknife-stable in 34/34 folds, and is the only candidate that materially lifts VIN8_F_SM. Physical story: brush/slip-ring wear, regulator hunting, or intermittent connection produces fast voltage noise before failure. **V1.1 should adopt the windowed definition (`_w`, L40 basis) to avoid inheriting the length confound (full-history version carries r=0.60 with span_days).**

### Candidates rejected for leakage risk (explicit list)

| candidate | AUROC (raw) | reason |
|---|---|---|
| vsi_std_ratio_90d | 0.9750 | r=+0.63 span_days; L40 drop -0.121 (partial artifact); r=0.77 with winner |
| vsi_std_ratio_60d | 0.9000 | r=+0.55 span; L40 drop -0.082; r=0.78 with winner |
| failed_crank_rate_delta90 | 0.7538 | r=+0.61 with t_start calendar (epoch proxy) |
| below21_rate_ratio_90 | 0.7464 | r=+0.59 span; L40 0.643 = exactly the residual length floor -> artifact |
| vsi_drive_zage_last90 / _abs_last90 | 0.546 / 0.736 | label-dependent NF baseline (in-fold recomputation mandatory; screening value optimistic); abs variant also r=0.39 span |
| vsi_dominant_freq (V1 winner) | 0.7482 | length artifact, see 1.4 |

### Honest negatives — families that DON'T work

- **Entropy/shape statistics:** vsi_weekly_entropy 0.525, vsi_spectral_entropy (V1) 0.539, dip_depth_skew 0.543, dip_depth_kurt 0.504, crank_dur_cv 0.639 (p=0.18). Dead.
- **Gradients/acceleration:** vsi_grad_last8 0.554, vsi_accel 0.593, vsi_drive_mean_last60_delta 0.554. The VSI *level* does not drift before SM failure — consistent with V1's no-lead-time finding.
- **Health composites:** crank_health_last90 0.573 (p=0.50) — multiplying two weak signals does not make a strong one.
- **Duty/energy:** sma_duty_last90 0.645 (p=0.16), sma_duty_ratio_90 0.611. Interesting for VIN8 (94th pctile) but not fleet-significant at n=34.
- **Event last-90 deltas:** crank_dur_last90_delta 0.669 (p=0.11), recovery_slope_last90_delta 0.515, min_vsi_crank_p05_last90_delta 0.546. Weak.
- **Fixed-window dominant freq:** 0.592 — confirms there is no real spectral signal to rescue.

### Model variants (LOVO, `B4_model_variants.csv`)

| variant | k | AUROC | Youden miss/FA | VIN8_F prob |
|---|---|---|---|---|
| A baseline 4 winners (V1) | 4 | 0.9214 | 1 / 2 | 0.303 |
| B drop domfreq | 3 | 0.8643 | 4 / 2 | 0.378 |
| D swap domfreq -> withinwk_w | 4 | 0.9000 | 1 / 5 | 0.436 |
| E winners + withinwk (keeps artifact) | 5 | **0.9679** | 1 / 1 | 0.364 |
| **J honest 3-feat: std_ratio_30d + withinwk_w + fcr_last90** | 3 | **0.9143** | 1 / 5 | **0.447** (captured; VIN1_F becomes the miss) |
| G fully windowed 4-feat | 4 | 0.8607 | 1 / 6 | 0.424 |

Bottom line: **V1's 0.9214 is partly artifact-supported** — drop vsi_dominant_freq and it falls to 0.864. The variant E 0.9679 should NOT be claimed (it keeps the artifact). The honest, artifact-free ceiling found here is **~0.91 with only 3 features** (J), or 0.86 if vsi_std_ratio_30d is also forced onto a fixed window. Caveat: ~10 variants were compared on the same 34 trucks; treat J/D as V1.1 starting hypotheses, not validated results — re-run the full exhaustive-subset + permutation protocol on the cleaned pool.

### Recommendations for V1.1

1. Remove vsi_dominant_freq; document the periodogram 1/n mechanism.
2. Re-anchor vsi_std_ratio_30d (and any new volatility ratio) to a fixed L40 masked-week basis.
3. Add vsi_withinwk_std_ratio_30d_w to the screening pool; carry failed_crank_rate_last30 and vsi_trend_persistence as pool members (standalone-significant, low proxy risk) but expect no incremental gain.
4. Upgrade the epoch control: the V1 calendar truncation is too weak; adopt the fixed-window control (B3) as a mandatory gate for every pooled feature.
5. Accept that VIN8_F_SM is at best partially recoverable (silent-gap abrupt failure); any claim of catching it must disclose the VIN1_F/false-alarm trade-off.
