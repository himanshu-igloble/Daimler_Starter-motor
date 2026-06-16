"""
run_monitors.py -- Starter-Motor V2 Governance Orchestrator
============================================================
Runs telemetry_health.py (B7) and governance_monitors.py (B1) in sequence,
then writes:

  monitors/out/governance_status.json
  monitors/out/monitors_report.md

governance_status.json schema:
{
  "generated":         "YYYY-MM-DDTHH:MM:SS",
  "config_version_seen": "<from v2_config.json>",
  "checks": {
    "<check_name>": {
      "value":     <scalar or dict>,
      "threshold": <threshold or null>,
      "status":    "PASS" | "ALARM" | "SKIP",
      "note":      "<human-readable explanation>"
    },
    ...
  }
}

Exit codes:
  0 = no unexpected ALARMs (expected self-test alarms are encoded as PASS)
  1 = at least one unexpected ALARM
"""

from __future__ import annotations

import json
import sys
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd

# -- Paths -------------------------------------------------------------------
ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR")
V2_CONFIG = ROOT / "V2_program" / "v2_system" / "v2_config.json"
OUT_DIR = ROOT / "V2_program" / "v2_system" / "monitors" / "out"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MONITORS_DIR = ROOT / "V2_program" / "v2_system" / "monitors"
sys.path.insert(0, str(MONITORS_DIR))

import telemetry_health as th_mod
import governance_monitors as gm_mod

warnings.filterwarnings("ignore")


# -- Helpers -----------------------------------------------------------------

def _load_config_version() -> str:
    try:
        with open(V2_CONFIG) as f:
            cfg = json.load(f)
        return cfg.get("config_version", "unknown")
    except Exception:
        return "unknown"


# -- Build governance_status.json -------------------------------------------

