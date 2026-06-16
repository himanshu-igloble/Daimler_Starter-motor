---
title: "SM V2 — Multi-Fleet Deployment Runbook (C5)"
status: "complete"
created: "2026-06-12"
program: "V2 Starter Motor"
author: "Technical Product Lead"
---

# SM V2 Deployment Runbook — New Fleet Onboarding

This runbook covers every step required to deploy the V2 starter-motor PdM system on a
fleet that is NOT the original 34-truck SM training fleet. Follow steps in order. Do not
skip or reorder.

---

## Step 1 — Signal Mapping and Column Dictionary Check

**Goal:** Confirm that the new fleet's telematics feed contains all required signals with
compatible semantics.

Required columns (check against `docs/column_dictionary.md`):

| Column | Meaning | Valid range | Sentinel values |
|--------|---------|-------------|----------------|
| `CSP` | Vehicle speed (km/h) | 0–100 | 65535 |
| `RPM` | Engine speed (rev/min) | 0–3500 | 65535 |
| `ANR` | Engine torque (Nm) | −400 to 1300 | 65535, −5000 |
| `GED` | State alternator excitation | {0,1,2,3} | — |
| `VSI` | Power supply voltage (V) | 0–36 (raw × 0.2 if >50) | 0, 255 |
| `SMA` | Starter motor active | {0,1} | — |

**Checks to perform:**
1. Confirm column names match exactly (case-sensitive); create a rename map if needed.
2. Confirm VSI scaling: if raw values > 50, apply V_actual = raw × 0.2. Document the
   scale factor in the fleet config.
3. Confirm SMA is binary; if it is a multi-state signal, map to {0,1} and document.
4. Spot-check 100 rows per VIN: verify RPM rises after SMA events (crank events exist
   and are non-trivial), VSI is in valid range during drive periods, no permanently stuck
   values.
5. Document null rates per column (especially VSI and SMA) in the fleet audit log.
   A VSI null rate > 40% is a red flag; investigate before proceeding.

---

## Step 2 — Cache Build

**Goal:** Build the weekly feature cache parquet files that the V2 pipeline consumes.

Use the V1 cache builders (same code base; they are fleet-agnostic given correct column
mapping from Step 1):

```
py -3 "STARTER MOTOR/V1.1/src/V1_SM_weekly_builder.py" \
    --input-dir <fleet-data-dir> \
    --output-dir <cache-dir>/weekly \
    --fleet-suffix <e.g. _SM2 or _NEWFLEET>
```

Verify output:
- One parquet file per VIN: `weekly_<VIN>.parquet`.
- Each file contains columns: `week`, `vin_label`, `n_rows`, `vsi_drive_std`,
  `vsi_rest_median`, `vsi_drive_mean`, and all other weekly aggregates.
- Spot-check: a VIN with known regular operation should show `n_rows > 0` for most weeks.
- Flag any VIN where `vsi_drive_std` is NaN for > 50% of weeks (possible SMA-dead or
  data quality issue; carry forward to Step 3).

---

## Step 3 — SMA-Dead / Cohort Audit (Null-Rate Scan)

**Goal:** Identify SMA-dead trucks and other cohort anomalies before building the
envelope. SMA-dead trucks distort the NF envelope if included.

Run a probe2-style null-rate scan:

```python
import pandas as pd
from pathlib import Path

cache_dir = Path("<cache-dir>/weekly")
for f in sorted(cache_dir.glob("*.parquet")):
    df = pd.read_parquet(f)
    sma_null = df["sma_events_count"].isna().mean() if "sma_events_count" in df.columns \
               else float("nan")
    vsi_null = (df["vsi_drive_std"].isna() | (df["n_rows"] == 0)).mean()
    print(f"{f.stem}: sma_null={sma_null:.2f}, vsi_null={vsi_null:.2f}")
```

Classify VINs:
- `sma_null > 0.90` → mark as **SMA-dead**: exclude from A1 crank-burst scoring;
  persistence scoring via VSI still applies.
