"""
Shadow-Quarter KPI Tracker (D8-C1)

Usage:
  py -3 kpi_tracker.py record   -- archive current snapshot + alert log (idempotent)
  py -3 kpi_tracker.py report   -- compute cumulative KPIs over all archived weeks

Paths are relative to this script's location. Inputs are read-only; outputs
are written to shadow_quarter/archive/ and shadow_quarter/out/.
"""
import os
import sys
import json
import shutil
import csv
from datetime import datetime, timezone
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
THIS_DIR = Path(__file__).resolve().parent
V2_SYSTEM = THIS_DIR.parent
OUT = V2_SYSTEM / "out"
ARCHIVE = THIS_DIR / "archive"
KPI_OUT = THIS_DIR / "out"

SNAPSHOT_CSV = OUT / "fleet_snapshot.csv"
ALERT_LOG_CSV = OUT / "shadow_alert_log.csv"
RUN_MANIFEST = OUT / "run_manifest.json"
LABELS_CSV = V2_SYSTEM / "labels" / "label_registry.csv"

N_TRUCKS = 34
WEEKS_IN_QUARTER = 13

# Blind-spot class (exempt from K4): documented SMA-dead VINs from v2_config
SMA_DEAD_VINS = {
    "VIN8_F_SM", "VIN9_F_SM", "VIN10_NF_SM", "VIN11_NF_SM",
    "VIN12_NF_SM", "VIN13_NF_SM", "VIN20_NF_SM"
}

# Watchlist VINs (K3)
WATCHLIST_VINS = {"VIN2_NF_SM", "VIN5_NF_SM", "VIN8_NF_SM", "VIN15_NF_SM"}

# Refit trigger (from v2_config governance)
REFIT_TRIGGER_N_FAILURES = 5


def load_manifest():
    with open(RUN_MANIFEST) as f:
        return json.load(f)


def archive_run(run_ts: str, force: bool = False) -> Path:
    """Copy snapshot + alert log into archive/<run_ts>/. Idempotent."""
    safe_ts = run_ts.replace(":", "-")
    dest = ARCHIVE / safe_ts
    if dest.exists() and not force:
        print(f"[record] Already archived: {safe_ts} — skipping (idempotent).")
        return dest
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SNAPSHOT_CSV, dest / "fleet_snapshot.csv")
    shutil.copy2(ALERT_LOG_CSV, dest / "shadow_alert_log.csv")
    # Save a copy of the manifest for audit
    shutil.copy2(RUN_MANIFEST, dest / "run_manifest.json")
    print(f"[record] Archived week to {dest.relative_to(THIS_DIR)}")
    return dest


def list_archived_weeks():
    """Return sorted list of (run_ts_str, archive_path) tuples."""
    if not ARCHIVE.exists():
        return []
    weeks = []
    for d in sorted(ARCHIVE.iterdir()):
        if d.is_dir() and (d / "fleet_snapshot.csv").exists():
            weeks.append((d.name, d))
    return weeks


