"""
V2_weekly_pipeline.py — SM V2 Staged Weekly Pipeline Orchestrator
==================================================================
Usage:
    py -3 V2_weekly_pipeline.py [--full] [--skip-dashboard] [--dry-run]
                                [--allow-stale-walking-scores] [--config <path>]

    --full             Print the exact upstream data-rebuild commands that
                       WOULD run (does NOT execute them; data is retrospective).
    --skip-dashboard   Skip Stage 5 even if dashboard/build_dashboard.py exists.
    --dry-run          Run Stage 0 + validation stage only; print execution plan;
                       write nothing except the log; exit 0/3.
    --allow-stale-walking-scores
                       Bypass the 45-day walking_scores staleness hard-fail.
    --config <path>    Path to config JSON (default: v2_config.json next to this file).
                       Used by tests to inject modified config copies.

Stages:
    0  Data freshness check
    V  Input-completeness + config-integrity validation (new production gate)
    1  Walking-scores freshness + staleness policy
    2  Scoring (V2_weekly_job.py)
    3  Monitors (monitors/run_monitors.py, if present)
    4  Cards (cards/generate_cards.py)
    5  Dashboard (dashboard/build_dashboard.py, if present)
    6  Manifest write (out/run_manifest.json + out/run_history.csv)

Exit codes:
    0  — mandatory stages all succeeded AND gates passed
    2  — verification-gate failure (scoring gates did not pass)
    3  — input-incomplete OR config tamper OR walking_scores stale
    4  — mandatory stage failed after retry (deterministic failure)

    (Legacy code 1 is preserved for scoring-job gate failure for compatibility;
     clean new failures use 2/3/4 as above.)
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent
SM_ROOT = HERE.parent.parent          # .../STARTER MOTOR

DATA_QUALITY    = SM_ROOT / "results" / "V1_SM_data_quality.csv"
WALKING_SCORES  = SM_ROOT / "V2_program" / "analysis" / "heuristics" / "out" / "walking_scores.csv"
WEEKLY_JOB      = HERE / "V2_weekly_job.py"
MONITORS_SCRIPT = HERE / "monitors" / "run_monitors.py"
CARDS_SCRIPT    = HERE / "cards" / "generate_cards.py"
DASHBOARD_SCRIPT= HERE / "dashboard" / "build_dashboard.py"
REGISTRY_SCRIPT = HERE / "registry" / "build_registry.py"

OUT_DIR         = HERE / "out"
OUT_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR        = OUT_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

MANIFEST_PATH   = OUT_DIR / "run_manifest.json"
HISTORY_PATH    = OUT_DIR / "run_history.csv"
SNAPSHOT_PATH   = OUT_DIR / "fleet_snapshot.csv"
ALERT_LOG_PATH  = OUT_DIR / "shadow_alert_log.csv"

PYTHON_EXE = "py"   # use `py -3` convention

# Alert CSVs consumed by the scoring job — checked in validate_inputs()
ALERT_POLICY     = SM_ROOT / "V1.1" / "results" / "V1_1_SM_alert_policy.csv"
ALERT_VALIDATION = SM_ROOT / "V1.1" / "results" / "V1_1_SM_alert_validation.csv"
WINDOW_MATRIX    = SM_ROOT / "V2_program" / "analysis" / "econ" / "failure_window_matrix.csv"

# Expected fleet
EXPECTED_N_VINS = 34

# Staleness thresholds
STALE_WARN_DAYS = 14
STALE_FAIL_DAYS = 45

# Retry policy for subprocess stages
RETRY_DELAY_S = 5
MAX_ATTEMPTS  = 2


# ── Config loading (deferred; re-loaded after --config arg is parsed) ─────────
def _load_config(config_path: Path) -> tuple[dict, str, str]:
    """Load config JSON; return (cfg_dict, config_version, config_hash_stored)."""
    with open(config_path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    return cfg, cfg.get("config_version", "unknown"), cfg.get("config_hash", "")


def _config_hash_computed(cfg: dict) -> str:
    """Recompute the config hash (sha256 of canonicalized JSON without hash field)."""
    cfg_copy = {k: v for k, v in cfg.items() if k != "config_hash"}
    canonical = json.dumps(cfg_copy, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ── Stage result container ────────────────────────────────────────────────────
class StageResult:
    def __init__(self, name: str, status: str, duration_s: float,
                 detail: str = "", output: str = "", attempt: int = 1,
                 error_tail: str | None = None):
        self.name = name
        self.status = status   # "OK" | "SKIP" | "WARN" | "FAIL"
        self.duration_s = duration_s
        self.detail = detail
        self.output = output
        self.attempt = attempt
        self.error_tail = error_tail

    def is_ok(self) -> bool:
        return self.status in ("OK", "SKIP")

    def to_log_dict(self) -> dict:
        return {
            "stage": self.name,
            "status": self.status,
            "duration_s": round(self.duration_s, 3),
            "attempt": self.attempt,
            "error_tail": self.error_tail,
        }


def run_subprocess(cmd: list[str], label: str, cwd: Path | None = None,
                   timeout: int = 300) -> tuple[int, str]:
    """Run a subprocess; return (returncode, combined_stdout+stderr)."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            cwd=str(cwd) if cwd else None,
        )
        out = result.stdout + result.stderr
        return result.returncode, out
    except subprocess.TimeoutExpired:
        return -1, f"[{label}] TIMEOUT after {timeout}s"
    except Exception as exc:
        return -1, f"[{label}] Exception: {exc}"


