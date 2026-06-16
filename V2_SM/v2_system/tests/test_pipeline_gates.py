"""
test_pipeline_gates.py — Unit tests for V2 pipeline hardening (Phase D, item 1)
================================================================================
Usage:
    py -3 tests/test_pipeline_gates.py    (from v2_system/)
    or
    py -3 test_pipeline_gates.py          (from tests/)

Tests:
  (a) Missing-VIN walking_scores copy -> validator fails naming the VIN
  (b) NaN prob row at k=0 -> validator fails
  (c) Tampered config copy (changed threshold, old hash) -> integrity check fails
  (d) Correct config + good inputs -> passes
  (e) Staleness boundary logic (14/45 day) with injected mtimes on TEMP copies

Design: imports validate_inputs() and check_walking_scores_staleness() from
V2_weekly_pipeline; constructs synthetic DataFrames / temp files so NO subprocess
of the full pipeline is needed and no real files are modified.

All tests print PASS/FAIL; exit 0 if all pass, exit 1 if any fail.
"""
from __future__ import annotations
import csv
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

# ── Make v2_system importable ─────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent
V2_SYS = HERE.parent
sys.path.insert(0, str(V2_SYS))

# Import the testable functions (no full pipeline subprocess needed)
from V2_weekly_pipeline import (
    validate_inputs,
    check_walking_scores_staleness,
    _config_hash_computed,
    WALKING_SCORES,
    STALE_WARN_DAYS,
    STALE_FAIL_DAYS,
    EXPECTED_N_VINS,
)

PASS_COUNT = 0
FAIL_COUNT = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS_COUNT, FAIL_COUNT
    if condition:
        PASS_COUNT += 1
        print(f"  PASS  {name}")
    else:
        FAIL_COUNT += 1
        msg = f"  FAIL  {name}"
        if detail:
            msg += f" — {detail}"
        print(msg)


# ── Load real config for baseline ─────────────────────────────────────────────
CONFIG_PATH = V2_SYS / "v2_config.json"
with open(CONFIG_PATH, encoding="utf-8") as _fh:
    REAL_CFG = json.load(_fh)

REAL_HASH_STORED = REAL_CFG.get("config_hash", "")


def _write_temp_config(cfg_dict: dict, tmp_dir: str) -> Path:
    """Write a config dict to a temp file and return its path."""
    p = Path(tmp_dir) / "v2_config_temp.json"
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(cfg_dict, fh, indent=2)
    return p


def _write_temp_ws(df: pd.DataFrame, tmp_dir: str, name: str = "walking_scores_temp.csv") -> Path:
    """Write a walking_scores DataFrame to a temp CSV and return its path."""
    p = Path(tmp_dir) / name
    df.to_csv(p, index=False)
    return p


def _set_mtime(path: Path, days_ago: float) -> None:
    """Set file mtime to simulate a file that is days_ago days old."""
    new_mtime = time.time() - days_ago * 86400
    os.utime(str(path), (new_mtime, new_mtime))


def _make_validate_inputs_with_ws(ws_path: Path, cfg: dict, hash_stored: str) -> tuple[bool, str]:
    """
    Call validate_inputs but patch WALKING_SCORES to use ws_path.
    We do this by temporarily monkeypatching the module-level variable.
    """
    import V2_weekly_pipeline as pl
    orig = pl.WALKING_SCORES
    pl.WALKING_SCORES = ws_path
    try:
        ok, msg = validate_inputs(cfg, CONFIG_PATH, hash_stored, allow_stale=True)
    finally:
        pl.WALKING_SCORES = orig
    return ok, msg


def _make_staleness_check_with_ws(ws_path: Path, allow_stale: bool) -> tuple[str, str]:
    """Call check_walking_scores_staleness with a patched WALKING_SCORES path."""
    import V2_weekly_pipeline as pl
    orig = pl.WALKING_SCORES
    pl.WALKING_SCORES = ws_path
    try:
        status, msg = check_walking_scores_staleness(allow_stale)
    finally:
        pl.WALKING_SCORES = orig
    return status, msg


# ── Load real walking scores once ────────────────────────────────────────────
real_ws = pd.read_csv(WALKING_SCORES)