def read_csv_dicts(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        # Skip comment lines starting with #
        lines = [l for l in f if not l.startswith("#")]
    if not lines:
        return []
    return list(csv.DictReader(lines))


# ── KPI calculations ──────────────────────────────────────────────────────────

def compute_k1(weeks_data: list) -> dict:
    """K1: shop-grade P0 alerts / truck-year. Threshold <= 0.30."""
    total_p0_shop = 0
    weeks_elapsed = len(weeks_data)
    for _, alert_rows in weeks_data:
        for row in alert_rows:
            if row.get("priority") == "P0":
                sil = row.get("silence_trigger_active", "False")
                if str(sil).strip().lower() not in ("true", "1", "yes"):
                    total_p0_shop += 1
    truck_years = (N_TRUCKS * weeks_elapsed) / 52.18
    value = total_p0_shop / truck_years if truck_years > 0 else 0.0
    threshold = 0.30
    status = "ON-TRACK" if value <= threshold else "BREACH"
    return {
        "kpi": "K1",
        "description": "Paging burden: shop-grade P0 alerts / truck-year",
        "value": round(value, 4),
        "threshold": f"<= {threshold}",
        "status": status,
        "detail": {
            "total_p0_shop_alerts": total_p0_shop,
            "weeks_elapsed": weeks_elapsed,
            "truck_years": round(truck_years, 4),
        }
    }


def compute_k2(labels_path: Path, snapshot_rows: list) -> dict:
    """K2: calibration slope in [0.5, 2.0]. PENDING-DATA if < 3 failure labels."""
    THRESHOLD_LO, THRESHOLD_HI = 0.5, 2.0
    FAILURE_MIN = 3

    labels = read_csv_dicts(labels_path) if labels_path.exists() else []
    failure_labels = [
        r for r in labels
        if r.get("finding_modes", "").lower() != "no fault found"
        and r.get("finding_modes", "") not in ("", "PENDING")
    ]
    n_failures = len(failure_labels)

    if n_failures < FAILURE_MIN:
        return {
            "kpi": "K2",
            "description": "Calibration slope in [0.5, 2.0]",
            "value": None,
            "threshold": f"[{THRESHOLD_LO}, {THRESHOLD_HI}]",
            "status": "PENDING-DATA",
            "detail": {
                "failure_labels_available": n_failures,
                "required_for_evaluation": FAILURE_MIN,
                "note": "Awaiting real failure labels from WO feedback loop."
            }
        }

    # Build prob -> label pairs from latest snapshot
    prob_map = {}
    for row in snapshot_rows:
        vin = row.get("vin", "")
        try:
            prob_map[vin] = float(row["prob"])
        except (ValueError, KeyError):
            pass

    y_true, y_pred = [], []
    for r in failure_labels:
        vin = r.get("vin", "")
        if vin in prob_map:
            y_true.append(1.0)
            y_pred.append(prob_map[vin])

    if len(y_true) < FAILURE_MIN:
        return {
            "kpi": "K2", "description": "Calibration slope in [0.5, 2.0]",
            "value": None, "threshold": f"[{THRESHOLD_LO}, {THRESHOLD_HI}]",
            "status": "PENDING-DATA",
            "detail": {"failure_labels_available": n_failures,
                       "matched_to_snapshot": len(y_true),
                       "required_for_evaluation": FAILURE_MIN}
        }

    # Simple OLS slope of y_true on y_pred (logistic would be better with more data)
    import statistics
    n = len(y_pred)
    mx = statistics.mean(y_pred)
    my = statistics.mean(y_true)
    num = sum((x - mx) * (y - my) for x, y in zip(y_pred, y_true))
    den = sum((x - mx) ** 2 for x in y_pred)
    slope = num / den if den > 0 else float("nan")

    status = "ON-TRACK" if THRESHOLD_LO <= slope <= THRESHOLD_HI else "BREACH"
    return {
        "kpi": "K2",
        "description": "Calibration slope in [0.5, 2.0]",
        "value": round(slope, 4),
        "threshold": f"[{THRESHOLD_LO}, {THRESHOLD_HI}]",
        "status": status,
        "detail": {"n_failure_labels_used": n_failures, "n_matched": n}
    }


def compute_k3(labels_path: Path) -> dict:
    """K3: >= 1 watchlist truck with a label_registry entry."""
    labels = read_csv_dicts(labels_path) if labels_path.exists() else []
    resolved = set()
    for r in labels:
        vin = r.get("vin", "")
        if vin in WATCHLIST_VINS and r.get("finding_modes", "").strip() not in ("", "PENDING"):
            resolved.add(vin)
    status = "ON-TRACK" if len(resolved) >= 1 else "PENDING-DATA"
    return {
        "kpi": "K3",
        "description": ">= 1 watchlist truck with recorded resolution",
        "value": len(resolved),
        "threshold": ">= 1",
        "status": status,
        "detail": {
            "watchlist_vins": sorted(WATCHLIST_VINS),
            "resolved_vins": sorted(resolved),
        }
    }


def compute_k4(weeks_data: list, labels_path: Path) -> dict:
    """K4: zero GREEN-then-failed trucks outside blind-spot class."""
    labels = read_csv_dicts(labels_path) if labels_path.exists() else []
    confirmed_failures = {
        r["vin"] for r in labels
        if r.get("finding_modes", "") not in ("no fault found", "", "PENDING")
    }

    violations = []
    for run_ts, arch_path in weeks_data:
        snap_rows, _ = _load_week_data(arch_path)
        for row in snap_rows:
            vin = row.get("vin", "")
            tier = row.get("tier", "")
            sma_dead = str(row.get("sma_dead_badge", "False")).strip().lower() in ("true", "1")
            silence = str(row.get("silence_trigger_active", "False")).strip().lower() in ("true", "1")
            in_blind_spot = sma_dead or (vin in SMA_DEAD_VINS) or silence

            if vin in confirmed_failures and tier == "GREEN" and not in_blind_spot:
                violations.append({"vin": vin, "run_ts": run_ts, "tier": tier})

    status = "ON-TRACK" if len(violations) == 0 else "BREACH"
    return {
        "kpi": "K4",
        "description": "Zero GREEN-then-failed outside documented blind-spot class",
        "value": len(violations),
        "threshold": "== 0",
        "status": status,
        "detail": {
            "violations": violations,
            "blind_spot_note": (
                "SMA-dead VINs and silence_trigger_active trucks are exempt. "
                "VIN1_F_SM (silence) and VIN9_F_SM (SMA-dead) are exempt in retrospective data."
            )
        }
    }


def compute_k5(weeks_data: list) -> dict:
    """K5: tracking tables — no threshold. weeks_data = list of (run_ts, arch_path)."""
    weekly_vol = []
    silence_counts = []
    evidence_transitions = []

    prev_evidence = {}
    for run_ts, arch_path in weeks_data:
        snap_rows, alert_rows = _load_week_data(arch_path)

        # Alert volume by priority
        prio_counts = {}
        for r in alert_rows:
            p = r.get("priority", "UNKNOWN")
            prio_counts[p] = prio_counts.get(p, 0) + 1
        weekly_vol.append({"run_ts": run_ts, **prio_counts})

        # Silence count
        sil = sum(
            1 for r in snap_rows
            if str(r.get("silence_trigger_active", "False")).strip().lower()
            in ("true", "1")
        )
        silence_counts.append({"run_ts": run_ts, "silence_count": sil})

        # Evidence-state transitions
        cur_evidence = {r["vin"]: r.get("evidence_state", "") for r in snap_rows}
        n_transitions = sum(
            1 for vin, state in cur_evidence.items()
            if prev_evidence.get(vin) and prev_evidence[vin] != state
        )
        evidence_transitions.append({"run_ts": run_ts, "n_transitions": n_transitions})
        prev_evidence = cur_evidence

    return {
        "kpi": "K5",
        "description": "Tracking only (no threshold): alert volume, transitions, silence",
        "value": "TRACKING",
        "threshold": "N/A",
        "status": "TRACKING",
        "detail": {
            "weekly_alert_volume": weekly_vol,
            "weekly_silence_counts": silence_counts,
            "weekly_evidence_transitions": evidence_transitions,
        }
    }


def _load_week_data(arch_path: Path):
    snap_rows = read_csv_dicts(arch_path / "fleet_snapshot.csv")
    alert_rows = read_csv_dicts(arch_path / "shadow_alert_log.csv")
    return snap_rows, alert_rows


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_record():
    manifest = load_manifest()
    run_ts = manifest["run_timestamp"]
    print(f"[record] run_timestamp = {run_ts}")
    archive_run(run_ts)
    print("[record] Done.")


def cmd_report():
    KPI_OUT.mkdir(parents=True, exist_ok=True)
    weeks = list_archived_weeks()
    weeks_elapsed = len(weeks)
    print(f"[report] {weeks_elapsed} archived week(s) found.")

    if weeks_elapsed == 0:
        print("[report] No archived weeks — run 'record' first.")
        sys.exit(1)

    # Latest snapshot for K2 (use most recent archived week)
    latest_snap_rows, latest_alert_rows = _load_week_data(weeks[-1][1])

    # Build weeks_data for K1/K4/K5 as list of (run_ts, arch_path)
    weeks_data_paths = weeks  # list of (run_ts_str, Path)

    # Build per-week (snap, alert) for K1 (needs alert rows per week)
    weeks_alert_data = [(ts, _load_week_data(p)) for ts, p in weeks_data_paths]

    k1 = compute_k1([(ts, al) for ts, (_, al) in weeks_alert_data])
    k2 = compute_k2(LABELS_CSV, latest_snap_rows)
    k3 = compute_k3(LABELS_CSV)
    k4 = compute_k4(weeks_data_paths, LABELS_CSV)

    # K5 needs both snap+alert per week
    k5_weeks = weeks_data_paths
    k5 = _compute_k5_internal(k5_weeks)

    kpis = [k1, k2, k3, k4, k5]

    # Quarter pass/fail
    pass_condition = (
        k1["status"] == "ON-TRACK"
        and k2["status"] in ("ON-TRACK", "PENDING-DATA")
        and k3["status"] in ("ON-TRACK",)
        and k4["status"] == "ON-TRACK"
    )
    quarter_status = "PASS" if pass_condition else "FAIL"

    # Build output
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "weeks_elapsed": weeks_elapsed,
        "weeks_in_quarter": WEEKS_IN_QUARTER,
        "quarter_status": quarter_status,
        "kpis": kpis,
    }

    out_json = KPI_OUT / "kpi_status.json"
    with open(out_json, "w") as f:
        json.dump(result, f, indent=2)
    print(f"[report] Wrote {out_json}")

    # Write markdown report
    out_md = KPI_OUT / "kpi_report.md"
    _write_md_report(result, out_md)
    print(f"[report] Wrote {out_md}")

    # Print summary
    print(f"\n=== Shadow-Quarter KPI Report — Week {weeks_elapsed}/{WEEKS_IN_QUARTER} ===")
    for k in kpis:
        val_str = str(k["value"]) if k["value"] is not None else "N/A"
        print(f"  {k['kpi']}: {val_str:>10}  threshold={k['threshold']:<18} [{k['status']}]")
    print(f"\n  Quarter status: {quarter_status}")


