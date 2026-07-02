---
title: "V3.1 Starter Motor — Feature Dictionary (7 Pre-Registered Candidates)"
status: "complete"
created: "2026-07-02"
program: "SM V3.1"
sources: "V3_1_gate_summary.json, V3_1_validation.json, V3_1_candidates.json, spec §7.2"
---

# V3.1 Starter Motor — Feature Dictionary

Seven candidates were pre-registered in `params/V3_1_candidates.json` before any result was
computed, engineered against the state engine + frozen crank-event catalog, and adjudicated
through the frozen V1.1/V3 gate (E0→E1→E2→E3). **All 7 received a REJECT verdict.** This
dictionary is the permanent record: each entry gives the registered definition and physics
**verbatim from spec §7.2**, the realized parameters, `n_nonnull`, the full E1 row, the E2
increment, and the verdict + reason quoted from `V3_1_gate_summary.json`.

Registered thresholds (`V3_1_gate_params.json`): good-voltage 27.0 V, low-voltage 26.0 V;
E1 = MW p ≤ 0.10 ∧ oriented AUROC ≥ 0.60 ∧ proxy-leak Spearman |ρ| ≤ 0.5 vs {n_weeks,
t_start, span} ∧ redundancy Pearson |r| < 0.85 vs each modal-4 feature; E2 ADD iff
ΔAUROC ≥ +0.01 over 0.9357. BH-FDR adjusted p from `V3_1_validation.json`.

---

## Family A — Attribution (battery-vs-starter separation)

### A1 — `hard_start_goodv_rate_delta90`

**Registered definition (spec §7.2).** "weekly rate = (failed cranks with `baseline_vsi`
≥ 27.0 V) / active days; feature = Δ90."

**Physics (spec §7.2).** "a starter that fails to achieve run-up despite a healthy 24 V bus
(rest median 28.0 V) isolates starter-side degradation — brush contact loss, solenoid
contact erosion, pinion engagement failure — from battery weakness. This is the
voltage-conditioned repair of two graveyard features (`first_crank_fail_rate` 0.706
admissible-never-selected; `failed_crank_rate_last30` E2 +0.004): the conditioning removes
battery-driven false positives that diluted them."

**Realized result.**
- Inputs: frozen crank-event catalog only. `n_nonnull` = **27 / 34** (failed-start sparsity on NF).
- E1: MW p = **0.2104** (FAIL, > 0.10); oriented AUROC = **0.6161** (pass, ≥ 0.60).
- Proxy audit: max |ρ| = 0.416 (t_start); {n_weeks −0.31, span −0.32} → no flag.
- Redundancy: max |r| = 0.238 (vsi_withinwk_std_ratio_30d_w) → no flag.
- E2: AUROC = **0.9536**, Δ = **+0.0179** — the **only positive E2 increment** in the set,
  and above the +0.01 bar in magnitude.
- BH-FDR adjusted p = 0.5411.

**Verdict: REJECT** — `"E1 fail (mw_p=0.2104, auroc=0.6161)"`. A1 is a **near-miss** (see
verdict report §near-miss): its positive multivariate lift arrives *without* univariate
significance, which is the small-n multivariate-lift signature the E1-before-E2 ordering is
designed to refuse (the V3 `weakbat_cold_load` analog). The pre-registered ordering held.

### A2 — `dip_resid_trend_12w`

**Registered definition (spec §7.2).** "per VIN: OLS fit `dip_depth ~ β0 + β1·baseline_vsi`
on non-artifact events in the L40 baseline window *excluding the last 12 masked weeks*
(≥ 30 qualifying events required, else null); weekly median residual over the last 12 masked
weeks; feature = Theil–Sen slope of those 12 weekly medians."

**Physics (spec §7.2).** "dip depth rising *at constant supply voltage* means rising current
draw or contact resistance in the crank circuit — a starter-side signature by construction.
Residualization is the designed decorrelator from the champion dip feature."

**Realized result.**
- `n_nonnull` = **26 / 34** (≥ 30-event regression-stability requirement).
- E1: MW p = **0.0679** (pass, ≤ 0.10 — the **only E1-significant candidate**); oriented
  AUROC = **0.6786** (pass; **best univariate AUROC** in the set). Proxy max |ρ| = 0.415
  (n_weeks) → no flag; redundancy max |r| = 0.406 (vsi_range_trend) → no flag.
  **`e1_pass = true`** — the sole E1 survivor.
- E2: AUROC = **0.9179**, Δ = **−0.0179** — a *negative* increment. Adding A2 **hurts** the
  champion.
