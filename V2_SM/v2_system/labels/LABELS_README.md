# Label Registry — Flow, Taxonomy, and Honesty Rule

## Label Flow

```
WO FEEDBACK CAPTURE (technician fills in checklist after inspection)
         |
         v
py -3 ingest_feedback.py <wo_file_or_dir>
         |
         v
labels/label_registry.csv
   vin, wo_date, source_file, finding_modes, parts_replaced,
   technician, completed_date, free_text, ingested_at, registry_version
         |
         +--- py -3 ingest_feedback.py --status
         |        prints counts + refit trigger distance
         |
         v
   When n_failure_labels >= 5  (refit trigger from v2_config governance)
         |
         v
v2_system/refit/run_refit.py --labels
   (C6 harness — built in parallel; path is the handoff point)
```

## Failure-Mode Taxonomy

The WO checklist maps to D2 physics modes as follows:

| Checklist Item                   | Registry Code       | D2 Physics Mode                          | Starter Replacement? |
|----------------------------------|---------------------|------------------------------------------|----------------------|
| Battery degraded                 | battery_degraded    | External battery confound — A2 channel   | No (battery swap)    |
| Solenoid contacts worn / burned  | solenoid_contacts   | A1 solenoid intermittency — wear-fatigue | Often (solenoid swap)|
| Brushes / commutator degraded    | brushes_commutator  | A3 VSI volatility / brush wear           | Often (full SM)      |
| Cable or terminal fault          | cable_terminal      | Wiring resistance — not SM internal      | No (cable/terminal)  |
| Clutch / pinion engagement fault | clutch_pinion       | Mechanical engagement — A1 variant       | Often (full SM)      |
| No fault found (false positive)  | no_fault_found      | False positive — model over-fired        | No                   |
| Other                            | other               | Unknown / unclassified                   | Inspect parts field  |

Multiple modes may be ticked on a single WO (stored `|`-delimited in registry).

## Honesty Rule: Findings vs Failures

The registry contains two semantically distinct label types:

**FINDING labels**: Any WO with completed feedback (any finding_mode, including
"no_fault_found"). These are inspection truth — what the technician observed
during a shop visit triggered by the PdM system.

**FAILURE labels**: A subset of findings where:
  1. finding_mode is NOT "no_fault_found", AND
  2. parts_replaced includes "Starter_motor_full" OR "Solenoid_only"
     (i.e., a starter replacement event occurred)

Only FAILURE labels count toward the refit trigger (≥ 5) and toward the K2
calibration slope calculation. Finding labels (including false-positive "no
fault found" cases) are recorded for audit and false-positive rate tracking
but do not advance the refit counter.

**Why the distinction matters**: In shadow data (retrospective, 2026-06-12),
zero failure labels exist — no real WOs have been returned with completed
feedback. The `ingest_feedback.py --status` command reports this as 0 failure
labels with a clear distance-to-trigger note. This is correct and expected.

## PENDING Records

A WO where the feedback form has not been completed (no boxes ticked, no
technician name, no date) is recorded as finding_modes = "PENDING". This
indicates the WO was issued but not yet closed. PENDING records are NOT
counted as findings or failures. Re-ingesting a file after the form is
completed will be a new ingest (different source file path or updated file)
and will create a new registry row — the PENDING row is retained for audit.

## Refit Trigger

Refit trigger threshold: **≥ 5 failure labels** (from v2_config.json governance).

When reached, run:
```
py -3 v2_system/refit/run_refit.py --labels
```

The refit harness (C6, built in parallel) reads `labels/label_registry.csv`
and re-evaluates whether the model should be retrained. Do not trigger refit
manually outside the C6 protocol.