def _compute_k5_internal(weeks_data_paths):
    prev_evidence = {}
    weekly_vol = []
    silence_counts = []
    evidence_transitions = []

    for run_ts, arch_path in weeks_data_paths:
        snap_rows, alert_rows = _load_week_data(arch_path)

        prio_counts = {}
        for r in alert_rows:
            p = r.get("priority", "UNKNOWN")
            prio_counts[p] = prio_counts.get(p, 0) + 1
        weekly_vol.append({"run_ts": run_ts, **prio_counts})

        sil = sum(
            1 for r in snap_rows
            if str(r.get("silence_trigger_active", "False")).strip().lower()
            in ("true", "1")
        )
        silence_counts.append({"run_ts": run_ts, "silence_count": sil})

        cur_evidence = {r["vin"]: r.get("evidence_state", "") for r in snap_rows}
        n_transitions = sum(
            1 for vin, state in cur_evidence.items()
            if prev_evidence.get(vin) and prev_evidence[vin] != state
        )
        evidence_transitions.append({"run_ts": run_ts, "n_transitions": n_transitions})
        prev_evidence = cur_evidence

    return {
        "kpi": "K5",
        "description": "Tracking only (no threshold): alert volume, transitions, silence",
        "value": "TRACKING",
        "threshold": "N/A",
        "status": "TRACKING",
        "detail": {
            "weekly_alert_volume": weekly_vol,
            "weekly_silence_counts": silence_counts,
            "weekly_evidence_transitions": evidence_transitions,
        }
    }


