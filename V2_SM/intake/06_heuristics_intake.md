---
title: "V2 SM — Heuristic Intelligence Layer Backtest (H1–H6)"
status: complete
created: "2026-06-12"
---

# V2 Starter Motor — Heuristic Intelligence Layer Backtest

## 0. Reconciliation Gate

**PASS.** k=0 feature reconciliation vs frozen `V1_1_SM_feature_matrix.csv`:

| Feature | max\|diff\| | NaN-mismatches | Status |
|---|---|---|---|
| vsi_withinwk_std_ratio_30d_w | 4.44e-16 | 0 | OK |
| rest_vsi_p05_delta90 | 2.22e-16 | 0 | OK |
| vsi_range_trend | 8.33e-17 | 0 | OK |
| dip_depth_last90_delta | 1.11e-16 | 0 | OK |

k=0 LOVO AUROC = **0.9357** (spec target 0.9357 ±0.002). **Gate PASS.**

---

## 1. Method

**Walking score engine** (`H_walking_scores.py`): For each of k=0..26 weekly
offset cuts (cut = t_end − 7k days), the 4 frozen X1 features are recomputed
causally (battery-step re-baseline only if step week < cut; SMA-dead masking
preserved; L40-window arithmetic verbatim from `V1_1_SM_horizon.py`). A 34-fold
LOVO RidgeClassifier(alpha=1.0) is run on the usable subset at each k, yielding
per-VIN causal decision values. Usability threshold: ≥8 masked active weeks
before cut (identical to X4).

**Platt calibration simplification**: Per-cut Platt calibration would require
inner-OOF scores per training fold — not accessible here. A single Platt sigmoid
is fitted at k=0 (34 LOVO decision values → probabilities) and applied unchanged
at all k. This is an approximation; probabilities at large k may be
miscalibrated but tier assignments (GREEN/AMBER/RED) reflect the same scale.
**This simplification is stated prominently throughout.** All downstream tier
comparisons use the frozen thresholds GREEN < 0.35 ≤ AMBER < 0.55 ≤ RED.

**Alert channel states** (H3, H4): loaded from `V1_1_SM_alert_validation.csv`
and `V1_1_SM_alert_policy.csv`. Persistence fire-state approximated as "active
from first-ever fire week onward" (conservative — full weekly episode intervals
not in CSV). A1 and A2: active from their respective first-fire dates.

**Heuristic parameters are FROZEN A PRIORI from the task spec** — no parameter
search was conducted on outcomes. All results are **SCREEN-GRADE** (n=34,
retrospective; pre-register thresholds before deployment evaluation).

---

## 2. Heuristic Definitions and Results

### H1 — Risk Momentum
**Rule**: Δ(walking prob) over trailing 4 weeks ≥ +0.15 → fire.
**Rationale**: Detects rapid deterioration, complementary to tier threshold.

| Failed VIN | First fire | Lead (d) |
|---|---|---|
| VIN10_F | 2025-08-25 | 126 |
| VIN11_F | 2025-06-21 | 154 |
| VIN12_F | 2025-07-20 | 140 |
| VIN13_F | 2025-06-19 | 140 |
| VIN14_F | 2025-08-04 | 105 |
| VIN1_F | **MISS** | — |
| VIN2_F | 2025-10-11 | 63 |
| VIN3_F | 2025-07-15 | 154 |
| VIN4_F | 2025-05-24 | 70 |
| VIN5_F | 2025-05-26 | 154 |
| VIN6_F | 2025-06-24 | 133 |
| VIN7_F | 2025-07-05 | 126 |
| VIN8_F | 2025-07-13 | 105 |
| VIN9_F | 2025-04-06 | 84 |

**Recall: 13/14 (92.9%)** | **Median lead: 126 d** | **NF ever-fire: 19/20 (95%)** | NF eps/truck-yr: 0.75

Miss: VIN1_F (GREEN-tier truck throughout; prob trajectory never shows a single
+0.15 step — consistent with the Layer-1 near-miss on this VIN).

### H2 — Persistent-RED Dwell
**Rule**: ≥3 consecutive weekly cuts in RED → fire.
**Rationale**: Reduces one-week RED spikes (false positive driver in H4).

