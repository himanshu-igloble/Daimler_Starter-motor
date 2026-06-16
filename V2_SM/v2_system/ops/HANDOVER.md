---
title: "SM V2 — System Handover Document"
status: "complete"
created: "2026-06-12"
owner: "Ops Owner / Model Owner"
version: "1.0.0"
---

# SM V2 System Handover Document

---

## 1. System Map

The SM V2 starter-motor predictive maintenance system monitors 34 trucks (14
failed, 20 non-failed; all with suffix `_SM`). It runs a 7-stage weekly
pipeline that ingests per-VIN weekly cache parquets, scores each truck against
a 4-feature Ridge classifier (nested LOVO AUROC 0.9321, 95% CI [0.811, 0.986]),
assigns tier (GREEN/AMBER/RED) and alert priority (P0–P2, P0_OPS), fires
channels (A2 battery-cascade, H2 dwell, H1/H5 rankers), writes outputs to
`v2_system/out/`, regenerates evidence cards and a self-contained HTML dashboard,
and runs 10 governance monitors. All thresholds and model parameters live in
`v2_config.json` (version 2.1.0-B; config hash `19c2fc99…`). The system
operates in shadow mode during the shadow quarter (13 weeks, KPIs K1–K4
pre-registered and frozen). Physical inspection decisions are routed via work
orders generated from `workorders/out/`. Technician feedback is ingested via
`labels/ingest_feedback.py` into `labels/label_registry.csv`, which drives
refit triggering and KPI evaluation. Detection horizon is 10 weeks; no
day-precision RUL. The irreducible blind spot is the SMA-dead + fully-silent
class (VIN9_F_SM archetype). Expected paging burden is 0.2–0.3
shop-grade alerts per truck-year.

---

## 2. Component Inventory

| Subdirectory | Purpose | Entry command / owner doc |
|---|---|---|
| `v2_system/` (root) | Pipeline entry + config | `py -3 V2_weekly_pipeline.py` |
| `v2_system/out/` | Weekly outputs: `fleet_snapshot.csv`, `shadow_alert_log.csv`, `run_manifest.json`, `run_history.csv` | `out/run_manifest.json` (authoritative clock) |
| `v2_system/monitors/` | 10 governance checks (PSI, calibration, H2 NF rate, taper, silence, self-test) | `py -3 monitors/run_monitors.py` |
| `v2_system/monitors/out/` | `governance_status.json`, `monitors_report.md`, `telemetry_health.csv` | Read `governance_status.json` |
| `v2_system/cards/` | 34 per-truck evidence cards + `cards.json` + `fleet_ranking.md` | `py -3 cards/generate_cards.py` · `cards_README.md` |
| `v2_system/dashboard/` | Self-contained HTML dashboard (`sm_v2_dashboard.html`) | `py -3 dashboard/build_dashboard.py` |
| `v2_system/workorders/` | WO generation + OPS checklist | `workorders/out/` (13 WOs + checklist) |
| `v2_system/shadow_quarter/` | KPI spec (K1–K5), tracker, simulator | `py -3 shadow_quarter/kpi_tracker.py` · `kpi_spec.md` |
| `v2_system/labels/` | Feedback ingestion → `label_registry.csv` | `py -3 labels/ingest_feedback.py` · `LABELS_README.md` |
| `v2_system/refit/` | Refit harness (C6) | `py -3 refit/run_refit.py` · `REFIT_RUNBOOK.md` |
| `v2_system/deployment_kit/` | New-fleet onboarding (Steps 1–9) | `py -3 deployment_kit/fleet_onboarding.py` · `DEPLOYMENT_RUNBOOK.md` |
| `v2_system/registry/` | Config registry (parallel-agent owned) | `registry.json` |
| `v2_system/specs/` | Data request specs for sale-date and maintenance records | `data_request_saledate.md`, `data_request_maintenance_records.md` |
| `v2_system/tests/` | Pipeline gate tests + onboarding tests | `py -3 tests/test_pipeline_gates.py` |
| `v2_system/ops/` | This document + ops runbooks | Owner: Ops Owner |

---

## 3. Runbook Index

