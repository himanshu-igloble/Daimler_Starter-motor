"""
V1_1_SM_package_rules.py — package the frozen SM V1.1 detection-horizon +
alert-channel RULES into a loadable joblib bundle under
STARTER MOTOR/V1.1/models/horizon_window_rules/.

HONESTY FRAME (read this): this artifact is NOT a fitted ML model. It is a
deployable wrapper around two frozen, deterministic objects that REPLACE
per-truck RUL for the starter motor (per-truck day-precision RUL is
mathematically closed at n=34):
  1. the validated 10-week DETECTION HORIZON (k_star_sustained=10, ~70 days),
     with the AUROC-vs-lead-week decay curve; and
  2. the three ALERT CHANNELS (persistence / A1 crank-burst / A2 battery
     cascade) with their per-VIN historical first-fire leads.
No coefficients are fitted here. `is_ml_model` is False throughout.

Reconciliation gates (script aborts on any failure — no fudging):
  R1  horizon_curve.csv: auroc at k_weeks==0 rounds to 0.9357 AND
      k_star_sustained == 10.
  R2  embedded alert-policy has the same row count as the CSV (34), and every
      failed truck that fired a channel has a strictly-positive first-fire lead.
  R3  joblib round-trip: reloaded bundle reproduces the horizon table + k_star.

Outputs -> STARTER MOTOR/V1.1/models/horizon_window_rules/:
  V1_1_SM_horizon_window_bundle.joblib
  V1_1_SM_horizon_curve.csv           (provenance copy)
  V1_1_SM_alert_policy.csv            (provenance copy)
  V1_1_SM_rules_verification.json
  V1_1_SM_rules_MANIFEST.json
  README.md                          (written separately; hashed into MANIFEST)

Run: py -3 "STARTER MOTOR/V1.1/src/V1_1_SM_package_rules.py"
"""
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn

ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery")
RES = ROOT / "STARTER MOTOR" / "V1.1" / "results"
HORIZON_CSV = RES / "V1_1_SM_horizon_curve.csv"
ALERT_CSV = RES / "V1_1_SM_alert_policy.csv"
OUT = ROOT / "STARTER MOTOR" / "V1.1" / "models" / "horizon_window_rules"

FROZEN_AUROC_K0 = 0.9357     # horizon_curve k_weeks==0
FROZEN_K_STAR = 10           # validated sustained detection horizon (weeks)
DETECTION_WINDOW_DAYS = 70   # 10 weeks * 7
TIER_AMBER_GE, TIER_RED_GE = 0.35, 0.55   # cross-ref to classifier tier bands

