---
title: "Starter Motor Vertical — 500+ Vehicle Full-Scale Execution Plan (HLD + LLD, Phase-Wise)"
status: "complete"
created: "2026-07-02"
updated: "2026-07-02"
---

# STARTER MOTOR — 500+ Vehicle Full-Scale Execution Plan

**Program:** DICV / BharatBenz 5528T Predictive Maintenance — Starter Motor vertical
**Baseline frozen model:** V1.1 modal-4 Ridge, nested LOVO AUROC 0.9321 (non-nested 0.9357), ceiling confirmed through V2 → V2.1 → V3 → V3.1 (4 consecutive iterations)
**Pilot fleet:** 34 trucks (14 failed + 20 non-failed) → **Target fleet: 500+ trucks (~250 failed + ~250 healthy retrospective cohort, then prospective)**
**Companion document:** `2026-07-02-19-04-56-ALT-500vehicle-fullscale-execution-plan.md` (Alternator vertical — independent fleet, shared platform)

> **VIN Independence rule carries forward:** SM and ALT fleets are disjoint physical trucks. All IDs suffixed `_SM`. No cross-vertical VIN-level analysis is valid.

---

## 0. Executive Summary

The 34-truck SM pilot is the most heavily audited model line in this program: a **4-feature Ridge** ("modal-4") achieves nested LOVO AUROC **0.9321** with per-fold Platt-calibrated, shippable probabilities; a **10-week prediction horizon** is demonstrated prequentially; three validated alert channels exist (a persistence condition-flag, a zero-false-alarm battery-cascade detector, and the **H2 persistent-RED dwell pager** at 0.19 false episodes/truck-year with 116-day median lead); a Youden-threshold maintenance-queue policy saves **43.3 %** of run-to-failure cost; and a rule-based **battery-vs-starter triage (T1)** attributes 9/11 scored failures correctly with zero false attributions on healthy trucks. Four iterations of candidate-feature hunting (19 candidates evaluated, none promoted) failed to beat this champion, and a GBM probe scored 0.843 < 0.932 — the ceiling is **data, not method**.

At **500 vehicles (~250 failure events)** the plan re-opens every one of those closed doors under pre-registered gates, because the rejections were **power-limited at n=34, not physics-refuted** — with one honest exception that no fleet size fixes:

| Pilot constraint (n=34, 14 failures) | At 500 vehicles (~250 failures) | Consequence |
|---|---|---|
| Modal-4 linear champion; every richer model/feature rejected | GBM/interactions estimable (SCANIA precedent) | Champion–challenger program (Phase 6) |
| Anomaly detection unusable at small n (program-wide finding) | ~250 healthy trucks give a real fleet reference | Budgeted watchlist channel (Phase 7) |
| Empirical A5 window lookup (126–284 d etc.), no per-truck RUL | Survival/hazard models estimable; **competing risks** (battery vs starter) become learnable with job-card codes | Calibrated P10–P90 windows + cause-specific hazards (Phase 8) |
| H2 pager threshold/dwell tuned on 34 trucks | Re-derived on OOF n=500 at the same 0.19 ep/truck-yr budget | Alert re-costing (Phase 5) |
| T1 starter-arm (26 V) never fires — threshold sits above fleet's real crank baselines | 26 V cut re-estimated from ~250-truck baseline distribution (pre-registered V3.2 lead) | Triage v2 (Phase 6) |
| Monsoon & hard-start-LEVEL leads at raw p≈0.02, killed by FDR at n=34 | Powered re-test | Graduation list (Phase 6) |
| 34-fold nested LOVO | Grouped stratified 10×5 CV + temporal holdout + prequential replay | Same discipline, scalable (Phase 4) |
| **5-second sampling collapses all starter-internal failure modes into one syndrome; a 1–3 s crank can produce zero VSI samples** | **Unchanged by fleet size** | Instrumentation workstream is the only fix: VSI 50–100 Hz burst during cranks (Section 11) |

**The honest physics constraint:** at 5 s / 0.2 V resolution, brush wear, solenoid degradation, and pinion problems all look identical until very late. More trucks sharpen *ranking* and *windows*; only crank-resolved sampling changes early *detection*. The plan states recall targets accordingly and carries the instrumentation ask as a first-class workstream.

**Deliverable stack at production:** weekly batch scoring of 500+ trucks (daily data refresh + daily A1/A2 event detectors), parquet lakehouse (SM measured compression 10.2:1 failed / 6.4:1 healthy), champion modal-4 + challenger program behind promotion gates, four alert channels + T1 triage feeding TruckConnect, label-triggered retraining on Spot A10 (~$2–3/cycle), full MLOps loop. Time to production: **~16 weeks with 2 engineers standalone, or +2 weeks offset behind the ALT vertical on the shared platform** (Section 13).

---

## 1. Starting Point — The Frozen 34-Truck Baseline (what we port, verbatim)

This section is the contract for Phase 4: the scale-up pipeline must reproduce these numbers on pilot data exactly before anything new is trained. (V3/V3.1 already demonstrated exact reproduction of 0.9357/0.9321 as their gate — that harness is inherited.)

### 1.1 Champion model — exact frozen spec

- **Model:** `RidgeClassifier(alpha=1.0)` on 4 standardized features; per fold: fold-internal train-median imputation → `StandardScaler` → Ridge. Verified against closed-form ridge to max |Δz| = 1.6e-15.
- **Validation:** fully nested 34-fold LOVO. Inside each outer fold: V1-faithful in-fold screening (Mann-Whitney p < 0.10, AUROC ≥ 0.60, |Spearman| < 0.85 dedup, stability ≥ 27/33 re-screens, pool cap 10) → exhaustive subset search k=3..6 → inner winner by 33-fold inner-LOVO AUROC (tie-break: smaller k, then MCC) → per-fold inner-OOF Youden threshold (pre-registered) → per-fold **Platt recalibration** on inner-OOF decision values.
- **Headline:** nested AUROC **0.9321**; non-nested modal-subset AUROC **0.9357** (optimism delta +0.0036 — evidence the selection protocol is honest).
- **Calibration:** V1's slope was 4.72 (rank-only); V1.1 Platt gives Brier 0.124 (constant-ref 0.242), CITL −0.062, slope 0.86 ∈ [0.5, 2] → **shippable probabilities**.
- **Known error:** sole nested miss VIN9_F_SM (OOF prob 0.401 vs fold threshold 0.406 — margin 0.005; recalibrated 0.224 → GREEN tier).
- **Horizon:** prequential AUROC ≥ 0.75 sustained k=0..**10 weeks** (0.768 at k=10; collapses to 0.704 at k=11; the isolated k=15 blip is a cohort-composition artifact, not counted).
- **Winner stability (honest footnote):** modal-4 selected in 14/34 outer folds (tied with its k=3 core at 14/34); the strict ≥17/34 stability gate FAILED even though the substantive core pair (`vsi_withinwk` + `vsi_range_trend`) is selected 34/34. Carry this nuance into the 500-vehicle model card.

### 1.2 The four frozen features (weekly masked-week cache; L40 window)

Aggregation basis: **masked weeks** = ISO weeks with `active_days ≥ 2`; **L40** = last 40 masked weeks per VIN. Crank features come from the frozen crank-event catalog (§1.3).

| # | Feature | Formula (verbatim) | Coef (X5 refit) | Notes |
|---|---|---|---|---|
| 1 | `vsi_withinwk_std_ratio_30d_w` | `nanmean(vsi_drive_std[last 4 masked wks]) / nanmean(vsi_drive_std[full L40])` | **+0.8862** | workhorse; univariate AUROC 0.921; selected 34/34 folds |
| 2 | `rest_vsi_p05_delta90` | `nanmean(vsi_rest_p05[last 13 wks]) − nanmean(baseline wks)`; baseline = L40 minus last 13; **battery-step-aware re-baseline**: if a step ≥ +0.5 V (SNR ≥ 2) falls in baseline, use post-step weeks only (≥4 required) | −0.2704 | resting-floor sag; re-baselined VINs: VIN8_F + VIN3/5/12/17/18_NF |
| 3 | `vsi_range_trend` | Theil–Sen slope of weekly `(vsi_drive_p95 − vsi_drive_p05)` over last 12 masked weeks (≥6 finite) | −0.4139 | **suppressor**: sign flipped by r=+0.82 collinearity with #1; univariate 0.732; flagged in model card |
| 4 | `dip_depth_last90_delta` | `mean(dip_depth | events ≤ 90 d before t_end) − mean(dip_depth | L40 baseline events > 90 d)`; ≥10 events each; non-artifact events only; **NaN for SMA-dead cohort** | +0.1409 | deepening crank dips; univariate 0.739; selected 20/34 folds |

### 1.3 Crank-event catalog (frozen segmentation — the SM vertical's special asset)

- **Segmentation:** consecutive rows with SMA=1 grouped; adjacent groups merged if gap ≤ 10 s (gap-aware). Pilot yield: **20,471 events** (vs 20,729 gap-naive).
- **Per-event fields:** t0, `dur_s`, `dip_depth` (V drop during crank), `baseline_vsi` (pre-crank), `rpm_max_15s`, success = `rpm_max_15s ≥ 550` within 15 s, retry linkage (retries within 120 s), `artifact` flag (`dur_s > 60 s`; 13 events, max 145 s — kept in catalog, excluded from stats).
- **Known artifact (resolved):** KT's "+48 % longer cranks in failed trucks" collapsed to +3.0 % under gap-aware segmentation — 5 s sampling quantizes ~93 % of events to a 5.0 s floor. Duration-based features are treated as quantized and low-information at this cadence.
- **SMA-dead cohort:** SMA observed-rows ≤ 1 % of history → all crank features NaN (never zero-filled; fold-internal median imputation). Pilot: 7/34 trucks (VIN8/9_F + VIN10/11/12/13/20_NF) showing 10× spurious event rates — a telematics config artifact. **Expect ~15–20 % of the 500-truck fleet SMA-dead** until the config is fixed (contract ask D4/D8).

### 1.4 Alert stack (four channels + triage + windows)