- BH-FDR adjusted p = **0.4753** (smallest in the set).

**Verdict: REJECT** — `"E2 delta=-0.0179 <= 0"`. A2 is the second **near-miss**: it passes
E1 cleanly but the residualized starter-side trend is effectively redundant with the champion
dip channel below the r-cut, so it degrades held-out AUROC when added. A genuine univariate
signal that carries no *incremental* information.

### A3 — `lowv_crank_share_delta90`

**Registered definition (spec §7.2).** "weekly share = (cranks with `baseline_vsi` < 26.0 V)
/ (cranks with valid `baseline_vsi`); feature = Δ90."

**Physics (spec §7.2).** "low-voltage cranking dose — each low-voltage crank draws higher
current for longer (P = VI at fixed work), accelerating brush/commutator and solenoid-contact
wear. Battery-side stress exposure, complementary to A1."

**Realized result.**
- `n_nonnull` = 27 / 34. E1: MW p = **1.0000** (FAIL); oriented AUROC = **0.5107** (FAIL, at
  chance). Proxy max |ρ| = 0.094; redundancy max |r| = 0.26 (dip_depth_last90_delta) → no flag.
- E2: AUROC = 0.9357, Δ = **0.0000**. BH-FDR adjusted p = 1.0000.

**Verdict: REJECT** — `"E1 fail (mw_p=1.0, auroc=0.5107)"`. The low-voltage-crank share does
not separate failed from non-failed at n = 34 (see T1 §: the 26.0 V threshold sits above the
typical pre-crank baseline under load, so the fleet lowv share clusters near its median 0.4953
and carries no discriminative edge).

---

## Family B — Usage-normalized intensity

### B1 — `starts_per_engine_hour_delta90`

**Registered definition (spec §7.2).** "weekly rate = valid cranks / engine-hours (null if
engine-hours < 5 h in week); feature = Δ90. Null for SMA-dead cohort."

**Physics (spec §7.2).** "start-cycle dose per operating hour is the correct wear-rate
normalization for a cycle-limited component (~30–40k crank design life). Calendar-day
denominators (graveyard `starts_per_active_day`) conflate observation density with duty."

**Realized result.**
- Inputs: crank catalog + state engine (engine-hours). `n_nonnull` = 27 / 34.
- E1: MW p = **0.7884** (FAIL); oriented AUROC = **0.5179** (FAIL). Proxy max |ρ| = 0.06;
  redundancy max |r| = 0.155 → no flag.
- E2: AUROC = 0.925, Δ = **−0.0107**. BH-FDR adjusted p = 0.9885.

**Verdict: REJECT** — `"E1 fail (mw_p=0.7884, auroc=0.5179)"`. Correcting the denominator to
engine-hours (the physically correct normalization, unlocked by the state engine) did not
rescue the duty-cycle family from its null history. SV-3 passed (0.936), so the failure is
discriminative, not an engine-hours data-quality artifact.

### B2 — `dose_dip_x_intensity`

**Registered definition (spec §7.2).** "fold-internal z(dip_depth_last90_level) ×
z(starts_per_engine_hour_last90)."

**Physics (spec §7.2).** "energy-per-crank × cycle rate = power dissipation dose.
Re-registration of V3's rejected `dose_dip_x_starts` with a materially changed denominator
(engine-hours, not active days) — allowed under the novel-or-materially-changed rule, with the
V3 rejection (MW p = 0.2515) disclosed as the prior."

**Realized result.**
- `n_nonnull` = 27 / 34. E1: MW p = **0.2319** (FAIL); oriented AUROC = **0.6000** (exactly at
  the 0.60 boundary — pass on AUROC, fail on p). Proxy max |ρ| = 0.105; redundancy max |r| =
  **0.512** (dip_depth_last90_delta) → no flag (< 0.85).
- E2: AUROC = 0.9321, Δ = **−0.0036**. BH-FDR adjusted p = 0.5411.

**Verdict: REJECT** — `"E1 fail (mw_p=0.2319, auroc=0.6)"`. Swapping the denominator to
engine-hours moved the V3 prior (p 0.2515) only marginally (p 0.2319); the dose interaction
remains univariately insignificant and non-incremental. The engine-hours re-registration is
now a closed door too.

---

## Family C — Expected-null honesty probes

### C1 — `dropout_share_delta90`

**Registered definition (spec §7.2).** "weekly share = DROPOUT hours / (DROPOUT + observed
hours); feature = Δ90." (SMA-dead-exempt — computes for all 34 VINs.)

