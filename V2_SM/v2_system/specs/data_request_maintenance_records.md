---
title: "C4 External Data Request — Maintenance and Parts Records"
status: "complete"
created: "2026-06-12"
program: "V2 Starter Motor"
author: "Technical Product Lead"
---

# C4 Data Request: Maintenance and Parts Records (All 34 SM Fleet Trucks)

## Request Summary

Request to DICV Service Team: provide maintenance work-order records and parts-replacement
records covering starter motor, battery, and electrical system events for all 34 trucks
in the telematics fleet — including all future trucks added to the fleet.

**Anonymized VIN linkage**: DICV retains the VIN-to-anon-label mapping; the analytics
team receives only records keyed to the anonymized labels already in use.

---

## Why This Is Needed

**Converting archetype labels to supervised failure-mode labels:**

The V1.1 discovery layer (`E_pattern_discovery.md §2`) identified four telemetry archetypes
(A1 solenoid intermittency, A2 battery cascade, A3 VSI volatility, A4 silent/abrupt).
These are inferred from signal patterns only. Maintenance records ground-truth them:

- **Battery replacement records** → confirm or refute the A2 battery-cascade archetype
  inference. V1.1 used a rest-VSI step-up heuristic (E5) to infer battery replacements
  on 5 NF trucks; actual records replace this with verified ground truth, eliminating
  the risk that the step-up proxy misidentifies battery replacements.
- **Starter overhaul / replacement records** → confirm failure mode and repair action;
  distinguish "starter replaced as part of normal service" from "starter replaced after
  roadside failure".
- **Cable / terminal service records** → identify Mode 14 (cable corrosion) events
  independently of the VSI signal, enabling model validation against a gold-standard label.
- **Long-cranking engine complaints** → cross-validate the SMA thermal-stress event flags
  (driver-reported hard starting vs. model-detected long-crank episodes).

**Enabling supervised failure-mode classification (V3 prerequisite):**

The current model predicts failure probability as a single score. With mode labels,
a V3 model can route differently: "this truck is battery-failing → replace battery;
this truck is brush-failing → schedule starter overhaul." This routing saves ~₹14,000
per event by avoiding an unnecessary starter replacement when the root cause is the
battery (A2 routing, currently estimated from signal patterns alone).

---

## Requested Fields

**Delivery format:** UTF-8 CSV, one row per work order / parts event.

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `anon_label` | string | Anonymized VIN label (DICV-side join) | VIN7_SM |
| `event_date` | ISO 8601 date YYYY-MM-DD | Date of service event or parts replacement | 2025-03-14 |
| `event_type` | string (controlled vocab) | See event type vocabulary below | starter_replacement |
| `part_number` | string (optional) | OEM or aftermarket part number for replaced component | 0001416009 |
| `part_description` | string | Plain-language description of part replaced or service performed | "24V starter motor assembly, co-axial" |
| `odometer_km` | integer (optional) | Odometer reading at service (if available) | 87450 |
| `service_outlet` | string (optional) | Authorized dealer vs. roadside repair vs. depot workshop | authorized_dealer |
| `warranty_claim` | boolean (optional) | Whether event was a warranty claim | True |
| `technician_notes` | string (optional) | Free-text fault description from technician | "Starter failed to engage on cold morning" |

**Event type controlled vocabulary** (use closest match; "other_electrical" is the
catch-all):

- `starter_replacement` — full starter motor unit replaced
- `starter_repair` — brush set, solenoid contact, or other sub-assembly repair without
  full unit replacement
- `battery_replacement` — one or both 12V batteries replaced
- `battery_test` — load test or conductance test performed (record result in notes)
- `cable_replacement` — main battery/starter cable or terminal replacement
- `terminal_cleaning` — corrosion cleaning of battery posts or main terminals
- `alternator_replacement` — alternator replacement (relevant context for battery health)
- `electrical_inspection` — electrical system check without parts replacement
- `roadside_failure` — breakdown event record (starter failed to crank; truck non-mobile)
- `other_electrical` — any other electrical or charging-system event

---

## Scope and Coverage

- **All 34 current telematics-fleet trucks**, historical records back to earliest
  available service data (ideally from in-service date or earliest telematics observation).
- **Future fleet trucks** as they are added: a periodic (quarterly) record pull is
  sufficient for model maintenance; real-time is not required.
- **Minimum viable delivery:** `anon_label`, `event_date`, `event_type`, `part_description`
  for starter and battery events only. Records for other event types are desirable but
  not blockers.

---

## Consumption Path

On receipt, the analytics team will:

1. **Validate schema** using `specs/consume_external_data.py::validate_maintenance(csv)`.
2. **Cross-reference E5 battery-step inferences**: compare the 5 NF trucks where V1.1
   inferred battery replacements from rest-VSI step-up against actual battery replacement
   dates. Discrepancies are documented and the E5 feature flag updated.
3. **Build a supervised label table** (`v2_system/labels/maintenance_labels.csv`): one row
   per truck-event, joined to the weekly cache, with a `failure_mode` column encoding the
   known work-order archetype for that VIN at that point in time.
4. **Gate V3 supervised modelling**: the label table becomes the unlock condition for
   the V3 mode-specific classifier (requires n_labeled_failures >= 20 per mode class
   before supervised training; current labeled count is 0).
5. **Validate A2 channel specificity**: confirm that the 4 A2-fired failed trucks
   (VIN13_F, VIN14_F, VIN3_F, VIN6_F) indeed received battery replacements proximate
   to failure; confirm the 0/20 NF false-alarm record is consistent with actual battery
   replacement timing on the 5 NF trucks with inferred replacements.

---

## Handling and Retention

- The raw mapping table is used for the join and immediately deleted.
- All retained records are keyed only to anonymized labels.
- Technician notes are retained as free text but are not published or shared outside
  the analytics-engineering team.
- Data is stored in the secure project data directory with access controls consistent
  with DICV data sharing agreement.

---

*See also: `data_request_saledate.md`. Both requests can be fulfilled in a single data
exchange. Validation stubs for both are in `specs/consume_external_data.py`.*
