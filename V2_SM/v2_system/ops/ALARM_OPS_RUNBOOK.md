---
title: "SM V2 — Alarm Operations Runbook"
status: "complete"
created: "2026-06-12"
owner: "Ops Owner (see GOVERNANCE_CHARTER.md)"
version: "1.0.0"
---

# SM V2 Alarm Operations Runbook

This is the pager manual for the SM V2 PdM system. It covers who is notified,
response SLAs, escalation rules, the full alert lifecycle, suppression logic,
the weekly cadence checklist, and the feedback SLA that keeps K3/K4 KPIs alive.

---

## 1. Paging Matrix

All alert priorities are defined in `v2_config.json` (config_version 2.1.0-B,
hash 19c2fc99…). The first matching rule wins (precedence order P0-A2 → P0-H2
→ P0_OPS → P1 → P2).

### P0-A2: Battery-First Inspection

| Field | Value |
|---|---|
| Trigger | A2_battery_cascade_fired (rest-VSI step ≤−0.5 V AND drive-VSI step ≥+0.3 V within ±8 wk AND dip widening >1 V) |
| Who is paged | Maintenance lead |
| Initial SLA | Battery-first work order scheduled within **48 hours** of alert |
| Scheduling window | **14–30 days** from alert date (retrospective n=4; min lead 28 d; 0/20 NF false alarms) |
| Why 48 h scheduling, not 48 h inspection | The minimum observed lead time is 28 days. A scheduling deadline of 48 h gives 26+ days of execution buffer. Waiting 7 days to schedule cuts that buffer to 21 days — acceptable, but a 5-day window for battery procurement and bay allocation versus a 26-day window is the practical difference. |
| Escalation | If the inspection has not been **scheduled** (bay + date confirmed) by **day 7**, escalate to fleet manager. If the truck has not been **physically inspected** by day 21 (i.e., 7 days before the minimum lead time), escalate to fleet manager and log as process-miss risk. |
| Protocol | Battery load test first (confound elimination). If battery passes, proceed to starter solenoid voltage-drop check (SAE J3053 ≤0.5 V/segment). See WO template in `workorders/out/`. |

**Math behind the 48-hour timer:** The scheduling window minimum is 28 days
(bootstrap 95% CI low bound). If the maintenance lead does not schedule within
48 hours, the internal fleet calendar booking process (typically 5–10 business
days) may consume enough of the buffer that the window closes before the truck
arrives. 48 h scheduling SLA + ≤10 d booking lead = inspection within ≤12 d,
leaving ≥16 d of the minimum window intact. The 7-day escalation to fleet
manager exists because a 7-day missed schedule implies something systemic (leave,
depot unavailability) that requires managerial override.

---

### P0-H2: Electrical Inspection (Dwell)

| Field | Value |
|---|---|
| Trigger | H2_dwell_fired: ≥3 consecutive weekly cuts RED |
| Who is paged | Maintenance lead |
| Initial SLA | Electrical inspection scheduled within **1 week** |
| Scheduling window | **2–4 weeks** (median ~14 d; persistent RED state) |
| Escalation | If not inspected by the 50% mark of the window (i.e., by day 10 from alert, midpoint of 2–4 wk window), escalate to fleet manager. |
| Protocol | Electrical inspection: battery load test → solenoid contacts → wiring resistance → brushes/commutator. See WO template. |

---

### P0_OPS: Silence Overlay — Dispatcher Connectivity Check

| Field | Value |
|---|---|
| Trigger | No telemetry for >30 days while truck tier is AMBER or RED |
| Who is paged | Fleet dispatcher (not maintenance) |
| SLA | Connectivity check completed within **72 hours** |
| Actions | 1. Verify truck operational status with depot/driver. 2. Check telemetry ECU/SIM/antenna. 3. Force manual data poll if supported. 4. Tag "telemetry fault" if truck is operational but silent. 5. Remove from monitoring queue if decommissioned. |
| Escalation | If no response from dispatcher within 72 h, escalate to fleet manager. |
| Note | P0_OPS does NOT replace any concurrent P0 or P1 shop alert. A truck that is P0-H2 AND P0_OPS carries both obligations. |

---

### P1: RED Tier — Weekly Planning Queue

| Field | Value |
|---|---|
| Trigger | RED tier, no P0 condition (single week, no H2 dwell, no A2 fire) |
| Who is notified | Maintenance planner at weekly review |
| SLA | Added to maintenance queue for inspection within **4–8 weeks** |
| Queue ranking | Rank P1 entries by H1_momentum first (delta_prob ≥+0.15 over 4 wk), then by H5 co-fire (≥p85 fleet percentile in ≥4 of 6 trailing weeks). Highest-ranked trucks get earliest slots. |
| Escalation | Promote to P0-H2 automatically if H2 fires before the inspection slot. |
| Protocol | Queue review occurs during the weekly cadence (see Section 4). |

---

### P2: AMBER Tier — Bundle at Next Service

| Field | Value |
|---|---|
| Trigger | AMBER tier (0.35 ≤ prob < 0.55), no higher-priority trigger |
| Who is notified | Maintenance planner (non-urgent) |
| SLA | Bundle into next scheduled service within **90 days** |
| Escalation | Promote to P1 if H1 AND H5 both fire. Promote to P0-H2 if H2 fires. |
| Note | AMBER carries no empirical lead-time data (0 failed trucks scored AMBER in OOF validation). Treat as uncertain risk zone. |

---

### Corroborate-Only (A1, Persistence Terminal)

