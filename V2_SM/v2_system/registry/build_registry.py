"""
build_registry.py  --  V2 Model Registry Builder
=================================================
Generates registry.json: a deterministic, byte-stable audit snapshot that
pins all input fingerprints, production model artifacts, decision rules, and
validation-of-record metadata so that every historical alert can be replayed
from a known, hash-verified state.

DETERMINISM CONTRACT
- Same inputs  -> identical registry.json bytes (except the `generated` field,
  which is sourced from the mtime of fleet_snapshot.csv, NOT wall-clock).
- JSON keys are sorted alphabetically at every nesting level.
- Floating-point numbers are round-tripped through repr() to avoid
  serializer-dependent precision drift.

RUN:  py -3 build_registry.py [--out <path>]
"""

import hashlib
import json
import os
import sys
import pathlib
import struct

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeClassifier, LogisticRegression
from sklearn.preprocessing import StandardScaler

# ---------------------------------------------------------------------------
# Paths  (all absolute; relative to this file's location)
# ---------------------------------------------------------------------------
REPO = pathlib.Path(r"D:\Daimler-starter_motor_alternator_battery")
SM   = REPO / "STARTER MOTOR"
V2   = SM / "V2_program" / "v2_system"

PATHS = {
    "config":           V2 / "v2_config.json",
    "cards_json":       V2 / "cards" / "cards.json",
    "walking_scores":   SM / "V2_program" / "analysis" / "heuristics" / "out" / "walking_scores.csv",
    "feature_matrix":   SM / "V1.1" / "results" / "V1_1_SM_feature_matrix.csv",
    "alert_policy":     SM / "V1.1" / "results" / "V1_1_SM_alert_policy.csv",
    "alert_validation": SM / "V1.1" / "results" / "V1_1_SM_alert_validation.csv",
    "window_matrix":    SM / "V2_program" / "analysis" / "econ" / "failure_window_matrix.csv",
    "fleet_snapshot":   V2 / "out" / "fleet_snapshot.csv",
    "shadow_alert_log": V2 / "out" / "shadow_alert_log.csv",
}

REGISTRY_OUT = pathlib.Path(__file__).parent / "registry.json"