| Channel | Rule (frozen) | Pilot evidence | Ship status |
|---|---|---|---|
| **H2 dwell pager** (primary) | ≥ 3 consecutive weekly scoring cuts in RED (recalibrated p ≥ 0.55); weekly causal recompute; single Platt sigmoid from k=0 reused across cuts | recall 10/14, NF ever-fire 5/20, **0.190 episodes/truck-yr** (accept-bar exact), median lead **116 d** | SHIPPED |
| Persistence flag | trailing-4-wk mean of weekly `vsi_drive_std`/expanding-mean above training-fold NF p90 envelope in ≥ 4 of last 12 scored weeks | recall 13/14 but ALL 20/20 NF enter fire state at least once (31.4 % of weeks) | condition flag ONLY — never first-crossing alert |
| **A2 battery-cascade** | rest-VSI step ≤ −0.5 V (SNR ≥ 2) AND drive-VSI step ≥ +0.3 V (SNR ≥ 2) within ±8 wks AND dip widening > +1 V (last 60 d vs earlier, ≥10 events each) — all three causal | 4/5 battery-archetype caught, **0/20 NF**, median lead 66.5 d; battery *replacements* provably don't fire | SHIPPED → routes BATTERY-FIRST |
| A1 crank-burst | daily (failed cranks + retries-within-120 s), 7-d rolling sum S7 > own-first-half mean + 3 SD (floor S7 ≥ 3) for ≥ 2 consecutive days; 2nd half of history only; SMA-dead excluded | 4/12 applicable F fire; NF 1.52 ep/truck-yr — too noisy standalone | tier-gated corroborator only (rescued GREEN-tier VIN1_F) |
| **T1 triage** | BATTERY_FIRST if (≥1/12 wks good-voltage hard starts AND A2 fired) OR rest-floor sag confirmed; STARTER arm requires `lowv_crank_share` with `baseline_vsi < 26.0 V`; else INSUFFICIENT | 9/11 scored failures converge with archetypes; battery 5/5; **0 false attributions on 20 NF**; starter arm never fires (fleet median lowv_crank_share 0.4953 — 26 V sits above real pre-crank baselines under load) | SHIPPED as rule set; 26 V re-estimation is a pre-registered V3.2 lead |
| **A5 graded-RUL windows** | lookup: GREEN → no near-term action; persistence∧RED → inspect in **126–284 d** (median 206); A2-cascade → **28–91 d** battery-first; AMBER-only → no empirical window (0 failed trucks were AMBER-only) | empirical, honest | SHIPPED |
| A3 recall lever (parked) | H4 voting (≥2 of {tier≥AMBER, persistence-terminal, A1, A2}) with persistence as *currently-firing terminal episode* | recall 13/14 at NF 7/20 (0.430 ep/yr) — exceeds 0.19 budget; best candidate if DICV relaxes FP budget | documented option |

**Queue economics (frozen frame):** Youden-threshold policy P3 saves **43.3 %** vs run-to-failure (₹3,64,850 vs ₹6,44,000) at inspection ₹1,500 / breakdown ₹46,000 (R≈31), p_convert 0.70 — 13/14 recall, 5/20 NF flags, 18 inspections. This cost frame is re-fit at field prevalence in Phase 5.

### 1.5 Honest ledger — refuted / bounded claims the plan must not resurrect

- **`vsi_dominant_freq` is BANNED**: the FFT grid makes it 1/n_weeks for 17/34 VINs (observation-length leak); AUROC collapses 0.748 → 0.525 under a fixed 24-week window. Any spectral candidate must pass fixed-window controls.
- **Leak ceilings measured:** `n_weeks` alone scores 0.952, `t_start` 0.893 — pure observation-window leaks. The L40 fixed-window control + proxy-correlation gate (drop > 0.05 or |r| > 0.5 ⇒ REJECT) is mandatory for every candidate, forever.
- **GED is useless for SM:** ged3/ged2 features zero-variance — GED=2 is absent in the failed SM fleet (`ged3_rate_delta90`: p=1.0, AUROC 0.500). The ALT emergency channel has **no SM analogue** on current signals.
- **19 candidates failed across V2/V2.1/V3/V3.1** (V2: 2 HOLD; V2.1: 3 REJECT; V3: 7 REJECT; V3.1: 7 REJECT — complete list in §6.3) and a 12-feature pool probe scored 0.875 (−0.057) — pool bloat actively hurts at n=34.
- **GBM 0.8429 < 0.9321** at n=34 (screen-grade probe) — model class was not the binding constraint at pilot n.
- **NaT asymmetry:** all 20 NF VINs (0 failed) carried NaT timestamps (up to 689,773 rows in VIN18_NF); root-fixed by dropping NaT before sort. Evidence the two cohorts came from different export pipelines — a leakage trap the 500-vehicle contract must close (D5).
- **Silent-gap VINs (5/14 failed):** telemetry stops 32–142 d before JCOPENDATE (VIN1 72, VIN4 97, VIN5 32, VIN8 37, VIN9 142). Features describe the pre-silence state; lead-time claims are stated against last-data, windows against JCOPENDATE.
- **Heartbeat hypothesis REFUTED** (V3.1): rest-heartbeat coverage is a firmware family trait, not a precursor.

---

## 2. Scope, Planning Assumptions, Data Contract

### 2.1 Fleet & cohort assumptions

| Parameter | Value | Status |
|---|---|---|
| Vehicles (SM vertical) | ~500 (≈250 failed + ≈250 healthy curated retrospective cohort) | **Assumption A1** (DICV brief 2026-06-24) |
| Failure events | ~250–500 (1–2 per failed truck; starter replacements can recur) | Assumption A2 |
| Signals | Same 6: CSP, RPM, ANR, GED, VSI, SMA + VIN/timestamp (+SALEDATE/JCOPENDATE/Failure_type on failed) | Confirmed by user 2026-07-02 |
| Cadence | ~5 s burst + ~900 s heartbeat bimodal (pilot pattern) | Assumption A3 |
| Delivery | Daily CSV batch → Azure Blob (TruckConnect) | Per Azure plan v2 |
| History | ≥ 18 months retrospective per truck | Assumption A4 |
| Platform / FX | Azure Central India; ₹94/USD | Locked |

**Prevalence warning:** curated 50/50 ≠ field (~1–5 %/yr). All PPV/alert volumes reported at field prevalence scenarios {2 %, 5 %, 10 %}/yr; FA budget ≤ 2 alerts/100 trucks/month; H2's 0.19 ep/truck-yr NF budget is the channel-level bar.

### 2.2 Signal schema

Identical to the ALT plan §2.2 (same 6 sensors, same sentinels/ranges, same cohort file-shape split: 11-column failed / 8-column healthy, differing column order, name-based reads mandatory). SM-specific notes:

- `Failure_type` literal is `"Starter Motor"` (with space).
- SMA is the SM vertical's key event signal — its per-VIN observability (SMA-dead detection) is a first-class DQ output, not a footnote.
- GED is retained in the lake (contract uniformity) but carries no SM model value (§1.5).

### 2.3 Data-contract asks to DICV (shared asks D1–D8 as in ALT plan §2.3, plus SM-specific)

| # | Ask | Why (SM-specific) | Fallback |
|---|---|---|---|
| D1–D8 | identical to ALT plan (SALEDATE for all; job-card codes + part confirmation; ODO/IGN; firmware config per VIN; **single export pipeline**; stable VINs; cadence policy) | NaT asymmetry and SMA-dead cohorts were both SM discoveries | as in ALT plan |
| **D9** | **Fix SMA transmission config** on affected trucks (pilot: 7/34 dead) | 20 % of fleet blind on crank features; crank features are half the champion's physics | SMA-dead roster + NaN/impute protocol (frozen behavior) |
| **D10** | **Job-card distinction: starter replaced vs battery replaced vs terminal/cable repair** | competing-risks labels (battery-cascade vs starter-internal); T1 validation; pilot could only infer archetypes from signals | T1 rule-based attribution remains inference-only |
| **D11** | **Crank-burst sampling: VSI at 50–100 Hz during SMA=1 ±10 s (trigger-based) + RPM at 1 Hz** (per instrumentation proposal 2026-06-12) | the ONLY path past the 5 s syndrome-collapse physics (§0); a 1–3 s crank currently yields 0–1 VSI samples | plan works without; early-detection ceiling stays |

---

## 3. Volume Math & Sizing

Measured pilot (SM): 107,176,069 raw rows (30.93 M failed + 76.25 M healthy) / 34 trucks; 7,164 MB CSV → 956 MB parquet (**10.20:1 failed, 6.40:1 healthy**); ≈ 66.8 bytes/row CSV; row density ≈ **3.5–5 k rows/truck/day** (bimodal cadence).

| Quantity | Basis | 500-truck SM projection |
|---|---|---|
| Rows/day | 500 × 4.5 k | **~2.25 M/day** |
| Rows/year | ×365 | **~0.8 B/yr** |
| Upper bound (24 h continuous 5 s) | 500 × 17,280 | 8.6 M/day — 3.8× headroom |
| Raw CSV/yr | 66.8 B/row | **~55 GB/yr** (upper ~210 GB/yr) |
| Parquet (zstd)/yr | ~8–12:1 | **~5–7 GB/yr** |
| Retrospective backfill | 500 × ~600 d | ~1.35 B rows ≈ 90 GB CSV ≈ **~9–13 GB parquet** |
| Crank-event catalog | pilot 20,471 events/34 trucks/~20 mo → ~0.9 ev/truck/day | **~450 events/day; ~160 k/yr** (tiny table) |
| Weekly cache | 500 VINs × ~90 weeks × ~60 stats | < 50 MB |

**Sizing verdict:** single-node Polars, same as ALT (ADR-2). The crank catalog and weekly cache are small enough to iterate on a laptop; the only heavy job is the one-time backfill (~1–2 h streaming).

---

## 4. High-Level Design (HLD)

The platform is **shared with the ALT vertical** (one lakehouse account, one job framework, one registry, one monitoring stack — built once in ALT plan Phases P0–P1 or here if SM leads). This section records the SM-specific deltas plus the full ADR set for standalone readability.

### 4.1 Architecture Decision Records

| ADR | Decision | Alternatives | Rationale |
|---|---|---|---|
| ADR-1 | **Daily data pipeline, WEEKLY model scoring, daily event detectors** | daily scoring | The champion is defined on masked *weeks* (active_days ≥ 2); weekly scoring is the validated cadence (H2 = 3 consecutive weekly cuts). A1/A2 are event/step detectors that benefit from daily refresh. Scoring daily would create 7× threshold-crossing noise without new information at week-scale physics. |
| ADR-2 | **Single-node Polars, no Spark** | Databricks/Spark; DuckDB | 0.8 B rows/yr, ~6 GB parquet/yr; pilot processed 107 M rows on a workstation. Escape hatch ≥10 k vehicles. |
| ADR-3 | **Champion–challenger; modal-4 Ridge stays champion until beaten under gates** | greenfield | 4 iterations of audited honesty are the asset; GBM must *prove* the crossover at n≈250 events. |
| ADR-4 | **Grouped stratified 10×5 CV + temporal holdout + prequential replay** replaces 34-fold nested LOVO; **nested in-fold screening/selection retained** | LOVO at 500; single split | Keeps the exact leakage discipline (screen→select→threshold→calibrate all in-fold) at tractable compute. |
| ADR-5 | **Parquet lakehouse bronze/silver/gold, zstd** | CSV; Delta | measured 6.4–10.2:1; append-only batches need no ACID; manifest covers idempotency. |
| ADR-6 | **Crank-event catalog as a first-class gold table** (event grain) alongside weekly cache | recompute per feature run | events are expensive to segment (gap-aware, retry linkage) and reused by 4 consumers (features, A1, A2, T1); build once, append daily. |
| ADR-7 | MLflow registry + frozen-spec JSONs (pilot `V1_1_SM_model_spec.json` pattern) as the deployment contract | git tags only | auditability; DICV-facing model cards. |
| ADR-8 | Anomaly & RUL ship as **budgeted advisory channels**; T1 triage stays **rule-based and explainable** until a learned attributor beats it under gates | learned end-to-end | workshop trust; pilot's zero-false-attribution record is the bar. |