These signals never generate a standalone page. They attach evidence to an
existing alert row in `shadow_alert_log.csv`. A1 crank-burst and
persistence_terminal annotate the WO but do not advance the priority.

---

## 2. Alert Lifecycle

```
NEW  ─────────────────────────────────────────────────────┐
 │  Pipeline writes row to shadow_alert_log.csv            │
 │  Pager fires per paging matrix above                    │
 ▼                                                         │
ACKNOWLEDGED                                               │
 │  Ops/maintenance lead confirms receipt                  │
 │  Auto-stale rule: if not ACKed within 7 d → re-page    │
 ▼                                                         │
SCHEDULED                                                  │
 │  Bay + date confirmed (WO open)                         │
 ▼                                                         │
INSPECTED                                                  │
 │  Truck physically inspected; technician fills WO form   │
 ▼                                                         │
FEEDBACK-RETURNED                                          │
 │  Completed WO form ingested:                            │
 │    py -3 labels/ingest_feedback.py <wo_file>            │
 │  Row written to labels/label_registry.csv               │
 │  Refit trigger distance reported                        │
 ▼                                                         │
CLOSED                                                     │
 │  Alert row marked closed in log; K3/K4 KPIs updated     │
 └─────────────────────────────────────────────────────────┘
```

**Auto-stale rules:**

| Condition | Action |
|---|---|
| Alert not ACKNOWLEDGED within 7 days | Re-page same recipient; log as ACK-miss |
| Scheduling window 100% elapsed with no inspection recorded | Escalate to fleet manager + log as process-miss |
| Truck transitions from AMBER/RED to GREEN while alert is open | Flag for review; do NOT auto-close — a false alarm deserves a "no fault found" feedback entry |

---

## 3. Suppression Rule

An alert that is already ACTIVE on a truck (status NEW → SCHEDULED) is NOT
re-paged unless:
1. The priority escalates (e.g., P1 → P0 due to H2 firing), OR
2. A new and distinct channel fires (e.g., A2 fires on a truck already carrying
   a P1-RED alert — this generates a fresh P0-A2 row alongside the existing P1).

This prevents duplicate paging for a truck that is already in the inspection
queue.

---

## 4. Weekly Cadence Checklist

Run every Monday morning (or the next business day after the weekly pipeline
completes). Expected wall clock: ~15 minutes.

```
[ ] 1. Run pipeline
        py -3 "STARTER MOTOR/V2_program/v2_system/V2_weekly_pipeline.py"
        Verify exit code 0 (all gates PASS). Exit code 2/3/4 = stop and
        investigate before surfacing any alerts.

[ ] 2. Record KPI tracker row
        py -3 shadow_quarter/kpi_tracker.py
        Check shadow_quarter/out/kpi_report.md — confirm K1 ≤ 0.30,
        K4 violations = 0. K2 PENDING-DATA is expected and not a breach.

[ ] 3. Triage new alerts
        Open out/shadow_alert_log.csv. Sort by timestamp (most recent).
        For every row with today's timestamp:
          - P0: page maintenance lead per paging matrix
          - P0_OPS: page dispatcher
          - P1/P2: add to planning queue

[ ] 4. Review queue
        Open cards/fleet_ranking.md — confirm P0 trucks are scheduled.
        Rank P1 entries by H1_momentum then H5 co-fire.
        Chase any alert that is SCHEDULED but past window mid-point.

[ ] 5. Chase pending feedback
        py -3 labels/ingest_feedback.py --status
        For any WO that is INSPECTED but not yet FEEDBACK-RETURNED:
          Contact technician/supervisor — feedback is due within 5 business
          days of inspection. Unfed WOs starve K3 and K4.
```

---

## 5. Feedback SLA

Technician WO feedback must be returned within **5 business days** of the
physical inspection.

**Why this matters for KPIs:** K3 requires at least one watchlist VIN to have
a label_registry entry by Week 13 of the shadow quarter. K4 requires zero
GREEN-tier failures outside the documented blind-spot class. Both KPIs depend
entirely on feedback being ingested. A WO left as PENDING does not count as
a finding or a failure.

**Ingestion command:**
```bash
py -3 "STARTER MOTOR/V2_program/v2_system/labels/ingest_feedback.py" <path_to_wo_file>
```

Check status at any time:
```bash
py -3 "STARTER MOTOR/V2_program/v2_system/labels/ingest_feedback.py" --status
```

The `--status` output reports: total findings, total failure labels, distance
to refit trigger (≥5 failure labels), and any PENDING records that need chasing.

---

## 6. Documented Blind Spots

The following failure patterns are irreducible under V2 architecture. When a
failure occurs in these classes, it is logged as a process-aware miss, NOT as
a K4 violation.

| Class | Representative case | Why undetectable |
|---|---|---|
| SMA-dead + fully silent | VIN9_F_SM | No SMA telemetry, no VSI data either. A1 not applicable, VSI features NaN, silence overlay fired (but GREEN). |
| A4-silent while AMBER/RED | VIN1_F_SM | Silence overlay fired; telemetry gap prevents score update. |

GREEN tier does NOT guarantee the truck is healthy. It guarantees that the
available telemetry does not show the four VSI-based risk signatures. A
GREEN-tier SMA-dead truck should be monitored via operational checks, not
via this PdM system alone.

---

*End of Alarm Ops Runbook. For alert channel definitions see v2_config.json.
For WO templates see workorders/out/. For feedback ingestion see LABELS_README.md.*
