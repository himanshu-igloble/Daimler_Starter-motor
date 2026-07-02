---
title: "V3.1 Starter Motor — Full Quantitative Results"
status: "complete"
created: "2026-07-02"
program: "SM V3.1"
sources: "V3_1_gate_summary.json, V3_1_validation.json, V3_1_sv_gates.json, T1_convergence.json, T1_attribution.csv, T2_windows.csv, T3_data_health.csv, catalog_exploratory_stats.csv"
---

# V3.1 Starter Motor — Full Quantitative Results

All numbers are cited directly from the produced artifacts. No rounding beyond the source
precision. Fleet: SM, n = 34 (14 failed / 20 non-failed). SCREEN-GRADE throughout.

---

## 0. Reconciliation gate (E0 / SV-5)

| Metric | Expected | Computed | \|Δ\| | Pass |
|---|---|---|---|---|
| Modal-4 non-nested LOVO AUROC | 0.9357 | **0.9357** | 0.0000 | **YES** |
| Modal-4 nested LOVO AUROC (E3 baseline) | — | 0.9321 | — | — |

`V3_1_gate_summary.json.reconciliation.pass = true`. The champion is byte-untouched; all
candidate results are valid relative to this baseline.

---

## 1. E1 admissibility gate

E1 = MW p ≤ 0.10 ∧ oriented AUROC ≥ 0.60 ∧ proxy-leak Spearman |ρ| ≤ 0.5 vs {n_weeks,
t_start, span} ∧ redundancy Pearson |r| < 0.85 vs each modal-4 feature. **Only A2 passed.**

| Feature | n_nonnull | MW p | Oriented AUROC | max\|ρ_proxy\| | max\|r_vs_modal\| | Proxy flag | Redund. flag | E1 pass |
|---|---|---|---|---|---|---|---|---|
| hard_start_goodv_rate_delta90 | 27 | 0.2104 | 0.6161 | 0.416 | 0.238 | No | No | No |
| dip_resid_trend_12w | 26 | **0.0679** | **0.6786** | 0.415 | 0.406 | No | No | **Yes** |
| lowv_crank_share_delta90 | 27 | 1.0000 | 0.5107 | 0.094 | 0.260 | No | No | No |
| starts_per_engine_hour_delta90 | 27 | 0.7884 | 0.5179 | 0.060 | 0.155 | No | No | No |
| dose_dip_x_intensity | 27 | 0.2319 | 0.6000 | 0.105 | 0.512 | No | No | No |
| dropout_share_delta90 | 34 | 0.8473 | 0.5214 | 0.102 | 0.269 | No | No | No |
| dip_seasonal_contrast | 16 | 0.8269 | 0.5089 | 0.046 | 0.786 | No | No | No |

**No proxy-leak or redundancy flag fired on any candidate.** Fleet-max proxy |ρ| = 0.416
(A1 vs t_start); fleet-max redundancy |r| = 0.786 (C2 vs `dip_depth_last90_delta`) — both
under their cuts. The REJECTs are genuine discriminative failures, not audit artifacts.
Notable: `dose_dip_x_intensity` hit oriented AUROC exactly 0.6000 but failed on MW p (0.2319).

---

## 2. E2 fixed-subset LOVO increment

E2 ADD iff Δ ≥ +0.01 over the 0.9357 non-nested baseline. Computed for all 7 as soft-signal
intelligence.

| Feature | E2 AUROC (modal-4 + cand.) | Δ vs 0.9357 | Pass (≥ +0.01) |
|---|---|---|---|
| hard_start_goodv_rate_delta90 | **0.9536** | **+0.0179** | No* |
| dip_resid_trend_12w | 0.9179 | −0.0179 | No |
| lowv_crank_share_delta90 | 0.9357 | 0.0000 | No |
| starts_per_engine_hour_delta90 | 0.9250 | −0.0107 | No |
| dose_dip_x_intensity | 0.9321 | −0.0036 | No |
| dropout_share_delta90 | 0.9179 | −0.0179 | No |
| dip_seasonal_contrast | 0.9000 | −0.0357 | No |

