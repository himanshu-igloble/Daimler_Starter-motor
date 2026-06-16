---
title: "C4 External Data Request — SALEDATE / In-Service Date"
status: "complete"
created: "2026-06-12"
program: "V2 Starter Motor"
author: "Technical Product Lead"
---

# C4 Data Request: SALEDATE and In-Service Date for SM Fleet

## Request Summary

Request to DICV Data Team: provide the sale date and in-service date for all 34
starter-motor telematics-fleet trucks (14 failed, 20 non-failed), joined to the
anonymized VIN labels already held by the analytics team.

**All PII / VIN de-anonymization is handled entirely on the DICV side.** The analytics
team holds only anonymized labels (VIN1_SM through VIN34_SM style). DICV provides a
mapping table keyed to the internal DICV VIN; the analytics team performs the join on its
own systems and immediately discards the raw mapping.

---

## Why This Is Needed

**NF fleet age-axis bias (§7.1 of D01 technical audit):**

For the 20 non-failed (NF) trucks, the current model sets `t_start = extraction-window
start` (the earliest date in the telematics parquet file for that VIN). This is not the
truck's true in-service date — it is the first date telematics data was captured, which
can be weeks to months after the vehicle left the factory.

Consequence: NF truck age is systematically understated. Features that embed time-since-
start (e.g., t_start-based Weibull position, fleet-clock reference) treat NF trucks as
younger than they are, biasing the fleet survival curve and the relative age comparison
between failed and non-failed trucks.

**Specific corrections enabled by SALEDATE:**

1. Corrected `t_start` for all NF trucks → corrected truck-week table with true week-of-
   life numbering (instead of week-of-observation numbering).
2. Fleet Weibull re-fit on correct age axis → more honest survival probability estimates.
3. Correct age-stratified feature baselines (features normalized by true truck age, not
   observed window length).
4. No model retrain required — the V1.1 model features are engineered at weekly-cache
   level and are age-free at that granularity. Only the age-axis reference table changes.

---

## Requested Fields

**Delivery format:** UTF-8 CSV, one row per truck.

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `dicv_internal_vin` | string | DICV's internal VIN or chassis number (used for join only; discarded after join) | CHA12345678 |
| `anon_label` | string | Anonymized label used in analytics (DICV-side mapping) | VIN7_SM |
| `saledate` | ISO 8601 date string YYYY-MM-DD | Date vehicle was sold to fleet operator | 2023-04-15 |
| `inservice_date` | ISO 8601 date string YYYY-MM-DD | Date vehicle entered active service (if different from saledate; else repeat saledate) | 2023-04-22 |
| `gvw_config` | string | GVW configuration (e.g., "5528T 6x4") | 5528T 6x4 |
| `spec_notes` | string (optional) | Any non-standard spec flags (e.g., "dual-battery upgrade", "generator-set duty") | standard |

**Minimum viable delivery:** `anon_label`, `saledate`. The remaining fields are
desirable for feature-engineering quality but are not blockers.

---

## What Changes When This Data Arrives

1. **Corrected truck-week table** (`V1_SM_weekly_corrected.parquet`): `week_of_life`
   column recalculated from true `inservice_date` instead of `first_obs_date`.
2. **Fleet-clock re-fit**: fleet survival reference re-estimated on correct age axis.
3. **Weibull bias check**: compare current vs. corrected failure-age distribution to
   quantify the bias magnitude.
4. **No model refit**: the V1.1 Ridge classifier features (VSI stats, SMA stats, crank
   features) are computed within rolling windows and are not sensitive to the absolute
   age reference. The alert calibration thresholds are unchanged.
5. **Documentation update**: a version note records the correction and the before/after
   comparison as an audit trail.

---

## Handling and Retention

- The raw mapping table (`dicv_internal_vin` → `anon_label`) is used for a single join
  and immediately deleted from the analytics environment.
- Only the corrected date fields keyed to `anon_label` are retained.
- No individual driver or operator data is requested or retained.

---

*See also: `data_request_maintenance_records.md` for the complementary maintenance
records request. Both requests can be fulfilled in a single data exchange.*