### 4.2 System diagram

```
 TruckConnect ──daily CSV──▶ ADLS Gen2 landing/ ──▶ bronze (parquet, zstd) ──▶ silver (R1–R16 clean)
                                                                                   │
                                     ┌─────────────────────────────────────────────┤
                                     ▼                                             ▼
                        gold/weekly_cache (VIN×ISO-week,            gold/crank_catalog (event grain,
                        masked-week stats: vsi_drive_std,           gap-aware SMA segmentation, dips,
                        p05/p95, vsi_rest_p05, active_days…)        retries, success, artifacts)
                                     │                                             │
                                     ├──────────────┬──────────────────────────────┤
                                     ▼              ▼                              ▼
                          05_features (L40      06_score_champion            daily: A1 crank-burst,
                          modal-4 + candidates,  (weekly cut: Ridge →        A2 cascade steps,
                          SMA-dead NaN rules)    Platt → tiers → H2 dwell)   T1 triage refresh
                                     │              │                              │
                                     └──────────────┴──────────►──────────────────┘
                                                    ▼
                                   08_alerts_publish (dedupe, debounce, A5 windows)
                                                    ▼
                        Postgres serving store ──▶ TruckConnect API + webhooks + Power BI
                        MLflow/Azure ML registry ◀── label-triggered retrain (Spot A10, scale-to-0)
                        monitors: PSI / calibration / alert SPC / DQ / R16 asymmetry
```

### 4.3 Component inventory, environments, security

Identical to ALT plan §4.3–4.4 (shared subscription): ADLS Gen2, Container Apps Jobs / Azure ML pipelines on D16ds_v5/D8ds_v5, Spot `Standard_NV36ads_A10_v5` for retrains (min 0/max 2, 300 s idle scale-down), Key Vault + managed identities, Postgres flexible server, Power BI, Log Analytics. Marginal SM cost on the shared platform ≲ ₹10 k/mo at 500 trucks; training bundle ~$77/mo shared envelope.

---

## 5. Low-Level Design — Data Engineering

### 5.1 Landing & lakehouse layout

Same medallion structure as ALT plan §5.1 with `abfss://dicv-sm@…/…/starter_motor/…`; silver partitioned by `vin`/`month`; two extra gold tables:

```
gold/starter_motor/weekly_cache/vin=VIN0001_SM/            # one row per (VIN, ISO week)
gold/starter_motor/crank_catalog/vin=VIN0001_SM/           # one row per crank event
gold/starter_motor/features/snapshot_week=YYYY-Www/        # scoring matrix (weekly cuts)
```

### 5.2 CSV → Parquet conversion spec

Identical converter to ALT plan §5.2 (name-based reads, `schema_overrides`, ISO8601→timestamp[us] tz-naive IST policy, zstd-3, ~1 M-row row groups, sorted (VIN, timestamp), statistics on, bronze by ingest_date). SM acceptance additions:

- Parity check must run **after NaT handling is decided**: bronze preserves NaT rows verbatim (bronze = as-delivered); silver drops them (R3). Row-count parity is asserted landing↔bronze; the bronze→silver NaT drop is counted, not silent.
- Ratio gate ≥ 8:1 on failed-cohort files (measured 10.2:1), ≥ 6:1 on healthy (measured 6.4:1 — more entropy from longer spans).

### 5.3 Cleaning & conformance suite (silver) — rules R1–R16

R1–R15 identical to ALT plan §5.3 (schema gate; tz policy; **NaT drop with per-VIN counters — an SM-born rule**; sort+dedupe keep-first; VSI ×0.2 contract; sentinel masks; range validation; all-null-row masks; cadence classifier 5 s/900 s/gap; firmware-family tag; silent-gap detector; GED-coverage tag [kept for uniformity]; plausibility screens; cohort-asymmetry sentinel). SM adds:

| Rule | Name | Exact behavior | Pilot evidence |
|---|---|---|---|
| **R16** | **SMA observability classifier** | per VIN over trailing 90 d and full history: `sma_obs_share = rows with SMA non-null / rows`; `sma_dead` if ≤ 1 % (frozen definition); membership drives crank-feature NaN rules and A1/A2 exclusion; roster published weekly; transitions (config fixed → alive) logged as feature-regime changes | 7/34 pilot trucks; 10× spurious event rates when dead |

**Leakage doctrine:** as in ALT plan — any cohort-correlated plumbing difference (R15/R16 outputs differing failed-vs-healthy beyond chance) is treated as a leak and escalated before modeling. The SM pilot supplied the program's two canonical examples (NaT asymmetry; SMA-dead clustering).

### 5.4 DQ gates & monitors

As ALT plan §5.4 (pandera-polars schemas; hard gates: schema mismatch, >5 % unparseable timestamps, row parity, duplicate hash; soft gates → quarantine) plus SM-specific weekly outputs: SMA-dead roster + deltas; crank-catalog sanity (events/day per truck vs own baseline — a 10× jump flags config change, the pilot signature); silent-gap watchlist (trucks approaching the 14-d no-data flag).

### 5.5 Label pipeline & curation

As ALT plan §5.5 (JCOPENDATE = failure date; gap table; censoring/spell table with usage axes; label ledger versioned) with SM-specific handling:

1. **Silent-gap labels:** for the ~35 % of pilot failed trucks whose telemetry stopped 32–142 d pre-failure — lead-time metrics computed to **last-data date**, maintenance windows to **JCOPENDATE**, both reported. New-fleet silent-gap rate is a Phase-2 KPI (if it stays ~35 %, escalate to DICV as a telematics reliability issue — it halves the value of any alert).
2. **Competing-risks coding (D10):** each failure event coded `cause ∈ {starter_internal, battery_cascade, terminal_cable, unknown}` from job-card codes; enables cause-specific hazards (Phase 8) and turns T1 from inference into supervised validation.
3. **Repeat events:** starter replacements recur; post-repair spells reset (new starter = new life), requiring part-replacement confirmation (D2/D10).

### 5.6 Weekly aggregation cache (gold) — LLD

One row per (VIN, ISO week), computed from silver burst-mode rows (dt-aware masks as ALT §5.6):

- Activity: `active_days` (days with ≥1 valid drive sample), `masked_week` flag = `active_days ≥ 2` (frozen), row counts, burst/heartbeat shares.
- Drive-state VSI (RPM ≥ 700 or CSP > 0): `vsi_drive_mean/std/p05/p95` → range = p95−p05.
- Rest-state VSI (engine-off RPM=0, excluding ±120 s around cranks): `vsi_rest_mean/p05/p50`, sample counts.
- Step detectors (causal, per week): rest-VSI step magnitude/SNR, drive-VSI step magnitude/SNR (A2 inputs; step = mean shift ≥ threshold with SNR ≥ 2 vs trailing baseline).
- Crank roll-ups from catalog: events, failed cranks, retries-within-120 s, `dip_depth` stats, `baseline_vsi` stats, `hard_start_goodv` count (failed cranks at baseline ≥ 27 V), `lowv_crank_share` (<26 V), success rate.
- Usage: active_hours (Σdt RPM>0, dt clipped ≤ 900 s), est_km (ΣCSP·dt), starts/active-day.
- L40 indexing: per-VIN masked-week sequence number so any feature can address "last 40 masked weeks" without recomputation.

### 5.7 Crank-event catalog builder (gold) — LLD