\*A1's Δ (+0.0179) exceeds +0.01 in magnitude but A1 **failed E1** (MW p 0.2104), so under
the pre-registered E1-before-E2 ordering it never reaches an E2 pass. See §6 verdict narrative.
Five of seven candidates carry **negative** E2 deltas — they actively harm held-out AUROC.

---

## 3. E3 nested rerun

**Not triggered.** E3 runs only for E2 survivors. The sole E1 survivor (A2) had a negative
E2 increment (−0.0179), so no candidate passed E2. `V3_1_gate_summary.json.E3 = null`.

---

## 4. Multiplicity control — Benjamini–Hochberg FDR

7 simultaneous Mann–Whitney tests (single family), from `V3_1_validation.json`.

| Feature | Raw MW p | BH-FDR adjusted p |
|---|---|---|
| dip_resid_trend_12w | 0.0679 | **0.4753** |
| hard_start_goodv_rate_delta90 | 0.2104 | 0.5411 |
| dose_dip_x_intensity | 0.2319 | 0.5411 |
| starts_per_engine_hour_delta90 | 0.7884 | 0.9885 |
| dropout_share_delta90 | 0.8473 | 0.9885 |
| dip_seasonal_contrast | 0.8269 | 0.9885 |
| lowv_crank_share_delta90 | 1.0000 | 1.0000 |

Smallest BH-FDR adjusted p = **0.4753** (`min_bh_p`). Nothing is significant under any
reasonable FDR level — an independent reconfirmation of the ceiling.

---

## 5. State-engine validation gates (SV-1..SV-5)

| Gate | Value | Verdict |
|---|---|---|
| SV-1 crank-boundary coverage | 0.9785 | PASS (≥ 0.90) |
| SV-2 per-VIN dwell report | 34-VIN report | PASS (report-only) |
| SV-3 km/day & engine-hrs/day plausibility | 0.936 | PASS (≥ 0.90; B1 retained) |
| SV-4 soak measurability | 0.7102 | pass = null (heartbeat refuted; clears 0.60 floor) |
| SV-5 champion reconciliation | 0.9357 (Δ 0.0000) | PASS |

Lowest per-VIN SV-1 fraction: VIN10_F_SM 0.9231; lowest soak_frac: VIN19_NF_SM 0.4039. Full
table in the state-engine report. Heartbeat `confirmed = false` (start_ok 0.9832 / end_ok
0.1587).

---

## 6. Channels (Tier 2 — SCREEN-GRADE, not E-gated)

### 6.1 T1 battery-vs-starter attribution

`T1_convergence.json`: `n_failed_scored = 11`, `n_agree = 9`, `a3_unscored = 3`; NF
distribution `{INSUFFICIENT: 20}`. **Convergence with V1.1 archetypes = 9/11 (82 %)** — a
consistency check against telemetry-derived archetypes, **not** ground-truth accuracy
(`Failure_type` is constant `"Starter Motor"`). Interpretation (curated): battery-family
5/5, A4-silent 4/4, both pure-A1 solenoid archetypes missed. **Present T1 as a battery-vs-
INSUFFICIENT triage, not a symmetric 3-way attributor**: the STARTER arm never fired
fleet-wide because the fleet `lowv_crank_share` median (0.4953) gates it off — the 26.0 V
registered low-voltage threshold sits above typical pre-crank baseline under load. The
solenoid channel is unvalidated (n = 2). **Zero false attributions on the 20 healthy trucks**
(all INSUFFICIENT).

Per-VIN failed (14) — from `T1_attribution.csv`:

