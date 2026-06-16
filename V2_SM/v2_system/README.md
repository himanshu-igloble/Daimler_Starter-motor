# Starter Motor V2 — Phase-A System (shadow mode)

Built 2026-06-12 from validated V1.1/V2 machinery. Config version `2.0.0-A`. Nothing here is
retuned — every threshold is pre-registered in `v2_config.json` (hash-pinned); refits happen only
via the D8 governance gates (≥5 new failure labels, or PSI > 0.2, or calibration slope outside
[0.5, 2]), always under the full nested + admissibility protocol.

## Run

```
py -3 V2_weekly_job.py            # snapshot at end of available data (k=0)
```

Outputs:
- `out/fleet_snapshot.csv` — one row per truck: walking prob/tier, H1 momentum, H2 dwell state,
  H5 fleet-percentile state, channel states (A2 / persistence-terminal / A1), evidence state,
  priority, silence days/trigger, watchlist + SMA-dead badges. The `label` column is
  SHADOW-EVAL-ONLY (header comment) — never surface to ops.
- `out/shadow_alert_log.csv` — one row per active alert (P0/P1/P2/P0_OPS) with evidence summary
  and the failure-window statement (median lead, CI, n, NOT-a-countdown line).
- stdout — verification gates (5) + priority/tier summaries. All 5 gates must PASS; any
  documented deviation is printed, never silenced.

Per-truck evidence cards and the planner ranking live in `cards/` (see `cards/cards_README.md`),
regenerated with `py -3 cards/generate_cards.py`.

## Semantics that matter

- **H2 dwell: current-state vs ever-fired.** `h2_fires` in the snapshot = the truck is in ≥3
  consecutive RED weeks *now* (the live pager state; 6 failed + VIN5_NF at end-of-data).
  "H2 ever fired" during the historical walk-back (10 failed) lives in
  `../analysis/heuristics/out/heuristic_fires.csv` and appears on cards as evidence. Do not
  conflate them.
- **Walking calibration.** Walking probabilities use the k=0 Platt map (documented
  simplification); tier boundaries are reliable, deep-truncation probabilities less so.
  Known boundary case: VIN4_F_SM at 0.352 vs the 0.35 AMBER threshold — the X2 OOF tier table
  remains validation-of-record (nested AUROC 0.9321).
- **Retrospective silence artifact.** At end-of-data, every truck whose history stops before the
  fleet data wall looks "silent", so failed trucks all carry P0_OPS rows in this shadow snapshot.
  On live weekly data this trigger is the real transmission-health alarm (the VIN8/9_F lesson).
- **Priority precedence** (frozen): A2 → P0 battery-first (14–30 d window, n=4, 0/20 NF history);
  H2 dwell → P0 electrical inspection (2–4 wk); RED → P1 queue ranked by H1 momentum then H5;
  AMBER → P2 bundle ≤90 d; persistence-terminal & A1 are corroborators (never page);
  silence >30 d while AMBER/RED → P0_OPS ≤72 h.

## A real new-data week (not automated in Phase A)

1. Rebuild caches for the new week: `STARTER MOTOR/src/V1_SM_build_weekly_cache.py`,
   `V1_SM_crank_events.py`, then the V1.1 daily cache builder.
2. Re-run channel detectors (`STARTER MOTOR/V1.1/src/V1_1_SM_alerts.py` logic) for A2/persistence/A1
   states.
3. Run `V2_weekly_job.py` — it recomputes walking scores via the heuristics engine when
   `walking_scores.csv` is stale.
Phase-B automation wires these into one scheduled pipeline (roadmap D8-B).

## Pipeline exit-code contract (Phase D hardening)

The weekly pipeline (`V2_weekly_pipeline.py`) uses these exit codes:

| Code | Meaning |
|------|---------|
| 0 | All mandatory stages OK and all 5 verification gates PASS |
| 2 | Verification-gate failure — scoring gates did not pass |
| 3 | Input-incomplete OR config tamper/unregistered edit OR walking_scores stale (>45 d) |
| 4 | Mandatory stage failed after one retry (deterministic failure) |

### New pipeline flags (Phase D)

```
py -3 V2_weekly_pipeline.py [--full] [--skip-dashboard] [--dry-run]
                             [--allow-stale-walking-scores] [--config <path>]
```

- `--dry-run`  Run Stage 0 + input/config validation only; print execution plan;
  write nothing except the structured log under `out/logs/`; exit 0 on success or
  3 on validation failure.
- `--allow-stale-walking-scores`  Bypass the 45-day hard-fail on walking_scores
  file age (demotes to WARN). **Do not use in production without documented sign-off.**
- `--config <path>`  Path to a config JSON other than the default `v2_config.json`.
  Intended for tests and CI that need to inject modified config copies without
  touching the registered file.

Both `V2_weekly_job.py` and `V2_weekly_pipeline.py` accept `--config`.

### Structured logging

Every run writes `out/logs/pipeline_<runts>.jsonl` — one JSON line per stage:
`{stage, status, duration_s, attempt, error_tail}`.  The manifest (`run_manifest.json`)
gains `log_path` and `exit_code` fields.

### Retry policy

Subprocess stages (scoring, monitors, cards, dashboard) are retried once after 5 s
on nonzero exit. If the second attempt fails with the same stderr tail, the failure is
marked `FAILED-DETERMINISTIC` (no further retry). Mandatory stages failing after retry
→ exit 4.

### Input-completeness + config-integrity pre-gate (Stage V)

Runs between Stage 0 and Stage 1. Checks:
- Config hash (sha256 of canonical JSON, keys sorted, `config_hash` field excluded)
  matches stored value; mismatch → exit 3 with `CONFIG TAMPER OR UNREGISTERED EDIT`.
- `walking_scores.csv` has all 34 expected VINs, each with a k=0 row, no NaN prob/tier.
- Alert CSVs (`V1_1_SM_alert_policy.csv`, `V1_1_SM_alert_validation.csv`), data-quality
  (34 rows), and window-matrix CSV all exist and parse.
- `walking_scores.csv` file age: warn > 14 days, fail (exit 3) > 45 days unless
  `--allow-stale-walking-scores` passed.

## Scope guards

- No threshold tuning here, ever. Changes go through the registry + governance gates.
- SM fleet only (`_SM`); alternator artifacts are a different physical fleet.
- Validation-of-record numbers (nested AUROC 0.9321, CI [0.811, 0.986], permutation p=0.005,
  calibration slope 0.86) are frozen in `v2_config.json`; the production fit used for card
  attributions is the standard post-validation refit and is labeled as such wherever shown.