ALERT_CHANNELS = {
    "persistence": "E3 sustained-risk persistence",
    "A1_crank_burst": "crank-burst rate spike",
    "A2_battery_cascade": "battery-voltage cascade",
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_head():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                              capture_output=True, text=True).stdout.strip()
    except Exception:
        return "unknown"


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    hz = pd.read_csv(HORIZON_CSV)
    al = pd.read_csv(ALERT_CSV)

    # ── R1: horizon reconciliation ──────────────────────────────────────────
    k0_rows = hz.loc[hz["k_weeks"] == 0, "auroc"]
    assert len(k0_rows) == 1, "R1 FAIL: horizon curve has no unique k_weeks==0 row"
    auroc_k0 = float(k0_rows.iloc[0])
    k_star = int(hz["k_star_sustained"].iloc[0])
    assert hz["k_star_sustained"].nunique() == 1, "R1 FAIL: k_star_sustained not constant"
    print(f"[R1] auroc(k=0) = {auroc_k0:.4f} (frozen {FROZEN_AUROC_K0}) ; "
          f"k_star_sustained = {k_star} (frozen {FROZEN_K_STAR})")
    assert round(auroc_k0, 4) == FROZEN_AUROC_K0, f"R1 FAIL: auroc(k=0)={auroc_k0}"
    assert k_star == FROZEN_K_STAR, f"R1 FAIL: k_star={k_star}"

    in_spec_max_week = int(hz.loc[hz["in_spec_range"] == True, "k_weeks"].max())  # noqa: E712
    auroc_by_week = [{"k_weeks": int(r.k_weeks), "auroc": float(r.auroc),
                      "ci95_lo": float(r.ci95_lo), "ci95_hi": float(r.ci95_hi),
                      "in_spec_range": bool(r.in_spec_range)}
                     for r in hz.itertuples(index=False)]

    # ── R2: alert-policy reconciliation ─────────────────────────────────────
    n_alert_rows = len(al)
    n_failed = int(al["failed"].sum())
    failed = al[al["failed"] == 1]
    fired = failed[failed["first_channel"].astype(str) != "NONE"].copy()
    leads = fired["lead_vs_t_end_d"].astype(float)
    all_positive = bool((leads > 0).all())
    n_failed_fired = int(len(fired))
    print(f"[R2] alert-policy rows = {n_alert_rows} (failed {n_failed}); "
          f"failed-truck channels fired = {n_failed_fired}; "
          f"all first-fire leads positive = {all_positive}")
    assert n_alert_rows == 34, f"R2 FAIL: expected 34 alert rows, got {n_alert_rows}"
    assert all_positive, f"R2 FAIL: non-positive failed first-fire lead present"

    lead_summary = {
        "metric": "lead_vs_t_end_d (days) at first-fire, failed trucks only",
        "n_failed_total": n_failed,
        "n_failed_fired": n_failed_fired,
        "n_failed_silent": n_failed - n_failed_fired,
        "median_days": float(np.median(leads)),
        "min_days": float(leads.min()),
        "max_days": float(leads.max()),
        "mean_days": round(float(leads.mean()), 1),
        "note": ("historical validation leads, not guarantees; "
                 "silent failed truck(s) fired no channel"),
    }

    alert_policy_records = al.where(pd.notnull(al), None).to_dict(orient="records")

    # ── assemble bundle (plain dict; no fitted estimator) ───────────────────
    env = {"python": platform.python_version(), "sklearn": sklearn.__version__,
           "numpy": np.__version__, "pandas": pd.__version__,
           "joblib": joblib.__version__, "platform": platform.platform()}
    bundle = {
        "component": "starter_motor",
        "artifact": "horizon_window_rules",
        "is_ml_model": False,
        "champion_version": "V1_1_SM",
        "created": date.today().isoformat(),
        "horizon": {
            "k_star_weeks": FROZEN_K_STAR,
            "detection_window_days": DETECTION_WINDOW_DAYS,
            "auroc_at_k0": auroc_k0,
            "auroc_by_week": auroc_by_week,
            "in_spec_max_week": in_spec_max_week,
        },
        "alert_channels": {
            **ALERT_CHANNELS,
            "per_vin_alert_policy": alert_policy_records,
        },
        "tier_bands": {"amber_ge": TIER_AMBER_GE, "red_ge": TIER_RED_GE},
        "validated_leads": lead_summary,
        "score_mapping": (
            "classifier RED -> schedule maintenance within the k*=10-week "
            "(~70-day) detection window; alert-channel first-fire "
            "(persistence / A1_crank_burst / A2_battery_cascade) gives the "
            "observed historical lead. AMBER -> watch; GREEN -> routine."),
        "honest_caveat": (
            "Deterministic detection-horizon + alert-channel rules plus a "
            "validated horizon constant (k*=10 weeks). NOT a fitted model — "
            "no coefficients are learned here (is_ml_model=False). This REPLACES "
            "per-truck day-precision RUL, which is mathematically closed at "
            "n=34. The per-VIN leads are historical validation observations, "
            "NOT forward guarantees."),
        "provenance": {
            "horizon_curve": "STARTER MOTOR/V1.1/results/V1_1_SM_horizon_curve.csv",
            "horizon_curve_sha256": sha256(HORIZON_CSV),
            "alert_policy": "STARTER MOTOR/V1.1/results/V1_1_SM_alert_policy.csv",
            "alert_policy_sha256": sha256(ALERT_CSV),
            "git_head": git_head(),
        },
        "environment": env,
    }
    bundle_path = OUT / "V1_1_SM_horizon_window_bundle.joblib"
    joblib.dump(bundle, bundle_path)

    # ── R3: round-trip ──────────────────────────────────────────────────────
    b2 = joblib.load(bundle_path)
    assert b2["horizon"]["k_star_weeks"] == FROZEN_K_STAR, "R3 FAIL: k_star"
    assert b2["horizon"]["auroc_by_week"] == auroc_by_week, "R3 FAIL: horizon table"
    assert b2["horizon"]["auroc_at_k0"] == auroc_k0, "R3 FAIL: auroc_at_k0"
    assert len(b2["alert_channels"]["per_vin_alert_policy"]) == n_alert_rows, \
        "R3 FAIL: alert-policy row count"
    print("[R3] joblib round-trip reproduces horizon table + k_star  OK")

    # ── provenance copies ───────────────────────────────────────────────────
    shutil.copy2(HORIZON_CSV, OUT / "V1_1_SM_horizon_curve.csv")
    shutil.copy2(ALERT_CSV, OUT / "V1_1_SM_alert_policy.csv")

    # ── verification.json ───────────────────────────────────────────────────
    verification = {
        "created": date.today().isoformat(),
        "artifact": "horizon_window_rules (rule-based, is_ml_model=False)",
        "R1_horizon_reconcile": {
            "auroc_at_k0": round(auroc_k0, 4), "frozen_auroc": FROZEN_AUROC_K0,
            "k_star_sustained": k_star, "frozen_k_star": FROZEN_K_STAR,
            "in_spec_max_week": in_spec_max_week, "pass": True},
        "R2_alert_policy": {
            "n_rows": n_alert_rows, "n_failed": n_failed,
            "n_failed_fired": n_failed_fired,
            "all_failed_first_fire_leads_positive": all_positive,
            "lead_median_days": lead_summary["median_days"],
            "lead_min_days": lead_summary["min_days"],
            "lead_max_days": lead_summary["max_days"], "pass": True},
        "R3_roundtrip": {"pass": True},
        "note": ("rule-based deployable wrapper around frozen detection-horizon "
                 "and alert channels; replaces per-truck RUL (closed at n=34)"),
        "environment": env,
    }
    (OUT / "V1_1_SM_rules_verification.json").write_text(
        json.dumps(verification, indent=2))

    # README (written by separate step if missing; hashed if present) ────────
    readme_path = OUT / "README.md"

    # ── manifest (hashes every emitted file + the two inputs) ───────────────
    files = sorted(p for p in OUT.iterdir()
                   if p.is_file() and p.name != "V1_1_SM_rules_MANIFEST.json")
    manifest = {
        "artifact": "V1_1_SM horizon + window rules (starter motor, rule-based)",
        "is_ml_model": False,
        "created": date.today().isoformat(),
        "git_head": git_head(),
        "environment": env,
        "files": [{"name": p.name, "bytes": p.stat().st_size, "sha256": sha256(p)}
                  for p in files],
        "inputs": [{"path": str(p.relative_to(ROOT)), "sha256": sha256(p)}
                   for p in (HORIZON_CSV, ALERT_CSV)],
        "readme_present": readme_path.exists(),
    }
    (OUT / "V1_1_SM_rules_MANIFEST.json").write_text(json.dumps(manifest, indent=2))

    print(f"\nPACKAGED OK -> {OUT}")
    for p in sorted(OUT.iterdir()):
        print(f"  {p.name}")
    print("\nR1 R2 R3 ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