def run_subprocess_with_retry(
    cmd: list[str], label: str, cwd: Path | None = None, timeout: int = 300
) -> tuple[int, str, int, str | None]:
    """
    Run subprocess with ONE retry after RETRY_DELAY_S seconds on nonzero exit.
    Returns (returncode, output, n_attempts, error_tail_if_failed).
    On second consecutive failure with identical stderr tail: marks FAILED-DETERMINISTIC.
    """
    rc1, out1 = run_subprocess(cmd, label, cwd, timeout)
    if rc1 == 0:
        return rc1, out1, 1, None

    tail1 = out1[-300:].strip()
    time.sleep(RETRY_DELAY_S)
    rc2, out2 = run_subprocess(cmd, label, cwd, timeout)
    if rc2 == 0:
        return rc2, out2, 2, None

    tail2 = out2[-300:].strip()
    deterministic = (tail1 == tail2)
    tag = "[FAILED-DETERMINISTIC]" if deterministic else "[FAILED-VARIABLE]"
    combined = f"Attempt1 rc={rc1}  Attempt2 rc={rc2}  {tag}\n{out2}"
    return rc2, combined, 2, tail2


# ── Input-completeness + config-integrity validation ──────────────────────────
def validate_inputs(cfg: dict, config_path: Path, config_hash_stored: str,
                    allow_stale: bool = False) -> tuple[bool, str]:
    """
    Validate all pipeline inputs and config integrity.
    Returns (ok: bool, message: str).
    On failure, message names exactly which check failed.
    """
    import pandas as pd

    # 1. Config integrity: recompute hash and compare
    computed = _config_hash_computed(cfg)
    if computed != config_hash_stored:
        return False, (
            f"CONFIG TAMPER OR UNREGISTERED EDIT — "
            f"expected hash: {config_hash_stored}  found hash: {computed}"
        )

    # 2. walking_scores existence and parse
    if not WALKING_SCORES.exists():
        return False, f"INPUT-MISSING: walking_scores.csv not found at {WALKING_SCORES}"
    try:
        ws = pd.read_csv(WALKING_SCORES)
    except Exception as exc:
        return False, f"INPUT-PARSE-FAIL: walking_scores.csv could not be read: {exc}"

    # 3. walking_scores: all 34 expected VINs present
    expected_vins = set(cfg["fleet"]["failed_vins"] + cfg["fleet"]["nonfailed_vins"])
    found_vins = set(ws["vin_label"].unique())
    missing_vins = sorted(expected_vins - found_vins)
    if missing_vins:
        return False, (
            f"INPUT-INCOMPLETE: walking_scores missing VINs: {missing_vins}"
        )

    # 4. walking_scores: each VIN has a k=0 row
    k0 = ws[ws["k_weeks"] == 0]
    vins_with_k0 = set(k0["vin_label"].unique())
    missing_k0 = sorted(expected_vins - vins_with_k0)
    if missing_k0:
        return False, (
            f"INPUT-INCOMPLETE: walking_scores missing k=0 row for VINs: {missing_k0}"
        )

    # 5. walking_scores: no NaN prob at k=0
    k0_nan_prob = k0[k0["prob"].isna()]
    if len(k0_nan_prob) > 0:
        bad_vins = sorted(k0_nan_prob["vin_label"].tolist())
        return False, (
            f"INPUT-INCOMPLETE: walking_scores k=0 rows have NaN prob for VINs: {bad_vins}"
        )

    # 6. walking_scores: no NaN tier at k=0
    k0_nan_tier = k0[k0["tier"].isna()]
    if len(k0_nan_tier) > 0:
        bad_vins = sorted(k0_nan_tier["vin_label"].tolist())
        return False, (
            f"INPUT-INCOMPLETE: walking_scores k=0 rows have NaN tier for VINs: {bad_vins}"
        )

    # 7. Alert CSVs: existence and parse
    for path_obj in (ALERT_POLICY, ALERT_VALIDATION):
        if not path_obj.exists():
            return False, f"INPUT-MISSING: {path_obj.name} not found at {path_obj}"
        try:
            pd.read_csv(path_obj)
        except Exception as exc:
            return False, f"INPUT-PARSE-FAIL: {path_obj.name} could not be read: {exc}"

    # 8. Window matrix CSV
    if not WINDOW_MATRIX.exists():
        return False, f"INPUT-MISSING: failure_window_matrix.csv not found at {WINDOW_MATRIX}"
    try:
        pd.read_csv(WINDOW_MATRIX)
    except Exception as exc:
        return False, f"INPUT-PARSE-FAIL: failure_window_matrix.csv could not be read: {exc}"

    # 9. Data quality CSV existence and 34 rows
    if not DATA_QUALITY.exists():
        return False, f"INPUT-MISSING: V1_SM_data_quality.csv not found at {DATA_QUALITY}"
    try:
        dq = pd.read_csv(DATA_QUALITY)
    except Exception as exc:
        return False, f"INPUT-PARSE-FAIL: V1_SM_data_quality.csv could not be read: {exc}"
    if len(dq) != EXPECTED_N_VINS:
        return False, (
            f"INPUT-INCOMPLETE: V1_SM_data_quality.csv has {len(dq)} rows "
            f"(expected {EXPECTED_N_VINS})"
        )

    return True, "All input checks passed"