Daily incremental job over new silver rows per VIN (needs ±10 s context → reads previous day's tail):

1. Mask to SMA-alive VINs (R16); extract SMA=1 runs; merge runs with inter-gap ≤ 10 s.
2. Per event: `t0, t1, dur_s (quantized, 5 s floor for ~93 %), n_rows, baseline_vsi` (median VSI in [t0−60 s, t0−5 s], engine-off preferred), `dip_min_vsi`, `dip_depth = baseline − min`, `rpm_max_15s`, `success = rpm_max_15s ≥ 550`, retry chain id (events within 120 s), `artifact = dur_s > 60`.
3. Append to catalog partition; recompute daily A1 counters (S7 rolling sum) and A2 dip-widening inputs.
4. **Reproduction gate:** on pilot data, catalog must yield exactly 20,471 events with matching per-event fields.

### 5.8 Feature store

As ALT plan §5.7: snapshot per weekly cut; point-in-time correct (features at cut W use masked weeks ≤ W only); modal-4 + candidate columns + DQ covariates (`sma_dead`, firmware family, silent-gap flag, active-week count *as diagnostics only* — never as features, per leak ban); registry module with formula strings is the single source of truth.

---

## 6. Low-Level Design — Feature Engineering

### 6.1 Frozen modal-4 — ported verbatim (§1.2 formulas)

Reproduction gate (Phase 4): pilot feature values to ≤1e-9; nested 0.9321 / non-nested 0.9357 reproduced exactly (the V3/V3.1 E0 gate harness is reused as-is).

### 6.2 Leak-guard protocol (hardened, SM-calibrated)

- Mandatory for every candidate: **L40 fixed-window control** (AUROC drop > 0.05 ⇒ REJECT) + proxy-correlation gate (|Spearman| > 0.5 vs `n_weeks`/`t_start`/span ⇒ REJECT). Measured leak ceilings to beat honestly: n_weeks 0.952, t_start 0.893.
- **Spectral features banned** unless computed on fixed-length windows with explicit frequency-grid audits (the `vsi_dominant_freq = 1/n_weeks` lesson).
- Battery-step re-baselining (§1.2 F2) retained; step events logged as covariates.
- Negative controls: permuted labels; exporter-fingerprint model (NaT/сolumn-order/SMA-dead as only inputs) must score ≈0.5 — if it doesn't, the *data contract* failed, not the model.
- BH-FDR across each phase's candidate battery (V3.1 pattern); pre-registration of hypotheses before touching outcome data.

### 6.3 Graduation re-tests & new candidates (Phase 6 backlog, pre-registered)

All 24 pilot rejections were power-limited at n=34 unless physics-refuted. Priority order:

| Candidate | Pilot stats | Why re-test at n=500 |
|---|---|---|
| `monsoon_start_share` | raw MW p=0.0219, AUROC 0.7357; FDR-killed | top pre-registered lead; seasonality × moisture on cranking |
| `hard_start_goodv_rate` (LEVEL form) | p=0.0239, AUROC 0.6875 | distinct from the rejected Δ90 form; direct hard-start physics |
| T1 starter-arm threshold re-fit | 26.0 V never fires (fleet median lowv_crank_share 0.4953) | re-estimate cut from 250-truck baseline_vsi distribution; percentile-based, not absolute volts |
| `dip_resid_trend_12w` | E1 p=0.0679, AUROC 0.6786; E2 −0.0179 | only candidate with a real univariate pulse in V3.1 |
| `cold_dip_delta90`, `rpm_rise_lag_delta90` | HOLD (redundant r=0.92 with dip_depth at n=34) | redundancy may break at n=500 with more duty-cycle diversity |
| `intercrank_cv_delta90`, `z_cold_dip_delta90`, `anr_pos_mean_delta90` | REJECT (Δ 0 to −0.043) | cheap to re-screen in the battery |
| V3 interaction/usage set (7: dose_dip_x_starts, weakbat_cold_load, reg_instab_x_usage, sag_under_load, cold_start_fraction_delta90, night_start_fraction_delta90, + dose_dip_x_intensity) | all REJECT p≥0.16 | interactions are exactly what GBMs find with n; screen via model-based importance rather than univariate MW |
| Fleet-relative features | impossible at n=34 | weekly percentile of dip_depth / vsi_drive_std vs healthy cohort of same usage band & firmware family |
| Cause-specific features (with D10 labels) | archetype inference only in pilot | battery-cascade detector features vs starter-internal features trained separately |
| ~~`ged*` family~~ | zero-variance in failed SM fleet | do NOT re-test unless GED coverage materially changes (documented exception) |
| ~~duration-based crank features~~ | 5 s quantization floor | only after D11 high-rate sampling lands |

Selection at scale: keep the nested in-fold screen (MW p<0.10, AUROC ≥ 0.60, |ρ|<0.85 dedup, stability), raise pool cap 10 → 25, exhaustive k search extended 3..8, GBM-importance screen added as a parallel track (§7.3). "Fewer features better" is expected to relax at n=500 — the harness decides, not the prior.

---

## 7. Modeling Program

### 7.1 Validation harness at n=500

Identical framework to ALT plan §7.1 (grouped stratified 10-fold × 5 repeats; strata = label × cause-code × firmware family × SMA-liveness; rolling-origin temporal backtests; locked 3-month prospective holdout; prequential weekly-rewind replay k=0..26 producing the AUROC(k) horizon curve — pilot metric; bootstrap CIs; DeLong + paired-fold Wilcoxon referees; prevalence-corrected reporting at {2,5,10} %/yr; FA budget ≤2/100 trucks/mo) with SM specifics:

- **Weekly cuts are the scoring unit** (t_end − 7k days), matching the frozen H2/persistence machinery.
- **Nested selection retained inside outer folds** (screen→subset-search→threshold→Platt per fold) — this is the pilot's honesty engine and is kept verbatim, just inside 10 grouped folds instead of 34 LOVO folds.
- Metrics contract adds: episode-level channel metrics (recall, NF episodes/truck-yr, median lead) for H2/A1/A2 — directly comparable to the pilot table in §1.4; per-cause recall (battery-cascade vs starter-internal) once D10 lands.

### 7.2 Champion port (Phase 4)

Modal-4 Ridge(α=1.0) + per-fold Platt, retrained on 500 under §7.1. Expected AUROC band 0.85–0.93 (regression to the mean from 0.9321 is expected and stated up front). Tier boundaries (RED ≥ 0.55 on recalibrated probability) re-derived from OOF; H2 dwell (3 weeks) re-tuned on the Pareto frontier at the 0.19 ep/truck-yr budget.

### 7.3 Classification challengers (Phase 6)

Same battery and rationale as ALT plan §7.3 — elastic-net logistic; **LightGBM as primary challenger** (shallow: num_leaves ≤ 15, depth 3–4, min_child_samples ≥ 25, native-NaN handling is a natural fit for SMA-dead crank features; monotone constraints where physics is signed: dip_depth↑risk, rest_vsi_p05↓risk); XGBoost cross-check; RF baseline; TabPFN v2 cheap swing; calibrated soft-vote/stacking ensemble; **isotonic calibration replacing Platt when n supports it** (validate CITL/slope per fold; pilot Platt numbers are the floor: Brier 0.124, slope 0.86). No SMOTE (cohort balanced; deployment prevalence handled by prior-shift logit correction + budgets). SM-specific challenger: **two-stage architecture** — stage 1 cause-agnostic risk (champion successor), stage 2 cause attribution (learned T1 successor: multinomial on {battery_cascade, starter_internal, other} using D10 labels; must beat rule-T1's 9/11 with 0 false attributions to ship).

### 7.4 Anomaly-detection program (Phase 7) — re-opened with a budget

Same stance and kill criteria as ALT plan §7.4 (watchlist channel, ≤0.2 ep/truck-yr, shadow-only, PARK sanctioned). SM-tailored methods:

| Method | Design | SM rationale |
|---|---|---|
| **Fleet-relative crank residuals** (primary) | expected dip_depth surface = f(baseline_vsi, ANR band, temp-season, firmware) from ~250 NF trucks; per-truck weekly residual; robust EWMA z > 3 sustained ≥ 3 weeks | operationalizes dip physics with a real reference; interpretable ("dips 1.2 V deeper than fleet-expected") |
| Rest-floor drift monitor | EWMA/CUSUM on `vsi_rest_p05` per truck (battery-health proxy) | formalizes A2's rest-arm as a continuous monitor |
| IsolationForest | weekly feature vectors, per-firmware-family, contamination='auto' | multivariate catch-all |
| Matrix Profile (STUMPY) | weekly `vsi_drive_std` and dip series discords (window 8–12 wks) | regime breaks the deltas smooth over |
| Event-sequence outliers | retry-chain length distribution per truck vs fleet | crank retry storms (A1 generalization) |

### 7.5 RUL / forecasting program (Phase 8) — windows + competing risks

Gate zero (program rule, from ALT's V10.6.2 lesson): beat the fleet-clock/window dummy on grouped OOF (Wilcoxon p<0.05) or ship the empirical windows. The SM pilot never even attempted per-truck point RUL (A5 lookup windows were the honest deliverable); the 500-vehicle program upgrades A5 → survival machinery:

| Model | Config | SM rationale | Output |
|---|---|---|---|
| **A5 v2 empirical windows** (baseline, ships day 1) | Kaplan–Meier strata by (channel-state, cause-code, usage band): survival from state-entry (e.g., first persistent-RED week) to failure | direct generalization of A5's `persistence∧RED → 126–284 d`; pilot's 4-row lookup becomes stratified KM curves with real CIs | P10–P50–P90 window per state, 3 axes (days / est-km / engine-h) |
| **Discrete-time hazard** (primary challenger) | weekly person-period GBM/logistic: P(fail in wk t | features_t, age, usage); ~250 events × ~80 wks ≈ 2 M rows | weekly panel is native; time-varying covariates (dip trends) natural | per-truck hazard → calibrated window |
| **Cause-specific hazards / Fine-Gray** | separate hazards for battery-cascade vs starter-internal (D10 labels) | the two causes have different signatures (A2 66-d lead vs H2 116-d) and different actions (battery-first vs starter queue) — one blended window under-serves both | cause-conditional windows + recommended action |
| Cox PH / RSF / Weibull AFT | as ALT plan §7.5 | interpretability / nonlinearity / parametric cross-checks | C-index referees |
| Quantile GBM | LightGBM quantile α∈{0.1,0.5,0.9} on spell TTF | cheap window-width baseline | P10/P90 direct |

Evaluation: C-index ≥ 0.65 to bother; **interval coverage 80±10 %** on OOF; beat-the-dummy referee; usefulness metric = fraction of failures with P10 ≥ 30 d notice. Left-truncation per D1; recurrent spells with post-repair reset; silent-gap trucks evaluated to last-data AND JCOPENDATE (both reported).

### 7.6 Deep / TS-FM challengers (Phase 9 — gated)

Identical gating to ALT plan §7.6 (clutch-first FM pilot must clear its kill criteria; SM enters only after classical plateau + ≥200 events with dense pre-failure coverage). SM-specific input design: weekly multichannel sequences (drive-VSI stats, rest-floor, dip stats, retry counts) — NOT raw 5 s rows; **crank-resolved deep models (1D-CNN on 100 Hz crank waveforms) become the flagship candidate IF AND ONLY IF D11 instrumentation lands** — that is where deep learning has a real physics edge over aggregates, and it is contingent on new data, not more trucks.

### 7.7 Promotion gates

Identical to ALT plan §7.7 (G1–G8: ΔAUROC ≥ +0.02 with DeLong p<0.05; Wilcoxon across folds; calibration slope [0.5,2.0]/CITL ±0.1/Brier ≤ champion; lead-time-at-precision non-inferior; alert budget; negative controls; temporal-holdout agreement; card+spec+reproduction committed) plus channel-level gate: **any change to H2/A2 must hold NF episodes/truck-yr ≤ 0.19 at recall ≥ 10/14-equivalent** (scaled: ≥ 71 % of failures with ≥ 90-d median lead) on the replay harness.

---

## 8. Alerting & Decision Layer (port + re-cost)

### 8.1 Channels at 500 vehicles

| Channel | Port | Changes at scale |
|---|---|---|
| **H2 dwell pager** | ≥3 consecutive weekly RED cuts | threshold + dwell re-derived on OOF Pareto frontier at the frozen 0.19 ep/truck-yr budget; expected fleet volume at 500 trucks: ≤ 95 NF episodes/yr worst-case budget → in practice target ≤ 8/mo fleet-wide, confirmed against workshop capacity |
| **A2 battery-cascade** | triple step detector | step thresholds (−0.5 V rest / +0.3 V drive / +1 V dip) re-validated on 250-NF distributions to hold ~0-FP posture; routes BATTERY-FIRST with A5-v2 28–91 d window successor |
| A1 crank-burst | tier-gated corroborator | stays gated (1.52 ep/yr standalone is unshippable); revisit inside A3-style voting only if DICV relaxes budget |
| Persistence flag | condition context on truck page | never a first-crossing alert (pilot: 20/20 NF eventually fire) |
| **T1 triage** | rule set + 26 V re-fit (§6.3) | attribution shown with every AMBER+ alert; learned attributor (§7.3) must beat it to replace it |
| A5 → windows | §7.5 outputs, tier-gated | GREEN trucks: stratum window only |
| A3 voting recall lever | parked option | offered to DICV as an explicit FP-budget knob (recall 13/14 at 0.43 ep/yr) |

### 8.2 Alert economics

Re-fit the frozen frame (inspection ₹1,500, breakdown ₹46,000, R≈31, p_convert 0.70) at field prevalence with DICV-confirmed SM costs; publish the cost-vs-threshold curve and both operating points (Youden, cost-optimal). The pilot's 43.3 % saving claim is **re-derived, not reused** — at 2–5 %/yr field prevalence the absolute ₹ numbers change even if the policy shape holds. Alert-volume forecast published per channel per month; hysteresis: tier downgrades require 3 clean weekly cuts.

### 8.3 Alert plumbing

As ALT plan §8.3: dedupe (VIN, channel, week); evidence-stack per-VIN graph attached to AMBER+ alerts (V1.1 SM 6-panel design is the artifact contract); alert replay tooling from pinned artifacts; every alert logs model version + feature snapshot + label-ledger version.

---

## 9. Deployment LLD (Azure jobs & TruckConnect)

### 9.1 Job DAG

```
DAILY (00:30–04:00 IST): ingest_validate → clean_conform (R1–R16) → weekly_cache upsert
                         → crank_catalog append → A1/A2 detector refresh → DQ monitors
WEEKLY (Mon 04:00 IST, after ISO week closes):
                         feature_snapshot (weekly cut) → score_champion (Ridge→Platt→tiers)
                         → H2 dwell evaluation → T1 triage refresh → A5 windows
                         → alerts_publish (dedupe/debounce) → TruckConnect API + webhooks
                         → weekly fleet report + evidence-stack graphs (AMBER+)
MONTHLY:                 PSI drift report, calibration tracking, alert SPC review, R15/R16 asymmetry report
ON LABEL ARRIVAL:        label ledger update → retrain-trigger counter
```

Runtime: daily chain minutes; weekly scoring < 15 min at 500 trucks on D8ds_v5.

### 9.2 Serving contract to TruckConnect

`GET /v1/sm/vehicles/{vin}/risk` → {score, tier, tier_since_weeks, h2_state{consecutive_red_weeks}, channels{a2_fired, a1_corroboration, persistence_state}, triage{attribution, confidence}, window{p10,p50,p90,axis,cause}, sma_dead, model_version, cut_week}. Webhooks: H2 fire, A2 fire, tier upgrade. Signed licensed container; tenancy per commercial Q&A Q17.

### 9.3 Retraining loop

As ALT plan §9.3: **label-triggered** (≥10 new confirmed SM failure labels OR quarterly, whichever first); feature pull < 1 GB → Spot A10 (classical retrains actually CPU-fine; GPU reserved for Phase-9) → §7.7 + channel gates vs live champion → promote/keep → scale-to-zero. ~$2–3/cycle; ~₹450–1,300/yr classical.

---

## 10. MLOps

Identical framework to ALT plan §10 (MLflow registry + frozen-spec JSON contract — the SM pilot's `V1_1_SM_model_spec.json` is the template the program standardized on; reproducibility pins = git commit × label ledger × lake manifest × seed; PSI/calibration/alert-SPC monitors with the same trigger levels; ≥4-week shadow for every change; alert replay; DICV model cards on the V1.1 SM card pattern — including its honest sections: winner-stability caveat, suppressor flag, SMA-dead protocol, silent-gap caveat; runbooks). SM-specific monitor additions: SMA-dead roster drift (config fixes change feature regimes — a truck leaving the roster gets a 12-week feature burn-in before its crank features re-enter scoring); crank-catalog event-rate SPC per truck (10× jump = config artifact, pilot signature).

---

## 11. Instrumentation Workstream (the only path past the 5-second ceiling)

From the DICV instrumentation proposal (2026-06-12) and V3.1 physics findings, priority-ordered:

| Priority | Ask | Today | What it unlocks |
|---|---|---|---|
| 1 | **VSI at 50–100 Hz during SMA=1 events ±10 s (trigger-based burst)** | 5 s sampling; 1–3 s cranks yield 0–1 samples; all starter-internal modes collapse to one late syndrome | crank waveform morphology: inrush depth, recovery slope, brush-wear signature vs solenoid chatter vs pinion engagement faults — separable failure modes and genuinely early detection; enables crank-resolved deep models (§7.6) |
| 2 | **RPM at 1 Hz continuous** | 5 s | crank success timing precision; rpm-rise lag becomes measurable (pilot candidate was quantization-limited) |
| 3 | **SMA config fix fleet-wide (D9)** | ~20 % SMA-dead | restores crank features for the blind cohort |
| 4 | Battery health signals (SoC/SoH or battery temp if BMS exposes them) | absent | separates battery-cascade cause cleanly; halves T1's inference burden |
| 5 | ODO + IGN (D3) | absent | exact km axes; true engine-off masks |

Plan impact: none of the Phase 1–8 commitments depend on these; Phase 9's flagship (crank-waveform CNN) is explicitly contingent on P1. Every DICV progress review restates this table — it is the difference between "better ranking" and "earlier detection."

---

## 12. Phase-Wise Execution Plan

Same phase skeleton as the ALT plan §12 (shared platform built once — if ALT leads, SM's P0–P1 shrink to configuration + SM-specific tables). Durations below are **standalone** (2 engineers); in the combined program SM runs offset +2 weeks behind ALT on shared phases.

### P0 — Setup & contracts (Week 1)
ALT-plan P0 plus: D9–D11 negotiations (SMA config, cause codes, crank-burst sampling); SM cost parameters confirmed (₹1,500/₹46,000 frame); workshop battery-first process agreed (A2 routes to battery inspection — needs a real workshop SOP, not just an API field).
**XG:** contracts dispositioned; SM repo scaffold (`SM_500/`) with pilot frozen-spec JSONs vendored.

### P1 — Lakehouse & converter (Weeks 2–3)
Shared converter + SM landing/bronze/silver; NaT counters wired; backfill runner.
**XG:** converter acceptance on delivered files (parity + ratio gates); NaT/asymmetry report on the 500-truck drop reviewed — **this is the moment R15 either passes or the program stops and renegotiates D5.**

### P2 — Labels & fleet registry (Weeks 3–4)
Job-card ingest with cause codes (D10); censoring/spell table; silent-gap KPI; SMA-dead roster v1; label ledger v1.
**XG:** every failed VIN has resolved failure date + cause (or `unknown`); silent-gap rate published; DICV service-data owner sign-off.

### P3 — Cleaning, weekly cache, crank catalog (Weeks 4–6)
R1–R16; weekly cache builder; crank-catalog builder (§5.7); dt-weighting decisions; **pilot-reproduction harness**: 34 pilot trucks through the scale pipeline.
**XG:** byte-exact reproduction — 20,471 crank events, modal-4 feature values ≤1e-9, weekly cache parity; DQ weekly report live.

### P4 — Champion port & validation harness (Weeks 6–8)
§7.1 harness (grouped CV with nested in-fold selection, temporal splits, prequential replay, negative controls incl. exporter-fingerprint); champion retrained; Platt→isotonic evaluation; thresholds re-derived; champion card v1.
**XG:** pilot nested 0.9321 reproduced exactly on pilot data; 500-cohort champion card with CIs; controls ≈0.5; prospective holdout hash-sealed.

### P5 — Alert channels & economics (Weeks 8–10)
H2 re-tune on Pareto frontier at 0.19 budget; A2 step-threshold re-validation on 250-NF; A1 gating; persistence context; T1 port + 26 V re-fit; A5-v2 KM windows; ₹ economics + volume forecast; evidence-stack generator ported.
**XG:** full-replay channel table (the §1.4 format) on retrospective data meets budgets; DICV sign-off on taxonomy, volumes, and the battery-first SOP.

### P6 — Challenger program (Weeks 10–13)
Graduation re-tests (§6.3, BH-FDR); classifier battery (§7.3); learned-T1 attributor vs rule-T1; ensemble; promotion under §7.7 + channel gates.
**XG:** challenger report (every candidate PROMOTE/REJECT with stats); shadow start for any promotion.

### P7 — Anomaly program (Weeks 12–14)
Crank-residual surface; rest-floor monitors; IForest/MatrixProfile battery; watchlist in shadow.
**XG:** verdict vs FP budget; SHIP-shadow / PARK per method.

### P8 — RUL & survival (Weeks 13–16)
A5-v2 stratified KM (ships regardless); discrete-time hazard + cause-specific hazards (D10) + Cox/RSF/AFT battery; coverage calibration; beat-the-dummy referee; window UX.
**XG:** RUL verdict — calibrated per-truck windows ship only if coverage 80±10 % AND beat dummy p<0.05; else A5-v2 ships alone (honest fallback).

### P9 — Deep/TS-FM (gated; earliest Weeks 17+)
Entry: clutch FM pilot verdict + classical plateau + event count. If D11 landed: crank-waveform CNN becomes the lead candidate with its own frozen kill criteria.
**XG:** beat-GBM verdict documented either way.

### P10 — Production deployment (Weeks 14–16)
DAG to prod (§9.1); TruckConnect API/webhooks/Power BI; monitors; shadow → soft-launch (DICV analysts) → launch.
**XG:** 2 clean soft-launch weeks (volumes in budget, zero hard-gate failures); prospective holdout unsealed, G7 satisfied; DICV sign-off.

### P11 — Operate & improve (Week 17+)
Label-triggered retrains; quarterly model-risk review; SMA-config remediation tracking; instrumentation onboarding (new bronze schema version; 12-week burn-in for re-alive trucks; crank-waveform pipeline when D11 lands).

---

## 13. Timeline, Staffing, Cost

```
Wk:        1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16 17+
P0 setup   ██
P1 lake       ████
P2 labels        ████
P3 caches           ██████
P4 champ                  ██████
P5 alerts                       ██████
P6 chall                              █████████
P7 anom                                     ██████
P8 RUL                                         █████████
P10 deploy                                        ████████
P9 deep(gated)                                             ██████…
P11 operate                                                ██████…
```

| Scenario | Duration to production | Effort |
|---|---|---|
| SM standalone, 2 engineers | **~16 weeks** | ~150 eng-days |
| SM standalone, 1 engineer | ~28–30 weeks | ~150 eng-days serialized |
| Combined program (shared platform, SM offset +2 wks behind ALT) | **~18–20 weeks for both verticals** | ~230 eng-days total |

Cost (₹94/USD): build compute ≤ ₹1.2 L; production marginal run-rate at 500 trucks ≲ ₹10 k/mo on the shared platform (the $300–560/mo envelope is the 10 k-vehicle, 3-vertical figure); classical retrains ~₹450–1,300/yr; Phase-9 tier if triggered ~₹1,700–3,800/yr. Consistent with the commercial Q&A price points (Clutch+Starter bundle ₹250/veh/yr; compute 3–7 % of price).

---

## 14. Risks & Mitigations (honest register)

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| S-1 | **5 s sampling ceiling**: early starter-internal detection stays physics-blocked regardless of n | Certain (until D11) | High (expectation mgmt) | instrumentation workstream §11 restated at every review; comms anchored to "ranking + windows + battery-cascade detection", never "predict every failure early" |
| S-2 | Curated 50/50 cohort ≠ field prevalence → optimistic PPV | Certain | High | prevalence-corrected reporting; budgets in ep/truck-yr; §7.1 |
| S-3 | Export-pipeline asymmetry recurs (NaT precedent was SM's) | Medium | High (silent leakage) | D5 contract; R15 sentinel; exporter-fingerprint negative control; P1 XG is a hard stop |
| S-4 | SMA-dead fraction stays ~20 % → crank features blind for 100 trucks | High | Medium | D9 config fix; NaN/impute protocol frozen; roster monitored; champion degrades gracefully (3 of 4 features are voltage-based) |
| S-5 | Silent-gap rate stays ~35 % of failures → alerts fire into telemetry darkness | Medium | Medium | silent-gap KPI to DICV as a telematics reliability issue; watchlist for trucks approaching gap flags; lead-times reported to last-data honestly |
| S-6 | Label noise: job cards lacking cause codes (D10 refused) | Medium | Medium | T1 stays rule-based inference; competing-risks module descoped to sensitivity analysis |
| S-7 | H2 budget breach at scale (0.19 ep/yr tuned on 33.7 NF truck-yrs) | Medium | Medium | re-derived on ~250 NF truck-yrs with CIs; shadow before exposure; A3 knob documented for DICV's explicit budget choice |
| S-8 | Anomaly program repeats the small-n FP history | Medium | Low (budgeted) | shadow-only; PARK sanctioned |
| S-9 | RUL windows fail coverage | Medium | Low (fallback ready) | A5-v2 ships regardless |
| S-10 | Threshold transfer from pilot (0.55 RED, 3-wk dwell, step magnitudes) | Certain (by design) | Low | all re-derived in P4/P5; pilot values are priors, never defaults |
| S-11 | Battery-first SOP not followed in workshops (p_convert < 0.70) | Medium | Medium | SOP agreed in P0; realized job-card outcomes feed quarterly economics re-fit |
| S-12 | Spot eviction / platform risks | Low | Trivial | checkpoint+retry; shared-platform runbooks |

---

## 15. Build Inventory — What We Are Going To Code

Every artifact below has an owner, a phase, and a Definition of Done (DoD = code + unit tests green + docstring with formula/contract + module-README entry + ⓖ golden-reproduction test against pilot artifacts where marked). Modules shared with the ALT vertical (ingest, converter, manifest, monitors, API skeleton, IaC, CI) are built **once** in the shared platform and listed here only where SM configures or extends them.

### 15.1 Repository layout (`SM_500/`)

```
SM_500/
  config/            champion.yaml (App. B), thresholds.yaml, schema_contracts/, cost_params.yaml
  src/
    ingest/          (shared platform) + sm_landing_config
    clean/           c01_conform(R1–R9)  c02_cadence_firmware(R10–R11)  c03_flags(R12–R15)
                     c16_sma_observability(R16)  c05_dq_ledger
    labels/          l01_jobcard_ingest(+cause codes D10)  l02_label_ledger  l03_spells
                     l04_label_qa  l05_silent_gap_kpi
    cache/           w01_weekly_cache  k01_crank_catalog ⓖ  k02_step_detectors  d02_usage_axes
    features/        f01_registry  f02_modal_four ⓖ  f03_candidates  f04_snapshot(weekly cuts)
                     f05_leak_gates(L40)  f06_battery_step_rebaseline ⓖ
    models/          m01_harness(+nested in-fold selection) ⓖ  m02_champion ⓖ  m03_challengers
                     m04_anomaly  m05_survival(+competing risks)  m06_negative_controls
                     m07_thresholds  m08_promotion  m09_attribution(T1-learned)
    alerts/          h01_h2_pager ⓖ  h02_a2_cascade ⓖ  h03_a1_burst ⓖ  h04_persistence ⓖ
                     h05_t1_triage ⓖ  h06_a5_windows ⓖ  h07_debounce_dedupe
                     h08_evidence_stack  h09_replay ⓖ  h10_economics ⓖ
    serve/           s01_weekly_score_job  s02_publish_api  s03_webhooks  s04_monitors
    ops/             o01_retrain_trigger  o02_registry_io  o03_report_weekly  o04_dq_report
                     o05_sma_roster_ops
  tests/             unit/ integration/ reproduction/ property/ perf/ fixtures/
  infra/             (shared) + sm pipeline yaml
  docs/              runbooks/ model_cards/ review_records/
```

### 15.2 Module inventory (module → purpose → key contents → phase)

**Data plane (SM-specific)**

| Module | Purpose | Key functions / contents | Phase |
|---|---|---|---|
| `c01–c05` | rules R1–R15 (shared implementations, SM config) | per-rule functions, counters, ledger reconciliation | P3 |
| `c16_sma_observability` | R16: `sma_obs_share`, `sma_dead` roster, transition log | `classify()`, `roster()`, burn-in state machine | P3 |
| `l01_jobcard_ingest` | job cards + **cause codes** {starter_internal, battery_cascade, terminal_cable, unknown} | code mapper, replacement-confirmation flag | P2 |
| `l05_silent_gap_kpi` | silent-gap rate KPI (pilot 5/14) + watchlist | gap detector against JCOPENDATE | P2 |
| `w01_weekly_cache` | §5.6 per-(VIN, ISO-week) aggregates, masked-week flag, L40 indexing | drive/rest VSI stats, crank roll-ups, usage | P3 |
| `k01_crank_catalog` ⓖ | §5.7 event segmentation (gap-aware ≤10 s merge, success ≥550 rpm/15 s, artifact >60 s, retry ≤120 s links) | `segment()`, `append_day()` with midnight-spanning handling | P3 |
| `k02_step_detectors` | causal rest/drive step detection (magnitude + SNR) | `detect_steps()` weekly | P3 |

**Feature & model plane**

| Module | Purpose | Key contents | Phase |
|---|---|---|---|
| `f02_modal_four` ⓖ | §1.2 features verbatim (ratio, rest-floor delta, Theil–Sen range trend, dip delta) | 4 functions, exact pilot semantics; SMA-dead → NaN | P3 |
| `f06_battery_step_rebaseline` ⓖ | step-aware baseline for `rest_vsi_p05_delta90` (step ≥ +0.5 V, SNR ≥ 2, ≥4 post-weeks) | reproduces pilot re-baselined VINs (VIN8_F + VIN3/5/12/17/18_NF) | P3 |
| `f05_leak_gates` | **L40 fixed-window control** + proxy-ρ gate + spectral-grid audit (the `vsi_dominant_freq` ban enforcement) | `l40_control()`, `proxy_gate()`, `assert_banned()` | P4 |
| `m01_harness` ⓖ | grouped 10×5 CV **with nested in-fold selection** (screen → subset search k=3..8 → inner-OOF Youden → per-fold Platt), temporal holdout, weekly prequential replay | the pilot's honesty engine, generalized | P4 |
| `m02_champion` ⓖ | modal-4 Ridge port + Platt (isotonic candidate) | spec JSON I/O (V1_1 pattern) | P4 |
| `m03_challengers` | EN / LightGBM(+monotone constraints) / XGB / RF / TabPFN / ensemble | common interface | P6 |
| `m09_attribution` | learned T1 successor: multinomial cause attributor | must beat rule-T1 (9/11, 0 false) to ship | P6 |
| `m05_survival` | A5-v2 KM strata + discrete-time hazard + **cause-specific hazards / Fine–Gray** + Cox/RSF/AFT + coverage metric | competing-risks referee | P8 |
| `m04/m06/m07/m08` | anomaly battery / negative controls (incl. exporter-fingerprint) / thresholds + prior shift / promotion gates | as ALT plan | P4–P7 |

**Alert & serving plane**

| Module | Purpose | Key contents | Phase |
|---|---|---|---|
| `h01_h2_pager` ⓖ | ≥3 consecutive weekly RED cuts (p ≥ 0.55 recal), episode semantics | Pareto re-tune tool at 0.19 ep/truck-yr budget | P5 |
| `h02_a2_cascade` ⓖ | triple detector (−0.5 V rest ∧ +0.3 V drive within ±8 wk ∧ dip widening > +1 V, ≥10 events) → BATTERY_FIRST routing | golden negative: battery replacement must NOT fire | P5 |
| `h03_a1_burst` ⓖ | S7 counter (mean+3 SD, floor 3, ≥2 d), tier-gated corroborator, SMA-dead excluded | second-half-of-history rule | P5 |
| `h04_persistence` ⓖ | NF-p90 envelope flag (≥4/12 weeks), terminal-episode state (A3 lesson) | condition-flag semantics only | P5 |
| `h05_t1_triage` ⓖ | rule attribution (battery arms + starter arm w/ re-fit 26 V→percentile cut) | INSUFFICIENT default; zero-false-attribution bar | P5 |
| `h06_a5_windows` ⓖ | state→window lookup, upgraded to stratified KM (§7.5) | tier-gated exposure | P5/P8 |
| `h10_economics` ⓖ | queue-policy cost engine (inspection ₹1,500 / breakdown ₹46,000 / p_convert 0.70) | reproduces pilot P3-policy 43.3 % saving; re-fits at field prevalence | P5 |
| `h07–h09`, `s01–s04`, `o01–o05` | dedupe/debounce, evidence-stack graphs, replay harness, weekly scoring DAG, API/webhooks, monitors, retrain trigger, SMA roster ops, reports | as ALT plan + SM cadences | P5–P11 |

**Estimated volume:** ~34 SM-specific source modules (plus shared platform), ~120 test files. Ports, not greenfield: `f02`, `f06`, `k01`, `h01–h06`, `h10` port pilot code (`V1_1_SM_features.py`, alert/heuristic evaluators, economics tables) with pilot artifacts as oracles.

---

## 16. Review Plan — What We Are Going To Review

### 16.1 Engineering reviews (every PR; second-engineer approval mandatory)

Same per-code-class blocking checklists as the ALT plan §16.1 (data plane: name-based reads, null propagation, counters, determinism, atomic writes; feature code: registry parity, walk-forward safety, NaN semantics, ban-list; model code: fold hygiene, seeds, pooled-OOF-only metrics; alert code: causality at cut, config-not-literals, replay determinism; serving/infra: least privilege, secrets, idempotent webhooks, rollback stated) **plus SM-specific blocking items**:

- Any code touching crank events must state its SMA-dead behavior explicitly (NaN vs excluded vs raise).
- Any weekly computation must state its masked-week rule (`active_days ≥ 2`) and L40 addressing.
- Any candidate feature PR must attach `f05_leak_gates` output (L40 control + proxy ρ) — no gate output, no review.
- Any threshold change to H2/A2 must attach the replay table (recall / NF ep-per-truck-yr / median lead) vs the frozen budgets.

### 16.2 Design & statistical review gates (records in `docs/review_records/`)

Same review board structure as ALT plan §16.2 (data-contract review; lakehouse review; label review board; **leakage review board**; harness review; calibration review; threshold & economics review with DICV; challenger verdict reviews; model-card review; security review; launch readiness review; quarterly model-risk review) with SM-specific gates added:

| Review | When | Reviewed artifact | Pass criteria |
|---|---|---|---|
| **Crank-catalog design review** | P3 | segmentation params vs frozen spec; golden 20,471 | byte-exact pilot reproduction; midnight/merge edge cases covered |
| **SMA-dead roster review** | P3, then monthly | R16 roster + transitions + 10× event-rate SPC | roster stable or explained; burn-in rules enforced |
| **Cause-code review (w/ DICV)** | P2 | D10 mapping table, unmapped-code rate | ≥80 % of failure events mapped to a cause, or competing-risks module descoped in writing |
| **Battery-first SOP review (w/ DICV workshop owner)** | P5 | A2→work-order routing, SOP document | drill completed (UAT-03); acknowledgment loop defined |
| **Channel budget review** | P5, per change | H2/A2/A1 replay tables | NF ≤ 0.19 ep/truck-yr (H2), ~0-FP posture (A2), A1 stays gated |
| **T1 vs learned-attribution review** | P6 | side-by-side attribution table | learned model ships only if ≥ rule-T1 on accuracy AND 0 false attributions on healthy holdout |

### 16.3 Recurring data reviews

Weekly: DQ report sign-off; **R15 cohort-asymmetry verdict (breach freezes modeling)**; SMA-dead roster delta; crank-event-rate SPC digest. Monthly: silent-gap KPI vs DICV telematics owner; label-ledger diff; firmware-family census; NaT counter trend (must stay ~0 post-D5 — any recurrence reopens the contract conversation).

### 16.4 Deliverable/report reviews

As ALT plan §16.4: QA-render inspection for every DICV-facing artifact, using the V1.1 SM deck-pair sanitizer checklist (no VSI-axis IP leaks, correct modal-selection wording — "14/34" class of errors, raw-vs-recalibrated probability labeling).

---

## 17. Test Plan — What We Are Going To Test (Test-Case Catalog)

### 17.0 Strategy

Identical pyramid, fixture policy, CI cadence, tolerance and coverage bars to ALT plan §17.0, with SM's immutable oracles being: the 34-truck pilot dataset; **20,471 crank events**; nested **0.9321** / non-nested **0.9357**; channel table (H2 10/14 • 5/20 • 0.190 ep/yr • 116 d; A2 4/5 • 0/20 • 66.5 d; A1 4/12 • 1.52 ep/yr; persistence 13/14 • 20/20 ever-fire); T1 (9/11, battery 5/5, 0 false, starter arm silent); economics (₹3,64,850 vs ₹6,44,000 = 43.3 %); leak ceilings (n_weeks 0.952, t_start 0.893); GBM probe 0.8429. Synthetic fleet generator profiles: healthy-flat, battery-cascade (rest sag + drive step + dip widening), starter-degrader (dip deepening only), SMA-dead, silent-gap, heartbeat-only, monsoon-seasonal.

### 17.1 Suite T-ING — Ingestion & conversion

Cases ING-01…ING-16 identical in design to ALT plan §17.1, with SM parameters: golden row counts **30,925,573 (failed) / 76,250,496 (healthy)**; `Failure_type` literal **"Starter Motor"** (with space — ING-17 asserts exact string, not "Startermotor"); compression gates ≥8:1 failed (measured 10.20:1) / ≥6:1 healthy (measured 6.40:1); VIN namespacing to `_SM` with cross-vertical isolation (E2E-07).

### 17.2 Suite T-CLN — Cleaning rules (R1–R16)

CLN-01…CLN-19 as ALT plan §17.2 (same rules, SM config) plus:

| ID | Rule | Case | Expected |
|---|---|---|---|
| CLN-20 ⓖ | R3 | pilot NaT golden | NaT present in all 20 NF VINs (81–689,773 rows/VIN), zero in failed; post-drop VIN18_NF duplicate-timestamp census falls 1,010,522 → 320,750 |
| CLN-21 | R16 | SMA obs 0.9 % / 1.1 % of history | `sma_dead` / alive |
| CLN-22 | R16 | SMA-dead truck emits 10× event rate | events suppressed from catalog; SPC config-artifact alarm raised (pilot signature) |
| CLN-23 | R16 | roster transition (dead → alive after config fix) | transition logged; 12-week burn-in state set; crank features stay NaN during burn-in |
| CLN-24 ⓖ | R15 | pilot cohort asymmetry replay | sentinel fires on pilot NaT pattern (NF-only) — the canonical positive case |

### 17.3 Suite T-LBL — Labels & spells

LBL-01…LBL-11 as ALT plan §17.3 (SM golden gap values: silent-gap VINs VIN1_F 72 d, VIN4_F 97 d, VIN5_F 32 d, VIN8_F 37 d, VIN9_F 142 d) plus:

| ID | Case | Expected |
|---|---|---|
| LBL-12 | cause-code mapping | known codes → {starter_internal, battery_cascade, terminal_cable}; unknown → `unknown` + report line |
| LBL-13 | silent-gap dual dating | lead-time metrics computed to last-data; windows to JCOPENDATE; both fields present |
| LBL-14 | recurrent starter replacement | 2 confirmed events → 2 spells with reset; unconfirmed second job card → 1 spell + warning |
| LBL-15 ⓖ | silent-gap KPI | pilot rate 5/14 reproduced by `l05_silent_gap_kpi` |

### 17.4 Suite T-CAC — Weekly cache & crank catalog (SM core suite)

| ID | Case | Expected |
|---|---|---|
| CAC-01 | masked week | active_days 2 → masked; 1 → not; ISO-week boundary rows assigned per ISO 8601 |
| CAC-02 | L40 indexing | 45 masked weeks → last 40 addressed; 32 → all 32; indexing stable under append |
| CAC-03 | weekly VSI stats | 30-row fixture → drive mean/std/p05/p95, rest p05 match hand-computed values |
| CAC-04 | crank merge boundary | SMA runs 10 s apart → merged into 1 event; 11 s → 2 events |
| CAC-05 ⓖ | pilot catalog golden | exactly **20,471** events (20,729 under gap-naive — asserted as the *wrong* answer); 13 artifacts, max dur 145 s |
| CAC-06 | duration quantization | single-row SMA event → dur_s = 5.0 (floor); pilot share ~93 % single-row reproduced on pilot data |
| CAC-07 | success rule | rpm_max_15s 549 → fail; 550 → success; RPM reaches 550 at t0+16 s → fail |
| CAC-08 | artifact rule | dur 61 s → artifact=True, kept in catalog, excluded from dip/duration stats |
| CAC-09 | retry chains | events 100 s apart → chained; 121 s → separate; chain id stable |
| CAC-10 | dip fields | baseline_vsi from pre-crank window; dip_depth = baseline − min; missing baseline → NaN not 0 |
| CAC-11 | midnight-spanning event | crank 23:59:58–00:00:07 → exactly one event, correct date attribution, no double count on daily append |
| CAC-12 | SMA-dead exclusion | R16-dead VIN → zero catalog entries; weekly crank roll-ups NaN |
| CAC-13 | step detectors | injected −0.6 V rest step SNR 2.5 → detected; SNR 1.5 → not; +0.4 V drive step → detected at ≥0.3 V rule |
| CAC-14 | incremental == rebuild | `append_day(D)` catalog + weekly upsert equals full rebuild |
| CAC-15 | hard-start counters | failed crank at baseline 27.5 V → `hard_start_goodv` +1; at 25 V → `lowv_crank_share` numerator +1 |
| CAC-16 | zero-activity week | no valid rows → no weekly row (not zero-filled); masked-week flag absent |
| CAC-17 ⓖ | pilot weekly cache | 34 trucks byte-equal to pilot cache tables |

### 17.5 Suite T-FEA — Features

| ID | Case | Expected |
|---|---|---|
| FEA-01 | ratio feature | fixture: last-4-week vds mean 0.9, L40 mean 0.45 → 2.0; all-NaN L40 → NaN |
| FEA-02 | rest-floor delta | last-13 mean 24.9 V, baseline 25.6 V → −0.7; baseline excludes terminal 13 weeks |
| FEA-03 ⓖ | battery-step re-baseline | synthetic +0.6 V step (SNR 2.4) inside baseline → post-step baseline only; 3 post-step weeks → fallback per frozen code; pilot re-baselined VIN set reproduced |
| FEA-04 | Theil–Sen trend | fixture range series → exact median-of-pairwise-slopes; 5 finite points (<6) → NaN |
| FEA-05 | dip delta | 12 recent + 15 baseline events → mean difference; 9 recent events (<10) → NaN |
| FEA-06 ⓖ | pilot reproduction | modal-4 × 34 VINs ≤1e-9 relative error |
| FEA-07 | walk-forward invariance | append 8 future weeks → snapshot at cut W unchanged |
| FEA-08 | SMA-dead NaN policy | dip feature NaN in snapshot; imputation only inside model folds |
| FEA-09 | ban enforcement | registering `vsi_dominant_freq` (variable window) → raises; fixed-window spectral variant requires grid audit artifact |
| FEA-10 ⓖ | leak-gate meta-test | feature = n_weeks scores 0.952-class AUROC raw, then auto-REJECT by L40 control + proxy gate (both leak ceilings reproduced as the gate's positive controls) |
| FEA-11 | proxy gate | synthetic ρ=0.6 vs span → REJECT; 0.3 → pass |
| FEA-12 | candidate battery plumbing | monsoon share / hard-start LEVEL / cold-dip computed on synthetic seasonal fixture correctly |
| FEA-13 | registry parity | formula-string hash pinned; code change without registry bump fails CI |

### 17.6 Suite T-MDL — Models & harness

MDL-01…MDL-21 as ALT plan §17.6 (fold hygiene spies; grouped-CV integrity; stratification incl. `sma_alive`; determinism; prequential causality; permuted/year-shuffled/exporter-fingerprint controls; calibration math; prior shift; DeLong/Wilcoxon reference vectors; threshold derivation; challenger smoke; survival machinery; left truncation; interval coverage; episode scorer; spec round-trip; promotion truth table) with SM-specific goldens and additions:

| ID | Case | Expected |
|---|---|---|
| MDL-02ⓖ | champion reproduction | nested **0.9321** exact; non-nested modal-4 **0.9357** exact; optimism delta +0.0036; sole nested miss VIN9_F (0.401 vs fold threshold 0.406; recal 0.224) |
| MDL-22 ⓖ | nested selection engine | in-fold screen (MW p<0.10, AUROC≥0.60, |ρ|<0.85, stability ≥27/33) + exhaustive k-search reproduces the pilot's per-fold subset choices (14/34 modal-4, core pair 34/34) |
| MDL-23 ⓖ | per-fold Platt | fold-level Platt on inner-OOF decision values reproduces pilot probability panel (Brier 0.124, CITL −0.062, slope 0.86) |
| MDL-24 ⓖ | horizon metric | prequential AUROC(k) curve reproduces ≥0.75 through k=10 (0.768), 0.704 at k=11; k=15 blip present but not counted by the sustained rule |
| MDL-25 ⓖ | GBM probe parity | LightGBM/GBM screen on pilot features reproduces 0.843-class result (±0.01), i.e., below champion — harness sanity that trees don't silently leak |
| MDL-26 | competing risks | synthetic two-cause fleet → cause-specific hazards recover planted effects; Fine–Gray CIF sums ≤1 |
| MDL-27 ⓖ | economics engine | pilot P3 policy reproduces ₹3,64,850 vs P0 ₹6,44,000 (43.3 % saving) to the rupee; sensitivity: p_convert 0.5/0.9 rows match hand grid |
| MDL-28 | attribution referee | learned attributor vs rule-T1 side-by-side table; ship gate = ≥ accuracy AND 0 false attributions on healthy holdout |

### 17.7 Suite T-ALR — Alert channels (SM)

| ID | Case | Expected |
|---|---|---|
| ALR-01 | H2 dwell logic | weekly tier pattern [R,R,G,R,R,R] → fires only at the 3rd consecutive R (6th cut); [R,R,G,R,R,G…] never fires |
| ALR-02 | H2 episode semantics | continued RED after fire → one open episode, no weekly re-alerts; G week closes episode |
| ALR-03 ⓖ | H2 replay | pilot: recall 10/14, NF ever-fire 5/20, **0.190 ep/truck-yr**, median lead 116 d — exact |
| ALR-04 | A2 triple boundary | all three conditions in ±8 wk → fire; any two → silent; rest step −0.4 V (below −0.5) → silent |
| ALR-05 ⓖ | A2 replay + golden negative | pilot: 4/5 battery archetype, 0/20 NF, median lead 66.5 d; battery-replacement pattern (rest step UP) → provably silent |
| ALR-06 | A1 boundaries | S7 = mean+3 SD with floor 3, ≥2 consecutive days, second-half-only; SMA-dead excluded |
| ALR-07 ⓖ | A1 replay | pilot: 4/12 applicable F fire; NF 1.52 ep/truck-yr; role stays corroborator (no standalone publish path exists — asserted) |
| ALR-08 ⓖ | persistence replay | pilot: 13/14 recall, 4/20 NF at end-of-history, 20/20 NF ever-fire (31.4 % of weeks) — and therefore publish-gate refuses first-crossing alerts from this channel |
| ALR-09 ⓖ | T1 replay | battery 5/5 correct; 0 false attributions on 20 NF; starter arm at 26.0 V silent fleet-wide (median lowv_crank_share 0.4953 reproduced); unscored trucks → INSUFFICIENT |
| ALR-10 | T1 re-fit tool | percentile-based starter-arm cut on synthetic fleet with planted low-voltage crank cohort → arm fires on planted trucks only |
| ALR-11 ⓖ | A5 lookup | state→window mapping exact (persistence∧RED → 126–284 d median 206; A2 → 28–91 d; AMBER-only → none) |
| ALR-12 | dedupe/debounce/payload/replay determinism/volume gate | as ALT plan ALR-08…ALR-11, SM cadence (weekly cuts) |

### 17.8 Suite T-E2E — Integration

| ID | Case | Expected |
|---|---|---|
| E2E-01 | 4-truck synthetic mini-fleet, 26 weeks | planted battery-cascade truck fires A2 then H2; starter-degrader reaches RED; SMA-dead truck scores on voltage features only; healthy stays GREEN |
| E2E-02 ⓖ | pilot end-to-end | raw 107,176,069 rows → NaT/dup handling → 20,471 events → modal-4 ≤1e-9 → nested 0.9321 → full channel table reproduced (the §1.4 table, every cell) |
| E2E-03 | week-close increment | new ISO week closes → weekly cut scores; mid-week days update caches/detectors only |
| E2E-04–07 | backfill, mid-DAG kill, schema evolution, vertical isolation | as ALT plan §17.8 (SM paths; SM identity cannot read ALT paths) |

### 17.9 Suite T-API/DEP — Serving & deployment

API-01…DEP-05 as ALT plan §17.9 with SM payload contract (h2_state, a2_fired, triage attribution, sma_dead flag, cut_week) schema-validated; webhook cases for H2 and A2 fires; rollback drill re-stamps model_version on weekly cut artifacts.

### 17.10 Suite T-PRF — Performance

| ID | Case | Budget |
|---|---|---|
| PRF-01 | daily increment (~2.25 M rows + catalog append + detectors) | < 15 min on D8ds_v5 |
| PRF-02 | full-history rebuild (~1.35 B rows + 20-mo catalog) | < 2 h streaming; peak RSS < 48 GB |
| PRF-03 | weekly scoring cut (500 trucks, nested-champion inference + channels) | < 15 min |
| PRF-04 | 3× headroom (24 h continuous 5 s) | daily chain < 60 min; no OOM |
| PRF-05 | harness | grouped 10×5 CV **with nested in-fold selection** overnight budget (≤ 12 h CPU); profiling report identifies the subset-search hot path |

### 17.11 Suite T-DQM — Monitors & MLOps

DQM-01…DQM-05 as ALT plan §17.11 (PSI, calibration drift, alert SPC, retrain trigger, Log Analytics plumbing) plus:

| ID | Case | Expected |
|---|---|---|
| DQM-06 | SMA roster burn-in | truck leaves dead-roster → crank features excluded from scoring for 12 weeks, then re-enter; event logged |
| DQM-07 | crank-rate SPC | 10× event-rate jump on one truck → config-artifact alarm within one daily cycle |
| DQM-08 | NaT recurrence monitor | any NaT rows post-D5 in either cohort → contract-breach alert |

### 17.12 Suite T-PBT — Property-based tests

PBT-01…PBT-05 as ALT plan §17.12, plus:

| ID | Property |
|---|---|
| PBT-06 | ∀ random SMA stream: crank events are disjoint in time, ordered, and every SMA=1 row belongs to exactly one event or the SMA-dead exclusion |
| PBT-07 | ∀ random weekly panel: masked-week count is monotone non-decreasing under data append; L40 window never addresses future weeks |
| PBT-08 | ∀ score path: H2 fires ⟹ at least 3 RED cuts exist ending at the fire week (no fire without dwell — safety property) |

### 17.13 Suite T-UAT — Shadow & launch

UAT-01…UAT-04 as ALT plan §17.13, plus **UAT-05 battery-first SOP drill**: a staged A2 alert produces the correct battery-inspection work-order type in the workshop system, and the outcome (battery replaced / starter replaced / no fault) round-trips into the label ledger — the p_convert measurement loop is proven before launch.

### 17.14 Out of scope (tested by contract, not by us)

As ALT plan §17.14, plus: battery SoC/SoH ground truth (until D11-family signals exist we infer from VSI only and say so); workshop diagnosis quality (we test the routing and the round-trip, not the mechanic).

### 17.15 Traceability

ING/CLN → P1/P3 XGs · LBL → P2 XG · CAC/FEA → P3 XG (goldens: 20,471 events, modal-4, weekly cache) · MDL → P4/P6/P8 XGs · ALR → P5 XG (channel table is the XG artifact) · E2E → P3/P4/P10 · API/DEP/PRF/DQM/UAT → P10/P11. The nightly reproduction suite (all ⓖ cases) is the regression backbone: **any red ⓖ test blocks every promotion and every deploy.**

---

## 18. Appendices

### A. Pilot artifacts this plan inherits (contract of record)
- Frozen model + spec: `STARTER MOTOR/V1.1/results/V1_1_SM_model_spec.json`; features `STARTER MOTOR/V1.1/src/V1_1_SM_features.py`; caches `V1_1_SM_build_daily_cache.py`; model card `V1.1/reports/V1_1_SM_model_card.md`.
- Alert channels + horizon: `V1.1/reports/V1_1_SM_alerts_horizon.md`; H2/economics: `V2_program/intake/06_heuristics_intake.md`, `04_economics_windows_intake.md`.
- A3/A5: `V2.1/reports/V2_1_SM_verdict.md`. T1 + state engine: `V3.1/reports/V3_1_SM_results.md`, `V3_1_SM_data_reality_memo.md`.
- Ceiling evidence: `V3/features/out/V3_gate_summary.json`, `V3/analysis/out/V3_validation.json` (gbm 0.8429), `V3.1/reports/V3_1_SM_feature_dictionary.md`.
- Crank physics: `STARTER MOTOR/V1.1/audit/D_failure_physics.md`; data quality: `A_data_quality_audit.md`.
- Instrumentation proposal: `docs/2026-06-12-19-45-00-sm-v2-dicv-instrumentation-proposal.md`.
- Azure/costing + FM-pilot gate spec: same four documents as ALT plan Appendix A.
- Evidence-stack graph design: `STARTER MOTOR/V1.1` per-VIN panel generators (V1.1 deck-pair sanitizer pattern for external artifacts).

### B. Champion config template (`sm500_champion.yaml`, excerpt)
```yaml
model: {type: ridge_classifier, alpha: 1.0}
features: [vsi_withinwk_std_ratio_30d_w, rest_vsi_p05_delta90,
           vsi_range_trend, dip_depth_last90_delta]
feature_rules:
  masked_week: {min_active_days: 2}
  window: {l40_weeks: 40, recent_weeks: 4, delta_weeks: 13, trend_weeks: 12}
  battery_step_rebaseline: {step_v: 0.5, snr_min: 2.0, min_post_weeks: 4}
  crank_features_nan_if: sma_dead            # sma_obs_share <= 0.01
preprocess: {impute: fold_train_median, scale: standard}
calibration: {method: platt_per_fold, upgrade_candidate: isotonic}
validation: {scheme: grouped_stratified_kfold, k: 10, repeats: 5, groups: vin,
             strata: [label, cause_code, firmware_family, sma_alive],
             nested_in_fold: {screen: {mw_p: 0.10, auroc_min: 0.60, dedup_rho: 0.85},
                              subset_search_k: [3, 8], threshold: inner_oof_youden},
             temporal_holdout_months: 3, prequential_max_rewind_weeks: 26}
channels:
  h2_pager: {tier: RED, prob_ge: 0.55, dwell_weeks: 3, nf_budget_ep_per_truck_yr: 0.19}
  a2_cascade: {rest_step_v: -0.5, drive_step_v: 0.3, window_weeks: 8,
               dip_widen_v: 1.0, min_events: 10, route: BATTERY_FIRST}
  a1_burst: {s7_sigma: 3, s7_floor: 3, consec_days: 2, role: corroborator_only}
  t1_triage: {starter_arm_baseline_v: 26.0, refit: percentile_based_p6}
crank_catalog: {merge_gap_s: 10, success_rpm: 550, success_window_s: 15,
                artifact_dur_s: 60, retry_link_s: 120}
labels: {failure_date: jcopendate, cause_codes: [starter_internal, battery_cascade,
         terminal_cable, unknown], ledger_version: pinned}
banned_features: [vsi_dominant_freq_family, n_weeks_monotone_family, t_start_family]
```

### C. Verification quick-list (every XG)
1. Reproduction suite: 20,471 events; modal-4 values ≤1e-9; nested 0.9321 exact.
2. DQ ledger clean (hard gates); R15/R16 asymmetry verdicts reviewed.
3. Negative controls ≈0.5 (incl. exporter-fingerprint model).
4. Channel replay table (H2/A2/A1) within budgets at field prevalence.
5. Model card rendered with no missing cells; frozen-spec JSON committed.

---
*Prepared 2026-07-02. Baseline commit 7b59ba1 (branch v11.1-alt). Pilot numbers cited from frozen artifacts in Appendix A; all 500-vehicle numbers are targets/assumptions pending the data drop and are labeled as such.*