| VIN | Attribution | goodv-hardstart wk (of 12) | lowv_crank_share | A2 fired | cranks last 90 d |
|---|---|---|---|---|---|
| VIN1_F_SM | BATTERY_FIRST | 3 | 0.667 | False | 132 |
| VIN2_F_SM | BATTERY_FIRST | 1 | 0.696 | False | 71 |
| VIN3_F_SM | BATTERY_FIRST | 0 | 0.392 | True | 93 |
| VIN6_F_SM | BATTERY_FIRST | 1 | 0.205 | True | 52 |
| VIN13_F_SM | BATTERY_FIRST | 0 | 0.391 | True | 31 |
| VIN14_F_SM | BATTERY_FIRST | 1 | 0.677 | True | 110 |
| VIN4_F_SM | INSUFFICIENT | 1 | 0.390 | False | 147 |
| VIN5_F_SM | INSUFFICIENT | 0 | 0.500 | False | 27 |
| VIN7_F_SM | INSUFFICIENT | 1 | 0.673 | False | 177 |
| VIN8_F_SM | INSUFFICIENT | 0 | 0.536 | False | 333 |
| VIN9_F_SM | INSUFFICIENT | 0 | 0.209 | False | 120 |
| VIN10_F_SM | INSUFFICIENT | 0 | 0.609 | False | 49 |
| VIN11_F_SM | INSUFFICIENT | 0 | 0.519 | False | 46 |
| VIN12_F_SM | INSUFFICIENT | 2 | 0.782 | False | 63 |

Failed split: **6 BATTERY_FIRST / 8 INSUFFICIENT**; A2 cascade fired on 4 (VIN3/6/13/14_F).

### 6.2 T2 graded-window bands

From `T2_windows.csv` (34 VINs). Actual band distribution — the spec's "12 non-GREEN"
estimate was low; the realized non-GREEN count is **16**:

| Band | Count | Window (days) |
|---|---|---|
| GREEN_no_action | 18 | None |
| persistence_AND_RED | 9 | [126, 284] (8 of 9; VIN2_F_SM is battery-first → [28, 91]) |
| A2_battery_cascade | 4 | [28, 91] |
| AMBER_only | 3 | None |

**13 actionable windows** (window ≠ None). Battery-first trucks correctly inherit the earlier
28–91 d window; starter-first / persistence∧RED bands inherit 126–284 d. The four
A2_battery_cascade trucks (VIN3/6/13/14_F) route to battery service first.

### 6.3 T3 data-health monitor

From `T3_data_health.csv` (2,636 VIN-weeks): **638 escalation-weeks across 32 of 34 VINs**
(only VIN3_F_SM and VIN4_F_SM never escalate). **Silent-gap escalation = 4/5**: VIN1_F (8
escalation-weeks), VIN5_F (4), VIN8_F (14), VIN9_F (33) all escalate; **VIN4_F is missed
mechanistically** — its 97-day silence is a blackout classified `UNKNOWN_GAP` (~1,968 h), not
`DROPOUT_RUNNING` (~12.8 h), so the dropout-ratio escalation rule cannot see it. Scoped fix:
add an unknown-gap channel. Framed as a **materially-elevated dropout tracker, not a pager**
(no pager claim; the V2.1 accept-bar is not invoked).

---

## 7. Exploratory post-gate leads (V3.2 pre-registration only)

Top raw separators on the descriptive catalog (BH-unsafe — 0.0219 raw → ~0.72 adjusted over
33 features; see feature catalog § Exploratory for the full 33-row table):

| Feature | raw MW p | oriented AUROC |
|---|---|---|
| monsoon_start_share | 0.0219 | 0.7357 |
| hard_start_goodv_rate (LEVEL) | 0.0239 | 0.6875 |
| consecutive_high_crank_days_max90 | 0.0404 | 0.6946 |
| dropout_hours_per_week | 0.0715 | 0.6857 |

None significant post-multiplicity; leads for V3.2 only, never promoted within V3.1.

*All numbers cited from the artifacts named in the frontmatter. Fleet: SM, n = 34.
SCREEN-GRADE caveat applies throughout.*