def check_walking_scores_staleness(allow_stale: bool) -> tuple[str, str]:
    """
    Check walking_scores file age.
    Returns (status: 'OK'|'WARN'|'FAIL', message: str).
    """
    if not WALKING_SCORES.exists():
        return "FAIL", "walking_scores.csv not found (checked in staleness check)"
    age_days = (time.time() - WALKING_SCORES.stat().st_mtime) / 86400
    if age_days > STALE_FAIL_DAYS:
        if allow_stale:
            return "WARN", (
                f"walking_scores is {age_days:.1f} days old (>{STALE_FAIL_DAYS}d); "
                "hard-fail bypassed by --allow-stale-walking-scores"
            )
        return "FAIL", (
            f"STALE: walking_scores.csv is {age_days:.1f} days old "
            f"(>{STALE_FAIL_DAYS}d hard limit); "
            "regenerate or pass --allow-stale-walking-scores"
        )
    if age_days > STALE_WARN_DAYS:
        return "WARN", (
            f"walking_scores.csv is {age_days:.1f} days old (>{STALE_WARN_DAYS}d) — "
            "consider refreshing"
        )
    return "OK", f"walking_scores.csv age {age_days:.1f} days — within freshness window"


# ── Stage implementations ─────────────────────────────────────────────────────

def stage0_data_freshness(full: bool) -> StageResult:
    """Stage 0: Check data freshness via fleet max date in data quality CSV."""
    t0 = time.monotonic()
    name = "Stage 0 — Data freshness"
    try:
        import pandas as pd

        if not DATA_QUALITY.exists():
            return StageResult(name, "FAIL", time.monotonic() - t0,
                               f"Data quality CSV not found: {DATA_QUALITY}",
                               error_tail=f"Data quality CSV not found: {DATA_QUALITY}")

        dq = pd.read_csv(DATA_QUALITY)
        dq["t_end"] = pd.to_datetime(dq["t_end"])
        fleet_max = dq["t_end"].max()
        fleet_max_str = fleet_max.strftime("%Y-%m-%d")

        # Compare to last run manifest if available
        last_run_fleet_date = None
        if MANIFEST_PATH.exists():
            with open(MANIFEST_PATH, encoding="utf-8") as fh:
                last_manifest = json.load(fh)
            last_run_fleet_date = last_manifest.get("fleet_max_date")

        if last_run_fleet_date and last_run_fleet_date == fleet_max_str:
            fresh_msg = (f"No new data since last run ({fleet_max_str}); "
                         "cache rebuild skipped.")
        else:
            fresh_msg = (f"Fleet data wall: {fleet_max_str}. "
                         "This is a retrospective environment — no new data; "
                         "cache rebuild skipped.")

        detail = fresh_msg
        if full:
            detail += (
                "\n\n  --- UPSTREAM COMMANDS (would run in live environment) ---"
                "\n  [CACHE-REBUILD] py -3 \"STARTER MOTOR/src/V1_SM_build_weekly_cache.py\""
                "\n  [CRANK-EVENTS]  py -3 \"STARTER MOTOR/src/V1_SM_crank_events.py\""
                "\n  [DAILY-CACHE]   py -3 \"STARTER MOTOR/V1.1/src/V1_1_SM_daily_cache_builder.py\""
                "\n  [ALERTS]        py -3 \"STARTER MOTOR/V1.1/src/V1_1_SM_alerts.py\""
                "\n  NOTE: These scan ~107M rows. Do NOT run in retrospective mode."
                "\n  --- END UPSTREAM COMMANDS ---"
            )

        return StageResult(name, "OK", time.monotonic() - t0, detail)

    except Exception as exc:
        return StageResult(name, "FAIL", time.monotonic() - t0, str(exc),
                           error_tail=str(exc))


