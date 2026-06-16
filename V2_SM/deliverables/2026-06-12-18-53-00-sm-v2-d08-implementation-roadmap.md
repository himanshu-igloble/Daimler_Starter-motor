---
title: "SM V2 Program — D8: V2 Implementation Roadmap"
status: "complete"
created: "2026-06-12"
---

# Deliverable 8 — V2 Implementation Roadmap

> Sequencing principle: ship the validated decision layer first (it is analysis-complete), buy the
> prospective evidence second (shadow quarter), and gate all research-grade extensions behind
> explicit entry criteria so the program never regresses into unvalidatable modeling.

## Phase A — Quick wins (1–2 weeks)

| # | Item | Output | Effort |
|---|---|---|---|
| A1 | **Pre-registration freeze**: config registry with tier thresholds, H1/H2/H5 params, banned-feature list, admissibility gates — hash-pinned | `v2_config.json` + registry doc | 1 d |
| A2 | **Walking-score weekly job**: package the X4/heuristics rerun as a scheduled task (input: new week of telemetry; output: scores, tiers, momentum, percentile per truck) | runnable job + CSV/parquet feed | 3 d |
| A3 | **Composite alert policy in shadow mode**: A2→P0, H2→P0, RED-queue→P1, silence→P0-ops (D4 §3); log alerts, page nobody yet | shadow alert log | 2 d |
| A4 | **Failure-window lookup service**: evidence state → window + CI + n (D6 card) attached to every shadow alert | lookup module | 1 d |
| A5 | **Watchlist activation**: VIN2/5/8/15_NF flagged; any outcome recorded as prospective evidence | watchlist tracker | 0.5 d |
| A6 | **Operating-point decision**: adopt Youden-queue with RED-priority per economics (P3 dominates at R≈31; flip threshold R=11.5) — sign-off with fleet ops | 1-page decision memo | 0.5 d |
| A7 | **Candidate adjudication**: accept/hold/reject cold_dip_delta90 + rpm_rise_lag_delta90 per D5 verdicts; if ADD, schedule the refit under full protocol (do NOT hot-patch the frozen model) | D5 verdict applied | 0.5 d |
| A8 | Evidence-card template: raw-unit drivers + archetype + channel history + counterfactual + confidence block | card generator v1 | 2 d |

## Phase B — Medium complexity (2–4 weeks)

| # | Item | Output |
|---|---|---|
| B1 | Governance dashboard: PSI per modal feature (alarm >0.2), calibration slope tracker, alert-volume vs 0.19–0.3 ep/truck-yr baseline, density/null monitors | ops dashboard |
| B2 | Fleet ranking + queue UI for maintenance planners (ranked table, evidence cards, window statements, blind-spot badges) | planner view |
| B3 | New-truck onboarding: fleet-prior scoring, AMBER cap, "immature" badge until 12 masked weeks | onboarding logic |
| B4 | Alert routing integration: A2 → battery-first work order template; H2/RED → electrical inspection template (DICV A6 cascade logic) | workshop integration |
| B5 | **DONE 2026-06-12** — true per-sample scan: NOT predictive (F 11.9 vs NF 7.8 ep/truck-yr, p=0.64); crank-while-running stays an operational telltale only (`V2_program/intake/07_raw_screens_intake.md`) | verdict: NULL/telltale |
| B6 | **DONE 2026-06-12** — daily aggregation resolves the V1 "insufficient data" verdict: VIN1_F fires cleanly 2025-04-08 (155 d lead, matching the X3 A1 date) and 2025-06-24 (78 d); NF sanity (2–6 alarms on busy trucks) confirms corroborator-only/tier-gated use | closed finding |
| B7 | Telemetry-health module: taper/silence analytics fleet-wide (the A4 countermeasure), 72 h ops trigger wired to dispatcher | silence ops loop |

## Phase C — Advanced (4–8 weeks)

| # | Item | Output / gate |
|---|---|---|
| C1 | **Prospective shadow quarter** (THE validation): run A3's shadow log 13 weeks on live data; KPIs: paging burden ≤0.3 shop-alerts/truck-yr, calibration slope ∈ [0.5, 2], ≥1 watchlist resolution, zero GREEN-then-failed outside the documented A4/SMA-dead blind-spot class | prospective validation report |
| C2 | **DICV instrumentation proposal**: current clamp / IBS pilot (₹2–15k/truck) + trigger-based high-rate VSI (firmware-only) on 20–50 trucks, with the D6/T4 economics case (break-even R=30.7 met at base costs) | funded pilot decision |
| C3 | Maintenance-records integration: parts/warranty data → supervised failure-mode labels (converts archetypes from inferred to ground-truth; also resolves starter-warranty coverage question) | labeled failure registry |
| C4 | NF SALEDATE acquisition from DICV: fixes the age-axis bias (F §7.1) and enables honest age-conditional reporting | corrected truck-week table |
| C5 | Multi-fleet scale-out: per-fleet NF envelopes + percentile baselines, config-driven; never transfer absolute VSI levels | deployment kit |
| C6 | Refit automation: nested protocol + admissibility + L40 + permutation as a one-command pipeline, triggered by ≥5 new labels or drift gates | refit harness |

## Phase D — Production-grade deployment readiness

- SLA'd weekly pipeline (retries, data-completeness gates before scoring, late-data handling).
- Model registry with hash-pinned artifacts; every alert replayable (model + features + state).
- Alarm operations runbook: who is paged for P0/P1/P2, escalation timers, feedback capture
  (inspection findings looped back as labels).
- Security/PII review of VIN mapping (`V1_1_SM_vin_naming_map.csv` pattern retained).
- Handover: model card (exists) + ops training + governance charter (refit gates, pre-registration
  discipline, restatement policy).
- **Research gates (do-not-enter-until)**: survival layer & SSL crank-encoder pretraining on the
  106M rows only when ALL of: n_failed ≥ 30–50, current or high-rate-VSI channel live, one clean
  prospective quarter on file. These are recorded as gates, not aspirations — the V1.1 evidence
  (EPV arithmetic, hazard MAE) stays binding until the data changes.

## Dependencies & risks

| Risk | Mitigation |
|---|---|
| Shadow quarter shows higher FP burden than retrospective 0.19 ep/truck-yr | Expected direction (retrospective optimism); thresholds may be re-registered ONCE after quarter 1, documented as restatement |
| DICV declines instrumentation pilot | Program still ships Layers 0–5; horizon stays 10 wk; revisit with accumulated savings evidence |
| New failures arrive during rollout | Good problem: feeds C6 refit under full protocol; labels also test the windows out-of-time |
| Fleet-ops adopts RED-only out of FP fear | A6 memo quantifies the cost: RED-only leaves ~₹62–83k/yr on the table at 34 trucks (scales linearly); revisit only if measured inspection costs exceed 2× assumptions |
| Key-person/process drift | Governance charter + registry make the discipline executable by a new team |

## Timeline summary

Weeks 1–2: Phase A (system live in shadow). Weeks 3–6: Phase B (ops integration). Weeks 7–19:
Phase C (prospective quarter runs concurrently with C2–C6). Week 20: production go/no-go on C1
KPIs. Deep-model/survival research remains gated regardless of calendar.
