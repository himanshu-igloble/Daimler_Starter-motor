---
title: "SM V2 — Governance Charter"
status: "complete"
created: "2026-06-12"
program: "Starter Motor V2 — Predictive Maintenance"
version: "1.0.0"
---

# SM V2 Governance Charter

This charter defines roles, pre-registration discipline, refit gates, watchlist
policy, restatement protocol, KPI freeze rules, and the annual audit obligation
for the SM V2 predictive maintenance system.

---

## 1. Roles

| Role | Responsibilities | Placeholder |
|---|---|---|
| **Model Owner** | Maintains v2_config.json and the canonical validation record; authorises refit; owns the restatement note; accountable for G1–G6 gate verdicts | [INSERT NAME / TEAM] |
| **Ops Owner** | Owns alert routing, weekly cadence checklist, feedback SLA, KPI tracker; escalates to fleet manager; files process-miss logs | [INSERT NAME / TEAM] |
| **DICV Liaison** | Interface to DICV fleet operations; receives go-live sign-off; approves data-sharing tier; routes watchlist findings to depot | [INSERT NAME / ORGANISATION] |

Role handover requires a dated handover note countersigned by both the outgoing
and incoming role-holder, with an updated entry in this file.

---

## 2. Pre-Registration Discipline

**Rule: if it isn't in the registry it doesn't exist.**

All model thresholds, heuristic parameters, channel definitions, and alert
precedence rules must be recorded in `v2_config.json` before they are evaluated
on live or shadow data.

- Current canonical config: `v2_system/v2_config.json`
- Current config version: **2.1.0-B**
- Current config hash: `19c2fc9921af0cdb128c08446bfaff28c5b8de16a4a0b1dde2c80c029b433f6f`

The hash is computed over the JSON content with the `config_hash` field removed,
serialised with `json.dumps(cfg, indent=2, sort_keys=True)` and hashed with
SHA-256 (see `refit/REFIT_RUNBOOK.md` Step 3 for the exact command). The hash
anchors the version: any configuration change, however minor, requires:

1. A version bump (increment the minor or patch field in `config_version`)
2. A hash recompute and insertion
3. A dated restatement note explaining what changed and why

**ANY evaluation result cited without the config version and hash is
unverifiable and will not be accepted as evidence for go-live or refit
decisions.**

---

## 3. Refit Gates and Promotion

Refit is triggered by any of three conditions (from `refit/REFIT_RUNBOOK.md`):

| Condition | Threshold | Detection |
|---|---|---|
| New confirmed failure labels | ≥5 new failures in `labels/label_registry.csv` | `ingest_feedback.py --status` |
| Calibration drift | Slope outside [0.5, 2.0] | G3 gate in weekly monitor output |
| Population shift (PSI) | PSI > 0.2 on any model feature | `monitors/governance_monitors.py` |

Refit is NOT triggered by trucks accumulating more weeks of history, by
threshold adjustments to H1/H2/H5 (those are config, not model), or by watchlist
additions.

**NEVER AUTO-DEPLOY.** The refit harness (`refit/run_refit.py`) always concludes
with a manual-review banner. The model owner must review `refit/out/refit_<ts>/
comparison_report.md` and tick all seven checklist items before touching
`v2_config.json`. The full checklist is in `refit/REFIT_RUNBOOK.md` Section 3.

Promotion sequence:
1. Write dated restatement note in `docs/`
2. Edit `v2_config.json` (model + validation fields)
3. Recompute and insert hash
4. Commit and tag (`git tag v2.<N>-sm-refit-<date>`)

Rollback: restore prior `v2_config.json` from git, publish a rollback note,
re-run pipeline. Refit artifacts in `refit/out/` are never deleted.

---

## 4. Watchlist Policy

The four pre-registered watchlist trucks are:
`VIN2_NF_SM`, `VIN5_NF_SM`, `VIN8_NF_SM`, `VIN15_NF_SM`
(source: `v2_config.json` → `watchlist.vins`)

These are non-failed trucks that showed anomalous signals at the time of V2
development. They serve as **prospective evidence**: the system has committed in
advance to monitoring them with elevated cadence, and every outcome must be
recorded, regardless of direction.

**Policy:**
- Every watchlist truck receives a per-truck evidence card (in `cards/`).
- Any tier change (GREEN → AMBER, AMBER → RED) for a watchlist truck triggers
  an expedited weekly review (do not wait for the next scheduled weekly cadence).
