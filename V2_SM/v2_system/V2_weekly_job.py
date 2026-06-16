"""
V2_weekly_job.py  — SM V2 Phase-B Weekly Scoring Job
=====================================================
Usage:
    py -3 V2_weekly_job.py [--as-of END]

    --as-of END   ISO date string (YYYY-MM-DD) for the scoring cut-off date.
                  Defaults to the k=0 state (end of available data per-VIN).

Outputs (under out/):
    fleet_snapshot.csv     — 34-row summary; label column is SHADOW-EVAL-ONLY
    shadow_alert_log.csv   — one row per active alert with evidence + window

Do NOT modify thresholds — frozen at config_version 2.1.0-B.
Refit only via D8 gates.

Onboarding (B3) maturity gating:
    Trucks with fewer than onboarding.min_weeks_mature (12) observation weeks
    are marked immature. Immature trucks have their display tier capped at AMBER,
    H1/H2/H5 heuristics suppressed, and evidence_state forced to IMMATURE_<12wk_fleet_prior.
    NOTE: weeks_observed is OPERATIONAL METADATA for maturity gating only —
    observation length remains BANNED as a model feature (leak class D5).
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# ── Paths ────────────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent
SM_ROOT = HERE.parent.parent      # .../STARTER MOTOR  (v2_system -> V2_program -> STARTER MOTOR)
CONFIG_PATH = HERE / "v2_config.json"
OUT_DIR = HERE / "out"
OUT_DIR.mkdir(parents=True, exist_ok=True)

WALKING_SCORES = SM_ROOT / "V2_program" / "analysis" / "heuristics" / "out" / "walking_scores.csv"
HEURISTIC_FIRES = SM_ROOT / "V2_program" / "analysis" / "heuristics" / "out" / "heuristic_fires.csv"
ALERT_POLICY = SM_ROOT / "V1.1" / "results" / "V1_1_SM_alert_policy.csv"
ALERT_VALIDATION = SM_ROOT / "V1.1" / "results" / "V1_1_SM_alert_validation.csv"
DATA_QUALITY = SM_ROOT / "results" / "V1_SM_data_quality.csv"
WINDOW_MATRIX = SM_ROOT / "V2_program" / "analysis" / "econ" / "failure_window_matrix.csv"

# ── Config (frozen parameters) ────────────────────────────────────────────────
with open(CONFIG_PATH, encoding="utf-8") as _fh:
    CFG = json.load(_fh)

TIER_GREEN_MAX = 0.35
TIER_AMBER_MIN = 0.35
TIER_AMBER_MAX = 0.55
TIER_RED_MIN   = 0.55

H1_DELTA_THRESHOLD  = 0.15   # Δprob >= +0.15 over trailing 4 weeks
H1_TRAILING_WEEKS   = 4
H2_CONSEC_RED_MIN   = 3      # >=3 consecutive RED cuts
H5_PCTILE           = 85     # >=p85 of fleet
H5_WINDOW_WEEKS     = 6
H5_MIN_ABOVE        = 4      # >=4 of trailing 6 weeks

SILENCE_DAYS        = 30     # no telemetry threshold
WATCHLIST           = set(CFG["watchlist"]["vins"])
SMA_DEAD            = set(CFG["cohort_masks"]["SMA_dead"]["vins"])

# ── Onboarding / maturity config (B3) ────────────────────────────────────────
_OB = CFG.get("onboarding", {})
MIN_WEEKS_MATURE: int = int(_OB.get("min_weeks_mature", 12))
IMMATURE_TIER_CAP: str = _OB.get("immature_tier_cap", "AMBER")
IMMATURE_SUPPRESS: set = set(_OB.get("immature_suppress", ["H1", "H2", "H5"]))
# weeks_observed is OPERATIONAL METADATA for maturity gating only —
# observation length remains BANNED as a model feature (leak class D5).

TIMESTAMP_NOW = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def load_data() -> tuple:
    """Load all upstream CSVs into DataFrames."""
    ws = pd.read_csv(WALKING_SCORES)
    ws["cut_date"] = pd.to_datetime(ws["cut_date"])
    hf = pd.read_csv(HEURISTIC_FIRES)
    ap = pd.read_csv(ALERT_POLICY)
    av = pd.read_csv(ALERT_VALIDATION)
    dq = pd.read_csv(DATA_QUALITY)
    dq["t_end"] = pd.to_datetime(dq["t_end"])
    return ws, hf, ap, av, dq


def compute_weeks_observed(ws: pd.DataFrame, vin: str) -> int:
    """
    Return the number of distinct k_weeks values available for this VIN in
    walking_scores.csv.  This equals the number of masked observation windows
    the score engine has computed for the truck.

    OPERATIONAL METADATA for maturity gating only.
    weeks_observed must NOT be used as a model feature — observation length
    is a banned feature class (leak class D5 in v2_config.json).
    """
    return int(ws[ws["vin_label"] == vin]["k_weeks"].nunique())


def apply_maturity_gate(
    vin: str,
    tier_raw: str,
    prob: float,
    weeks_observed: int,
    h1: dict,
    h2: dict,
    h5: dict,
) -> dict:
    """
    Apply onboarding maturity gate (B3).

    For trucks with weeks_observed < MIN_WEEKS_MATURE:
      - tier display is capped at IMMATURE_TIER_CAP (AMBER)
      - H1, H2, H5 heuristics are suppressed (set to False with reason)
      - priority is computed from capped tier
      - immature_badge=True, evidence_state forced to IMMATURE_<12wk_fleet_prior

    For mature trucks: all values pass through unchanged.

    Returns a dict with keys:
      immature, tier_display, tier_uncapped, h1_fires, h2_fires, h5_fires,
      suppress_reason
    """
    immature = weeks_observed < MIN_WEEKS_MATURE

    # Tier cap logic — only RED gets capped; GREEN/AMBER unchanged
    tier_uncapped = tier_raw
    if immature and tier_raw == "RED":
        tier_display = IMMATURE_TIER_CAP   # cap RED → AMBER
    else:
        tier_display = tier_raw

    # Heuristic suppression
    if immature:
        suppress_reason = (
            f"immature_truck: weeks_observed={weeks_observed} < "
            f"min_weeks_mature={MIN_WEEKS_MATURE}; "
            f"H1/H2/H5 suppressed per onboarding policy"
        )
        h1_fires_eff = False if "H1" in IMMATURE_SUPPRESS else h1["h1_fires"]
        h2_fires_eff = False if "H2" in IMMATURE_SUPPRESS else h2["h2_fires"]
        h5_fires_eff = False if "H5" in IMMATURE_SUPPRESS else h5["h5_fires"]
    else:
        suppress_reason = ""
        h1_fires_eff = h1["h1_fires"]
        h2_fires_eff = h2["h2_fires"]
        h5_fires_eff = h5["h5_fires"]

    return {
        "immature": immature,
        "tier_display": tier_display,
        "tier_uncapped": tier_uncapped,
        "h1_fires": h1_fires_eff,
        "h2_fires": h2_fires_eff,
        "h5_fires": h5_fires_eff,
        "suppress_reason": suppress_reason,
    }


def get_k0_scores(ws: pd.DataFrame) -> pd.DataFrame:
    """Return the k=0 row for each VIN (latest available state)."""
    return ws[ws["k_weeks"] == 0].copy().set_index("vin_label")


def compute_h1_momentum(ws: pd.DataFrame, vin: str) -> dict:
    """
    H1: Δprob >= +0.15 over trailing 4 weeks (k=0 to k=H1_TRAILING_WEEKS).
    Returns {'h1_fires': bool, 'h1_delta': float | None}
    """
    vd = ws[ws["vin_label"] == vin].sort_values("k_weeks").reset_index(drop=True)
    if len(vd) <= H1_TRAILING_WEEKS:
        return {"h1_fires": False, "h1_delta": None}
    p_now  = vd.loc[vd["k_weeks"] == 0, "prob"].values
    p_prev = vd.loc[vd["k_weeks"] == H1_TRAILING_WEEKS, "prob"].values
    if len(p_now) == 0 or len(p_prev) == 0:
        return {"h1_fires": False, "h1_delta": None}
    delta = float(p_now[0]) - float(p_prev[0])
    return {"h1_fires": delta >= H1_DELTA_THRESHOLD, "h1_delta": round(delta, 4)}


def compute_h2_dwell(ws: pd.DataFrame, vin: str) -> dict:
    """
    H2: >=3 consecutive RED cuts starting from k=0.
    Returns {'h2_fires': bool, 'h2_consec_red': int}
    """
    vd = ws[ws["vin_label"] == vin].sort_values("k_weeks").reset_index(drop=True)
    consec = 0
    for _, row in vd.iterrows():
        if row["tier"] == "RED":
            consec += 1
        else:
            break
    return {"h2_fires": consec >= H2_CONSEC_RED_MIN, "h2_consec_red": consec}


def compute_h5_fleet_pctile(ws: pd.DataFrame, vin: str) -> dict:
    """
    H5: score >= p85 of fleet in the same week for >=4 of trailing 6 weeks.
    Uses decision_value as the score (same unit as fleet-wide walking scores).
    Returns {'h5_fires': bool, 'h5_weeks_above': int}
    """
    weeks_above = 0
    for k in range(H5_WINDOW_WEEKS):
        week_scores = ws[ws["k_weeks"] == k]["decision_value"].dropna()
        if len(week_scores) < 5:
            continue
        p85 = np.percentile(week_scores, H5_PCTILE)
        vin_row = ws[(ws["vin_label"] == vin) & (ws["k_weeks"] == k)]
        if len(vin_row) == 0:
            continue
        vin_score = vin_row["decision_value"].values[0]
        if np.isfinite(vin_score) and vin_score >= p85:
            weeks_above += 1
    return {"h5_fires": weeks_above >= H5_MIN_ABOVE, "h5_weeks_above": weeks_above}


def get_channel_states(vin: str, av: pd.DataFrame, ap: pd.DataFrame) -> dict:
    """
    Extract channel states from alert CSVs:
      - a2_fired_ever: bool (from alert_validation.a2_fire)
      - persistence_terminal_active: bool (from alert_validation.pers_fire_end)
      - a1_episodes: int (from alert_validation.a1_n_episodes)
      - a1_applicable: bool
    """
    av_row = av[av["vin_label"] == vin]
    if len(av_row) == 0:
        return {
            "a2_fired_ever": False,
            "persistence_terminal_active": False,
            "a1_episodes": 0,
            "a1_applicable": False,
        }
    r = av_row.iloc[0]
    a1_fire_val = r.get("a1_fire", False)
    # Handle "n/a (SMA-dead)" entries
    a1_fire_bool = (str(a1_fire_val).strip().lower() == "true") if isinstance(a1_fire_val, str) else bool(a1_fire_val)
    a1_applicable = bool(r.get("a1_applicable", True))

    return {
        "a2_fired_ever": bool(r.get("a2_fire", False)),
        "persistence_terminal_active": bool(r.get("pers_fire_end", False)),
        "a1_episodes": int(r.get("a1_n_episodes", 0)) if pd.notna(r.get("a1_n_episodes", 0)) else 0,
        "a1_applicable": a1_applicable,
    }


def lookup_window(evidence_state: str) -> dict:
    """Return the window row for the given evidence state from the config."""
    for row in CFG["window_matrix"]["rows"]:
        if row["evidence_state"] == evidence_state:
            return row
    return {}


def window_statement(evidence_state: str) -> str:
    """Return a single-line window statement with n and CI for P0/P1 alerts."""
    row = lookup_window(evidence_state)
    if not row:
        return "No window data"
    n = row.get("n", "?")
    ci_lo = row.get("bootstrap_95ci_lo_d")
    ci_hi = row.get("bootstrap_95ci_hi_d")
    sched = row.get("scheduling_window_d", "?")
    if ci_lo is not None and ci_hi is not None:
        return (
            f"n={n}; bootstrap 95% CI [{ci_lo:.0f}d, {ci_hi:.0f}d]; "
            f"scheduling window: {sched}. {row.get('honest_caveat', '')}"
        )
    return f"n={n}; scheduling window: {sched}. {row.get('honest_caveat', '')}"


def determine_evidence_state(
    tier: str,
    h2_fires: bool,
    a2_fired: bool,
    persistence_terminal: bool,
    silence_trigger: bool,
) -> tuple[str, str, str]:
    """
    Apply precedence rules. Returns (priority, trigger_label, evidence_state_key).
    Silence overlay is noted separately but does not replace inspection priority.
    """
    # Rule 1: A2 fired
    if a2_fired:
        return ("P0", "A2_battery_cascade_fired", "A2_battery_cascade_fired")
    # Rule 2: H2 dwell (>=3 consecutive RED)
    if h2_fires:
        return ("P0", "H2_dwell_fired", "persistence_terminal_AND_RED_tier")
    # Rule 3: RED single week (no higher trigger)
    if tier == "RED":
        return ("P1", "RED_tier_no_channel_yet", "RED_tier_no_channel_yet")
    # Rule 4: AMBER
    if tier == "AMBER":
        return ("P2", "AMBER_tier", "AMBER_tier_no_channel")
    # Green / unknown
    return ("GREEN_OK", "GREEN_tier", "GREEN_tier_channel_fires_eventually")


def build_fleet_snapshot(
    ws: pd.DataFrame,
    hf: pd.DataFrame,
    av: pd.DataFrame,
    ap: pd.DataFrame,
    dq: pd.DataFrame,
) -> pd.DataFrame:
    """Build the 34-row fleet snapshot (Phase-B: includes onboarding maturity columns)."""
    fleet_max_date = dq["t_end"].max()

    k0 = get_k0_scores(ws)
    rows = []

    for vin in sorted(k0.index):
        k0_row = k0.loc[vin]
        tier_raw = k0_row["tier"]
        prob  = float(k0_row["prob"]) if pd.notna(k0_row["prob"]) else float("nan")
        label = int(k0_row["label"])

        h1 = compute_h1_momentum(ws, vin)
        h2 = compute_h2_dwell(ws, vin)
        h5 = compute_h5_fleet_pctile(ws, vin)
        ch = get_channel_states(vin, av, ap)

        # Onboarding maturity gating (B3)
        # weeks_observed = count of distinct k values = OPERATIONAL METADATA only
        # (observation length is BANNED as a model feature — leak class D5)
        weeks_obs = compute_weeks_observed(ws, vin)
        mg = apply_maturity_gate(
            vin=vin,
            tier_raw=tier_raw,
            prob=prob,
            weeks_observed=weeks_obs,
            h1=h1,
            h2=h2,
            h5=h5,
        )
        tier = mg["tier_display"]  # capped tier for display/routing
        h1_fires_eff = mg["h1_fires"]
        h2_fires_eff = mg["h2_fires"]
        h5_fires_eff = mg["h5_fires"]

        # Silence days: today − VIN t_end (proxy: fleet_max_date − VIN t_end)
        vin_t_end = dq[dq["vin_label"] == vin]["t_end"]
        if len(vin_t_end) > 0:
            t_end_val = vin_t_end.values[0]
            silence_days = int((fleet_max_date - t_end_val).days)
        else:
            silence_days = -1

        silence_trigger_active = (silence_days > SILENCE_DAYS) and (tier in ("AMBER", "RED"))

        # Badges
        is_watchlist = vin in WATCHLIST
        is_sma_dead  = vin in SMA_DEAD

        # Determine evidence state: immature trucks get forced evidence state
        if mg["immature"]:
            # Immature truck: use forced evidence state; no heuristic-driven P0/P1 escalation
            priority, trigger, evidence_state_key = determine_evidence_state(
                tier=tier,
                h2_fires=False,                   # suppressed
                a2_fired=ch["a2_fired_ever"],      # A2 still applies (channel-based, not heuristic)
                persistence_terminal=ch["persistence_terminal_active"],
                silence_trigger=silence_trigger_active,
            )
            # Override evidence state to immature label (but retain A2 P0 if fired)
            if not ch["a2_fired_ever"]:
                evidence_state_key = "IMMATURE_<12wk_fleet_prior"
        else:
            priority, trigger, evidence_state_key = determine_evidence_state(
                tier=tier,
                h2_fires=h2_fires_eff,
                a2_fired=ch["a2_fired_ever"],
                persistence_terminal=ch["persistence_terminal_active"],
                silence_trigger=silence_trigger_active,
            )

        rows.append({
            # SHADOW-EVAL-ONLY: label column retained for evaluation, not for ops use
            "vin": vin,
            "label": label,                  # SHADOW-EVAL-ONLY
            "tier": tier,
            "prob": round(prob, 4),
            "priority": priority,
            "trigger": trigger,
            "evidence_state": evidence_state_key,
            "h1_fires": h1_fires_eff,
            "h1_delta_prob": h1["h1_delta"],
            "h2_fires": h2_fires_eff,
            "h2_consec_red": h2["h2_consec_red"],
            "h5_fires": h5_fires_eff,
            "h5_weeks_above": h5["h5_weeks_above"],
            "a2_fired_ever": ch["a2_fired_ever"],
            "persistence_terminal_active": ch["persistence_terminal_active"],
            "a1_episodes": ch["a1_episodes"],
            "a1_applicable": ch["a1_applicable"],
            "silence_days": silence_days,
            "silence_trigger_active": silence_trigger_active,
            "watchlist_badge": is_watchlist,
            "sma_dead_badge": is_sma_dead,
            # Onboarding columns (B3)
            "weeks_observed": weeks_obs,
            "immature_badge": mg["immature"],
            "tier_uncapped": mg["tier_uncapped"],
        })

    df = pd.DataFrame(rows)
    return df


def build_shadow_alert_log(snapshot: pd.DataFrame) -> pd.DataFrame:
    """
    Build the shadow alert log: one row per active alert (P0/P1/P2/P0_OPS).
    Includes corroborator evidence summary and window statement for P0/P1.
    """
    log_rows = []

    for _, row in snapshot.iterrows():
        vin = row["vin"]
        priority = row["priority"]
        tier = row["tier"]
        trigger = row["trigger"]
        evidence_state_key = row["evidence_state"]

        if priority not in ("P0", "P1", "P2"):
            # Still emit watchlist + silence overlays even for GREEN trucks
            if row["silence_trigger_active"]:
                pass  # handled below
            elif not row["watchlist_badge"]:
                continue

        # Build evidence summary
        corroborators = []
        if row["h1_fires"]:
            corroborators.append(f"H1_momentum(Δprob={row['h1_delta_prob']:+.3f})")
        if row["h2_fires"]:
            corroborators.append(f"H2_dwell({row['h2_consec_red']}wk RED)")
        if row["h5_fires"]:
            corroborators.append(f"H5_fleet_pctile({row['h5_weeks_above']}/6 wk)")
        if row["a2_fired_ever"]:
            corroborators.append("A2_battery_cascade(fired)")
        if row["persistence_terminal_active"]:
            corroborators.append("persistence_terminal(active)")
        if row["a1_applicable"] and row["a1_episodes"] > 0:
            corroborators.append(f"A1_crank_burst({row['a1_episodes']} ep)")

        evidence_summary = "; ".join(corroborators) if corroborators else "tier_only"

        win_stmt = ""
        if priority in ("P0", "P1"):
            win_stmt = window_statement(evidence_state_key)

        base_row = {
            "vin": vin,
            "priority": priority,
            "trigger": trigger,
            "tier": tier,
            "prob": row["prob"],
            "evidence_summary": evidence_summary,
            "window_statement": win_stmt,
            "watchlist_badge": row["watchlist_badge"],
            "sma_dead_badge": row["sma_dead_badge"],
            "silence_trigger_active": row["silence_trigger_active"],
            "timestamp": TIMESTAMP_NOW,
        }
        log_rows.append(base_row)

        # Silence overlay: add separate P0_OPS row if triggered
        if row["silence_trigger_active"]:
            log_rows.append({
                **base_row,
                "priority": "P0_OPS",
                "trigger": "silence_overlay",
                "evidence_summary": f"silence_days={row['silence_days']}; tier={tier}; ops check <=72h",
                "window_statement": (
                    f"No telemetry for {row['silence_days']} days while tier={tier}. "
                    "Verify vehicle operational and telematics connectivity within 72 hours. "
                    "A quiet truck is itself a maintenance signal (VIN8/9_F lesson); note 5 NF "
                    "trucks are also SMA-dead — silence is not proof of failure. In this "
                    "retrospective snapshot, trucks whose history ends before the fleet data "
                    "wall appear silent by construction."
                ),
            })

    return pd.DataFrame(log_rows) if log_rows else pd.DataFrame(
        columns=["vin", "priority", "trigger", "tier", "prob",
                 "evidence_summary", "window_statement",
                 "watchlist_badge", "sma_dead_badge",
                 "silence_trigger_active", "timestamp"]
    )


def print_verification_summary(snapshot: pd.DataFrame) -> None:
    """Print gate-check summary to stdout."""
    print("\n" + "=" * 68)
    print("V2 Phase-A Verification Gates")
    print("=" * 68)

    # Gate 1: Tier counts at k=0
    tier_by_label = snapshot.groupby(["label", "tier"]).size().unstack(fill_value=0)
    print("\nTier counts at k=0 (label 1=failed, 0=NF):")
    print(tier_by_label.to_string())
    red_failed = snapshot[(snapshot["label"] == 1) & (snapshot["tier"] == "RED")].shape[0]
    red_nf     = snapshot[(snapshot["label"] == 0) & (snapshot["tier"] == "RED")].shape[0]
    gate1_pass = (red_failed == 10) and (red_nf == 2)
    print(f"\nGate 1 — RED: failed={red_failed} (need 10), NF={red_nf} (need 2) => {'PASS' if gate1_pass else 'FAIL'}")
    amber_f = sorted(snapshot[(snapshot["label"] == 1) & (snapshot["tier"] == "AMBER")]["vin"].tolist())
    if amber_f:
        print(f"  Documented deviation: AMBER failed {amber_f} — VIN4_F_SM sits at the GREEN/AMBER "
              f"boundary (walking prob 0.352 vs 0.35) under the single-Platt walking calibration; "
              f"X2 OOF tier table (AMBER failed=0) remains validation-of-record.")

    # Gate 2: A2 fired set
    a2_vins = sorted(snapshot[snapshot["a2_fired_ever"]]["vin"].tolist())
    expected_a2 = sorted(["VIN3_F_SM", "VIN6_F_SM", "VIN13_F_SM", "VIN14_F_SM"])
    gate2_pass = (a2_vins == expected_a2)
    print(f"Gate 2 — A2-fired: {a2_vins} => {'PASS' if gate2_pass else 'FAIL'}")
    if not gate2_pass:
        print(f"  Expected: {expected_a2}")

    # Gate 3: H2 CURRENT dwell state (snapshot semantics: >=3 consecutive RED cuts ending at k=0).
    # NOTE: distinct from "H2 ever fired in history" (heuristic_fires.csv: 10 failed) — the
    # snapshot reports the live alert state; historical fires are evidence, not current alerts.
    h2_fired_f  = sorted(snapshot[(snapshot["label"] == 1) & snapshot["h2_fires"]]["vin"].tolist())
    h2_fired_nf = sorted(snapshot[(snapshot["label"] == 0) & snapshot["h2_fires"]]["vin"].tolist())
    expected_h2_f = sorted(["VIN10_F_SM", "VIN12_F_SM", "VIN14_F_SM", "VIN5_F_SM", "VIN6_F_SM", "VIN7_F_SM"])
    gate3_pass = (h2_fired_f == expected_h2_f) and set(h2_fired_nf) <= {"VIN5_NF_SM"}
    print(f"Gate 3 — H2 current dwell: failed={h2_fired_f} (expect {expected_h2_f}), "
          f"NF={h2_fired_nf} (expect subset of ['VIN5_NF_SM']) => {'PASS' if gate3_pass else 'FAIL'}")
    print(f"  Info: H2 ever-fired in walk-back history = 10 failed (heuristic_fires.csv ground truth);"
          f" current-dwell is the deployable alert state.")

    # Gate 4: VIN9_F_SM GREEN + SMA-dead + no channel
    vin9 = snapshot[snapshot["vin"] == "VIN9_F_SM"]
    if len(vin9) > 0:
        v9 = vin9.iloc[0]
        gate4_pass = (v9["tier"] == "GREEN") and v9["sma_dead_badge"] and not v9["a2_fired_ever"] and not v9["persistence_terminal_active"]
        print(f"Gate 4 — VIN9_F_SM: tier={v9['tier']}, sma_dead={v9['sma_dead_badge']}, a2={v9['a2_fired_ever']}, pers={v9['persistence_terminal_active']} => {'PASS' if gate4_pass else 'FAIL'}")
    else:
        gate4_pass = False
        print("Gate 4 — VIN9_F_SM NOT FOUND => FAIL")

    # Gate 5: Watchlist 4 NF flagged
    wl_flagged = sorted(snapshot[snapshot["watchlist_badge"]]["vin"].tolist())
    gate5_pass = len(wl_flagged) == 4
    print(f"Gate 5 — Watchlist: {wl_flagged} => {'PASS' if gate5_pass else 'FAIL'}")

    all_pass = all([gate1_pass, gate2_pass, gate3_pass, gate4_pass, gate5_pass])
    print(f"\nOverall: {'ALL GATES PASS' if all_pass else 'GATE FAILURE — see above'}")
    print("=" * 68)

    # Priority summary
    print("\nAlert Priority Summary:")
    prio_counts = snapshot["priority"].value_counts().sort_index()
    print(prio_counts.to_string())
    print("\nTier Summary:")
    tier_counts = snapshot["tier"].value_counts().sort_index()
    print(tier_counts.to_string())


def main(as_of: str | None = None) -> None:
    print(f"V2 Weekly Job — config_version {CFG['config_version']}")
    print(f"Timestamp: {TIMESTAMP_NOW}")
    if as_of:
        print(f"As-of override: {as_of} (NOTE: walking_scores are pre-computed at k=0; this flag is reserved for future live data)")

    ws, hf, ap, av, dq = load_data()

    print(f"Loaded walking_scores: {ws.shape[0]} rows ({ws['vin_label'].nunique()} VINs)")
    print(f"Loaded heuristic_fires: {hf.shape[0]} rows")
    print(f"Loaded alert_policy: {ap.shape[0]} rows")
    print(f"Loaded alert_validation: {av.shape[0]} rows")
    print(f"Loaded data_quality: {dq.shape[0]} rows")

    snapshot = build_fleet_snapshot(ws, hf, av, ap, dq)
    alert_log = build_shadow_alert_log(snapshot)

    # Save outputs
    snap_path = OUT_DIR / "fleet_snapshot.csv"
    log_path  = OUT_DIR / "shadow_alert_log.csv"

    # Add header comment line noting SHADOW-EVAL-ONLY for label column
    with open(snap_path, "w", encoding="utf-8") as fh:
        fh.write("# SHADOW-EVAL-ONLY: 'label' column is ground-truth for evaluation only — do NOT surface to ops\n")
        snapshot.to_csv(fh, index=False)

    alert_log.to_csv(log_path, index=False)

    print(f"\nSaved fleet_snapshot.csv  ({snapshot.shape[0]} rows) -> {snap_path}")
    print(f"Saved shadow_alert_log.csv ({alert_log.shape[0]} rows) -> {log_path}")

    print_verification_summary(snapshot)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SM V2 Phase-A weekly scoring job")
    parser.add_argument(
        "--as-of",
        default=None,
        help="Override scoring date (YYYY-MM-DD). Default: end of available data (k=0).",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to config JSON (default: v2_config.json next to this file). "
             "Used by tests to inject modified config copies.",
    )
    args = parser.parse_args()

    # Allow --config override so tests can use modified copies without touching registry
    if args.config:
        import hashlib as _hashlib
        _cfg_path = Path(args.config)
        if not _cfg_path.is_absolute():
            _cfg_path = Path.cwd() / _cfg_path
        with open(_cfg_path, encoding="utf-8") as _fh:
            _new_cfg = json.load(_fh)
        # Patch module-level CFG used by load_data and globals
        CFG.clear()
        CFG.update(_new_cfg)
        # Re-patch derived globals that were set at import time from CFG
        WATCHLIST.clear()
        WATCHLIST.update(set(CFG["watchlist"]["vins"]))
        SMA_DEAD.clear()
        SMA_DEAD.update(set(CFG["cohort_masks"]["SMA_dead"]["vins"]))
        _OB2 = CFG.get("onboarding", {})
        # Re-patch int/str/set globals at module scope (no global decl needed here)
        import sys as _sys
        _mod = _sys.modules[__name__]
        _mod.MIN_WEEKS_MATURE = int(_OB2.get("min_weeks_mature", 12))
        _mod.IMMATURE_TIER_CAP = _OB2.get("immature_tier_cap", "AMBER")
        _mod.IMMATURE_SUPPRESS = set(_OB2.get("immature_suppress", ["H1", "H2", "H5"]))

    main(as_of=args.as_of)