FEATURES = [
    "vsi_withinwk_std_ratio_30d_w",
    "rest_vsi_p05_delta90",
    "vsi_range_trend",
    "dip_depth_last90_delta",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_json(obj: dict) -> str:
    """Hash a JSON-serialisable object deterministically."""
    canon = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()


def recompute_config_hash(cfg: dict) -> str:
    """
    Replicate the stored config_hash: sha256 over the config dict
    with the config_hash key itself removed.
    Matches V2_weekly_pipeline.py _config_hash_computed() exactly:
      json.dumps(stripped, sort_keys=True, separators=(',',':'), ensure_ascii=False)
    """
    stripped = {k: v for k, v in cfg.items() if k != "config_hash"}
    canon = json.dumps(stripped, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def fit_production_model(feat_matrix_path: pathlib.Path):
    """
    Deterministic refit of the production model on all-34 trucks:
      - 4 modal features (from v2_config.json)
      - median impute (all-34 medians)
      - StandardScaler
      - RidgeClassifier(alpha=1.0)
      - Platt calibration (LogisticRegression on decision values)
    Returns dict of model artefacts.
    """
    df = pd.read_csv(feat_matrix_path)
    X = df[FEATURES].copy()
    y = df["failed"].values.astype(int)

    # Median impute (global, all-34)
    medians = X.median()
    X_imp = X.fillna(medians)

    # Scale
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_imp)

    # Ridge
    ridge = RidgeClassifier(alpha=1.0, random_state=42)
    ridge.fit(X_scaled, y)

    # Platt calibration on decision values
    dv = ridge.decision_function(X_scaled).reshape(-1, 1)
    platt = LogisticRegression(C=1e9, solver="lbfgs", random_state=42)
    platt.fit(dv, y)

    artefacts = {
        "features":        FEATURES,
        "impute_medians":  {f: float(repr(medians[f])) for f in FEATURES},
        "scaler_mean":     [float(repr(v)) for v in scaler.mean_],
        "scaler_scale":    [float(repr(v)) for v in scaler.scale_],
        "ridge_coef":      [float(repr(float(v))) for v in np.ravel(ridge.coef_)],
        "ridge_intercept": float(repr(float(np.ravel(ridge.intercept_)[0]))),
        "platt_a":         float(repr(platt.coef_[0][0])),
        "platt_b":         float(repr(platt.intercept_[0])),
    }
    return artefacts


def compute_artifact_hash(artefacts: dict) -> str:
    """sha256 over the canonicalized model numbers (no wall-clock)."""
    payload = {k: v for k, v in artefacts.items() if k != "artifact_hash"}
    return sha256_json(payload)


def snapshot_mtime_str(snapshot_path: pathlib.Path) -> str:
    mtime = os.path.getmtime(snapshot_path)
    import datetime
    return datetime.datetime.utcfromtimestamp(mtime).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build(out_path: pathlib.Path = REGISTRY_OUT) -> dict:
    print("== V2 Registry Builder ==")

    # 1. Load config (utf-8 required to match pipeline hash computation)
    with open(PATHS["config"], encoding="utf-8") as fh:
        cfg = json.load(fh)

    stored_hash   = cfg.get("config_hash", "")
    recomputed_hash = recompute_config_hash(cfg)

    if stored_hash != recomputed_hash:
        print(f"\nERROR: config_hash MISMATCH")
        print(f"  Stored:     {stored_hash}")
        print(f"  Recomputed: {recomputed_hash}")
        sys.exit(1)
    print(f"  config hash OK: {recomputed_hash[:16]}...")

    # 2. Fit production model
    print("  Fitting production model on all-34...")
    artefacts = fit_production_model(PATHS["feature_matrix"])
    artefacts["artifact_hash"] = compute_artifact_hash(artefacts)
    print(f"  artifact_hash: {artefacts['artifact_hash'][:16]}...")

    # 3. Input fingerprints
    print("  Computing input fingerprints...")
    input_fingerprints = {}
    for key, path in PATHS.items():
        if key == "config":  # config is covered by config_hash
            continue
        h = sha256_file(path)
        input_fingerprints[key] = {"path": str(path), "sha256": h}
        print(f"    {key}: {h[:12]}...")

    # 4. Validation of record (verbatim from config)
    vor = cfg["model"]["validation_of_record"]

    # 5. Decision rules verbatim from config
    decision_rules = {
        "tier_thresholds":  cfg["tier_thresholds"],
        "heuristics":       cfg["heuristics"],
        "channels":         cfg["channels"],
        "alert_precedence": cfg["alert_precedence"],
        "window_matrix":    cfg["window_matrix"],
    }

    # 6. Generated timestamp from snapshot mtime (deterministic)
    generated = snapshot_mtime_str(PATHS["fleet_snapshot"])

    # 7. Assemble registry
    registry = {
        "schema_version": "1.0.0",
        "generated": generated,
        "config": {
            "version":     cfg["config_version"],
            "config_hash": recomputed_hash,
        },
        "validation_of_record": vor,
        "production_model": artefacts,
        "input_fingerprints": input_fingerprints,
        "decision_rules": decision_rules,
    }

    # 8. Write  (sort_keys=True + separators for determinism)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_str = json.dumps(registry, sort_keys=True, indent=2, separators=(",", ": "))
    out_path.write_text(out_str, encoding="utf-8")
    print(f"\n  registry.json written -> {out_path}")
    print(f"  Top-level keys: {list(registry.keys())}")
    return registry


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REGISTRY_OUT))
    args = ap.parse_args()
    build(pathlib.Path(args.out))