- If a watchlist truck fails: record outcome in `labels/label_registry.csv` as
  SAVE (if alert preceded failure) or MISS (if no alert).
- If a watchlist truck is proactively inspected and found clean: record as
  "no_fault_found" finding — this ALSO satisfies K3 for the shadow quarter.
- Watchlist additions after the shadow quarter starts require D8 sign-off and
  a dated protocol deviation note (same rule as KPI threshold changes).

The watchlist is prospective evidence, not a prediction. Calling a watchlist
truck a "likely failure" on the basis of inclusion alone is not supported by the
protocol. The trucks are monitored because their signals were elevated; the
outcome decides what the signal meant.

---

## 5. Restatement Policy

The canonical precedent is the V1 → V1.1 restatement (2026-06-12):

| Item | V1 | V1.1 |
|---|---|---|
| Nested AUROC | 0.8929 | 0.9321 |
| Optimism delta | +0.0428 (non-nested minus nested) | +0.0036 |
| Key change | vsi_dominant_freq in winner (leaked observation length) | Feature removed; clean 4-feature pool |
| Disclosure | Disclosed in restatement note + V1.1 audit trail | Baselines re-pinned to V1.1 |

Lessons encoded as standing rules:
1. An AUROC *increase* after removing a feature is a diagnostic signal of
   removed leakage, not overfitting. Verify G1 (L40 control) first.
2. Optimism disclosures are mandatory. V1.1 restated V1's non-nested number
   (0.8929) as the baseline, not the inflated estimate.
3. Baselines are re-pinned at each restatement. Comparisons to pre-restatement
   numbers must be explicitly labelled as cross-version.

Any future refit that shows performance worse than V1.1 baseline (nested AUROC
0.9321 or lower) requires root-cause analysis before the result is presented
externally. Degraded performance on new labels is informative signal, not noise.

---

## 6. KPI Freeze Rule

The shadow-quarter KPI thresholds are defined in
`shadow_quarter/kpi_spec.md` and are **frozen as of 2026-06-12**, before
Week 1 data is observed.

- K1 threshold (≤0.30 shop-grade alerts/truck-year): frozen
- K2 slope range ([0.5, 2.0]): frozen
- K3 resolution criterion (≥1 watchlist truck labelled by Week 13): frozen
- K4 violation definition (zero GREEN-tier failures outside blind-spot class): frozen

**One documented re-registration is permitted** after the first quarter, only
if the roadmap risk note (`intake/04_economics_windows_intake.md` or analogous)
explicitly identified the threshold as provisional. Any re-registration must:
1. Be dated and appended to `kpi_spec.md` as a protocol deviation note
2. Be signed by the model owner and ops owner
3. State the reason the original threshold was unachievable and why the new
   threshold is still meaningful

No retroactive threshold change after Week 13 data is observed, ever. A breach
is a breach. The appropriate response to a breach is a root-cause analysis and
a planned remediation, not a threshold re-definition.

---

## 7. Annual Full-Audit Rule

Once per calendar year (month 12 or at go-live + 12 months, whichever comes
first), the model owner must conduct a full audit covering:

1. **Config integrity check:** recompute the hash from current `v2_config.json`
   and confirm it matches `config_hash`.
2. **Label registry review:** confirm all WOs issued in the year have
   corresponding registry entries (no PENDING records older than 90 days).
3. **KPI re-evaluation:** re-run the shadow quarter KPI calculations on the
   full year of live data and publish a KPI year-end report.
4. **Banned-feature audit (G6):** confirm no banned feature token appears in
   the current model subset (see `v2_config.json → banned_feature_classes`).
5. **Watchlist resolution:** document the outcome of all four watchlist VINs
   (failed, inspected-clean, still active, or decommissioned).
6. **Blind-spot class review:** confirm the documented blind-spot classes still
   represent all undetectable truck types. If new SMA-dead trucks have been
   added without ops follow-up, flag for remediation.

The audit report is published as a dated `.md` file in `docs/` and linked in
the registry.

---

*End of Governance Charter. For refit procedures see refit/REFIT_RUNBOOK.md.
For KPI definitions see shadow_quarter/kpi_spec.md. For config hash
computation see refit/REFIT_RUNBOOK.md Step 3.*