| Failed VIN | First fire | Lead (d) |
|---|---|---|
| VIN10_F | 2025-12-01 | 28 |
| VIN11_F | 2025-10-18 | 35 |
| VIN12_F | 2025-08-31 | 98 |
| VIN13_F | 2025-06-26 | 133 |
| VIN14_F | 2025-06-02 | 168 |
| VIN1_F | **MISS** | — |
| VIN2_F | **MISS** | — |
| VIN3_F | 2025-07-22 | 147 |
| VIN4_F | **MISS** | — |
| VIN5_F | 2025-05-12 | 168 |
| VIN6_F | 2025-05-20 | 168 |
| VIN7_F | 2025-08-09 | 91 |
| VIN8_F | 2025-08-31 | 56 |
| VIN9_F | **MISS** | — |

**Recall: 10/14 (71.4%)** | **Median lead: 116 d** | **NF ever-fire: 5/20 (25%)** | NF eps/truck-yr: 0.19

Best NF specificity among H1–H5 except H5. Misses 4 trucks: VIN1_F/VIN4_F
(GREEN tier), VIN2_F (short data history, RED appears too late), VIN9_F
(SMA-dead + GREEN tier, irreducible blind spot).

### H3 — Escalation Ladder
**Rule**: Monotone GREEN→AMBER→RED tier climb within any 8-week window AND
any channel (persistence/A1/A2) active in same window → fire.
**Rationale**: Requires directional worsening AND corroboration, reducing
spurious single-channel triggers.

**Recall: 9/14 (64.3%)** | **Median lead: 77 d** | **NF ever-fire: 8/20 (40%)** | NF eps/truck-yr: 0.24

H3 requires a full GREEN→AMBER→RED sequence — trucks that start AMBER/RED
(VIN5_F, VIN9_F) or whose tier jumps non-monotonically (VIN1_F, VIN3_F, VIN4_F)
are missed. Lead times are shorter because the window completion naturally
occurs later in the failure trajectory.

### H4 — Multi-Channel Agreement
**Rule**: Count of {tier≥AMBER, persistence fire-state, A1 episode active,
A2 fired} ≥ 2 at any week → fire.
**Rationale**: Cross-source corroboration; catches tier misses via channels.

**Recall: 14/14 (100.0%)** | **Median lead: 175 d** | **NF ever-fire: 20/20 (100%)** | NF eps/truck-yr: 1.00

H4 achieves perfect recall because **all 20/20 NF trucks also fire** — the
persistence channel fires on every NF truck at some point in its history
(20/20 ever-fire, per X3 validation). Combined with any tier≥AMBER (VIN20_NF,
VIN2_NF, VIN5_NF are already AMBER/RED), the threshold of ≥2 channels is
trivially met. **H4 in isolation is not useful as a pager** — it must be used
as a priority-scoring or stratification input, not a go/no-go alarm.
VIN4_F fires with 0-day lead (first fire = t_end exactly).

### H5 — Fleet-Percentile Persistence
**Rule**: Walking prob ≥ 85th fleet percentile at same-k cut in ≥4 of trailing
6 weeks → fire.
**Rationale**: Relative rank within contemporaneous fleet; lowest FP burden.

**Recall: 7/14 (50.0%)** | **Median lead: 119 d** | **NF ever-fire: 3/20 (15%)** | NF eps/truck-yr: 0.11

Best NF specificity: 3/20 NF ever-fire and 0.11 eps/truck-year — cleanest
standalone rule. But recall of 50% means it misses half the failed fleet
(including VIN1_F, VIN2_F, VIN4_F, VIN8_F, VIN9_F, VIN11_F, VIN12_F). It
fires late (VIN10_F lead only 14 d). Best use: as a high-confidence escalation
signal when it does fire, not as the primary detection layer.

---

## 3. Ranked Summary Table

| Heuristic | Recall (n/14) | Med Lead (d) | NF ever-fire (n/20) | NF eps/yr | Complexity | Explainability | Priority |
|---|---|---|---|---|---|---|---|
| H4_multichannel | **14/14 (100%)** | 175 | **20/20 (100%)** ⚠️ | 1.00 ⚠️ | Medium | High | 1† |
| H1_momentum | **13/14 (93%)** | 126 | 19/20 (95%) ⚠️ | 0.75 | Low | High | 2† |
| BASELINE_persistence | 13/14 (93%) | **168** | 20/20 (100%) ⚠️ | — | Low | High | Ref |
| H2_pers_red | 10/14 (71%) | 116 | 5/20 (25%) ✓ | **0.19** | Low | High | 3 |
| H3_escalation | 9/14 (64%) | 77 | 8/20 (40%) | 0.24 | Medium | High | 4 |
| H5_fleet_pctile | 7/14 (50%) | 119 | 3/20 (15%) ✓ | **0.11** ✓ | Low | Medium | 5 |
| BASELINE_A2 | 4/14 (29%) | 66.5 | 0/20 (0%) ✓ | 0.00 ✓ | Medium | High | Ref |