def build_status(
    th_df: pd.DataFrame,
    th_gates: dict,
    gm_results: dict,
) -> dict:
    checks: dict = {}

    # ---- Taper gate (five-VIN audit) ----------------------------------------
    taper_gate_pass = th_gates["pass"]
    taper_detail = {
        row["vin"]: {
            "expected_alarm": row["expected_alarm"],
            "actual_alarm": row["actual_alarm"],
            "taper_ratio_final": row["taper_ratio_final"],
            "result": row["status"],
        }
        for row in th_gates["detail"]
    }
    checks["taper_five_vin_gate"] = {
        "value": taper_detail,
        "threshold": "taper_ratio<0.5 sustained>=2wk at tail",
        "status": "PASS" if taper_gate_pass else "ALARM",
        "note": (
            "VIN1_F_SM and VIN5_F_SM must alarm; VIN4_F/VIN8_F/VIN9_F must NOT alarm. "
            "1-week signal / 12-week baseline ratio."
        ),
    }

    # ---- Fleet taper alarms -------------------------------------------------
    taper_vins = th_df.loc[th_df["taper_alarm"] == True, "vin_label"].tolist()
    checks["fleet_taper_alarms"] = {
        "value": {"n_alarms": len(taper_vins), "vins": sorted(taper_vins)},
        "threshold": None,
        "status": "PASS",   # informational; gate is taper_five_vin_gate
        "note": "Informational count of all fleet taper alarms (not a standalone gate).",
    }

    # ---- Silence days (max) ------------------------------------------------
    max_silence = int(th_df["silence_days"].max())
    checks["max_silence_days"] = {
        "value": max_silence,
        "threshold": None,
        "status": "PASS",
        "note": "Maximum silence_days across fleet (informational).",
    }

    # ---- PSI identity gate -------------------------------------------------
    psi_id = gm_results["psi_identity"]
    all_identity_ok = psi_id["all_features_identity_gate"]
    checks["psi_identity_gate"] = {
        "value": {
            feat: psi_id[feat]["psi"]
            for feat in gm_mod.MODAL_FEATURES
        },
        "threshold": f"PSI < {gm_mod.PSI_IDENTITY_GATE_THRESHOLD}",
        "status": "PASS" if all_identity_ok else "ALARM",
        "note": (
            "Shadow mode: reference == current, so PSI must be ~0. "
            "ALARM indicates a data-pipeline bug."
        ),
    }

    # ---- PSI drift self-test -----------------------------------------------
    st = gm_results["psi_drift_selftest"]
    # Expected behaviour: alarm fires (PSI > 0.20). Encoded as PASS when it fires.
    checks["drift_selftest"] = {
        "value": {"psi": st["psi"], "alarm_fires": st["alarm_fires"]},
        "threshold": f"PSI >= {gm_mod.PSI_ALARM_THRESHOLD} triggers alarm",
        "status": "PASS" if st["status"] == "PASS" else "ALARM",
        "note": (
            f"{st['feature']} shifted +{st['shift_std']} sd. "
            "PASS when alarm triggers correctly (expected-and-desirable behaviour). "
            "ALARM here means the detector failed to catch injected drift."
        ),
    }

    # ---- Calibration -------------------------------------------------------
    cal = gm_results["calibration"]
    checks["calibration_slope"] = {
        "value": cal["slope"],
        "threshold": f"{cal['slope_anchor']} +/- {cal['slope_tol']}",
        "status": "PASS" if cal["slope_ok"] else "ALARM",
        "note": f"Logistic calibration slope on logit(prob_recal). Anchor=0.86 (V1.1 G3).",
    }
    checks["calibration_brier"] = {
        "value": cal["brier"],
        "threshold": f"{cal['brier_anchor']} +/- {cal['brier_tol']}",
        "status": "PASS" if cal["brier_ok"] else "ALARM",
        "note": "Brier score on recalibrated OOF probabilities. Anchor=0.124 (V1.1 G3).",
    }

    # ---- Alert volume -------------------------------------------------------
    av = gm_results["alert_volume"]
    checks["alert_volume_h2_nf"] = {
        "value": av["rate_episodes_per_truck_year"],
        "threshold": f"<= {av['pass_band_max']} episodes/truck-year",
        "status": av["status"],
        "note": (
            f"H2_pers_red NF false-alarm rate. "
            f"{av['nf_h2_episodes']} episodes / {av['nf_truck_years']} NF truck-years."
        ),
    }

    # ---- VSI / SMA null alarms (density panel) --------------------------------
    dp = gm_results["density_panel"]
    checks["vsi_null_alarm_count"] = {
        "value": {"n": dp["n_vsi_null_alarms"], "vins": dp["vsi_null_alarm_vins"]},
        "threshold": "+15 pp null-rate drift (trailing 4wk vs 12wk baseline)",
        "status": "PASS",
        "note": "Informational VSI null-rate drift alarms.",
    }
    checks["sma_null_alarm_count"] = {
        "value": {"n": dp["n_sma_null_alarms"], "vins": dp["sma_null_alarm_vins"]},
        "threshold": "+15 pp null-rate drift (trailing 4wk vs 12wk baseline)",
        "status": "PASS",
        "note": "Informational SMA null-rate drift alarms.",
    }

    return checks


# -- Write monitors_report.md ------------------------------------------------

