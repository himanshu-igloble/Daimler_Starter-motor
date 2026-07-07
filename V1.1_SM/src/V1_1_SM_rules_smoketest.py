"""
V1_1_SM_rules_smoketest.py — load-and-use smoke test for the packaged SM V1.1
horizon + window RULES bundle. Exits non-zero on any failure.

Run: py -3 "STARTER MOTOR/V1.1/src/V1_1_SM_rules_smoketest.py"
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

import joblib

ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery")
DEP = ROOT / "STARTER MOTOR" / "V1.1" / "models" / "horizon_window_rules"
BUNDLE = DEP / "V1_1_SM_horizon_window_bundle.joblib"
PREDICT = DEP / "V1_1_SM_predict.py"

EXPECT_KEYS = {"component", "artifact", "is_ml_model", "champion_version",
               "created", "horizon", "alert_channels", "tier_bands",
               "validated_leads", "score_mapping", "honest_caveat",
               "provenance", "environment"}


def main():
    if not BUNDLE.exists():
        print(f"BUNDLE MISSING: {BUNDLE}")
        return 1

    b = joblib.load(BUNDLE)
    missing = EXPECT_KEYS - set(b)
    assert not missing, f"bundle missing keys: {missing}"
    assert b["is_ml_model"] is False, "artifact must be rule-based (is_ml_model=False)"
    assert b["component"] == "starter_motor"
    assert b["champion_version"] == "V1_1_SM"

    hz = b["horizon"]
    assert hz["k_star_weeks"] == 10, f"k_star_weeks={hz['k_star_weeks']} != 10"
    assert hz["auroc_at_k0"] == 0.9357, f"auroc_at_k0={hz['auroc_at_k0']} != 0.9357"
    assert hz["detection_window_days"] == 70

    ap = b["alert_channels"]["per_vin_alert_policy"]
    assert len(ap) == 34, f"alert table has {len(ap)} rows, expected 34"

    assert b["tier_bands"] == {"amber_ge": 0.35, "red_ge": 0.55}

    # Exercise the SHIPPED loader in-process (folder has a space + dot; import
    # by file path). Verify the public library API against the bundle.
    _spec = importlib.util.spec_from_file_location("v1_1_sm_predict", str(PREDICT))
    m = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(m)

    win = m.maintenance_window("RED", b)
    assert win["window_weeks"] == 10, f"RED window_weeks={win['window_weeks']} != 10"
    assert win["window_days"] == 70
    assert win["action"] == "schedule within"
    assert m.maintenance_window("AMBER", b)["action"] == "watch"
    assert m.maintenance_window("GREEN", b)["action"] == "routine"

    assert m.horizon_auroc(0, b) == 0.9357
    ls = m.channel_lead_summary(b)
    assert ls["n_failed_fired"] >= 1 and ls["median_days"] > 0

    # CLI must exit 0 and print the rule-based banner.
    r = subprocess.run([sys.executable, str(PREDICT), "--tier", "RED", "--k-weeks", "0"],
                       capture_output=True, text=True)
    assert r.returncode == 0, f"predict.py CLI failed:\n{r.stderr}"
    assert "HORIZON + WINDOW RULES" in r.stdout, "CLI banner missing"
    assert "is_ml_model=False" in r.stdout, "CLI must declare rule-based"

    print("SM RULES SMOKE PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