def run_tests() -> None:
    print("=" * 68)
    print("V2 Pipeline Hardening — Gate Unit Tests (Phase D item 1)")
    print(f"Config: {CONFIG_PATH}")
    print(f"Config stored hash: {REAL_HASH_STORED[:16]}...")
    print(f"STALE_WARN_DAYS={STALE_WARN_DAYS}, STALE_FAIL_DAYS={STALE_FAIL_DAYS}")
    print("=" * 68)

    with tempfile.TemporaryDirectory() as tmp_dir:

        # ── (a) Missing-VIN walking_scores ────────────────────────────────────
        print("\n[A] Missing-VIN walking_scores -> validator fails naming the VIN")

        # Remove one VIN (e.g. VIN1_F_SM) from the walking_scores
        missing_vin = "VIN1_F_SM"
        ws_missing = real_ws[real_ws["vin_label"] != missing_vin].copy()
        ws_missing_path = _write_temp_ws(ws_missing, tmp_dir, "ws_missing_vin.csv")

        ok_a, msg_a = _make_validate_inputs_with_ws(ws_missing_path, REAL_CFG, REAL_HASH_STORED)
        check("A1: validate_inputs returns False for missing VIN", not ok_a,
              f"ok={ok_a}, msg={msg_a}")
        check("A2: failure message names the missing VIN", missing_vin in msg_a,
              f"VIN not in msg: {msg_a}")

        # ── (b) NaN prob at k=0 ───────────────────────────────────────────────
        print("\n[B] NaN prob at k=0 -> validator fails")

        ws_nan = real_ws.copy()
        # Inject NaN prob on the k=0 row of VIN2_F_SM
        nan_vin = "VIN2_F_SM"
        mask = (ws_nan["vin_label"] == nan_vin) & (ws_nan["k_weeks"] == 0)
        ws_nan.loc[mask, "prob"] = float("nan")
        ws_nan_path = _write_temp_ws(ws_nan, tmp_dir, "ws_nan_prob.csv")

        ok_b, msg_b = _make_validate_inputs_with_ws(ws_nan_path, REAL_CFG, REAL_HASH_STORED)
        check("B1: validate_inputs returns False for NaN prob at k=0", not ok_b,
              f"ok={ok_b}, msg={msg_b}")
        check("B2: failure message mentions NaN prob", "NaN prob" in msg_b,
              f"'NaN prob' not in msg: {msg_b}")

        # ── (c) Tampered config: changed threshold, old hash → integrity fails ─
        print("\n[C] Tampered config (changed threshold, old hash) -> integrity check fails")

        import copy
        tampered_cfg = copy.deepcopy(REAL_CFG)
        # Change a threshold value (this makes the recomputed hash differ)
        tampered_cfg["tier_thresholds"]["GREEN_max_exclusive"] = 0.40
        # Keep the old stored hash (from the original config)
        tampered_hash_stored = REAL_HASH_STORED
        # Do NOT recompute: hash field in dict stays as-is (old hash)

        tampered_cfg_path = _write_temp_config(tampered_cfg, tmp_dir)

        # Call validate_inputs with the tampered cfg dict and old stored hash
        ok_c, msg_c = validate_inputs(tampered_cfg, tampered_cfg_path,
                                      tampered_hash_stored, allow_stale=True)
        check("C1: validate_inputs returns False for tampered config", not ok_c,
              f"ok={ok_c}, msg={msg_c}")
        check("C2: failure message contains CONFIG TAMPER keyword",
              "CONFIG TAMPER" in msg_c,
              f"'CONFIG TAMPER' not in msg: {msg_c}")
        check("C3: failure message names expected hash",
              tampered_hash_stored[:8] in msg_c,
              f"expected hash prefix not in msg: {msg_c}")

        # ── (d) Correct config and good inputs -> passes ───────────────────────
        print("\n[D] Correct config + good inputs -> passes")

        ok_d, msg_d = validate_inputs(REAL_CFG, CONFIG_PATH, REAL_HASH_STORED,
                                      allow_stale=True)
        check("D1: validate_inputs returns True for valid config + inputs", ok_d,
              f"ok={ok_d}, msg={msg_d}")
        check("D2: success message mentions 'passed'", "passed" in msg_d.lower(),
              f"msg={msg_d}")

        # ── (e) Staleness boundary logic: 14/45 day thresholds ───────────────
        print("\n[E] Staleness boundary logic with injected mtimes on TEMP copies")

        # Write a temp walking_scores file
        ws_temp_path = _write_temp_ws(real_ws, tmp_dir, "ws_stale_test.csv")

        # e1: 5 days old -> OK
        _set_mtime(ws_temp_path, 5.0)
        status_e1, msg_e1 = _make_staleness_check_with_ws(ws_temp_path, allow_stale=False)
        check("E1: 5-day-old file -> OK", status_e1 == "OK",
              f"status={status_e1}, msg={msg_e1}")

        # e2: 15 days old -> WARN (> STALE_WARN_DAYS=14 but < STALE_FAIL_DAYS=45)
        _set_mtime(ws_temp_path, 15.0)
        status_e2, msg_e2 = _make_staleness_check_with_ws(ws_temp_path, allow_stale=False)
        check("E2: 15-day-old file -> WARN", status_e2 == "WARN",
              f"status={status_e2}, msg={msg_e2}")

        # e3: 13.9 days old -> still OK (threshold is >14, so 13.9 is under)
        _set_mtime(ws_temp_path, 13.9)
        status_e3, msg_e3 = _make_staleness_check_with_ws(ws_temp_path, allow_stale=False)
        check("E3: 13.9-day-old file -> OK (just under >14 warn threshold)",
              status_e3 == "OK",
              f"status={status_e3}, msg={msg_e3}")

        # e4: 46 days old, no allow_stale -> FAIL
        _set_mtime(ws_temp_path, 46.0)
        status_e4, msg_e4 = _make_staleness_check_with_ws(ws_temp_path, allow_stale=False)
        check("E4: 46-day-old file without --allow-stale -> FAIL",
              status_e4 == "FAIL",
              f"status={status_e4}, msg={msg_e4}")

        # e5: 46 days old, allow_stale=True -> WARN (bypassed)
        _set_mtime(ws_temp_path, 46.0)
        status_e5, msg_e5 = _make_staleness_check_with_ws(ws_temp_path, allow_stale=True)
        check("E5: 46-day-old file with allow_stale=True -> WARN (bypassed)",
              status_e5 == "WARN",
              f"status={status_e5}, msg={msg_e5}")

        # e6: 44.9 days old -> still WARN not FAIL (threshold is >45, so 44.9 is under)
        _set_mtime(ws_temp_path, 44.9)
        status_e6, msg_e6 = _make_staleness_check_with_ws(ws_temp_path, allow_stale=False)
        check("E6: 44.9-day-old file -> WARN not FAIL (just under >45 fail threshold)",
              status_e6 == "WARN",
              f"status={status_e6}, msg={msg_e6}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 68)
    total = PASS_COUNT + FAIL_COUNT
    print(f"Results: {PASS_COUNT}/{total} PASS, {FAIL_COUNT} FAIL")
    if FAIL_COUNT == 0:
        print("ALL TESTS PASS")
    else:
        print("SOME TESTS FAILED — see above")
        sys.exit(1)


if __name__ == "__main__":
    run_tests()