† H4 and H1 achieve high recall at the cost of near-universal NF firing —
  use as **scoring inputs** in a multi-criterion gate, not standalone alarms.

---

## 4. H6 — Crank-While-Running Operational Abuse Metric

**Proxy definition**: Non-artifact crank events where `rpm_max_15s > 500` at
the start of the event. This proxies for engine-running crank engagement.
**Caveat**: `rpm_max_15s` is the maximum RPM in the first 15 seconds — it
includes the engine spin-up phase. True crank-while-running requires a
per-sample SMA=1 AND RPM>400 joint check on raw telemetry (not available in
the processed crank-events parquet).

| Group | n trucks | Total CWR proxy events | Mean rate / truck-yr |
|---|---|---|---|
| Failed (14) | 14 | 5,709 | 347 |
| Non-Failed (20) | 20 | 11,613 | 338 |

Mann-Whitney U test (F > NF rates): U=161, **p=0.24** — no significant
difference. **Conclusion: insufficient evidence to claim failure prediction
from this proxy.** The metric is elevated in both groups (~340 events/truck-yr),
suggesting fleet-wide operational behavior rather than a discriminative abuse
pattern. Domain physics (crank-while-running as a clutch/ring-gear killer)
may still apply but is not detectable at per-truck resolution with this proxy
measure and sample size.

**Recommendation**: Validate with raw telemetry scan (SMA=1 AND RPM>400, with
previous-row RPM>400 sustained-run check) before drawing conclusions.

---

## 5. Caveats and Deployment Guidance

1. **Sample size (n=34)**: All results are SCREEN-GRADE. Confidence intervals
   are wide; a single truck's behavior can shift recall by 7 percentage points.
2. **Pre-registered parameters**: H1–H5 thresholds come from the task spec,
   not from search on outcomes. Report them as is — do not tune retrospectively.
3. **Platt simplification**: Probabilities at large k (>10 weeks) are
   miscalibrated (score distribution shifts from k=0). Tier assignments are more
   reliable than raw probability values at those offsets.
4. **Persistence channel inflation**: The alert_validation CSV records "first
   fire ever" for the persistence channel, which fires on all 20 NF trucks at
   some point. H4 and H1 inherit this inflation. For deployment, use terminal
   episode state (is it still firing?) not historical first-fire.
5. **Right-censoring**: Several NF trucks with high activity (VIN2_NF, VIN5_NF,
   VIN8_NF, VIN15_NF) are plausibly degrading systems that had not failed by
   end of observation — they may be true detections in disguise.
6. **Multiplicity**: Five heuristics were evaluated simultaneously. Without
   a Bonferroni or Benjamini-Hochberg correction, at least one H1–H5 result
   would be expected to appear significant by chance. Pre-register thresholds
   before prospective deployment evaluation.

## 6. Recommended Deployment Combination

Based on recall, lead time, and FP burden:

- **Primary gate**: H2 (persistent-RED dwell, 10/14, 0.19 NF-eps/yr) —
  fires late but with high specificity; combine with A2 for short-fuse cases.
- **Scoring amplifier**: H1 (momentum, 13/14) — high sensitivity; use to
  rank severity within already-alarmed trucks, not as standalone pager.
- **Confirmatory channel**: H5 (fleet-percentile, 7/14, 0.11 NF-eps/yr) —
  when H5 fires alongside H2 or persistence, confidence is high.
- **Avoid standalone H4** as a pager: perfect recall but 100% NF fire rate
  makes it unsuitable as an alert trigger; use for internal risk scoring.

---

*Scripts:* `V2_program/analysis/heuristics/H_walking_scores.py`,
`H_eval_heuristics.py`, `H6_crank_while_running.py`

*Outputs:* `V2_program/analysis/heuristics/out/walking_scores.csv`,
`heuristic_fires.csv`, `heuristic_summary.csv`, `H6_crank_while_running.csv`