def stage_V_validate(cfg: dict, config_path: Path, config_hash_stored: str,
                     allow_stale: bool) -> StageResult:
    """
    Stage V — Input-completeness + config-integrity pre-gate.
    Must pass before scoring is attempted.
    """
    t0 = time.monotonic()
    name = "Stage V — Input & config validation"

    ok, msg = validate_inputs(cfg, config_path, config_hash_stored, allow_stale)
    if not ok:
        return StageResult(name, "FAIL", time.monotonic() - t0, msg, error_tail=msg)

    # Staleness sub-check
    stale_status, stale_msg = check_walking_scores_staleness(allow_stale)
    if stale_status == "FAIL":
        return StageResult(name, "FAIL", time.monotonic() - t0, stale_msg,
                           error_tail=stale_msg)
    if stale_status == "WARN":
        return StageResult(name, "OK", time.monotonic() - t0,
                           f"{msg} | STALENESS-WARN: {stale_msg}")

    return StageResult(name, "OK", time.monotonic() - t0, msg)


def stage1_walking_scores(allow_stale: bool) -> StageResult:
    """Stage 1: Verify walking_scores.csv exists, report age."""
    t0 = time.monotonic()
    name = "Stage 1 — Walking-scores freshness"
    try:
        if not WALKING_SCORES.exists():
            return StageResult(
                name, "FAIL", time.monotonic() - t0,
                f"walking_scores.csv NOT FOUND at {WALKING_SCORES}. "
                "Regenerate by running the walking-score engine "
                "(STARTER MOTOR/V2_program/analysis/heuristics/).",
                error_tail="walking_scores.csv NOT FOUND",
            )

        mtime = WALKING_SCORES.stat().st_mtime
        age_days = (time.time() - mtime) / 86400
        age_str = f"{age_days:.1f} days" if age_days >= 1 else f"{age_days*24:.1f} hours"

        import pandas as pd
        ws = pd.read_csv(WALKING_SCORES)
        n_vins = ws["vin_label"].nunique()
        n_rows = len(ws)

        detail = (
            f"walking_scores.csv found — age: {age_str}, "
            f"{n_vins} VINs, {n_rows} rows."
        )

        # Staleness warning surfaced here too (hard-fail already caught in stage_V)
        stale_status, stale_msg = check_walking_scores_staleness(allow_stale)
        if stale_status == "WARN":
            detail += f"  [{stale_msg}]"
            return StageResult(name, "OK", time.monotonic() - t0, detail)

        return StageResult(name, "OK", time.monotonic() - t0, detail)

    except Exception as exc:
        return StageResult(name, "FAIL", time.monotonic() - t0, str(exc),
                           error_tail=str(exc))


def stage2_scoring(config_path: Path) -> tuple[StageResult, dict]:
    """Stage 2: Run V2_weekly_job.py, parse gate results. Retries once on failure."""
    t0 = time.monotonic()
    name = "Stage 2 — Scoring (V2_weekly_job.py)"
    gates: dict = {}
    try:
        cmd = [PYTHON_EXE, "-3", str(WEEKLY_JOB), "--config", str(config_path)]
        rc, out, attempts, err_tail = run_subprocess_with_retry(
            cmd, label="V2_weekly_job", cwd=HERE, timeout=120
        )

        # Parse gate lines from stdout
        overall_match = re.search(r"Overall:\s+(ALL GATES PASS|GATE FAILURE.*)", out)
        overall = overall_match.group(1).strip() if overall_match else "UNKNOWN"

        gate_pattern = re.compile(r"Gate (\d+)[^\n]*=>\s*(PASS|FAIL)")
        for m in gate_pattern.finditer(out):
            gates[f"gate{m.group(1)}"] = m.group(2)

        if rc != 0 or overall != "ALL GATES PASS":
            return (StageResult(name, "FAIL", time.monotonic() - t0,
                                f"rc={rc}, overall='{overall}', attempts={attempts}",
                                out[:2000], attempt=attempts, error_tail=err_tail),
                    gates)

        return (StageResult(name, "OK", time.monotonic() - t0,
                            f"rc=0, {overall}", out[:500], attempt=attempts),
                gates)

    except Exception as exc:
        return (StageResult(name, "FAIL", time.monotonic() - t0, str(exc),
                            error_tail=str(exc)), gates)