- `vsi_null > 0.50` → mark as **data-sparse**: flag for ops follow-up before scoring.
- Confirm all SMA-dead VINs with operations (is the vehicle actually operating?
  SMA-dead can mean: (a) telematics misconfiguration, (b) vehicle at rest, (c) genuine
  no-start condition). A truck that is SMA-dead AND RED-tier is a **72-hour ops check**
  trigger, not just a data quality flag.

Record the SMA-dead VIN list and insert it into the `config_patch.json` from Step 4:
`cohort_masks.sma_dead_vins`.

---

## Step 4 — Run fleet_onboarding.py

**Goal:** Generate the fleet-specific NF p90 envelope and the three JSON artefacts.

```
py -3 "STARTER MOTOR/V2_program/v2_system/deployment_kit/fleet_onboarding.py" \
    --weekly-cache-dir <cache-dir>/weekly \
    --fleet-name <fleet-name> \
    [--nf-vins <nf-vin-list.txt>]
```

This writes to `deployment_kit/out/`:
- `<fleet-name>_envelope.json` — the −12..−1 end-aligned NF p90 envelope
- `<fleet-name>_baselines.json` — fleet percentile policy (walking scores computed at
  runtime from this fleet's NF trucks)
- `<fleet-name>_config_patch.json` — fragment to merge into v2_config.json

Review the reconciliation table printed by the script:
- For the SM production fleet: expected 13/14 F recall, 2/20 NF fire (VIN2_NF, VIN5_NF)
  with the ALL-NF production envelope. Two VINs differ from LOVO (VIN8_NF, VIN15_NF)
  because their LOVO fold excluded them from the NF training set; production behaviour
  is correct and documented.
- For new fleets: there is no prior LOVO CSV to compare against. Document the
  production end-rule fire table as the baseline.

**Minimum NF truck count:** The script refuses if fewer than 5 NF trucks are available.
At fewer than 10 NF trucks, the p90 envelope is unreliable; flag the deployment as
provisional and plan a re-fit when more NF history is available.

---

## Step 5 — Config Merge and Hash Bump

**Goal:** Integrate the new fleet envelope into the live v2_config.json.

1. Open `v2_system/v2_config.json`.
2. Add or update the fleet entry by merging `<fleet-name>_config_patch.json`:
   - Set `fleet_name`, `envelope_ref`, `baselines_ref`, `source_hash`.
   - Set `cohort_masks.sma_dead_vins` to the list from Step 3.
   - Set `alert_rule.m_of_12 = 4` (frozen; this field is informational only).
3. Bump the config version hash (increment `config_version` field by 1).
4. Commit the updated config with a message referencing the fleet name and source hash.

The source hash in the envelope JSON is the deterministic fingerprint of the NF cache
files used to build the envelope. If the cache is rebuilt (new data arrives), re-run
Step 4 and re-merge; the hash will change and will be recorded in the config.

---

## Step 6 — Immature-Truck Policy Active by Default

**Trucks with fewer than 12 weeks of history** cannot be scored by the persistence alert
(the 12-week trailing window has no data). These trucks are automatically classified as
**immature** and:
- Are scored by Layer-1 risk tier only (if Layer-1 features are available).
- Are NOT included in the fleet percentile reference for walking-score baselines until
  they reach 12 weeks.
- Are listed in a weekly `immature_trucks` audit log entry.

This policy is ACTIVE BY DEFAULT for all new trucks added to the fleet. No configuration
change is needed; the V2 weekly job enforces it automatically.

A truck exits immature status automatically when its weekly cache reaches 12 rows with
`n_rows > 0`. The first persistence score is computed at that point.

---

## Step 7 — Shadow Mode and Quarter Gate

**Goal:** Run in shadow mode for one quarter before any operational alerts are acted on.

Shadow mode: the V2 pipeline runs on full data and generates alerts, but:
- Alerts are logged to `v2_system/shadow_quarter/` only.
- No alert is surfaced to operations or maintenance teams.
- The V2 weekly job outputs a shadow alert CSV; no tickets, no pages.

**Quarter gate KPIs** (pre-registered; evaluate at week 13):

| KPI | Threshold | Consequence if missed |
|-----|-----------|-----------------------|
| False-alarm rate (NF trucks flagged per truck-week) | <= 0.25 ep/truck-week | Investigate; re-register threshold before go-live |
| Failed truck detection rate (among trucks that fail during shadow quarter) | >= 0.80 | Root-cause analysis required; defer go-live |
| SMA-dead-trigger latency | 100% of SMA-dead + RED trucks surface within 7 days | Fix ops-trigger integration before go-live |
| Data completeness | >= 90% of weeks have non-null VSI and SMA data per truck | Investigate data pipeline; defer go-live |

See `v2_system/shadow_quarter/` for the shadow mode runner and the KPI evaluation script.

---

## Step 8 — Go-Live Rules

**Go-live is authorised if ALL of the following hold after the shadow quarter:**

1. All four Step 7 KPIs passed.
2. Config version hash matches the envelope source hash in production.
3. The SMA-dead VIN list has been confirmed by operations (not just data audit).
4. At least one operations team member has reviewed the alert routing:
   - A2 fire → battery-first inspection (schedule within 14–30 days).
   - Persistence terminal + RED → planned electrical inspection within 14–28 days.
   - SMA-dead while RED/AMBER → 72-hour ops check.
5. The new-fleet prospective alert register is initialised (pre-registration of go-live
   alert states for all current watchlist trucks).

---

## Step 9 — The Absolute Don'ts

These rules are non-negotiable. Violations silently corrupt the alert system.

**DO NOT transfer thresholds across fleets.**
The >=4-of-12 rule (m=4) is frozen from the SM training fleet validation. It must not
be re-tuned on the new fleet using the new fleet's outcome data — that is in-sample
tuning. If the new fleet's false-alarm rate is unacceptable, investigate the data
quality and signal mapping first; retune only via a pre-registered, held-out evaluation.

**DO NOT transfer absolute VSI levels across fleets.**
The VSI regulation setpoints on 24V truck fleets vary 27.6–28.2 V by vehicle batch,
alternator, and duty cycle. An absolute threshold (e.g., "rest VSI < 24.5 V = degraded")
that holds for fleet A will produce different false-alarm and recall rates on fleet B.
All VSI-based features are ratio- or delta-based for exactly this reason.

**DO NOT reuse another fleet's envelope JSON.**
The `<fleet-name>_envelope.json` file is valid ONLY for the fleet it was generated from.
Even if two fleets use identical trucks from the same model year, their NF p90 envelopes
will differ due to different duty cycles, route profiles, and maintenance histories.
`fleet_onboarding.py` enforces this rule with a printed warning and must be re-run for
every distinct fleet.

**DO NOT pool VINs from different fleets without separate validation.**
SM fleet VINs and ALT fleet VINs are different physical trucks (VIN Independence Rule).
If a new fleet is added that includes a mix of trucks from multiple prior deployments,
each prior fleet group must be validated independently before cross-fleet features are
considered. Cross-fleet feature engineering is not supported in V2; it requires a
separate research program with prospective validation.

**DO NOT score trucks with <12 weeks of history using the persistence rule.**
The trailing-12-week window requires 12 weeks of data. Any persistence score computed
on fewer weeks is undefined. The weekly job enforces the immature-truck exclusion;
do not override it manually.

---

## Reference Links

- Column dictionary: `docs/column_dictionary.md`
- Envelope formula source: `STARTER MOTOR/V1.1/src/V1_1_SM_alerts.py` (E3 rule, LOVO)
- V2 config: `v2_system/v2_config.json`
- KPI spec: `v2_system/shadow_quarter/` (kpi_spec.json)
- Economics: `STARTER MOTOR/V2_program/intake/04_economics_windows_intake.md`
- Instrumentation proposal: `docs/2026-06-12-19-45-00-sm-v2-dicv-instrumentation-proposal.md`
- Data requests: `v2_system/specs/data_request_saledate.md`,
                 `v2_system/specs/data_request_maintenance_records.md`