**Physics (spec §7.2).** "missingness-as-signal — degrading electrical systems can kill the
TCU before the starter fails outright (V12-ALT precedent: GED-absence; SM precedent: 5/14
failed VINs go silent 32–142 d before JCOPENDATE)."

**Realized result.**
- `n_nonnull` = **34 / 34** (only candidate computing for the whole fleet). E1: MW p =
  **0.8473** (FAIL); oriented AUROC = **0.5214** (FAIL). Proxy max |ρ| = 0.102 (span) — well
  under the 0.5 cut, so the anticipated leak-audit trip did **not** fire; redundancy max |r| =
  0.269 → no flag.
- E2: AUROC = 0.9179, Δ = **−0.0179**. BH-FDR adjusted p = 0.9885.

**Verdict: REJECT** — `"E1 fail (mw_p=0.8473, auroc=0.5214)"`. Missingness-as-signal is a
real information channel (see T3 monitor: 638 escalation-weeks), but the *delta-90 dropout
share* does not separate failed from non-failed as a scalar feature. The strict proxy audit
was decisive-either-way by design, and here it cleared — the feature simply carries no label
signal in this form.

### C2 — `dip_seasonal_contrast`

**Registered definition (spec §7.2).** "median dip_depth over non-artifact events in Dec–Feb
minus median over Apr–Jun, within the VIN's L40-masked span (pooling across calendar years if
the span covers more than one); null unless ≥ 15 qualifying events in *each* window. No Δ90
(it is already a within-VIN contrast)."

**Physics (spec §7.2).** "an aging battery/starter amplifies cold-morning dips; the within-VIN
contrast dodges the no-GPS problem (each VIN is its own climate control)."

**Realized result.**
- `n_nonnull` = **16 / 34** (high null rate — the ≥ 15-events-per-window requirement is
  demanding). E1: MW p = **0.8269** (FAIL); oriented AUROC = **0.5089** (FAIL). Proxy max |ρ|
  = 0.046; redundancy max |r| = **0.786** (dip_depth_last90_delta — the highest in the set) →
  no flag (< 0.85, but the overlap with the champion dip is documented).
- E2: AUROC = 0.9, Δ = **−0.0357** (the largest negative increment). BH-FDR adjusted p = 0.9885.

**Verdict: REJECT** — `"E1 fail (mw_p=0.8269, auroc=0.5089)"`. This is the last
temperature-adjacent construction, now closed **with evidence** rather than assumption (see
`appendix/temperature_closure_and_annex.md`). The within-VIN winter-minus-summer dip contrast
carries no SM failure signal at n = 16.

---

## Summary table

| # | Feature | Family | n_nonnull | MW p | Oriented AUROC | E1 pass | E2 AUROC | E2 Δ | BH-FDR adj-p | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| A1 | hard_start_goodv_rate_delta90 | Attribution | 27 | 0.2104 | 0.6161 | No | 0.9536 | **+0.0179** | 0.5411 | REJECT |
| A2 | dip_resid_trend_12w | Attribution | 26 | **0.0679** | **0.6786** | **Yes** | 0.9179 | −0.0179 | **0.4753** | REJECT |
| A3 | lowv_crank_share_delta90 | Attribution | 27 | 1.0000 | 0.5107 | No | 0.9357 | 0.0000 | 1.0000 | REJECT |
| B1 | starts_per_engine_hour_delta90 | Usage | 27 | 0.7884 | 0.5179 | No | 0.9250 | −0.0107 | 0.9885 | REJECT |
| B2 | dose_dip_x_intensity | Usage | 27 | 0.2319 | 0.6000 | No | 0.9321 | −0.0036 | 0.5411 | REJECT |
| C1 | dropout_share_delta90 | Probe | 34 | 0.8473 | 0.5214 | No | 0.9179 | −0.0179 | 0.9885 | REJECT |
| C2 | dip_seasonal_contrast | Probe | 16 | 0.8269 | 0.5089 | No | 0.9000 | −0.0357 | 0.9885 | REJECT |

E1 threshold: MW p ≤ 0.10 AND oriented AUROC ≥ 0.60 (both required). E2 threshold:
Δ ≥ +0.01 over the modal-4 non-nested baseline 0.9357. Only A2 passed E1; its E2 Δ was
negative, so no candidate reached E3. Smallest BH-FDR adjusted p = 0.4753 (A2) — nothing is
significant under multiplicity control.

*All numbers cited from `V3_1_gate_summary.json` and `V3_1_validation.json`. Fleet: SM,
n = 34 (14 F / 20 NF). SCREEN-GRADE caveat applies throughout.*
