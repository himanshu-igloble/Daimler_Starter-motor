# Shadow-Quarter KPI Specification (D8-C1)

**Status: PRE-REGISTERED — thresholds frozen before Week 1**

Thresholds are locked now, before any live week is observed. This is the entire
point of pre-registration: no post-hoc threshold tuning is permitted. Any
proposed threshold change after Week 1 must be logged as a protocol deviation
and requires explicit D8 sign-off.

---

## Quarter Definition

- **Duration**: 13 consecutive weekly pipeline runs (one per week)
- **Clock starts**: First weekly `py -3 V2_weekly_pipeline.py` run after this
  spec is filed
- **Data sources** (read-only):
  - `v2_system/out/fleet_snapshot.csv` — per-truck state each week
  - `v2_system/out/shadow_alert_log.csv` — per-alert rows each week
  - `v2_system/out/run_manifest.json` — run timestamp (authoritative clock)
  - `v2_system/out/run_history.csv` — one row per run (overall_ok, gate flags)
  - `analysis/heuristics/out/walking_scores.csv` — retrospective per-VIN
    per-k scores (simulation only)
  - `labels/label_registry.csv` — feedback labels (ingested via C3)

---

## K1 — Paging Burden

**Definition**: Shop-grade (actionable) alerts per truck-year must remain low
enough to avoid alert fatigue.

**Metric**:
```
K1 = count(P0_alerts_shop) / truck_years_elapsed

where:
  P0_alerts_shop = rows in shadow_alert_log with priority == "P0"
                   AND silence_trigger_active == False
                   (P0_OPS rows are excluded — ops checks, not shop visits)
  truck_years_elapsed = (n_trucks × weeks_elapsed) / 52.18
  n_trucks = 34
  weeks_elapsed = number of archived weeks (1..13)
```

**Threshold**: K1 ≤ 0.30 shop-grade alerts / truck-year

**Sources**: `shadow_alert_log.csv` (priority, silence_trigger_active columns),
`run_manifest.json` (run_timestamp)

**Notes**:
- P0_OPS rows (silence_overlay) are excluded from the numerator — they are
  telemetry ops checks, not shop inspections.
- The metric is cumulative over the full quarter; a single-week spike is not
  a breach unless the rolling total crosses the threshold.

---

## K2 — Calibration Slope

**Definition**: The regression slope of observed failure rate on predicted
probability must confirm the model is neither over- nor under-confident.

**Metric**:
```
K2 = calibration_slope from isotonic or logistic regression of
     failure_labels (0/1) on model_prob across all labeled trucks

Evaluable condition: >= 3 new failure labels in label_registry.csv
  (failure label = finding_mode != "no fault found" AND parts_replaced
   includes "Starter motor (full)" or "Solenoid only")
```

**Threshold**: K2 ∈ [0.5, 2.0]

**Status before ≥3 failure labels**: PENDING-DATA

**Sources**: `labels/label_registry.csv`, `fleet_snapshot.csv` (prob column)

**Notes**:
- Slope < 0.5 = model over-confident; slope > 2.0 = under-confident.
- At n=34 retrospective, calibration slope was 0.86 (v2_config.json).
- This KPI will remain PENDING-DATA for most or all of the shadow quarter;
  that is expected and not a breach.

---

## K3 — Watchlist Resolution

**Definition**: At least one of the four pre-registered watchlist trucks
(VIN2_NF_SM, VIN5_NF_SM, VIN8_NF_SM, VIN15_NF_SM) must have a documented
resolution event during the quarter.

**Resolution events** (either satisfies K3):
1. Truck fails → outcome recorded as SAVE (alerted in advance) or MISS
   (not alerted) in the label registry
2. Truck is proactively inspected → finding recorded in the label registry
   (any finding including "no fault found" counts if the WO was issued)

**Threshold**: ≥ 1 watchlist truck with a label_registry entry by Week 13

**Sources**: `labels/label_registry.csv` (vin column), v2_config.json
(watchlist.vins)

---

## K4 — No GREEN-then-Failed Outside Blind-Spot Class

**Definition**: Zero cases of a truck that was GREEN-tier at the time a real
failure is confirmed, unless the truck belongs to a documented blind-spot class.

**Metric**:
```
K4_violations = count(trucks where:
  label == 1 (failure confirmed via label_registry)
  AND tier_at_failure_week == "GREEN"
  AND vin NOT IN blind_spot_class)

blind_spot_class = {A4-silent trucks, SMA-dead trucks}
  = any truck with silence_trigger_active == True continuously for >= 4 weeks
    OR sma_dead_badge == True in fleet_snapshot at the time of failure

K4 passes iff K4_violations == 0
```

**Threshold**: 0 violations

**Sources**: `fleet_snapshot.csv` (tier, sma_dead_badge,
silence_trigger_active), `labels/label_registry.csv`

**Notes**:
- VIN1_F_SM and VIN9_F_SM are GREEN-tier at end-state in retrospective data.
  VIN1_F_SM has silence_trigger_active=True (blind-spot class: A4-silent).
  VIN9_F_SM has sma_dead_badge=True (blind-spot class: SMA-dead).
  Both are exempt from K4 under the documented blind-spot rule.
- VIN4_F_SM (AMBER-tier, not GREEN) is not a K4 case but is flagged for
  monitoring as an AMBER boundary truck.
- In shadow simulation using retrospective end-state, K4 violations = 0
  (verified in simulate_quarter.py).

---

## K5 — Tracking Only (No Threshold)

**Definition**: Operational telemetry tracked weekly for trend awareness.
No pass/fail threshold. Reported in kpi_report.md each week.

**Tracked metrics**:
1. Weekly alert volume by channel: count of P0, P1, P2, P0_OPS per week
2. Evidence-state transition counts: how many trucks changed evidence_state
   (e.g., RED_tier_no_channel → persistence_terminal_AND_RED_tier)
3. Silence trigger count: trucks with silence_trigger_active == True per week

**Sources**: `shadow_alert_log.csv`, `fleet_snapshot.csv`

---

## Quarter Pass Rule

The shadow quarter PASSES if and only if ALL of the following hold:

```
PASS = K1_status == "ON-TRACK"
   AND (K2_status == "ON-TRACK" OR K2_status == "PENDING-DATA")
   AND K3_status == "ON-TRACK"
   AND K4_status == "ON-TRACK"
```

K5 is tracking-only and does not affect the pass/fail verdict.

**On K2**: If ≥3 failure labels arrive and K2 breaches [0.5, 2.0], the quarter
fails on K2. If < 3 labels arrive by Week 13, K2 stays PENDING-DATA and does
not cause failure — the calibration question is deferred to the next evaluation
cycle.

---

## Freeze Notice

These thresholds and definitions are frozen as of the file creation date
(2026-06-12), before Week 1 data is observed. Any retroactive change requires
a dated protocol deviation note appended to this file with D8 sign-off.
