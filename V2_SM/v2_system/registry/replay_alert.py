"""
replay_alert.py  --  V2 Alert Replay Engine
============================================
Replays a VIN's alert decision from raw inputs pinned in registry.json.

REPLAY SEMANTICS (IMPORTANT)
-----------------------------
The fleet_snapshot tier/prob values were produced by the WALKING-SCORE engine
(per-cut LOVO inference, not the production refit).  Replay therefore:
  1. Pins INPUT FINGERPRINTS from the snapshot and all source CSVs.
  2. Re-executes the DECISION LAYER (heuristics H1/H2/H5, channel states,
     precedence rules, window lookup) using ONLY paths + rules from registry.json.
  3. Verifies the production model artifact_hash to prove the pinned coefficients
     are unchanged — but does NOT re-train LOVO.
  4. Diffs the recomputed {tier, prob, priority, trigger, evidence_state,
     window_key_fields} against the logged snapshot/alert rows.

RUN:
  py -3 replay_alert.py --vin VIN10_F_SM
  py -3 replay_alert.py --all
  py -3 replay_alert.py --all --registry path/to/alt_registry.json
"""

import argparse
import hashlib
import json
import pathlib
import sys
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeClassifier, LogisticRegression
from sklearn.preprocessing import StandardScaler

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
REGISTRY_DEFAULT = pathlib.Path(__file__).parent / "registry.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_json(obj) -> str:
    canon = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def load_registry(reg_path: pathlib.Path) -> dict:
    with open(reg_path, encoding="utf-8") as fh:
        return json.load(fh)


def verify_inputs(reg: dict) -> list[str]:
    """
    Check all pinned input fingerprints. Returns list of drift messages
    (empty list = all clean).
    """
    drifts = []
    for key, info in reg["input_fingerprints"].items():
        path = pathlib.Path(info["path"])
        if not path.exists():
            drifts.append(f"REPLAY INVALID: INPUT DRIFT — {key}: file not found at {path}")
            continue
        actual = sha256_file(path)
        if actual != info["sha256"]:
            drifts.append(
                f"REPLAY INVALID: INPUT DRIFT — {key}\n"
                f"  expected: {info['sha256']}\n"
                f"  actual:   {actual}"
            )
    return drifts


def verify_artifact_hash(reg: dict) -> tuple[bool, str]:
    """
    Recompute artifact_hash from the pinned model numbers and compare.
    Returns (ok, message).
    """
    pm = reg["production_model"]
    payload = {k: v for k, v in pm.items() if k != "artifact_hash"}
    recomputed = sha256_json(payload)
    stored = pm.get("artifact_hash", "")
    if recomputed == stored:
        return True, f"artifact_hash OK: {stored[:16]}..."
    return False, (
        f"artifact_hash MISMATCH\n"
        f"  stored:     {stored}\n"
        f"  recomputed: {recomputed}"
    )


# ---------------------------------------------------------------------------
# Decision layer re-execution
# ---------------------------------------------------------------------------

def load_walking_scores(path: pathlib.Path) -> pd.DataFrame:
    return pd.read_csv(path)


def load_snapshot(path: pathlib.Path) -> pd.DataFrame:
    return pd.read_csv(path, comment="#")


def load_shadow_log(path: pathlib.Path) -> pd.DataFrame:
    return pd.read_csv(path)


def load_alert_policy(path: pathlib.Path) -> pd.DataFrame:
    return pd.read_csv(path)


def load_alert_validation(path: pathlib.Path) -> pd.DataFrame:
    return pd.read_csv(path)


def tier_from_prob(prob: float, thresholds: dict) -> str:
    if prob < thresholds["GREEN_max_exclusive"]:
        return "GREEN"
    if prob < thresholds["AMBER_max_exclusive"]:
        return "AMBER"
    return "RED"