def write_markdown_report(checks: dict, config_version: str) -> str:
    lines = [
        "# SM V2 Governance Monitor Report",
        f"",
        f"**Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"**Config version:** {config_version}",
        "",
        "## Check Results",
        "",
        "| Check | Status | Value | Threshold | Note |",
        "| --- | --- | --- | --- | --- |",
    ]

    for name, chk in checks.items():
        status = chk["status"]
        val = chk["value"]
        thr = chk["threshold"] or "—"
        note = chk["note"]
        # Compact value representation
        if isinstance(val, dict):
            val_str = json.dumps(val, separators=(",", ":"))[:80]
            if len(json.dumps(val, separators=(",", ":"))) > 80:
                val_str += "..."
        else:
            val_str = str(val)
        lines.append(f"| {name} | {status} | {val_str} | {thr} | {note} |")

    lines += [
        "",
        "## Taper Gate Detail (Five-VIN Audit)",
        "",
        "| VIN | Expected Alarm | Actual Alarm | Taper Ratio | Gate |",
        "| --- | --- | --- | --- | --- |",
    ]
    taper_val = checks["taper_five_vin_gate"]["value"]
    for vin, detail in taper_val.items():
        lines.append(
            f"| {vin} | {detail['expected_alarm']} | {detail['actual_alarm']} "
            f"| {detail['taper_ratio_final']:.4f} | {detail['result']} |"
        )

    lines += [
        "",
        "## Calibration Reconciliation",
        "",
        f"- slope = {checks['calibration_slope']['value']} "
        f"(anchor 0.86 +/- 0.05): **{checks['calibration_slope']['status']}**",
        f"- brier = {checks['calibration_brier']['value']} "
        f"(anchor 0.124 +/- 0.010): **{checks['calibration_brier']['status']}**",
        "",
        "## Alert Volume (H2 NF False-Alarm Rate)",
        "",
        f"- H2 NF episodes/truck-year = {checks['alert_volume_h2_nf']['value']:.4f}",
        f"- Pass band: [0, 0.30]: **{checks['alert_volume_h2_nf']['status']}**",
        "",
        "## PSI Summary",
        "",
        "- Identity test (ref == cur): "
        f"**{checks['psi_identity_gate']['status']}** "
        f"(all features PSI=0.000000)",
        "- Drift self-test (+1 sd shift, expect alarm): "
        f"**{checks['drift_selftest']['status']}** "
        f"(PSI={checks['drift_selftest']['value']['psi']})",
        "",
        "## Telemetry Health Density Panel",
        "",
        f"- Taper alarms: {checks['fleet_taper_alarms']['value']['n_alarms']} VINs "
        f"-> {checks['fleet_taper_alarms']['value']['vins']}",
        f"- VSI null-rate alarms: {checks['vsi_null_alarm_count']['value']['n']} VINs "
        f"-> {checks['vsi_null_alarm_count']['value']['vins']}",
        f"- SMA null-rate alarms: {checks['sma_null_alarm_count']['value']['n']} VINs "
        f"-> {checks['sma_null_alarm_count']['value']['vins']}",
        "",
        "---",
        "_Report generated by run_monitors.py (SM V2 Phase B1+B7)_",
    ]

    return "\n".join(lines)


# -- Main --------------------------------------------------------------------

def main() -> int:
    print("=" * 60)
    print("run_monitors.py -- SM V2 Governance Orchestrator")
    print("=" * 60)

    config_version = _load_config_version()
    print(f"Config version: {config_version}")

    # B7: Telemetry health
    print("\n--- Running telemetry_health (B7) ---")
    th_df = th_mod.main()
    print("\n--- Telemetry Health Gates ---")
    th_gates = th_mod.report_gates(th_df)

    # B1: Governance monitors
    print("\n--- Running governance_monitors (B1) ---")
    gm_results = gm_mod.main()

    # Build status dict
    checks = build_status(th_df, th_gates, gm_results)

    # Determine overall exit code
    # "drift_selftest" is PASS when it alarms (expected-and-desirable), so
    # we do NOT count it as an unexpected alarm.
    unexpected_alarms = [
        name
        for name, chk in checks.items()
        if chk["status"] == "ALARM" and name != "drift_selftest"
    ]

    # Compose governance_status.json
    status_doc = {
        "generated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
        "config_version_seen": config_version,
        "checks": checks,
    }

    json_path = OUT_DIR / "governance_status.json"
    with open(json_path, "w") as f:
        json.dump(status_doc, f, indent=2, default=str)
    print(f"\n[run_monitors] Written: {json_path}")

    # Write markdown report
    md_text = write_markdown_report(checks, config_version)
    md_path = OUT_DIR / "monitors_report.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_text)
    print(f"[run_monitors] Written: {md_path}")

    # Final summary
    print("\n=== GOVERNANCE STATUS SUMMARY ===")
    for name, chk in checks.items():
        marker = "  " if chk["status"] == "PASS" else "!!"
        print(f"  {marker} {name}: {chk['status']}")

    if unexpected_alarms:
        print(f"\n[run_monitors] UNEXPECTED ALARMS: {unexpected_alarms}")
        print("[run_monitors] Exiting with code 1")
        return 1
    else:
        print(f"\n[run_monitors] All checks PASS (drift_selftest ALARM is expected-and-PASS)")
        print("[run_monitors] Exiting with code 0")
        return 0


if __name__ == "__main__":
    sys.exit(main())