def stage3_monitors() -> StageResult:
    """Stage 3: Run monitors/run_monitors.py if present, else SKIP. Retries once."""
    t0 = time.monotonic()
    name = "Stage 3 — Monitors"
    if not MONITORS_SCRIPT.exists():
        return StageResult(name, "SKIP", time.monotonic() - t0,
                           "monitors pending (Phase-B parallel build) — SKIP")
    try:
        rc, out, attempts, err_tail = run_subprocess_with_retry(
            [PYTHON_EXE, "-3", str(MONITORS_SCRIPT)],
            label="run_monitors", cwd=HERE / "monitors", timeout=180
        )
        if rc == 0:
            return StageResult(name, "OK", time.monotonic() - t0,
                               "monitors completed", out[:500], attempt=attempts)
        return StageResult(name, "FAIL", time.monotonic() - t0,
                           f"monitors exit rc={rc} after {attempts} attempt(s)",
                           out[:1000], attempt=attempts, error_tail=err_tail)
    except Exception as exc:
        return StageResult(name, "FAIL", time.monotonic() - t0, str(exc),
                           error_tail=str(exc))


def stage4_cards() -> StageResult:
    """Stage 4: Run cards/generate_cards.py; tolerate failure with warning. Retries once."""
    t0 = time.monotonic()
    name = "Stage 4 — Cards (generate_cards.py)"
    try:
        rc, out, attempts, err_tail = run_subprocess_with_retry(
            [PYTHON_EXE, "-3", str(CARDS_SCRIPT)],
            label="generate_cards", cwd=HERE / "cards", timeout=180
        )
        if rc == 0:
            gen_match = re.search(r"GENERATION COMPLETE.*", out)
            detail = gen_match.group(0)[:100] if gen_match else "completed"
            return StageResult(name, "OK", time.monotonic() - t0, detail,
                               attempt=attempts)
        # Warn but do not fail pipeline — cards are presentation layer
        return StageResult(name, "WARN", time.monotonic() - t0,
                           f"cards generation exited rc={rc} after {attempts} attempt(s) "
                           "(non-mandatory — continuing)",
                           out[-500:], attempt=attempts, error_tail=err_tail)
    except Exception as exc:
        return StageResult(name, "WARN", time.monotonic() - t0,
                           f"cards exception (non-mandatory): {exc}")


def stage5_dashboard(skip: bool) -> StageResult:
    """Stage 5: Run dashboard/build_dashboard.py if present. Retries once."""
    t0 = time.monotonic()
    name = "Stage 5 — Dashboard"
    if skip:
        return StageResult(name, "SKIP", time.monotonic() - t0,
                           "--skip-dashboard flag set")
    if not DASHBOARD_SCRIPT.exists():
        return StageResult(name, "SKIP", time.monotonic() - t0,
                           "dashboard pending (Phase-B parallel build) — SKIP")
    try:
        rc, out, attempts, err_tail = run_subprocess_with_retry(
            [PYTHON_EXE, "-3", str(DASHBOARD_SCRIPT)],
            label="build_dashboard", cwd=HERE / "dashboard", timeout=300
        )
        if rc == 0:
            return StageResult(name, "OK", time.monotonic() - t0,
                               "dashboard built", attempt=attempts)
        return StageResult(name, "FAIL", time.monotonic() - t0,
                           f"dashboard exit rc={rc} after {attempts} attempt(s)",
                           out[-500:], attempt=attempts, error_tail=err_tail)
    except Exception as exc:
        return StageResult(name, "FAIL", time.monotonic() - t0, str(exc),
                           error_tail=str(exc))


def stage5b_registry() -> StageResult:
    """Stage 5b: Rebuild the model/decision registry (registry/build_registry.py).

    Pins input fingerprints + production-model artifact hash for alert replay.
    Non-mandatory: a registry failure must not lose the week's scoring, but it
    is surfaced loudly (WARN) because the audit trail is degraded until fixed.
    """
    t0 = time.monotonic()
    name = "Stage 5b — Registry (build_registry.py)"
    if not REGISTRY_SCRIPT.exists():
        return StageResult(name, "SKIP", time.monotonic() - t0,
                           "registry pending — SKIP")
    try:
        rc, out, attempts, err_tail = run_subprocess_with_retry(
            [PYTHON_EXE, "-3", str(REGISTRY_SCRIPT)],
            label="build_registry", cwd=HERE / "registry", timeout=180
        )
        if rc == 0:
            tail = out.strip().splitlines()[-1] if out.strip() else "registry built"
            return StageResult(name, "OK", time.monotonic() - t0, tail[:100],
                               attempt=attempts)
        return StageResult(name, "WARN", time.monotonic() - t0,
                           f"registry build exited rc={rc} after {attempts} attempt(s) "
                           "(non-mandatory — AUDIT TRAIL DEGRADED until fixed)",
                           out[-500:], attempt=attempts, error_tail=err_tail)
    except Exception as exc:
        return StageResult(name, "WARN", time.monotonic() - t0,
                           f"registry exception (non-mandatory, audit trail degraded): {exc}")