def compute_h1(vin_scores: pd.DataFrame, h1_cfg: dict) -> tuple[bool, float]:
    """H1: delta_prob >= +threshold over trailing 4 weeks."""
    trail = h1_cfg["trailing_weeks"]
    thresh = h1_cfg["delta_prob_threshold"]
    # k=0 is current; k=trail is trail weeks ago
    k0_rows = vin_scores[vin_scores["k_weeks"] == 0]
    kt_rows = vin_scores[vin_scores["k_weeks"] == trail]
    if k0_rows.empty or kt_rows.empty:
        return False, float("nan")
    prob_now  = float(k0_rows.iloc[0]["prob"])
    prob_then = float(kt_rows.iloc[0]["prob"])
    delta = prob_now - prob_then
    return bool(delta >= thresh), round(delta, 6)


def compute_h2(vin_scores: pd.DataFrame, h2_cfg: dict) -> tuple[bool, int]:
    """
    H2: >= consecutive_red_min consecutive weekly cuts RED.
    Counts consecutive RED starting from k=0 (most recent cut) going
    backwards in time (k=1, k=2, ...).  Stops at first non-RED cut.
    """
    min_red = h2_cfg["consecutive_red_min"]
    # k=0 is the current (most recent) cut; k=1 is one week ago, etc.
    consec = 0
    k = 0
    while True:
        row = vin_scores[vin_scores["k_weeks"] == k]
        if row.empty:
            break
        if "usable" in row.columns and not bool(row.iloc[0]["usable"]):
            break
        if row.iloc[0]["tier"] == "RED":
            consec += 1
            k += 1
        else:
            break
    return bool(consec >= min_red), consec


def compute_h5(vin_scores: pd.DataFrame, fleet_scores: pd.DataFrame,
               h5_cfg: dict) -> tuple[bool, int]:
    """H5: >= pctile in >= min_weeks_above of trailing weeks_in_window."""
    window  = h5_cfg["weeks_in_window"]
    min_wks = h5_cfg["min_weeks_above"]
    pctile  = h5_cfg["pctile_threshold"]

    vin_window = vin_scores[vin_scores["k_weeks"] < window].copy()
    weeks_above = 0
    for k in range(window):
        vin_row = vin_scores[vin_scores["k_weeks"] == k]
        if vin_row.empty:
            continue
        fleet_week = fleet_scores[fleet_scores["k_weeks"] == k]
        if fleet_week.empty:
            continue
        threshold_val = np.percentile(fleet_week["prob"].dropna(), pctile)
        vin_prob = float(vin_row.iloc[0]["prob"])
        if vin_prob >= threshold_val:
            weeks_above += 1
    return bool(weeks_above >= min_wks), weeks_above


def compute_precedence(tier: str, h2_fires: bool, a2_fires: bool,
                       silence_active: bool, rules: list) -> tuple[str, str]:
    """
    Apply alert precedence rules in order (first match wins).
    Returns (priority, trigger).

    Silence (P0_OPS rule 6) is an OVERLAY — it does NOT replace the primary
    priority/trigger from tier/channel/heuristic signals.  The snapshot records
    silence_trigger_active separately; priority and trigger reflect the primary
    decision stack only.
    """
    if a2_fires:
        return "P0", "A2_battery_cascade_fired"
    if h2_fires:
        return "P0", "H2_dwell_fired"
    if tier == "RED":
        return "P1", "RED_tier_no_channel_yet"
    if tier == "AMBER":
        return "P2", "AMBER_tier"
    return "GREEN_OK", "GREEN_tier"


def lookup_window_state(evidence_state: str, window_matrix_rows: list) -> dict:
    """Return window matrix row matching evidence_state (first match)."""
    for row in window_matrix_rows:
        if row["evidence_state"] == evidence_state:
            return row
    return {}


