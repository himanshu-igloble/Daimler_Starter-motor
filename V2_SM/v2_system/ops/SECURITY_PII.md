---
title: "SM V2 — Security and PII Classification"
status: "complete"
created: "2026-06-12"
owner: "Ops Owner / DICV Liaison"
version: "1.0.0"
---

# SM V2 Security and PII Classification

---

## 1. VIN Naming Map Inspection Finding

**File inspected:** `STARTER MOTOR/V1.1/results/V1_1_SM_vin_naming_map.csv`

**What it actually contains:**

The file has four columns: `old_label`, `new_label`, `cohort`, `raw_file_vin`.
It is a **label-renaming map used during the V1 → V1.1 refactoring**. The
`raw_file_vin` column contains the VIN tokens that appeared in the raw CSV data
files (values: VIN1 through VIN20). The `old_label` and `new_label` columns
contain the project's anonymised display labels (e.g., `VIN1_F_SM`,
`VIN15_NF_SM`). The `cohort` column is `failed` or `non_failed`.

**Finding: the file does NOT contain real chassis numbers, licence plates, or
any other personally identifying vehicle identifiers.** The `raw_file_vin`
values (VIN1–VIN20) are themselves sequential anonymisation tokens assigned
during the original DICV data extraction — they are not the 17-character ISO
3779 VIN codes used by the manufacturer or registry. The mapping is VIN1 →
VIN1_F_SM (failed), VIN1 → VIN15_NF_SM (non-failed), etc.

**Important nuance:** The failed and non-failed cohorts were extracted
separately, so the same `raw_file_vin` token (e.g., VIN1) appears once in the
failed cohort and once in the non-failed cohort, mapping to entirely different
physical trucks. This is a direct consequence of the VIN Independence Rule:
VIN labels reuse sequential numbering across cohorts and refer to different
vehicles.

**Classification: INTERNAL-ONLY** — not because it contains real identifiers,
but because any re-linkage attempt using the mapping sequence could theoretically
reduce anonymisation strength if combined with external fleet records. Treat as
internal operational data.

---

## 2. Data Classification Table

| Artifact | Location | Contains real identifiers? | Sharing class |
|---|---|---|---|
| Raw parquets (failed/NF telemetry) | `Data/*.parquet` | No (VIN tokens are anonymised) | **Internal-only** |
| Cache weekly parquets | `STARTER MOTOR/cache/` | No (VIN tokens) | **Internal-only** |
| Feature matrices | `V1.1/results/V1_1_SM_feature_matrix.csv`, `refit/out/*/feature_matrix.csv` | No (VIN tokens) | **Internal-only** |
| Fleet snapshots | `v2_system/out/fleet_snapshot.csv` | No — BUT contains `label` column (ground-truth failure flag) | **Internal-only; SHADOW-EVAL-ONLY for `label` column** |
| Shadow alert log | `v2_system/out/shadow_alert_log.csv` | No (VIN tokens) | **Internal-only** |
| Evidence cards | `v2_system/cards/card_*.md`, `cards.json` | No (VIN tokens + risk scores) | **DICV-shareable** (ops-safe; no ground-truth labels exposed) |
| Dashboard | `v2_system/dashboard/sm_v2_dashboard.html` | No (VIN tokens) | **DICV-shareable** (see Section 3) |
| Work orders | `v2_system/workorders/out/WO_*.md` | No (VIN tokens) | **Ops-floor** (maintenance team only; contain risk evidence and inspection protocols) |
| Label registry | `v2_system/labels/label_registry.csv` | No (VIN tokens) — but contains confirmed failure outcomes | **Internal-only; model-owner access only** |
| VIN naming map | `V1.1/results/V1_1_SM_vin_naming_map.csv` | No (VIN tokens, not ISO VINs) | **Internal-only** |
| Governance status | `v2_system/monitors/out/governance_status.json` | No | **Internal-only** |
| Config | `v2_system/v2_config.json` | No | **DICV-shareable** (describes system, no truck-level data) |

**Sharing class definitions:**
- **Internal-only**: accessible only to the ML team and named ops contacts; not to be emailed externally or placed on shared drives without encryption.
- **DICV-shareable**: may be shared with the DICV fleet operations team under the project data agreement.
- **Ops-floor**: accessible to the maintenance team for inspection; should not be forwarded to parties outside the fleet operations chain.

---

## 3. The `label` Column: SHADOW-EVAL-ONLY Rule

The `label` column in `fleet_snapshot.csv` (values 0/1) is the **ground-truth
failure label** used for shadow-quarter KPI evaluation. It is drawn from the
retrospective training data and represents confirmed historical outcomes.

**Rule:** the `label` column is SHADOW-EVAL-ONLY and must NEVER be surfaced to
ops or maintenance teams. Specifically:

- It must not appear in any work order, dashboard view, or pager notification.
- It must not be used as an input to alert routing decisions (alert routing uses
  only `tier`, `priority`, `trigger`, and the channel-fire flags).
- Scripts that consume `fleet_snapshot.csv` for ops purposes must explicitly
  drop or ignore the `label` column.

**Where it is enforced:** The `fleet_snapshot.csv` file carries a header
comment (`# SHADOW-EVAL-ONLY: 'label' column is ground-truth for evaluation
only — do NOT surface to ops`). The `kpi_tracker.py` and `simulate_quarter.py`
scripts are the only authorised consumers of the `label` column. Any new script
that reads `fleet_snapshot.csv` must be reviewed to confirm it does not pass
`label` to any output that ops staff can see.

---

## 4. Dashboard External-URL Verification

**Claim:** `v2_system/dashboard/sm_v2_dashboard.html` contains zero external
HTTP/HTTPS URLs and is fully self-contained.

**How verified:** The file was parsed programmatically for all `https?://`
matches using Python's `re.findall` on the full file content. Result: **0
external URLs found.** The dashboard does not load any CDN resources, external
fonts, analytics scripts, or remote images. All visualisation assets are inline.

This means the dashboard can be shared with DICV or viewed on an air-gapped
network without any outbound network requests.

---

## 5. Retention and Access Recommendations

**Raw parquets and caches:** Retain for the duration of the project plus 24
months for audit purposes. Access: ML team only. Store on the project drive;
do not copy to personal machines or cloud storage without encryption.

**Feature matrices and label registry:** Same retention as raw data. The label
registry is particularly sensitive because it encodes confirmed failure outcomes
that could be re-linked to operational events. Model owner access only; rotate
access if the model owner role changes.

**Evidence cards and dashboard:** Retain for the active monitoring period plus
12 months. These are the only artifacts rated DICV-shareable; they do not
contain failure confirmation.

**Work orders:** Retain for 5 years (standard maintenance record retention for
commercial vehicle fleets). Ops-floor access. Do not include in any public
documentation or research publication without anonymisation review.

**VIN naming map:** Retain until the project concludes. Internal-only. In the
event of a security incident, this file should be treated as a potential
de-anonymisation risk if the counterparty also possesses DICV fleet records.

**Access control:** The `v2_system/` directory and its subdirectories should
have OS-level access control restricting write access to the model owner.
Read access to `workorders/out/` and `cards/` may be extended to the maintenance
team lead and DICV liaison.

---

*End of Security and PII Classification. For audit questions contact the model
owner (see GOVERNANCE_CHARTER.md).*