def stage6_manifest(
    run_ts: str,
    all_stages: list[StageResult],
    gates: dict,
    fleet_max_date: str,
    log_path: Path,
    exit_code: int,
    dry_run: bool = False,
) -> StageResult:
    """Stage 6: Write run_manifest.json and append to run_history.csv."""
    t0 = time.monotonic()
    name = "Stage 6 — Manifest"
    if dry_run:
        return StageResult(name, "SKIP", time.monotonic() - t0,
                           "--dry-run: manifest write skipped")
    try:
        import pandas as pd
        snap_rows = 0
        alert_counts: dict = {}
        if SNAPSHOT_PATH.exists():
            snap = pd.read_csv(SNAPSHOT_PATH, comment="#")
            snap_rows = len(snap)
        if ALERT_LOG_PATH.exists():
            log = pd.read_csv(ALERT_LOG_PATH)
            if "priority" in log.columns:
                alert_counts = log["priority"].value_counts().to_dict()

        manifest = {
            "run_timestamp": run_ts,
            "config_version": all_stages[0].detail if False else _GLOBAL_CONFIG_VERSION,
            "config_hash": _GLOBAL_CONFIG_HASH_STORED,
            "config_hash_verified": (_GLOBAL_CONFIG_HASH_STORED == _config_hash_computed(_GLOBAL_CFG)),
            "fleet_max_date": fleet_max_date,
            "snapshot_row_count": snap_rows,
            "alert_counts_by_priority": alert_counts,
            "gate_results": gates,
            "log_path": str(log_path),
            "exit_code": exit_code,
            "stages": [
                {
                    "name": sr.name,
                    "status": sr.status,
                    "duration_s": round(sr.duration_s, 3),
                    "detail": sr.detail,
                }
                for sr in all_stages
            ],
        }

        with open(MANIFEST_PATH, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2, ensure_ascii=False)

        overall_ok = all(
            s.is_ok() for s in all_stages
            if s.name.startswith(("Stage 0", "Stage V", "Stage 1", "Stage 2", "Stage 6"))
        )
        gates_ok = all(v == "PASS" for v in gates.values()) if gates else False
        history_row = {
            "run_timestamp": run_ts,
            "config_version": _GLOBAL_CONFIG_VERSION,
            "overall_ok": overall_ok,
            "gates_pass": gates_ok,
            "snapshot_rows": snap_rows,
            "p0_alerts": alert_counts.get("P0", 0),
            "p1_alerts": alert_counts.get("P1", 0),
            "p2_alerts": alert_counts.get("P2", 0),
            "exit_code": exit_code,
            "stage_statuses": "|".join(f"{s.name.split(' ')[1]}:{s.status}"
                                       for s in all_stages),
        }
        file_exists = HISTORY_PATH.exists()
        with open(HISTORY_PATH, "a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(history_row.keys()))
            if not file_exists:
                writer.writeheader()
            writer.writerow(history_row)

        detail = (f"Manifest -> {MANIFEST_PATH.name}; history appended -> {HISTORY_PATH.name}; "
                  f"log_path={log_path.name}")
        return StageResult(name, "OK", time.monotonic() - t0, detail)

    except Exception as exc:
        return StageResult(name, "FAIL", time.monotonic() - t0, str(exc),
                           error_tail=str(exc))


# ── Structured logging ────────────────────────────────────────────────────────
def write_jsonl_log(log_path: Path, stage_results: list[StageResult]) -> None:
    """Write one JSON line per stage to the structured log file."""
    with open(log_path, "w", encoding="utf-8") as fh:
        for sr in stage_results:
            fh.write(json.dumps(sr.to_log_dict(), ensure_ascii=False) + "\n")


# ── Global config state (set in main after arg parsing) ─────────────────────
_GLOBAL_CFG: dict = {}
_GLOBAL_CONFIG_VERSION: str = "unknown"
_GLOBAL_CONFIG_HASH_STORED: str = ""


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> int:
    global _GLOBAL_CFG, _GLOBAL_CONFIG_VERSION, _GLOBAL_CONFIG_HASH_STORED

    parser = argparse.ArgumentParser(
        description="SM V2 staged weekly pipeline orchestrator"
    )
    parser.add_argument(
        "--full", action="store_true",
        help="Print upstream cache-rebuild commands (does not execute them)",
    )
    parser.add_argument(
        "--skip-dashboard", action="store_true",
        help="Skip Stage 5 dashboard build",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Run Stage 0 + validation only; print execution plan; write nothing except log; exit 0/3",
    )
    parser.add_argument(
        "--allow-stale-walking-scores", action="store_true",
        help="Bypass the 45-day walking_scores staleness hard-fail",
    )
    parser.add_argument(
        "--config", default=None,
        help="Path to config JSON (default: v2_config.json next to this file)",
    )
    args = parser.parse_args()

    # Resolve config path
    config_path = Path(args.config) if args.config else (HERE / "v2_config.json")
    if not config_path.is_absolute():
        config_path = Path.cwd() / config_path

    cfg, config_version, config_hash_stored = _load_config(config_path)
    _GLOBAL_CFG = cfg
    _GLOBAL_CONFIG_VERSION = config_version
    _GLOBAL_CONFIG_HASH_STORED = config_hash_stored

    run_ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    log_path = LOGS_DIR / f"pipeline_{run_ts.replace(':', '-')}.jsonl"

    print(f"\nV2 Weekly Pipeline — config {config_version}")
    print(f"Run timestamp: {run_ts}")
    print(f"Config: {config_path}")
    print(f"Config hash (stored):   {config_hash_stored}")
    print(f"Config hash (computed): {_config_hash_computed(cfg)}")
    if args.dry_run:
        print("[DRY-RUN MODE] Only Stage 0 + validation will run; no outputs written")
    print("=" * 68)

    all_stages: list[StageResult] = []
    gates: dict = {}
    fleet_max_date = "unknown"

    # ── Stage 0 ──────────────────────────────────────────────────────────────
    s0 = stage0_data_freshness(full=args.full)
    all_stages.append(s0)
    import pandas as pd
    if DATA_QUALITY.exists():
        try:
            dq = pd.read_csv(DATA_QUALITY)
            dq["t_end"] = pd.to_datetime(dq["t_end"])
            fleet_max_date = dq["t_end"].max().strftime("%Y-%m-%d")
        except Exception:
            pass
    _print_stage(s0)

    # ── Stage V — Input & config validation ──────────────────────────────────
    sv = stage_V_validate(cfg, config_path, config_hash_stored,
                          allow_stale=args.allow_stale_walking_scores)
    all_stages.append(sv)
    _print_stage(sv)

    if not sv.is_ok():
        print(f"\n[PIPELINE ABORT] Stage V FAIL — {sv.detail}")
        write_jsonl_log(log_path, all_stages)
        # Manifest for failed pre-gate run (no outputs written in dry-run)
        if not args.dry_run:
            s6 = stage6_manifest(run_ts, all_stages, gates, fleet_max_date,
                                 log_path, exit_code=3, dry_run=False)
            all_stages.append(s6)
            _print_stage(s6)
        _print_summary(all_stages, gates, run_ts)
        return 3

    # ── Dry-run: print plan and exit ──────────────────────────────────────────
    if args.dry_run:
        print("\n[DRY-RUN] Execution plan (stages that would run in full mode):")
        plan = [
            "  Stage 1 — Walking-scores freshness",
            "  Stage 2 — Scoring (V2_weekly_job.py)",
            "  Stage 3 — Monitors (if monitors/run_monitors.py present)",
            "  Stage 4 — Cards (cards/generate_cards.py)",
            "  Stage 5 — Dashboard (if dashboard/build_dashboard.py present)",
            "  Stage 6 — Manifest write (out/run_manifest.json + out/run_history.csv)",
        ]
        if args.skip_dashboard:
            plan[4] += " [SKIPPED — --skip-dashboard]"
        for line in plan:
            print(line)
        print("\n[DRY-RUN] No outputs written (except log).")
        write_jsonl_log(log_path, all_stages)
        print(f"[DRY-RUN] Log written: {log_path}")
        return 0

    # ── Stage 1 ──────────────────────────────────────────────────────────────
    s1 = stage1_walking_scores(allow_stale=args.allow_stale_walking_scores)
    all_stages.append(s1)
    _print_stage(s1)

    if not s1.is_ok():
        print("\n[PIPELINE ABORT] Stage 1 FAIL — walking_scores.csv missing.")
        write_jsonl_log(log_path, all_stages)
        s6 = stage6_manifest(run_ts, all_stages, gates, fleet_max_date,
                             log_path, exit_code=3)
        all_stages.append(s6)
        _print_stage(s6)
        write_jsonl_log(log_path, all_stages)
        _print_summary(all_stages, gates, run_ts)
        return 3

    # ── Stage 2 ──────────────────────────────────────────────────────────────
    s2, gates = stage2_scoring(config_path)
    all_stages.append(s2)
    _print_stage(s2)

    if not s2.is_ok():
        # Distinguish gate failure (exit 2) from job crash (exit 4)
        if "GATE FAILURE" in s2.detail or "UNKNOWN" in s2.detail:
            exit_code_s2 = 2
        else:
            exit_code_s2 = 4
        print(f"\n[PIPELINE ABORT] Stage 2 FAIL — gate failure or job error (exit {exit_code_s2}).")
        write_jsonl_log(log_path, all_stages)
        s6 = stage6_manifest(run_ts, all_stages, gates, fleet_max_date,
                             log_path, exit_code=exit_code_s2)
        all_stages.append(s6)
        _print_stage(s6)
        write_jsonl_log(log_path, all_stages)
        _print_summary(all_stages, gates, run_ts)
        return exit_code_s2

    # ── Stage 3 ──────────────────────────────────────────────────────────────
    s3 = stage3_monitors()
    all_stages.append(s3)
    _print_stage(s3)

    # Stage 3 is mandatory if the script is present — exit 4 on FAIL
    if s3.status == "FAIL":
        print("\n[PIPELINE ABORT] Stage 3 FAIL — monitors failed after retry (exit 4).")
        write_jsonl_log(log_path, all_stages)
        s6 = stage6_manifest(run_ts, all_stages, gates, fleet_max_date,
                             log_path, exit_code=4)
        all_stages.append(s6)
        _print_stage(s6)
        write_jsonl_log(log_path, all_stages)
        _print_summary(all_stages, gates, run_ts)
        return 4

    # ── Stage 4 ──────────────────────────────────────────────────────────────
    s4 = stage4_cards()
    all_stages.append(s4)
    _print_stage(s4)
    # Cards are non-mandatory (WARN is acceptable)

    # ── Stage 5 ──────────────────────────────────────────────────────────────
    s5 = stage5_dashboard(skip=args.skip_dashboard)
    all_stages.append(s5)
    _print_stage(s5)

    # Stage 5 FAIL when present is a mandatory failure
    if s5.status == "FAIL":
        print("\n[PIPELINE ABORT] Stage 5 FAIL — dashboard failed after retry (exit 4).")
        write_jsonl_log(log_path, all_stages)
        s6 = stage6_manifest(run_ts, all_stages, gates, fleet_max_date,
                             log_path, exit_code=4)
        all_stages.append(s6)
        _print_stage(s6)
        write_jsonl_log(log_path, all_stages)
        _print_summary(all_stages, gates, run_ts)
        return 4

    # ── Stage 5b ─────────────────────────────────────────────────────────────
    s5b = stage5b_registry()
    all_stages.append(s5b)
    _print_stage(s5b)
    # Registry is non-mandatory (WARN acceptable; audit trail degraded until fixed)

    # ── Stage 6 ──────────────────────────────────────────────────────────────
    # Determine final exit code
    mandatory_ok = all(
        s.is_ok()
        for s in all_stages
        if any(s.name.startswith(f"Stage {n}") for n in ("0", "V", "1", "2", "6"))
    )
    gates_ok = all(v == "PASS" for v in gates.values()) if gates else False
    final_exit = 0 if (mandatory_ok and gates_ok) else 2

    s6 = stage6_manifest(run_ts, all_stages, gates, fleet_max_date,
                         log_path, exit_code=final_exit)
    all_stages.append(s6)
    _print_stage(s6)

    # Write final log after manifest is in all_stages
    write_jsonl_log(log_path, all_stages)
    print(f"\n[LOG] Structured log -> {log_path}")

    _print_summary(all_stages, gates, run_ts)

    # Recompute mandatory_ok with Stage 6 included
    mandatory_ok = all(
        s.is_ok()
        for s in all_stages
        if any(s.name.startswith(f"Stage {n}") for n in ("0", "V", "1", "2", "6"))
    )
    gates_ok = all(v == "PASS" for v in gates.values()) if gates else False

    return 0 if (mandatory_ok and gates_ok) else 2


def _print_stage(sr: StageResult) -> None:
    icon = {"OK": "[OK  ]", "SKIP": "[SKIP]", "WARN": "[WARN]", "FAIL": "[FAIL]"}.get(
        sr.status, "[????]"
    )
    dur = f"{sr.duration_s:.1f}s"
    print(f"  {icon} {sr.name} ({dur})")
    if sr.detail:
        first_line = sr.detail.split("\n")[0]
        print(f"         {first_line}")
        extra_lines = sr.detail.split("\n")[1:]
        for line in extra_lines:
            print(f"         {line}")


def _print_summary(all_stages: list[StageResult], gates: dict, run_ts: str) -> None:
    print("\n" + "=" * 68)
    print("PIPELINE SUMMARY")
    print("=" * 68)
    for sr in all_stages:
        icon = {"OK": "OK  ", "SKIP": "SKIP", "WARN": "WARN", "FAIL": "FAIL"}.get(
            sr.status, "????"
        )
        print(f"  {icon}  {sr.name}")
    if gates:
        print(f"\nGate results: {gates}")
    all_ok = all(s.is_ok() for s in all_stages
                 if any(s.name.startswith(f"Stage {n}") for n in ("0","V","1","2","6")))
    gates_ok = all(v == "PASS" for v in gates.values()) if gates else False
    overall = "SUCCESS" if (all_ok and gates_ok) else "FAILURE"
    print(f"\nOverall: {overall}")
    print(f"Manifest: {MANIFEST_PATH}")
    print(f"History:  {HISTORY_PATH}")
    print("=" * 68)


if __name__ == "__main__":
    sys.exit(main())