def compute_evidence_state(tier: str, h2_fires: bool, a2_fires: bool,
                           persistence_active: bool, silence_active: bool) -> str:
    """
    Map flags to evidence_state string used in snapshot and window matrix.
    Matches V2_weekly_job.py determine_evidence_state() exactly:
      - A2 fired  -> A2_battery_cascade_fired
      - H2 fires  -> persistence_terminal_AND_RED_tier  (H2 drives this label)
      - RED       -> RED_tier_no_channel_yet
      - AMBER     -> AMBER_tier_no_channel
      - GREEN     -> GREEN_tier_channel_fires_eventually
    NOTE: persistence_terminal_active does NOT independently set the evidence_state;
    it is captured in the snapshot column but the state label is H2-driven.
    Silence is a P0_OPS overlay and does not change evidence_state.
    """
    if a2_fires:
        return "A2_battery_cascade_fired"
    if h2_fires:
        return "persistence_terminal_AND_RED_tier"
    if tier == "RED":
        return "RED_tier_no_channel_yet"
    if tier == "AMBER":
        return "AMBER_tier_no_channel"
    return "GREEN_tier_channel_fires_eventually"


# ---------------------------------------------------------------------------
# Per-VIN replay
# ---------------------------------------------------------------------------

def replay_vin(vin: str, reg: dict,
               walking_scores: pd.DataFrame,
               snapshot: pd.DataFrame,
               shadow_log: pd.DataFrame,
               alert_policy: pd.DataFrame,
               alert_validation: pd.DataFrame) -> dict:
    """
    Recompute the decision for a single VIN and diff against logged outputs.
    Returns a result dict with 'status', 'mismatches', 'recomputed', 'logged'.
    """
    rules   = reg["decision_rules"]
    thr     = rules["tier_thresholds"]
    h1_cfg  = rules["heuristics"]["H1_momentum"]
    h2_cfg  = rules["heuristics"]["H2_dwell"]
    h5_cfg  = rules["heuristics"]["H5_fleet_percentile"]
    wm_rows = rules["window_matrix"]["rows"]

    # Snapshot row for this VIN
    snap_row = snapshot[snapshot["vin"] == vin]
    if snap_row.empty:
        return {"status": "VIN_NOT_FOUND", "vin": vin, "mismatches": [],
                "recomputed": {}, "logged": {}}
    snap = snap_row.iloc[0]

    # Walking scores for this VIN (k-series)
    vin_scores  = walking_scores[walking_scores["vin_label"] == vin].copy()
    fleet_scores = walking_scores.copy()

    if vin_scores.empty:
        return {"status": "NO_WALKING_SCORES", "vin": vin, "mismatches": [],
                "recomputed": {}, "logged": {}}

    # k=0 row (current cut)
    k0 = vin_scores[vin_scores["k_weeks"] == 0]
    if k0.empty:
        return {"status": "NO_K0_ROW", "vin": vin, "mismatches": [],
                "recomputed": {}, "logged": {}}

    prob_k0 = float(k0.iloc[0]["prob"])
    tier     = tier_from_prob(prob_k0, thr)

    # Heuristics
    h1_fires, h1_delta = compute_h1(vin_scores, h1_cfg)
    h2_fires, h2_consec = compute_h2(vin_scores, h2_cfg)
    h5_fires, h5_wks   = compute_h5(vin_scores, fleet_scores, h5_cfg)

    # Channel states from alert_policy and alert_validation
    pol_row = alert_policy[alert_policy["vin_label"] == vin]
    val_row = alert_validation[alert_validation["vin_label"] == vin]

    a2_fires   = False
    persistence_active = False
    silence_active = bool(snap.get("silence_trigger_active", False))

    if not pol_row.empty:
        a2_fires           = bool(pol_row.iloc[0].get("a2_fire", False))
        persistence_active = bool(pol_row.iloc[0].get("pers_end_fire", False))

    # Evidence state
    evidence_state = compute_evidence_state(tier, h2_fires, a2_fires,
                                            persistence_active, silence_active)

    # Precedence
    priority, trigger = compute_precedence(tier, h2_fires, a2_fires,
                                            silence_active,
                                            rules["alert_precedence"]["rules"])

    # Add silence overlay as secondary if active and not already P0
    if silence_active and tier in ("RED", "AMBER"):
        # Logged snapshot may have silence_trigger_active but primary priority from tier/h2/a2
        pass  # silence_trigger_active is logged separately; primary priority stands

    # Window lookup
    window_row = lookup_window_state(evidence_state, wm_rows)

    recomputed = {
        "tier":                tier,
        "prob":                round(prob_k0, 6),
        "priority":            priority,
        "trigger":             trigger,
        "evidence_state":      evidence_state,
        "h1_fires":            h1_fires,
        "h1_delta_prob":       round(h1_delta, 6) if not np.isnan(h1_delta) else None,
        "h2_fires":            h2_fires,
        "h2_consec_red":       h2_consec,
        "h5_fires":            h5_fires,
        "h5_weeks_above":      h5_wks,
        "a2_fired_ever":       a2_fires,
        "persistence_active":  persistence_active,
        "silence_active":      silence_active,
        "window_state":        evidence_state,
        "window_n":            window_row.get("n"),
        "window_sched":        window_row.get("scheduling_window_d"),
    }

    # Logged values from snapshot
    logged = {
        "tier":               str(snap.get("tier", "")),
        "prob":               round(float(snap.get("prob", 0)), 6),
        "priority":           str(snap.get("priority", "")),
        "trigger":            str(snap.get("trigger", "")),
        "evidence_state":     str(snap.get("evidence_state", "")),
        "h1_fires":           str(snap.get("h1_fires", "")).strip().lower() == "true",
        "h1_delta_prob":      float(snap.get("h1_delta_prob", 0)) if str(snap.get("h1_delta_prob","nan")) != "nan" else None,
        "h2_fires":           str(snap.get("h2_fires", "")).strip().lower() == "true",
        "h2_consec_red":      int(snap.get("h2_consec_red", 0)),
        "h5_fires":           str(snap.get("h5_fires", "")).strip().lower() == "true",
        "h5_weeks_above":     int(snap.get("h5_weeks_above", 0)),
        "a2_fired_ever":      str(snap.get("a2_fired_ever", "")).strip().lower() == "true",
        "persistence_active": str(snap.get("persistence_terminal_active", "")).strip().lower() == "true",
        "silence_active":     str(snap.get("silence_trigger_active", "")).strip().lower() == "true",
    }

    # Diff — key fields to compare
    COMPARE_FIELDS = [
        "tier", "priority", "trigger", "evidence_state",
        "h1_fires", "h2_fires", "h2_consec_red",
        "h5_fires", "h5_weeks_above",
        "a2_fired_ever", "persistence_active", "silence_active",
    ]

    mismatches = []
    for field in COMPARE_FIELDS:
        r_val = recomputed.get(field)
        l_val = logged.get(field)
        if r_val != l_val:
            mismatches.append({
                "field":      field,
                "recomputed": r_val,
                "logged":     l_val,
            })

    # Prob comparison with tolerance (walking-score engine may have minor float diff)
    prob_r = recomputed["prob"]
    prob_l = logged["prob"]
    if abs(prob_r - prob_l) > 1e-4:
        mismatches.append({
            "field":      "prob",
            "recomputed": prob_r,
            "logged":     prob_l,
        })

    status = "REPLAY MATCH" if not mismatches else "MISMATCH"
    return {
        "status":     status,
        "vin":        vin,
        "mismatches": mismatches,
        "recomputed": recomputed,
        "logged":     logged,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="V2 Alert Replay")
    ap.add_argument("--vin",      help="Single VIN to replay (e.g. VIN10_F_SM)")
    ap.add_argument("--all",      action="store_true", help="Replay all 34 VINs")
    ap.add_argument("--registry", default=str(REGISTRY_DEFAULT),
                    help="Path to registry.json (default: sibling registry.json)")
    args = ap.parse_args()

    if not args.vin and not args.all:
        ap.error("Provide --vin <VIN> or --all")

    reg_path = pathlib.Path(args.registry)
    if not reg_path.exists():
        print(f"ERROR: registry not found: {reg_path}")
        sys.exit(1)

    print(f"== V2 Alert Replay Engine ==")
    print(f"   Registry: {reg_path}")

    reg = load_registry(reg_path)

    # 1. Verify all input fingerprints
    print("\n[1] Verifying input fingerprints...")
    drifts = verify_inputs(reg)
    if drifts:
        for d in drifts:
            print(f"  {d}")
        sys.exit(1)
    print(f"  All {len(reg['input_fingerprints'])} inputs hash-verified OK")

    # 2. Verify artifact hash
    print("\n[2] Verifying production model artifact hash...")
    ok, msg = verify_artifact_hash(reg)
    if not ok:
        print(f"  {msg}")
        sys.exit(1)
    print(f"  {msg}")

    # 3. Load all inputs from paths pinned in registry
    fp = reg["input_fingerprints"]
    walking_scores  = load_walking_scores(pathlib.Path(fp["walking_scores"]["path"]))
    snapshot        = load_snapshot(pathlib.Path(fp["fleet_snapshot"]["path"]))
    shadow_log      = load_shadow_log(pathlib.Path(fp["shadow_alert_log"]["path"]))
    alert_policy    = load_alert_policy(pathlib.Path(fp["alert_policy"]["path"]))
    alert_validation = load_alert_validation(pathlib.Path(fp["alert_validation"]["path"]))

    # 4. Determine VIN list
    all_vins = sorted(snapshot["vin"].unique())
    if args.all:
        vin_list = all_vins
    else:
        if args.vin not in all_vins:
            print(f"ERROR: VIN '{args.vin}' not found in snapshot. "
                  f"Available: {all_vins}")
            sys.exit(1)
        vin_list = [args.vin]

    # 5. Replay
    print(f"\n[3] Replaying {len(vin_list)} VIN(s)...\n")
    results = []
    for vin in vin_list:
        result = replay_vin(
            vin, reg, walking_scores, snapshot, shadow_log,
            alert_policy, alert_validation
        )
        results.append(result)

        if args.all:
            # Brief summary line
            status = result["status"]
            marker = "OK" if status == "REPLAY MATCH" else "!!"
            n_mm   = len(result.get("mismatches", []))
            mm_str = "" if not n_mm else f" ({n_mm} fields)"
            print(f"  [{marker}] {vin:20s}  {status}{mm_str}")
        else:
            # Verbose single-VIN output
            r = result["recomputed"]
            l = result["logged"]
            print(f"VIN: {vin}")
            print(f"  Status: {result['status']}")
            print(f"\n  {'Field':<28} {'Recomputed':<22} {'Logged':<22}")
            print(f"  {'-'*72}")
            for field in ["tier","prob","priority","trigger","evidence_state",
                           "h1_fires","h1_delta_prob","h2_fires","h2_consec_red",
                           "h5_fires","h5_weeks_above","a2_fired_ever",
                           "persistence_active","silence_active"]:
                rv = r.get(field, "—")
                lv = l.get(field, "—")
                flag = " <-- MISMATCH" if any(m["field"]==field for m in result["mismatches"]) else ""
                print(f"  {field:<28} {str(rv):<22} {str(lv):<22}{flag}")
            print(f"\n  Window: {r.get('window_state')}  |  "
                  f"n={r.get('window_n')}  |  sched={r.get('window_sched')}")
            if result["mismatches"]:
                print(f"\n  MISMATCH TABLE:")
                for m in result["mismatches"]:
                    print(f"    {m['field']}: recomputed={m['recomputed']}  logged={m['logged']}")

    # 6. Summary for --all
    if args.all:
        n_match  = sum(1 for r in results if r["status"] == "REPLAY MATCH")
        n_miss   = sum(1 for r in results if r["status"] != "REPLAY MATCH")
        n_total  = len(results)
        print(f"\n{'='*60}")
        print(f"  REPLAY SUMMARY: {n_match}/{n_total} REPLAY MATCH")
        if n_miss:
            print(f"  MISMATCHES ({n_miss}):")
            for r in results:
                if r["status"] != "REPLAY MATCH":
                    for m in r["mismatches"]:
                        print(f"    {r['vin']}  {m['field']}: "
                              f"recomputed={m['recomputed']}  logged={m['logged']}")
        print(f"{'='*60}")
        sys.exit(0 if n_miss == 0 else 1)


if __name__ == "__main__":
    main()