| Runbook | Location | One-liner |
|---|---|---|
| Alarm Ops Runbook | `ops/ALARM_OPS_RUNBOOK.md` | Paging matrix, alert lifecycle, weekly checklist, feedback SLA |
| Governance Charter | `ops/GOVERNANCE_CHARTER.md` | Roles, pre-registration, refit gates, watchlist, restatement, KPI freeze, annual audit |
| Security and PII | `ops/SECURITY_PII.md` | Data classification, label column rule, dashboard verification, retention |
| Handover (this doc) | `ops/HANDOVER.md` | System map, component inventory, runbook index, training, FAQ |
| Research Gates | `ops/RESEARCH_GATES.md` | Formal do-not-enter register for premature research directions |
| Refit Runbook | `refit/REFIT_RUNBOOK.md` | Refit triggers, harness usage, comparison checklist, promotion sequence, rollback |
| Deployment Runbook | `deployment_kit/DEPLOYMENT_RUNBOOK.md` | New-fleet onboarding Steps 1–9, go-live rules, absolute don'ts |
| Labels README | `labels/LABELS_README.md` | Feedback taxonomy, honesty rule (findings vs failures), refit trigger |
| Cards README | `cards/cards_README.md` | Evidence card structure, production vs OOF probability distinction, feature table |
| KPI Spec | `shadow_quarter/kpi_spec.md` | K1–K5 definitions, quarter pass rule, freeze notice |

---

## 4. Four-Session Training Outline

### Session 1 — Planner View (~90 min)
Goal: understand what the system produces and how to read it.
- Read `cards/fleet_ranking.md` — understand tier/priority columns and H1/H5 badges.
- Open `dashboard/sm_v2_dashboard.html` in browser — identify each panel.
- Read one P0-A2 work order and one P1-RED work order from `workorders/out/`.
- Verify: can you identify the top-3 drivers, the window statement, and the routing protocol?
- Key concept: window = scheduling guide, NOT countdown clock. No day-precision RUL.

### Session 2 — Ops Triage (~90 min)
Goal: run the weekly cadence checklist without supervision.
- Run `py -3 V2_weekly_pipeline.py --dry-run` and interpret exit code.
- Run `py -3 shadow_quarter/kpi_tracker.py` and read `kpi_report.md`.
- Simulate a P0-A2 page: identify the truck, the maintenance lead contact, and
  the 48-hour scheduling deadline.
- Run `py -3 labels/ingest_feedback.py --status` — confirm you understand
  distance-to-refit output.
- Key concept: PENDING records do NOT count as findings; chase technician
  feedback within 5 business days.

### Session 3 — Governance and Registry (~90 min)
Goal: understand the pre-registration discipline and config hash rule.
- Read `ops/GOVERNANCE_CHARTER.md` in full.
- Read `shadow_quarter/kpi_spec.md` in full — identify the four frozen
  thresholds and the quarter pass rule.
- Recompute the config hash from `v2_config.json` using the command in
  `refit/REFIT_RUNBOOK.md` Step 3 and confirm it matches `19c2fc99…`.
- Read the V1 → V1.1 restatement precedent (REFIT_RUNBOOK.md Section 5).
- Key concept: any undisclosed threshold change invalidates the shadow-quarter
  results retroactively.

### Session 4 — Refit and Deployment (~2 hours)
Goal: know when and how to refit, and how to onboard a new fleet.
- Read `refit/REFIT_RUNBOOK.md` end to end.
- Run `py -3 refit/run_refit.py --self-test --perm-n 20` and verify AUROC
  = 0.9321 ± 0.002.
- Walk through `deployment_kit/DEPLOYMENT_RUNBOOK.md` Steps 1–9.
- Identify the three "absolute don'ts" and explain why each exists.
- Key concept: NEVER AUTO-DEPLOY. Every refit ends with a manual-review banner
  that must be cleared by the model owner.

---

## 5. FAQ

**Q1: Why is there no failure date or RUL countdown?**
The SM fleet has no recorded failure dates in the raw data (only a job-close
date from the maintenance system, `JCOPENDATE`, which may lag the actual fault
by days or weeks). RUL survival models tested against the constant-time baseline
produced MAE of 576 days vs 44 days for the constant predictor — a 13× shortfall
(see `RESEARCH_GATES.md`). The system delivers risk tiers and scheduling windows
instead, which are empirically calibrated on retrospective lead times.

**Q2: What does GREEN tier actually guarantee (and NOT guarantee)?**
GREEN guarantees that none of the four VSI-based risk signatures are elevated
above the truck's own baseline. It does NOT guarantee the truck is healthy.
Specifically: if a truck is SMA-dead (no crank telemetry) and its VSI is
also silent, the system has no signal and will score GREEN regardless of the
actual starter condition. VIN9_F_SM is the archetype. GREEN = no evidence of
risk within the detection scope of V2. It is not a safety guarantee.

**Q3: Why did truck X not alert? (Blind-spot classes)**
There are two documented undetectable classes:
(a) SMA-dead + fully silent (VIN9_F_SM class): SMA telemetry absent, VSI absent.
    A1, H2, A2, and persistence channels are all inapplicable. Score defaults GREEN.
