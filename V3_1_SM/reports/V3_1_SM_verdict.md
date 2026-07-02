---
title: "V3.1 Starter Motor — Synthesis and Verdict"
status: "complete"
created: "2026-07-02"
program: "SM V3.1"
sources: "V3_1_gate_summary.json, V3_1_validation.json, V3_1_sv_gates.json, T1/T2/T3 outputs, spec §14"
---

# V3.1 Starter Motor — Synthesis and Verdict

## 1. Outcome statement

**V3.1 result: NO IMPROVEMENT / ALL HOLD.**

All 7 pre-registered candidates REJECTED. The frozen modal-4 feature set remains the
production configuration. The data ceiling holds at **non-nested LOVO AUROC = 0.9357 / nested
= 0.9321**. This was the **pre-registered expected outcome** (spec §1, §12: "All 7 candidates
REJECT — High, this is the stated prior"). A rigorous negative on the operational-state /
usage-normalized surface is a legitimate, valuable result: it closes seven more doors with
exact numbers and hardens the ceiling argument, while the Tier 2–4 deliverables (state engine,
T1 triage, T3 monitor, annexes) ship regardless of any AUROC movement.

---

## 2. Per-candidate verdict (from `V3_1_gate_summary.json`)

| Feature | Family | Oriented AUROC | MW p | E2 Δ | Verdict | Reason (verbatim) |
|---|---|---|---|---|---|---|
| hard_start_goodv_rate_delta90 | A | 0.6161 | 0.2104 | +0.0179 | **REJECT** | E1 fail (mw_p=0.2104, auroc=0.6161) |
| dip_resid_trend_12w | A | 0.6786 | 0.0679 | −0.0179 | **REJECT** | E2 delta=-0.0179 <= 0 |
| lowv_crank_share_delta90 | A | 0.5107 | 1.0000 | 0.0000 | **REJECT** | E1 fail (mw_p=1.0, auroc=0.5107) |
| starts_per_engine_hour_delta90 | B | 0.5179 | 0.7884 | −0.0107 | **REJECT** | E1 fail (mw_p=0.7884, auroc=0.5179) |
| dose_dip_x_intensity | B | 0.6000 | 0.2319 | −0.0036 | **REJECT** | E1 fail (mw_p=0.2319, auroc=0.6) |
| dropout_share_delta90 | C | 0.5214 | 0.8473 | −0.0179 | **REJECT** | E1 fail (mw_p=0.8473, auroc=0.5214) |
| dip_seasonal_contrast | C | 0.5089 | 0.8269 | −0.0357 | **REJECT** | E1 fail (mw_p=0.8269, auroc=0.5089) |
| **Frozen modal-4** | — | — | — | **0.0000** | **KEEP** | — |

No candidate cleared both E1 criteria and E2. Smallest BH-FDR adjusted p = 0.4753. No proxy
or redundancy flag fired.

---

## 3. The two near-misses (the story behind the numbers)

The rejection is not uniform noise — two candidates each cleared exactly one of the two hurdles
that E1-before-E2 is designed to require jointly, and the pre-registered ordering correctly
refused both.

**A2 `dip_resid_trend_12w` — the sole E1 pass that hurts the champion.** A2 is the only
candidate to clear E1 (MW p 0.0679, oriented AUROC 0.6786 — both best-in-set) and it carries
the smallest BH-FDR adjusted p (0.4753). It is a *genuine univariate signal*: dip depth rising
at constant supply voltage is a starter-side signature by construction. But its E2 increment is
**−0.0179** — adding it *degrades* held-out AUROC. The residualized trend is effectively
redundant with the champion dip channel (r = 0.406 vs `vsi_range_trend`, 0.359 vs
`dip_depth_last90_delta`) below the 0.85 r-cut: real signal, zero *incremental* signal.

**A1 `hard_start_goodv_rate_delta90` — the sole positive E2 Δ without E1 merit.** A1 is the
only candidate with a positive E2 increment (**+0.0179**, above +0.01 in magnitude), yet it
**fails E1** (MW p 0.2104). A multivariate lift that appears without univariate significance at
n = 34 is the textbook small-n multivariate-lift signature — the direct analog of V3's
`weakbat_cold_load` (which showed GBM in-sample weight and +0.0071 E2 with no univariate merit,
confirmed as overfit). The pre-registered **E1-before-E2 ordering refuses it**, and BH-FDR
(adjusted p 0.5411) independently reconfirms there is no univariate evidence to support the
fold-level gain. Had the ordering been reversed, A1 would have been a false positive.

Both near-misses are *wins for the protocol*: the gate did exactly what pre-registration is
for — it prevented a redundant signal and an overfit signal from shipping.

---

## 4. The ceiling holds — a fourth consecutive iteration

The data ceiling is now evidenced across four independent iterations:

| Iteration | Evidence | Ceiling |
|---|---|---|
| V1.1 | nested 0.9321; prequential AUROC decays to ~0.5 at k = 11 weeks | 0.9321 |
| V2 | density audit r(failed, n_weeks) = −0.771; 12-feature pool dropped nested to 0.875 | held |
| V2.1 / V3 | strict gate rejected best prior candidates; V3 all-7 REJECT; GBM probe 0.843 < 0.932 (data-not-method) | held |
| **V3.1** | **state-engine + usage-normalized surface all-7 REJECT; near-misses redundant/overfit** | **0.9357 / 0.9321** |

**V3.1 adds a distinct new line of evidence — the fourth consecutive iteration at the ceiling**: even with a proper operational-state layer —
correct engine-hours denominators (B1), soak context, dropout accounting (C1), and a
starter-side decorrelated dip trend (A2) — the surface carries no incremental signal. The
things that were structurally impossible before the state engine existed (physically-correct
duty normalization, missingness-as-signal, residualized starter-side trend) have now been
built and tested. They REJECT. The cap is the **data** — n = 34 and the 5-second, 6-signal
frame — not missing feature engineering and not the linear model class.

---

## 5. Tiered-success scorecard (spec §1)

| Tier | Deliverable | Success condition | Result |
|---|---|---|---|
| **1 — Confirmatory** | 7 candidates through E0→E3 | Honest verdict; all-REJECT acceptable | **MET** — all 7 REJECT, exactly as pre-registered; near-misses explained |
| **2 — Channel** | T1 battery-vs-starter triage | Convergence with archetypes (SCREEN-GRADE) | **MET** — 9/11 (82 %) convergence; battery-vs-INSUFFICIENT triage; **0 false attributions on 20 NF**; solenoid arm unvalidated (n = 2), disclosed |
| **3 — Infrastructure** | State engine + episode/usage catalog + data-health monitor | SV gates pass; promotable to `src/` | **MET** — SV-1 0.9785, SV-3 0.936, SV-5 exact, SV-4 0.7102 (clears floor); 34-VIN episode/weekly rollups; 33-feature catalog; T3 monitor (638 escalation-weeks) |
| **4 — Roadmap** | Instrumentation annex v2 | Region / GPS / SPN 171 / SPN 110 asks refined | **MET** — `appendix/temperature_closure_and_annex.md` + `appendix/instrumentation_v2.md` |

**Artifact list (Tier 3).** `state/sm_state_engine.py` (+ tests); `state/out/`
episode/trip/weekly parquets × 34 VINs + `V3_1_state_weekly_ALL.parquet` (fleet: 130,842.9
engine-hrs, 3,552,966.9 km, 20,877 CRANK episodes); `V3_1_sv_gates.json`;
`features/out/V3_1_SM_catalog.csv`; `heuristics/out/{T1_attribution.csv, T1_convergence.json,
T2_windows.csv, T3_data_health.csv}`; graphs G1–G8.

---

## 6. What would change our mind

The ceiling is a data ceiling, so only new data moves it:

1. **New instrumentation** (highest ROI; see `appendix/instrumentation_v2.md`) — a battery
   current sensor for true crank-current I²t dose, 1 Hz VSI burst sampling around SMA events to
   recover the sub-second dip waveform the 5 s cadence destroys, and SPN 110 coolant-at-key-on
   as the best available crank thermal proxy. These reach physics the voltage-only 5 s frame
   cannot.
2. **A larger failure cohort** — n = 14 failed is SCREEN-GRADE; one truck ≈ 7 pp of recall.
   Every ~10 additional failed examples cuts LOVO variance by ~√(n/(n+10)); at n ≈ 50 failed
   the SCREEN-GRADE caveat relaxes substantially.
3. **Maintenance / parts records** — would convert T1's telemetry-derived archetypes and the
   attribution channel into supervised labels, ending the convergence-vs-accuracy caveat and
   letting the solenoid arm (currently n = 2) be validated.

Absent these, feature engineering on the existing 6-signal / 5-second frame is **closed** —
V3.1 tested the last structurally-new surface (operational state) and it holds.

---

## 7. Definition of Done (spec §14 — 8 items)

| # | Item | Status | Artifact |
|---|---|---|---|
| 1 | `params/` JSONs committed before any result | DONE | `V3_1_candidates.json`, `V3_1_gate_params.json`, `V3_1_state_params.json` |
| 2 | P0-1..P0-6 executed; data-reality memo; state params frozen | DONE | `state/out/P0_*.json`, `reports/V3_1_SM_data_reality_memo.md` |
| 3 | State engine + tests; SV-1..SV-5 adjudicated; rollups × 34 VINs | DONE | `state/sm_state_engine.py`, `state/tests/`, `V3_1_sv_gates.json`, `state/out/*.parquet` |
| 4 | E0 passes; all candidates E1→E2(→E3); BH-FDR reported | DONE | `V3_1_gate_summary.json`, `V3_1_validation.json` |
| 5 | Catalog (~36) computed + classified; §6.3 discipline honored | DONE | `V3_1_SM_catalog.csv`, `reports/V3_1_SM_feature_catalog.md` |
| 6 | T1 attribution + convergence; T2 window table; T3 monitor | DONE | `T1_attribution.csv`, `T1_convergence.json`, `T2_windows.csv`, `T3_data_health.csv` |
| 7 | All §10 deliverables written; G1–G8 rendered; one honest verdict permitting all-REJECT | DONE | `reports/*.md`, `graphs/G1–G8.png`, this verdict |
| 8 | Column-dictionary correction note (VSI volts / sentinel reality) | DONE | `docs/column_dictionary.md` — "Correction note (2026-07 V3.1 SM probes)" (Task 15; source: data-reality memo P0-6) |

---

## 8. Recommendation

- **FREEZE the feature set at modal-4** (`vsi_withinwk_std_ratio_30d_w`, `rest_vsi_p05_delta90`,
  `vsi_range_trend`, `dip_depth_last90_delta`); AUROC 0.9357 non-nested / 0.9321 nested.
- **PROMOTE the state engine to `src/`** as a separate future commit (all SV gates pass).
- **SHIP T1 battery-first routing** as an operational triage (SCREEN-GRADE), and **T3** as a
  dropout tracker (not a pager).
- **Feature engineering on the existing frame: CLOSED.** Next iteration only on new
  instrumentation or a larger cohort.

*All numbers cited from the artifacts named in the frontmatter. Fleet: SM, n = 34 (14 F /
20 NF). SCREEN-GRADE caveat applies throughout.*
