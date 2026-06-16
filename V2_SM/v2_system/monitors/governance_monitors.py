"""
governance_monitors.py  (B1) -- Starter-Motor V2 Governance Monitors
=====================================================================
Governance checks: PSI feature drift, calibration tracking, alert-volume
tracker, and telemetry-health density panel.

B1a  PSI per modal feature
--------------------------
Population Stability Index using 10-bin quantile PSI with epsilon smoothing.

Formula (per bin):
  PSI = sum_i [ (P_cur_i - P_ref_i) * ln(P_cur_i / P_ref_i) ]
where:
  P_ref_i = (count_ref_in_bin_i + eps) / (N_ref + K*eps)
  P_cur_i = (count_cur_in_bin_i + eps) / (N_cur + K*eps)
  eps = 1e-6 (epsilon smoothing to avoid log(0))
  K = number of bins (10)

Bins are determined solely from the reference distribution (production matrix
values), using 10 equal-quantile bin edges.  The same edges are then applied
to the current distribution.

IDENTITY SANITY GATE: reference == current (same 34 rows) => PSI ~ 0.
  Gate passes if PSI < 0.01 for all 4 modal features.

DRIFT SELF-TEST: vsi_withinwk_std_ratio_30d_w shifted by +1.0 std dev.
  PSI must exceed 0.20 and alarm must fire.  Encoded as PASS when alarm fires.

B1b  Calibration tracker
------------------------
Recompute pooled slope + Brier from V1.1 nested LOVO OOF predictions.

Method (identical to V1.1 gates script, V1_1_SM_nested_ridge.py, G3):
  brier = mean((y - prob_recal)^2)   [brier_score_loss]
  slope = LogisticRegression(C=1e6).fit(logit(prob_recal).reshape(-1,1), y).coef_[0,0]

RECONCILIATION GATE: slope within 0.86 +/- 0.05 AND brier within 0.124 +/- 0.01.

B1c  Alert-volume tracker
-------------------------
H2 (H2_pers_red) NF false-alarm rate = H2 NF episodes / NF truck-years.
NF truck-years computed from V1_SM_data_quality.csv (active_days_total / 365.25).
PASS band: [0, 0.30] episodes/truck-year.

B1d  Density panel
------------------
Summarises telemetry_health.csv alarms:
  - n_taper_alarms, n_vsi_null_alarms, n_sma_null_alarms
  - VINs triggering each alarm type
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss

# -- Paths -------------------------------------------------------------------
ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR")
FEAT_MATRIX = ROOT / "V1.1" / "results" / "V1_1_SM_feature_matrix.csv"
OOF_PREDS = ROOT / "V1.1" / "results" / "V1_1_SM_nested_lovo_predictions.csv"
HEURISTIC_FIRES = (
    ROOT / "V2_program" / "analysis" / "heuristics" / "out" / "heuristic_fires.csv"
)
DATA_QUALITY = ROOT / "results" / "V1_SM_data_quality.csv"
TELEMETRY_HEALTH_OUT = (
    ROOT / "V2_program" / "v2_system" / "monitors" / "out" / "telemetry_health.csv"
)
OUT_DIR = ROOT / "V2_program" / "v2_system" / "monitors" / "out"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# -- Configuration -----------------------------------------------------------
MODAL_FEATURES = [
    "vsi_withinwk_std_ratio_30d_w",
    "rest_vsi_p05_delta90",
    "vsi_range_trend",
    "dip_depth_last90_delta",
]
PSI_BINS = 10
PSI_EPS = 1e-6
PSI_ALARM_THRESHOLD = 0.20
PSI_IDENTITY_GATE_THRESHOLD = 0.01
DRIFT_SELFTEST_SHIFT_FEATURE = "vsi_withinwk_std_ratio_30d_w"
DRIFT_SELFTEST_SHIFT_STD = 1.0

# Calibration reconciliation bounds
SLOPE_ANCHOR = 0.86
SLOPE_TOL = 0.05
BRIER_ANCHOR = 0.124
BRIER_TOL = 0.010

# Alert volume
ALERT_VOL_PASS_MAX = 0.30   # episodes/truck-year


# -- PSI utilities -----------------------------------------------------------

def _psi(
    ref: np.ndarray,
    cur: np.ndarray,
    n_bins: int = PSI_BINS,
    eps: float = PSI_EPS,
    bins: np.ndarray | None = None,
) -> tuple[float, np.ndarray]:
    """
    Compute quantile PSI between ref and cur distributions.

    Parameters
    ----------
    ref    : 1-D reference values (non-NaN)
    cur    : 1-D current values (non-NaN)
    n_bins : number of equal-quantile bins
    eps    : additive smoothing constant
    bins   : pre-computed bin edges; if None, derived from ref quantiles

    Returns
    -------
    psi_value : scalar PSI
    bins      : bin edges used (for reuse in self-test)
    """
    ref = np.asarray(ref, dtype=float)
    cur = np.asarray(cur, dtype=float)

    if bins is None:
        q = np.linspace(0, 100, n_bins + 1)
        bins = np.percentile(ref, q)
        bins[0] = -np.inf
        bins[-1] = np.inf

    n_ref = len(ref)
    n_cur = len(cur)
    K = n_bins

    ref_counts = np.zeros(K, dtype=float)
    cur_counts = np.zeros(K, dtype=float)
    for b in range(K):
        ref_counts[b] = np.sum((ref >= bins[b]) & (ref < bins[b + 1]))
        cur_counts[b] = np.sum((cur >= bins[b]) & (cur < bins[b + 1]))

    p_ref = (ref_counts + eps) / (n_ref + K * eps)
    p_cur = (cur_counts + eps) / (n_cur + K * eps)

    psi_value = float(np.sum((p_cur - p_ref) * np.log(p_cur / p_ref)))
    return psi_value, bins


# -- B1a: PSI per modal feature ---------------------------------------------

def check_psi_identity(feat_df: pd.DataFrame) -> dict:
    """
    Identity test: reference == current.  PSI must be < PSI_IDENTITY_GATE_THRESHOLD
    for all modal features.
    """
    results = {}
    all_pass = True
    for feat in MODAL_FEATURES:
        valid_mask = feat_df[feat].notna()
        vals = feat_df.loc[valid_mask, feat].values
        psi_val, bins = _psi(vals, vals)
        alarm = psi_val >= PSI_ALARM_THRESHOLD
        gate_ok = psi_val < PSI_IDENTITY_GATE_THRESHOLD
        if not gate_ok:
            all_pass = False
        results[feat] = {
            "psi": round(psi_val, 6),
            "alarm": alarm,
            "identity_gate_ok": gate_ok,
            "_bins": bins,
        }
        print(
            f"  [PSI identity] {feat}: PSI={psi_val:.6f}  "
            f"identity_gate={'PASS' if gate_ok else 'FAIL'}"
        )
    results["all_features_identity_gate"] = all_pass
    return results


def check_psi_drift_selftest(feat_df: pd.DataFrame, bins: np.ndarray) -> dict:
    """
    Self-test: shift DRIFT_SELFTEST_SHIFT_FEATURE by +1 std dev.
    PSI must exceed PSI_ALARM_THRESHOLD (0.20) and alarm must fire.
    Encoded as PASS when the alarm triggers (expected behaviour).
    """
    feat = DRIFT_SELFTEST_SHIFT_FEATURE
    valid_mask = feat_df[feat].notna()
    ref_vals = feat_df.loc[valid_mask, feat].values
    std_dev = float(np.std(ref_vals, ddof=1))
    cur_shifted = ref_vals + DRIFT_SELFTEST_SHIFT_STD * std_dev

    psi_val, _ = _psi(ref_vals, cur_shifted, bins=bins)
    alarm_fires = psi_val >= PSI_ALARM_THRESHOLD

    # PASS = alarm fires as expected (correctly detects injected drift)
    test_pass = alarm_fires
    print(
        f"  [PSI selftest]  {feat} +{DRIFT_SELFTEST_SHIFT_STD}sd shift: "
        f"PSI={psi_val:.4f}  alarm={'YES' if alarm_fires else 'NO'}  "
        f"-> {'PASS' if test_pass else 'FAIL (alarm should have fired)'}"
    )
    return {
        "feature": feat,
        "shift_std": DRIFT_SELFTEST_SHIFT_STD,
        "psi": round(psi_val, 4),
        "alarm_fires": alarm_fires,
        "expected": "alarm_fires=True",
        "status": "PASS" if test_pass else "ALARM_DID_NOT_FIRE",
    }


# -- B1b: Calibration tracker -----------------------------------------------

def check_calibration(oof_df: pd.DataFrame) -> dict:
    """
    Recompute pooled slope and Brier from OOF predictions.
    Uses logit(prob_recal) as input to LogisticRegression (mirrors V1.1 G3).
    """
    y = oof_df["failed"].values.astype(int)
    rc = np.clip(oof_df["prob_recal"].values, PSI_EPS, 1 - PSI_EPS)

    brier = float(brier_score_loss(y, rc))

    lg = np.log(rc / (1 - rc))
    lr = LogisticRegression(C=1e6, max_iter=10000, random_state=42)
    lr.fit(lg.reshape(-1, 1), y)
    slope = float(lr.coef_[0, 0])

    slope_ok = abs(slope - SLOPE_ANCHOR) <= SLOPE_TOL
    brier_ok = abs(brier - BRIER_ANCHOR) <= BRIER_TOL
    reconciled = slope_ok and brier_ok

    print(
        f"  [Calibration] slope={slope:.4f} (anchor={SLOPE_ANCHOR}+-{SLOPE_TOL}) "
        f"{'OK' if slope_ok else 'OUT-OF-TOLERANCE'}"
    )
    print(
        f"  [Calibration] brier={brier:.4f} (anchor={BRIER_ANCHOR}+-{BRIER_TOL}) "
        f"{'OK' if brier_ok else 'OUT-OF-TOLERANCE'}"
    )
    print(
        f"  [Calibration] reconciliation: {'PASS' if reconciled else 'FAIL'}"
    )

    return {
        "slope": round(slope, 4),
        "slope_anchor": SLOPE_ANCHOR,
        "slope_tol": SLOPE_TOL,
        "slope_ok": slope_ok,
        "brier": round(brier, 4),
        "brier_anchor": BRIER_ANCHOR,
        "brier_tol": BRIER_TOL,
        "brier_ok": brier_ok,
        "reconciled": reconciled,
    }


# -- B1c: Alert-volume tracker -----------------------------------------------

def check_alert_volume(heuristic_df: pd.DataFrame, dq_df: pd.DataFrame) -> dict:
    """
    H2 NF false-alarm rate = H2_pers_red NF episodes / NF truck-years.
    PASS band: [0, ALERT_VOL_PASS_MAX].
    """
    nf_h2 = heuristic_df[
        (heuristic_df["label"] == 0) & (heuristic_df["heuristic"] == "H2_pers_red")
    ]
    total_episodes = int(nf_h2["n_episodes"].sum())

    nf_dq = dq_df[dq_df["failed"] == False]
    truck_years = float(nf_dq["active_days_total"].sum() / 365.25)

    rate = total_episodes / truck_years if truck_years > 0 else float("nan")
    pass_ok = (0 <= rate <= ALERT_VOL_PASS_MAX) if not np.isnan(rate) else False

    print(
        f"  [AlertVolume] H2 NF episodes={total_episodes}  "
        f"NF truck-years={truck_years:.2f}  "
        f"rate={rate:.4f} ep/truck-yr  "
        f"pass_band=[0,{ALERT_VOL_PASS_MAX}]  -> {'PASS' if pass_ok else 'ALARM'}"
    )

    return {
        "heuristic": "H2_pers_red",
        "nf_h2_episodes": total_episodes,
        "nf_truck_years": round(truck_years, 4),
        "rate_episodes_per_truck_year": round(rate, 4),
        "pass_band_max": ALERT_VOL_PASS_MAX,
        "status": "PASS" if pass_ok else "ALARM",
    }


# -- B1d: Density panel -------------------------------------------------------

def check_density_panel(th_df: pd.DataFrame) -> dict:
    """
    Summarise telemetry_health alarms.
    """
    taper_vins = th_df.loc[th_df["taper_alarm"] == True, "vin_label"].tolist()
    vsi_vins = th_df.loc[th_df["vsi_null_alarm"] == True, "vin_label"].tolist()
    sma_vins = th_df.loc[th_df["sma_null_alarm"] == True, "vin_label"].tolist()

    panel = {
        "n_taper_alarms": len(taper_vins),
        "taper_alarm_vins": sorted(taper_vins),
        "n_vsi_null_alarms": len(vsi_vins),
        "vsi_null_alarm_vins": sorted(vsi_vins),
        "n_sma_null_alarms": len(sma_vins),
        "sma_null_alarm_vins": sorted(sma_vins),
    }

    print(f"  [DensityPanel] taper_alarms={len(taper_vins)}  {sorted(taper_vins)}")
    print(f"  [DensityPanel] vsi_null_alarms={len(vsi_vins)}  {sorted(vsi_vins)}")
    print(f"  [DensityPanel] sma_null_alarms={len(sma_vins)}  {sorted(sma_vins)}")

    return panel


# -- Main --------------------------------------------------------------------

def main() -> dict:
    warnings.filterwarnings("ignore")

    feat_df = pd.read_csv(FEAT_MATRIX)
    oof_df = pd.read_csv(OOF_PREDS)
    heuristic_df = pd.read_csv(HEURISTIC_FIRES)
    dq_df = pd.read_csv(DATA_QUALITY)

    if not TELEMETRY_HEALTH_OUT.exists():
        raise FileNotFoundError(
            f"telemetry_health.csv not found at {TELEMETRY_HEALTH_OUT}. "
            "Run telemetry_health.py first."
        )
    th_df = pd.read_csv(TELEMETRY_HEALTH_OUT)

    results: dict = {}

    # B1a: PSI identity
    print("\n=== B1a: PSI Identity (reference == current) ===")
    psi_identity = check_psi_identity(feat_df)
    # B1a: PSI drift self-test (use bins from the main feature)
    bins_main = psi_identity[DRIFT_SELFTEST_SHIFT_FEATURE]["_bins"]
    print("\n=== B1a: PSI Drift Self-Test ===")
    psi_selftest = check_psi_drift_selftest(feat_df, bins_main)

    # Build clean PSI identity output (drop internal _bins)
    psi_identity_clean = {
        feat: {k: v for k, v in psi_identity[feat].items() if k != "_bins"}
        for feat in MODAL_FEATURES
    }
    psi_identity_clean["all_features_identity_gate"] = psi_identity[
        "all_features_identity_gate"
    ]

    results["psi_identity"] = psi_identity_clean
    results["psi_drift_selftest"] = psi_selftest

    # B1b: Calibration
    print("\n=== B1b: Calibration Tracker ===")
    results["calibration"] = check_calibration(oof_df)

    # B1c: Alert volume
    print("\n=== B1c: Alert Volume Tracker ===")
    results["alert_volume"] = check_alert_volume(heuristic_df, dq_df)

    # B1d: Density panel
    print("\n=== B1d: Density Panel ===")
    results["density_panel"] = check_density_panel(th_df)

    return results


if __name__ == "__main__":
    print("=" * 60)
    print("governance_monitors.py  (B1)")
    print("=" * 60)

    res = main()

    print("\n--- SUMMARY ---")
    print(f"  PSI identity gate (all features): "
          f"{'PASS' if res['psi_identity']['all_features_identity_gate'] else 'FAIL'}")
    for feat in MODAL_FEATURES:
        print(f"    {feat}: PSI={res['psi_identity'][feat]['psi']:.6f}")
    print(f"  PSI drift self-test: {res['psi_drift_selftest']['status']}")
    print(f"  Calibration reconciled: {'PASS' if res['calibration']['reconciled'] else 'FAIL'}")
    print(f"    slope={res['calibration']['slope']}  brier={res['calibration']['brier']}")
    print(f"  Alert volume: {res['alert_volume']['status']}")
    print(f"    rate={res['alert_volume']['rate_episodes_per_truck_year']} ep/truck-yr")