(b) A4-silent while AMBER/RED (VIN1_F_SM class): telemetry gap during the
    critical monitoring window prevents score update. Silence overlay fires
    (P0_OPS) but no inspection alert is generated.
Any truck outside these classes that fails GREEN is a K4 violation and triggers
a root-cause analysis.

**Q4: What happens when a battery is replaced on a watchlist truck? Does the A2/E5 sign logic reset?**
Yes. The A2 channel detects the signature of a battery that is degrading while
still installed: rest-VSI floor sagging (negative step) AND drive-VSI floor
rising (positive step) because the alternator is working harder to compensate.
After a battery replacement, both VSI baselines reset. The A2 channel will not
re-fire until a new degradation pattern accumulates. The fleet snapshot will show
the truck's `a2_fired_ever` flag as True historically, but the channel is not
re-active until the sign condition is met again on fresh data. Document the
replacement date in the label registry (`finding_mode: battery_degraded`,
`parts_replaced` field) so the refit harness can correctly attribute the outcome.

**Q5: When do we retrain?**
Three conditions trigger formal refit evaluation (see `refit/REFIT_RUNBOOK.md`):
(1) ≥5 new confirmed failure labels accumulated in `labels/label_registry.csv`.
(2) Calibration slope drifts outside [0.5, 2.0] on live deployment data.
(3) PSI > 0.2 on any model feature (population shift).
A refit evaluation does NOT guarantee a new model is promoted. The comparison
report must show the new model meets all six gates before the model owner
authorises promotion.

**Q6: Can we change a threshold (e.g., move RED from 0.55 to 0.60)?**
Only via the formal pre-registration process. Any change requires: (a) a
documented rationale, (b) a version bump in `v2_config.json`, (c) a hash
recompute, (d) a dated restatement note, and (e) re-evaluation of the
shadow-quarter KPIs from the beginning (because K1 and K4 are threshold-
dependent). A change mid-shadow-quarter invalidates the quarter results for
those KPIs. The governance charter forbids retroactive threshold changes after
Week 13 data is observed.

**Q7: What is the watchlist and why are those four trucks on it?**
The watchlist (VIN2_NF_SM, VIN5_NF_SM, VIN8_NF_SM, VIN15_NF_SM) was
pre-registered in `v2_config.json` before the shadow quarter began. These
non-failed trucks showed elevated VSI risk signals during retrospective
analysis. They are not predicted failures — they are prospective monitoring
targets. Every outcome (failure, clean inspection, continued non-failure) is
recorded. At least one of them must have a label_registry entry by Week 13 to
satisfy KPI K3. See `GOVERNANCE_CHARTER.md` Section 4.

**Q8: How do new trucks onboard? What happens during the <12-week immature period?**
New trucks are automatically classified as immature by the weekly pipeline until
their weekly cache contains ≥12 weeks with `n_rows > 0`. During immaturity:
the truck is scored by Layer-1 risk tier only (if VSI features are available),
is NOT included in the fleet percentile reference, and heuristics H1/H2/H5 are
suppressed (these require trailing windows that don't exist yet). The immature
tier is capped at AMBER — no RED classification during the immature period.
This prevents false alarms from data-sparse trucks and eliminates the
observation-length leak (banned feature class D5).

**Q9: What would earlier warning require? (Sensors)**
Earlier warning would require signals that are either absent or too sparse in
the current data feed. Candidates identified in the V2 analysis:
(a) AC ripple on the DC bus (alternator diode health proxy — not in current feed).
(b) Crank current magnitude (distinguishes starter draw from battery source
    impedance — not in current feed as a direct measurement; only inferred from VSI).
(c) Starter motor temperature (thermal fatigue precursor — not in current feed).
See `specs/data_request_saledate.md` and `specs/data_request_maintenance_records.md`
for pending data requests. Adding new sensors requires a fresh prospective
validation; do not re-use the existing V2 thresholds on augmented data.

**Q10: Who do I call?**
- Alert is P0 or P1: contact the Maintenance Lead (see GOVERNANCE_CHARTER.md
  roles section — placeholder to be filled in at go-live).
- Alert is P0_OPS (silence): contact the Fleet Dispatcher.
- Escalation beyond 7 days (P0-A2) or 50% window elapsed (P0-H2): contact the
  Fleet Manager.
- Config change, refit decision, or governance question: contact the Model Owner.
- Data agreement or DICV interface question: contact the DICV Liaison.
- All contacts are recorded in `ops/GOVERNANCE_CHARTER.md` roles table.

---

*End of Handover Document. For cross-reference of all paths see
ops/RESEARCH_GATES.md (path verification table).*