def _write_md_report(result: dict, path: Path):
    lines = [
        f"# Shadow-Quarter KPI Report",
        f"",
        f"**Generated**: {result['generated_at']}",
        f"**Week**: {result['weeks_elapsed']} of {result['weeks_in_quarter']}",
        f"**Quarter Status**: {result['quarter_status']}",
        f"",
        f"## KPI Summary",
        f"",
        f"| KPI | Value | Threshold | Status |",
        f"|-----|-------|-----------|--------|",
    ]
    for k in result["kpis"]:
        val = str(k["value"]) if k["value"] is not None else "N/A"
        lines.append(f"| {k['kpi']} | {val} | {k['threshold']} | **{k['status']}** |")

    lines += ["", "## Pass Rule", "",
              "Quarter PASSES iff K1=ON-TRACK AND (K2=ON-TRACK OR PENDING-DATA) AND K3=ON-TRACK AND K4=ON-TRACK.",
              "K5 is tracking-only and does not affect pass/fail.",
              ""]

    # K5 tables
    k5 = next(k for k in result["kpis"] if k["kpi"] == "K5")
    lines += ["## K5 Tracking Tables", "", "### Weekly Alert Volume by Channel", ""]
    vol = k5["detail"]["weekly_alert_volume"]
    if vol:
        all_prios = sorted({p for row in vol for p in row if p != "run_ts"})
        lines.append("| Week | " + " | ".join(all_prios) + " |")
        lines.append("|------|" + "|".join(["----"] * len(all_prios)) + "|")
        for i, row in enumerate(vol, 1):
            vals = " | ".join(str(row.get(p, 0)) for p in all_prios)
            lines.append(f"| {i} | {vals} |")
    lines += ["", "### Weekly Silence Trigger Count", ""]
    sil = k5["detail"]["weekly_silence_counts"]
    if sil:
        lines.append("| Week | Silence Count |")
        lines.append("|------|--------------|")
        for i, row in enumerate(sil, 1):
            lines.append(f"| {i} | {row['silence_count']} |")
    lines += ["", "### Weekly Evidence-State Transitions", ""]
    trans = k5["detail"]["weekly_evidence_transitions"]
    if trans:
        lines.append("| Week | N Transitions |")
        lines.append("|------|--------------|")
        for i, row in enumerate(trans, 1):
            lines.append(f"| {i} | {row['n_transitions']} |")

    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("record", "report"):
        print("Usage: py -3 kpi_tracker.py record|report")
        sys.exit(1)
    if sys.argv[1] == "record":
        cmd_record()
    else:
        cmd_report()
