"""
V1_1_SM_daily_risk_graphs.py — V1.1 Starter Motor DAILY-RISK RUL dashboards
============================================================================
34 per-VIN two-subplot dashboards replicating the alternator V10.5.3
production aesthetic (V5.2_ALT/src/V10.5.3_20_5_ALT_production_graphs.py,
spec: STARTER MOTOR/V1.1/Plan/ALT_graph_study.md) at DAILY resolution:
one curve point per ACTIVE DAY instead of one per week.

ALT recipe with the study's SM porting table applied:
  - Degradation score per active day: 30-day lookback over the daily
    driving-regime stats (V1_1_SM_daily_{VIN}.parquet) — components
    s1 vsi_drive_std level, s2 (p95-p05) range, s3 |mean - 28.2|,
    s5 undervoltage share (vsi_below_21_rows), and s4 = 30-day
    FAILED-CRANK rate (replaces ALT ged2_rate; from
    STARTER MOTOR/cache/events/V1_SM_crank_events.parquet).
    SMA-dead trucks (sma_obs_rows/n_rows < 1%): s4 weight redistributed
    proportionally onto the other components (noted on the graph).
  - Same ALT baseline normalization (first 90 days), weights
    [0.25, 0.25, 0.20, 0.20, 0.10], deg^1.5 risk-modulated countdown
    RUL = max(0, (max_rul - elapsed)/(1 + deg^1.5*2) + N(0, 0.02*remaining))
    with per-VIN deterministic seed.
  - FAILED VINs: max_rul = actual ttf_days (saledate -> JCOPENDATE).
  - NON-FAILED VINs: max_rul = 779 d (SM fleet Weibull median,
    lambda=133.3 wk, rho=2.03). If first_date + 779 d falls within 14 d of
    (or before) last data, use the Weibull CONDITIONAL median given survival
    to the observed age: solve S(t) = 0.5*S(t_obs)  =>
    t* = lambda_d * ((t_obs/lambda_d)^rho + ln 2)^(1/rho).
  - Historical/forecast split at 60% of active days (solid then dashed),
    markers thinned to every ~28 active days.
  - Dotted power-decay projection to RUL=0 at forecast_fail_date on ALL
    34 VINs, widening envelope, maintenance-alert at first RUL < 90 d.
  - GAP-MASKING: NaN inserted where no active day within 7 days — the
    curve and sparkline break across telemetry gaps (never interpolated).
  - Hatched silent-gap region between t_end and JCOPENDATE for the 5
    gap VINs (VIN1/4/5/8/9_F).
  - Bottom sparkline: daily vsi_drive_mean + p05-p95 fill, DICV 26.0/24.0
    hlines (24.0 emphasized for SM), 28.0-28.4 nominal band, FAILED-crank
    ticks at y=20.5 (successes omitted for clarity), up to 3 callouts.

Honest framing (footer): the RUL curve is a fleet-Weibull-anchored
illustration modulated by the daily degradation score — the validated
deliverable is the risk tier + <=10-wk horizon.

Usage
-----
    py -3 "STARTER MOTOR/V1.1/src/V1_1_SM_daily_risk_graphs.py"             # all 34
    py -3 "STARTER MOTOR/V1.1/src/V1_1_SM_daily_risk_graphs.py" VIN1_F_SM   # specific

Output:  STARTER MOTOR/V1.1/graphs/V1_1_SM_daily_risk_{VIN_LABEL}_dashboard.png
"""
from __future__ import annotations

import hashlib
import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Display-level VIN renumbering (2026-06-11): failed VIN1-14 unchanged, NF
# shifted +14 (old VIN1_NF -> VIN15_NF). Data is still loaded/keyed by the
# ORIGINAL labels; only titles, footers and output filenames use the new ones.
from V1_1_SM_vin_display_map import display_label, raw_file_note

warnings.filterwarnings("ignore", category=UserWarning, module="matplotlib")

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------
ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery")
SM = ROOT / "STARTER MOTOR"
DAILY_DIR = SM / "V1.1" / "cache" / "daily"
EVENTS_PQ = SM / "cache" / "events" / "V1_SM_crank_events.parquet"
PRED_CSV = SM / "V1.1" / "results" / "V1_1_SM_nested_lovo_predictions.csv"
DQ_CSV = SM / "results" / "V1_SM_data_quality.csv"
ARCH_CSV = SM / "V1.1" / "discovery" / "out" / "E2_failed_vin_archetypes.csv"
OUTPUT_DIR = SM / "V1.1" / "graphs"

VERSION = "V1.1_SM"
AUROC_STR = "0.932"
MODEL_STR = "Ridge Nested-CV (k=4)"

# SM fleet Weibull (F_survival_analysis.md s2): lambda=133.3 wk, rho=2.03
WEIBULL_LAMBDA_D = 133.3 * 7.0     # 933.1 days
WEIBULL_RHO = 2.03
NF_MAX_RUL = 779.0                 # fleet Weibull median TTF (days)

ZONE_THRESHOLDS = {"yellow": 0.15, "orange": 0.35, "red": 0.55}
ZONE_COLORS = {"GREEN": "#a5d6a7", "YELLOW": "#fff176",
               "ORANGE": "#ffb74d", "RED": "#ef9a9a"}
ZONE_COLORS_LC = {k.lower(): v for k, v in ZONE_COLORS.items()}
ZONE_LABELS = {"green": "GREEN", "yellow": "YELLOW",
               "orange": "ORANGE", "red": "RED"}

CLR_MODEL = "#d35400"
CLR_BAND = "#e67e22"
CLR_VSI_LINE = "#2c3e50"
CLR_VSI_FILL = "#e67e22"
CLR_CRANK = "#e74c3c"
CLR_GREEN = "#27ae60"
CLR_NOMINAL = "#27ae60"

VSI_NORMAL_RUNNING = 28.2
VSI_UNDERVOLTAGE = 26.0   # A5
VSI_MIN_CRANK = 24.0      # A6 — headline threshold for SM

GAP_MASK_DAYS = 7         # break line if no active day within 7 days
MARKER_EVERY = 28         # thin markers to every ~28 active days
MAINT_ALERT_RUL = 90.0
SMA_DEAD_FRAC = 0.01      # sma_obs_rows/n_rows < 1% -> SMA-dead config

DEG_WEIGHTS = [0.25, 0.25, 0.20, 0.20, 0.10]   # s1 std, s2 range, s3 dev, s4 crank, s5 uv
# SMA-dead: redistribute s4's 0.20 proportionally onto the others (/0.8)
DEG_WEIGHTS_SMADEAD = [0.3125, 0.3125, 0.25, 0.0, 0.125]


def stable_seed(vin_label: str) -> int:
    """Deterministic per-VIN seed (Python hash() is process-salted)."""
    return int(hashlib.md5(vin_label.encode()).hexdigest(), 16) % 10000


# ---------------------------------------------------------------------------
# External data loaders
# ---------------------------------------------------------------------------
def load_predictions() -> dict[str, dict]:
    df = pd.read_csv(PRED_CSV)
    out = {}
    for _, r in df.iterrows():
        out[r["vin_label"]] = {"prob_recal": float(r["prob_recal"]),
                               "tier": str(r["tier"])}
    return out


def load_metadata() -> dict[str, dict]:
    df = pd.read_csv(DQ_CSV)
    out = {}
    for _, r in df.iterrows():
        m = {
            "t_start": pd.Timestamp(r["t_start"]),
            "t_end": pd.Timestamp(r["t_end"]),
            "saledate": pd.Timestamp(r["saledate"]) if pd.notna(r["saledate"]) and str(r["saledate"]).strip() else None,
            "jcopendate": pd.Timestamp(r["jcopendate"]) if pd.notna(r["jcopendate"]) and str(r["jcopendate"]).strip() else None,
            "gap_days": int(r["gap_days"]) if pd.notna(r["gap_days"]) and str(r["gap_days"]).strip() else 0,
        }
        out[r["vin_label"]] = m
    return out


def load_archetypes() -> dict[str, str]:
    df = pd.read_csv(ARCH_CSV)
    return {r["vin_label"]: str(r["archetype"]) for _, r in df.iterrows()}


def load_failed_crank_daily() -> dict[str, pd.Series]:
    """Per-VIN daily counts of FAILED, non-artifact crank events."""
    e = pd.read_parquet(EVENTS_PQ)
    e = e[(e["success"].eq(False)) & (~e["artifact"].astype(bool))].copy()
    e["date"] = pd.to_datetime(e["ts_start"]).dt.normalize()
    out = {}
    for vin, g in e.groupby("vin_label"):
        out[vin] = g.groupby("date").size().sort_index()
    return out


PREDS = load_predictions()
META = load_metadata()
ARCHETYPES = load_archetypes()
FAILED_CRANKS = load_failed_crank_daily()


# ---------------------------------------------------------------------------
# Degradation features from the daily cache (30-day lookback)
# ---------------------------------------------------------------------------
def window_features(daily: pd.DataFrame, fc_dates: np.ndarray, fc_counts: np.ndarray,
                    end_date: pd.Timestamp, window_days: int) -> dict[str, float]:
    """ALT compute_weekly_degradation_features ported to the daily cache."""
    start = end_date - pd.Timedelta(days=window_days)
    w = daily[(daily["date"] > start) & (daily["date"] <= end_date)]
    drive = w[w["vsi_drive_rows"] > 0]
    n_samples = int(drive["vsi_drive_rows"].sum())

    f: dict[str, float] = {}
    if n_samples > 500 and len(drive) >= 2:
        wgt = drive["vsi_drive_rows"].astype(float).values
        f["vsi_mean"] = float(np.average(drive["vsi_drive_mean"].values, weights=wgt))
        f["vsi_std"] = float(np.average(drive["vsi_drive_std"].fillna(0.0).values, weights=wgt))
        f["vsi_range"] = float(np.average(
            (drive["vsi_drive_p95"] - drive["vsi_drive_p05"]).values, weights=wgt))
        f["vsi_deviation"] = float(abs(f["vsi_mean"] - VSI_NORMAL_RUNNING))
        f["uv_share"] = float(drive["vsi_below_21_rows"].sum() / max(n_samples, 1))
    else:  # ALT healthy-fallback constants
        f["vsi_mean"] = 28.0
        f["vsi_std"] = 0.3
        f["vsi_range"] = 1.0
        f["vsi_deviation"] = 0.2
        f["uv_share"] = 0.0

    if len(fc_dates):
        m = (fc_dates > start.to_datetime64()) & (fc_dates <= end_date.to_datetime64())
        fc = int(fc_counts[m].sum())
    else:
        fc = 0
    f["failed_crank_rate"] = fc / max(window_days, 1)
    return f


def features_to_degradation(f: dict, baseline: dict, sma_dead: bool) -> float:
    """ALT features_to_degradation with s4 = failed-crank-rate excess over baseline."""
    baseline_std_floor = max(baseline["vsi_std"], 0.30)
    baseline_range_floor = max(baseline["vsi_range"], 1.0)

    s1 = min(1.0, max(0.0, (f["vsi_std"] / baseline_std_floor - 1.0) / 3.0))
    s2 = min(1.0, max(0.0, (f["vsi_range"] / baseline_range_floor - 1.0) / 4.0))
    s3 = min(1.0, f["vsi_deviation"] / 4.0)
    # s4: excess failed cranks/day over baseline rate, saturating at +0.3/day
    s4 = min(1.0, max(0.0, (f["failed_crank_rate"] - baseline["failed_crank_rate"]) / 0.3))
    s5 = min(1.0, max(0.0, f["uv_share"] / 0.05))

    weights = DEG_WEIGHTS_SMADEAD if sma_dead else DEG_WEIGHTS
    deg = sum(w * s for w, s in zip(weights, [s1, s2, s3, s4, s5]))
    return float(np.clip(deg, 0.0, 1.0))


def degradation_to_rul(deg: float, max_rul: float, elapsed_days: int, seed_salt: int) -> float:
    """ALT degradation_to_rul verbatim (deg^1.5 risk-modulated countdown)."""
    remaining_linear = max(0.0, max_rul - elapsed_days)
    acceleration = 1.0 + (deg ** 1.5) * 2.0
    adjusted_rul = remaining_linear / acceleration
    rng = np.random.RandomState(int(elapsed_days * 7 + seed_salt) % (2 ** 31))
    noise = rng.normal(0, remaining_linear * 0.02)
    return max(0.0, adjusted_rul + noise)


# ---------------------------------------------------------------------------
# Daily RUL trajectory — one point per ACTIVE DAY
# ---------------------------------------------------------------------------
def compute_daily_trajectory(vin_label: str, daily: pd.DataFrame, max_rul: float) -> tuple[pd.DataFrame, bool]:
    daily = daily.sort_values("date").reset_index(drop=True)
    sma_dead = (daily["sma_obs_rows"].sum() / max(daily["n_rows"].sum(), 1)) < SMA_DEAD_FRAC

    fc = FAILED_CRANKS.get(vin_label, pd.Series(dtype="int64"))
    fc_dates = fc.index.values if len(fc) else np.array([], dtype="datetime64[ns]")
    fc_counts = fc.values if len(fc) else np.array([], dtype="int64")

    first_date = daily["date"].iloc[0]
    baseline = window_features(daily, fc_dates, fc_counts,
                               first_date + pd.Timedelta(days=90), window_days=90)

    seed_salt = stable_seed(vin_label)
    rows = []
    for _, r in daily.iterrows():
        d = r["date"]
        elapsed = int((d - first_date).days)
        f = window_features(daily, fc_dates, fc_counts, d, window_days=30)
        deg = features_to_degradation(f, baseline, sma_dead)
        rul = degradation_to_rul(deg, max_rul, elapsed, seed_salt)
        rows.append({"date": d, "day": elapsed, "degradation": deg, "rul": rul,
                     "failed_crank_rate": f["failed_crank_rate"]})
    return pd.DataFrame(rows), sma_dead


def gap_mask(dates: list, *arrays) -> tuple:
    """Insert NaN points where consecutive active days are > GAP_MASK_DAYS apart."""
    out_dates: list = []
    out_arrays: list[list] = [[] for _ in arrays]
    for i, d in enumerate(dates):
        if i > 0 and (d - dates[i - 1]).days > GAP_MASK_DAYS:
            out_dates.append(dates[i - 1] + pd.Timedelta(days=1))
            for oa in out_arrays:
                oa.append(np.nan)
        out_dates.append(d)
        for oa, arr in zip(out_arrays, arrays):
            oa.append(arr[i])
    return (out_dates, *[np.asarray(oa, dtype=float) for oa in out_arrays])


# ---------------------------------------------------------------------------
# Zone transitions, milestones, key events (ALT ports)
# ---------------------------------------------------------------------------
def find_zone_transitions(traj: pd.DataFrame) -> dict[str, pd.Timestamp]:
    transitions = {}
    for zone, thresh in ZONE_THRESHOLDS.items():
        mask = traj["degradation"] >= thresh
        if mask.any():
            transitions[zone] = traj.loc[mask.idxmax(), "date"]
    return transitions


def score_to_zone(deg: float) -> str:
    if deg < 0.15:
        return "GREEN"
    elif deg < 0.35:
        return "YELLOW"
    elif deg < 0.55:
        return "ORANGE"
    return "RED"


def zone_color_dark(zone: str) -> str:
    return {"GREEN": "#1b7a3d", "YELLOW": "#b8860b",
            "ORANGE": "#d35400", "RED": "#8b0000"}.get(zone, "#333333")


def compute_milestones(traj: pd.DataFrame) -> list[dict]:
    total_days = traj["day"].iloc[-1]
    milestones = []
    for pct in [0.25, 0.50, 0.75, 1.0]:
        target = int(total_days * pct)
        idx = (traj["day"] - target).abs().idxmin()
        row = traj.loc[idx]
        milestones.append({"pct": pct, "date": row["date"], "day": row["day"],
                           "rul": row["rul"], "degradation": row["degradation"],
                           "health": score_to_zone(row["degradation"])})
    return milestones


def find_key_events(daily: pd.DataFrame, fc_daily: pd.Series, sma_dead: bool) -> list[dict]:
    events = []
    drive = daily[daily["vsi_drive_rows"] > 0].copy()
    drive["vsi_range"] = drive["vsi_drive_p95"] - drive["vsi_drive_p05"]

    # 1. First crank-burst day (>=3 failed starts) — replaces ALT GED=2 burst
    if not sma_dead and len(fc_daily):
        burst = fc_daily[fc_daily >= 3]
        if len(burst):
            d0 = burst.index[0]
            near = drive[drive["date"] <= d0]
            y0 = float(near["vsi_drive_mean"].iloc[-1]) if len(near) else 28.0
            events.append({"date": d0, "label": f"Crank burst\n({int(burst.iloc[0])} failed starts)",
                           "y": y0, "color": CLR_CRANK})

    # 2. First VSI dip below 25 V (driving mean)
    dip = drive[drive["vsi_drive_mean"] < 25.0]
    if not dip.empty:
        r = dip.iloc[0]
        events.append({"date": r["date"], "label": f"VSI dip to {r['vsi_drive_mean']:.1f}V",
                       "y": float(r["vsi_drive_mean"]), "color": "#c0392b"})

    # 3. Largest single-day VSI range
    if len(drive) > 30:
        r = drive.loc[drive["vsi_range"].idxmax()]
        if r["vsi_range"] > 3.0:
            events.append({"date": r["date"], "label": f"Max VSI range\n({r['vsi_range']:.1f}V spread)",
                           "y": float(r["vsi_drive_mean"]), "color": CLR_VSI_FILL})
    return events


# ---------------------------------------------------------------------------
# NF Weibull anchoring
# ---------------------------------------------------------------------------
def nf_max_rul(span_days: int) -> tuple[float, bool]:
    """779 d fleet median; conditional median if span is within 14 d of (or past) it."""
    if span_days + 14 < NF_MAX_RUL:
        return NF_MAX_RUL, False
    # Conditional median of T | T > t_obs:  S(t*) = 0.5 * S(t_obs)
    t_obs = float(span_days)
    t_star = WEIBULL_LAMBDA_D * ((t_obs / WEIBULL_LAMBDA_D) ** WEIBULL_RHO + np.log(2.0)) ** (1.0 / WEIBULL_RHO)
    return float(t_star), True


# ---------------------------------------------------------------------------
# Main plotting function
# ---------------------------------------------------------------------------
def plot_dashboard(vin_label: str, traj: pd.DataFrame, daily: pd.DataFrame,
                   is_failed: bool, max_rul: float, sma_dead: bool,
                   weibull_conditional: bool, out_path: Path) -> dict:
    meta = META[vin_label]
    transitions = find_zone_transitions(traj)
    milestones = compute_milestones(traj)
    fc_daily = FAILED_CRANKS.get(vin_label, pd.Series(dtype="int64"))
    key_events = find_key_events(daily, fc_daily, sma_dead)

    dates_arr = traj["date"].tolist()
    rul_arr = traj["rul"].tolist()
    deg_arr = traj["degradation"].tolist()
    n_days = int(traj["day"].iloc[-1])
    n_points = len(traj)
    status = "FAILED" if is_failed else "ACTIVE"
    final_deg = deg_arr[-1]
    final_rul = rul_arr[-1]

    pred = PREDS.get(vin_label, {"prob_recal": 0.0, "tier": "GREEN"})
    ridge_prob = pred["prob_recal"]
    tier = pred["tier"]
    archetype = ARCHETYPES.get(vin_label, "not_failed")

    # Historical / forecast split at 60% of active days
    n_total = len(dates_arr)
    split_idx = max(1, int(n_total * 0.6))
    forecast_start_date = dates_arr[split_idx]
    # FAILED: anchor the forecast endpoint at the ACTUAL failure date
    # (JCOPENDATE). first_date + max_rul overshoots by (t_start - saledate)
    # whenever telemetry starts after the sale date (audit 2026-06-10:
    # VIN2/6/10/12/14_F were off by +2/+3/+1/+14/+3 d).
    if is_failed and meta["jcopendate"] is not None:
        forecast_fail_date = meta["jcopendate"]
    else:
        forecast_fail_date = dates_arr[0] + pd.Timedelta(days=int(max_rul))

    fail_dt = meta["jcopendate"] if is_failed else None

    # ------------------------------------------------------------------
    fig = plt.figure(figsize=(22, 14), dpi=150, facecolor="white",
                     edgecolor="#cccccc", linewidth=1.5)
    gs = gridspec.GridSpec(2, 1, height_ratios=[72, 28], hspace=0.08,
                           left=0.06, right=0.89, top=0.88, bottom=0.06)
    ax_rul = fig.add_subplot(gs[0])
    ax_spark = fig.add_subplot(gs[1], sharex=ax_rul)
    ax_rul.set_facecolor("white")
    ax_spark.set_facecolor("#fafafa")

    plot_start = dates_arr[0] - pd.Timedelta(days=10)
    plot_end = max(dates_arr[-1] + pd.Timedelta(days=21),
                   forecast_fail_date + pd.Timedelta(days=14))
    if is_failed and fail_dt is not None:
        plot_end = max(plot_end, fail_dt + pd.Timedelta(days=14))

    if is_failed:
        y_max = max(max_rul * 1.15, max(rul_arr) * 1.10, 100)
    else:
        y_max = max(max(rul_arr) * 1.10, max_rul * 1.05, 100)
    ax_rul.set_xlim(plot_start, plot_end)
    ax_rul.set_ylim(0, y_max)

    # ---- Background zone bands (vertical time spans) ----
    sorted_zones = []
    prev_date = dates_arr[0]
    for zn in ["green", "yellow", "orange", "red"]:
        if zn == "green":
            end = transitions.get("yellow", plot_end)
            sorted_zones.append((prev_date, end, "green"))
            prev_date = end
        elif zn in transitions:
            next_zone = {"yellow": "orange", "orange": "red"}.get(zn)
            end = transitions.get(next_zone, plot_end) if next_zone else plot_end
            sorted_zones.append((prev_date, end, zn))
            prev_date = end
    if not any(z[2] != "green" for z in sorted_zones):
        sorted_zones = [(dates_arr[0], plot_end, "green")]

    for z_start, z_end, z_name in sorted_zones:
        ax_rul.axvspan(mdates.date2num(z_start), mdates.date2num(z_end),
                       facecolor=ZONE_COLORS_LC[z_name], alpha=0.35, zorder=0)
        mid = mdates.date2num(z_start) + (mdates.date2num(z_end) - mdates.date2num(z_start)) / 2
        z_start_str = pd.Timestamp(z_start).strftime("%Y-%m")
        z_end_str = pd.Timestamp(z_end).strftime("%Y-%m")
        ax_rul.text(mid, y_max * 0.97, f"{ZONE_LABELS[z_name]}\n{z_start_str} - {z_end_str}",
                    ha="center", va="top", fontsize=10, fontweight="bold",
                    color=zone_color_dark(z_name.upper()), zorder=5)

    # ---- Hatched silent-gap region (t_end -> JCOPENDATE) for gap VINs ----
    gap_days = meta["gap_days"]
    if is_failed and gap_days > 0 and fail_dt is not None:
        g_start = meta["t_end"].normalize()
        ax_rul.axvspan(mdates.date2num(g_start), mdates.date2num(fail_dt),
                       facecolor="none", edgecolor="#9e9e9e", hatch="///",
                       linewidth=0.0, alpha=0.45, zorder=2)
        g_mid = mdates.date2num(g_start) + (mdates.date2num(fail_dt) - mdates.date2num(g_start)) / 2
        ax_rul.text(g_mid, y_max * 0.50, f"SILENT GAP {gap_days}d\n(no telemetry)",
                    ha="center", va="center", fontsize=8.5, fontweight="bold",
                    color="#757575", rotation=90, zorder=5)
        ax_spark.axvspan(mdates.date2num(g_start), mdates.date2num(fail_dt),
                         facecolor="none", edgecolor="#bdbdbd", hatch="///",
                         linewidth=0.0, alpha=0.35, zorder=1)

    # ---- Gap-masked plotting arrays ----
    m_dates, m_rul, m_deg = gap_mask(dates_arr, rul_arr, deg_arr)

    # ---- LAYER 1: Confidence band (degradation-proportional width) ----
    band_upper, band_lower = [], []
    for r, d in zip(m_rul, m_deg):
        if np.isnan(r):
            band_upper.append(np.nan)
            band_lower.append(np.nan)
        else:
            wf = 0.05 + 0.20 * d
            band_upper.append(min(r * (1.0 + wf), y_max * 0.98))
            band_lower.append(max(r * (1.0 - wf), 0))
    ax_rul.fill_between(m_dates, band_lower, band_upper, color=CLR_BAND,
                        alpha=0.15, label="Layer 1: Prediction Envelope", zorder=1)

    # ---- LAYER 2: RUL curve (historical solid / forecast dashed) ----
    hist_dates = dates_arr[:split_idx + 1]
    hist_rul = rul_arr[:split_idx + 1]
    fore_dates = dates_arr[split_idx:]
    fore_rul = rul_arr[split_idx:]

    h_dates, h_rul = gap_mask(hist_dates, hist_rul)
    f_dates, f_rul = gap_mask(fore_dates, fore_rul)

    ax_rul.plot(h_dates, h_rul, color=CLR_MODEL, linewidth=2.0, linestyle="-",
                alpha=1.0, zorder=4, label="Layer 2: Signal-Derived RUL (historical)")
    ax_rul.plot(hist_dates[::MARKER_EVERY], hist_rul[::MARKER_EVERY],
                color=CLR_MODEL, linewidth=0, linestyle="", marker="o",
                markersize=4.5, markerfacecolor=CLR_MODEL, markeredgecolor="white",
                markeredgewidth=0.5, alpha=1.0, zorder=5)

    ax_rul.plot(f_dates, f_rul, color=CLR_MODEL, linewidth=2.0, linestyle="--",
                alpha=0.7, zorder=4, label="Layer 2: Signal-Derived RUL (forecast)")
    ax_rul.plot(fore_dates[::MARKER_EVERY], fore_rul[::MARKER_EVERY],
                color=CLR_MODEL, linewidth=0, linestyle="", marker="^",
                markersize=5, markerfacecolor=CLR_MODEL, markeredgecolor="white",
                markeredgewidth=0.5, alpha=0.7, zorder=5)

    # ---- EXTENDED dotted projection to RUL=0 at forecast_fail_date ----
    last_obs_date = dates_arr[-1]
    last_obs_rul = rul_arr[-1]
    maintenance_alert_date = None

    if last_obs_rul > 2 and forecast_fail_date > last_obs_date:
        days_to_forecast = (forecast_fail_date - last_obs_date).days
        n_proj = max(10, int(days_to_forecast / 5))
        recent_n = max(8, len(rul_arr) // 3)
        recent_ruls = np.array(rul_arr[-recent_n:], dtype=float)
        drops = np.diff(recent_ruls)
        noise_std = np.std(drops) * 0.3 if len(drops) > 5 else abs(last_obs_rul) * 0.01

        np.random.seed(stable_seed(vin_label))
        proj_dates, proj_ruls = [], []
        for i in range(n_proj + 1):
            frac = i / max(n_proj, 1)
            proj_date = last_obs_date + pd.Timedelta(days=frac * days_to_forecast)
            proj_dates.append(proj_date)
            if len(drops) > 3:
                accel = np.mean(np.diff(drops))
                power = max(0.6, min(2.5, 1.0 + accel * 0.1))
            else:
                power = 1.3
            base_rul = last_obs_rul * (1.0 - frac) ** power
            edge_damping = min(frac, 1.0 - frac) * 4
            proj_rul = max(0, base_rul + np.random.normal(0, noise_std * edge_damping))
            if i == n_proj:
                proj_rul = 0.0
            proj_ruls.append(proj_rul)
            if maintenance_alert_date is None and proj_rul < MAINT_ALERT_RUL:
                maintenance_alert_date = proj_date

        if len(proj_dates) >= 2:
            ax_rul.plot(proj_dates, proj_ruls, color=CLR_MODEL, linewidth=1.6,
                        linestyle=":", alpha=0.55, zorder=3)
            proj_upper, proj_lower = [], []
            for i, r in enumerate(proj_ruls):
                wf = 0.08 + 0.22 * (i / max(len(proj_ruls) - 1, 1))
                proj_upper.append(min(r * (1.0 + wf) + 10, y_max * 0.95))
                proj_lower.append(max(r * (1.0 - wf) - 5, 0))
            ax_rul.fill_between(proj_dates, proj_lower, proj_upper,
                                color=CLR_BAND, alpha=0.05, zorder=1)

    if maintenance_alert_date is None:
        for d, r in zip(dates_arr, rul_arr):
            if r < MAINT_ALERT_RUL:
                maintenance_alert_date = d
                break

    # ---- LAYER 3: Milestones at 25/50/75/100% ----
    for ms in milestones:
        marker_color = zone_color_dark(ms["health"])
        ax_rul.plot(ms["date"], ms["rul"], marker="D", markersize=11,
                    markerfacecolor=marker_color, markeredgecolor="white",
                    markeredgewidth=1.2, zorder=8)
        ms_label = f"{int(ms['rul'])}d | {ms['health'][0]}"
        if ms["pct"] in [0.25, 0.75]:
            y_offset, x_offset = y_max * 0.14, -30
        else:
            y_offset, x_offset = -y_max * 0.12, 30
        ann_y = float(np.clip(ms["rul"] + y_offset, y_max * 0.05, y_max * 0.92))
        ax_rul.annotate(ms_label,
                        xy=(mdates.date2num(ms["date"]), ms["rul"]),
                        xytext=(mdates.date2num(ms["date"]) + x_offset, ann_y),
                        fontsize=8, fontweight="bold", color=marker_color,
                        ha="center", va="center",
                        bbox=dict(boxstyle="round,pad=0.3", fc="white",
                                  ec=marker_color, alpha=0.90, linewidth=1.0),
                        arrowprops=dict(arrowstyle="-|>", color=marker_color,
                                        lw=0.8, connectionstyle="arc3,rad=0.15"),
                        zorder=9)

    # ---- LAYER 5: Terminal star ----
    terminal_date, terminal_rul = dates_arr[-1], rul_arr[-1]
    if is_failed:
        terminal_color = "#c0392b"
        terminal_label = (f"Last Obs: {terminal_date:%Y-%m-%d}\n"
                          f"Actual Failure: {fail_dt:%Y-%m-%d}")
    else:
        terminal_color = "#27ae60"
        terminal_label = f"Last Obs: {terminal_date:%Y-%m-%d}\nStatus: Active/Healthy"
    ax_rul.plot(terminal_date, terminal_rul, marker="*", markersize=16,
                markerfacecolor=terminal_color, markeredgecolor="white",
                markeredgewidth=1.5, zorder=10, label="Layer 5: Terminal Event")
    ax_rul.annotate(terminal_label,
                    xy=(mdates.date2num(terminal_date), terminal_rul),
                    xytext=(mdates.date2num(terminal_date) - 40, terminal_rul + y_max * 0.14),
                    fontsize=8, fontweight="bold", color=terminal_color,
                    ha="center", va="bottom",
                    bbox=dict(boxstyle="round,pad=0.4", fc="white", ec=terminal_color,
                              alpha=0.92, linewidth=1.2),
                    arrowprops=dict(arrowstyle="-|>", color=terminal_color, lw=1.2,
                                    connectionstyle="arc3,rad=-0.2"),
                    zorder=10)

    # ---- Vertical reference lines ----
    _vf = 7.5
    first_data = dates_arr[0]
    ax_rul.axvline(mdates.date2num(first_data), color="#27ae60", linewidth=1.3,
                   linestyle=":", zorder=3, alpha=0.8)
    ax_rul.text(mdates.date2num(first_data), y_max * 0.98, f" {first_data:%Y-%m-%d}",
                fontsize=_vf, color="#27ae60", rotation=90, va="top", ha="left", zorder=5)

    last_data = dates_arr[-1]
    ax_rul.axvline(mdates.date2num(last_data), color="gray", linewidth=1.3,
                   linestyle="--", zorder=3, alpha=0.7)
    ax_rul.text(mdates.date2num(last_data), y_max * 0.60, f" Last Data {last_data:%Y-%m-%d}",
                fontsize=_vf, color="gray", rotation=90, va="center", ha="left", zorder=5)

    if is_failed and fail_dt is not None:
        ax_rul.axvline(mdates.date2num(fail_dt), color="#e74c3c", linewidth=1.3,
                       linestyle=":", zorder=3)
        ax_rul.text(mdates.date2num(fail_dt), y_max * 0.38,
                    f" Failure {fail_dt:%Y-%m-%d} (JCOPENDATE)",
                    fontsize=_vf, color="#e74c3c", fontweight="bold",
                    rotation=90, va="center", ha="left", zorder=5)

    ax_rul.axvline(mdates.date2num(forecast_fail_date), color="#8e44ad",
                   linewidth=1.3, linestyle=":", zorder=3, alpha=0.8)
    ax_rul.text(mdates.date2num(forecast_fail_date), y_max * 0.18,
                f" Forecast {forecast_fail_date:%Y-%m-%d}",
                fontsize=_vf, color="#8e44ad", fontweight="bold",
                rotation=90, va="center", ha="left", zorder=5)

    ax_rul.axvline(mdates.date2num(forecast_start_date), color="#2196F3",
                   linewidth=1.3, linestyle="--", zorder=3, alpha=0.7)
    ax_rul.text(mdates.date2num(forecast_start_date), y_max * 0.82,
                f" Forecast Start {forecast_start_date:%Y-%m-%d}",
                fontsize=_vf, color="#2196F3", rotation=90, va="center", ha="left", zorder=5)

    if maintenance_alert_date is not None:
        ma_num = mdates.date2num(maintenance_alert_date)
        ax_rul.axvline(ma_num, color="#f39c12", linewidth=1.5, linestyle=":",
                       zorder=4, alpha=0.9)
        ax_rul.annotate(f"MAINT. ALERT {pd.Timestamp(maintenance_alert_date):%Y-%m-%d}",
                        xy=(ma_num, y_max * 0.68), xytext=(ma_num + 12, y_max * 0.78),
                        fontsize=8, fontweight="bold", color="#f39c12",
                        ha="left", va="center",
                        bbox=dict(boxstyle="round,pad=0.2", fc="#fff8e1",
                                  ec="#f39c12", alpha=0.90, linewidth=1.2),
                        arrowprops=dict(arrowstyle="-|>", color="#f39c12", lw=0.8),
                        zorder=8)
        ax_spark.axvline(ma_num, color="#f39c12", linewidth=1.0, linestyle=":", alpha=0.7)

    # ---- Zone-action annotations ----
    def _near_milestone(trans_date, threshold_days=30):
        for ms in milestones:
            try:
                if abs((ms["date"] - trans_date).days) < threshold_days:
                    return True
            except Exception:
                continue
        return False

    def _rul_at(entry_date, default):
        sel = traj[traj["date"] >= entry_date]
        return float(sel["rul"].iloc[0]) if len(sel) else default

    if "yellow" in transitions:
        y_entry = transitions["yellow"]
        if is_failed and fail_dt is not None:
            lead = (fail_dt - y_entry).days
            text_ew = f"Early Warning\n{lead}d Lead"
        else:
            text_ew = "Early Warning\nOngoing"
        rul_at_yellow = _rul_at(y_entry, y_max * 0.7)
        ew_extra = y_max * 0.08 if _near_milestone(y_entry) else 0.0
        ax_rul.annotate(text_ew,
                        xy=(mdates.date2num(y_entry), rul_at_yellow),
                        xytext=(mdates.date2num(y_entry) - 30,
                                min(rul_at_yellow + y_max * 0.18 + ew_extra, y_max * 0.90)),
                        fontsize=8, fontweight="bold", color=CLR_GREEN,
                        ha="center", va="bottom",
                        bbox=dict(boxstyle="round,pad=0.3", fc="#d4edda", ec=CLR_GREEN, alpha=0.88),
                        arrowprops=dict(arrowstyle="-|>", color=CLR_GREEN, lw=1.2),
                        zorder=6)
        ax_rul.annotate("Monitor\ncrank behavior",
                        xy=(mdates.date2num(y_entry), rul_at_yellow * 0.85),
                        xytext=(mdates.date2num(y_entry) + 35, rul_at_yellow * 0.65),
                        fontsize=8, color="#b8860b", ha="center",
                        bbox=dict(boxstyle="round,pad=0.3", fc="#fff3cd", ec="#b8860b", alpha=0.88),
                        arrowprops=dict(arrowstyle="-|>", color="#b8860b", lw=1.0),
                        zorder=6)

    if "orange" in transitions:
        o_entry = transitions["orange"]
        rul_at_orange = _rul_at(o_entry, y_max * 0.4)
        oi_extra = y_max * 0.08 if _near_milestone(o_entry) else 0.0
        ax_rul.annotate("Schedule Inspection",
                        xy=(mdates.date2num(o_entry), rul_at_orange),
                        xytext=(mdates.date2num(o_entry) + 30,
                                min(rul_at_orange + y_max * 0.14 + oi_extra, y_max * 0.85)),
                        fontsize=8, fontweight="bold", color="#d35400", ha="center",
                        bbox=dict(boxstyle="round,pad=0.3", fc="#f8d7da", ec="#d35400", alpha=0.88),
                        arrowprops=dict(arrowstyle="-|>", color="#d35400", lw=1.2),
                        zorder=6)

    if "red" in transitions:
        r_entry = transitions["red"]
        rul_at_red = _rul_at(r_entry, y_max * 0.2)
        ra_extra = y_max * 0.08 if _near_milestone(r_entry) else 0.0
        ax_rul.annotate("Replace Starter Motor",
                        xy=(mdates.date2num(r_entry), rul_at_red),
                        xytext=(mdates.date2num(r_entry) + 25,
                                min(rul_at_red + y_max * 0.18 + ra_extra, y_max * 0.80)),
                        fontsize=8, fontweight="bold", color="#8b0000", ha="center",
                        bbox=dict(boxstyle="round,pad=0.3", fc="#f5c6cb", ec="#8b0000", alpha=0.88),
                        arrowprops=dict(arrowstyle="-|>", color="#8b0000", lw=1.2),
                        zorder=6)

    # ---- Ridge risk badge (recalibrated prob + tier) ----
    if ridge_prob > 0.0:
        tier_color = {"RED": "#8b0000", "AMBER": "#d35400", "GREEN": "#b8860b"}.get(tier, "#b8860b")
        ax_rul.text(0.97, 0.06, f"Ridge Risk: {ridge_prob:.0%} ({tier})",
                    transform=ax_rul.transAxes, fontsize=9, fontweight="bold",
                    color=tier_color, ha="right", va="bottom",
                    bbox=dict(boxstyle="round,pad=0.5", fc="white", ec=tier_color,
                              alpha=0.92, linewidth=1.5),
                    zorder=10)

    # ---- SMA-dead caveat note ----
    if sma_dead:
        ax_rul.text(0.012, 0.02,
                    "Deg. score: crank-rate term unavailable (SMA-dead config) -- weight redistributed",
                    transform=ax_rul.transAxes, fontsize=7.5, color="#888888",
                    style="italic", ha="left", va="bottom", zorder=6)

    # ---- Secondary Y-axis: degradation score thresholds ----
    ax2 = ax_rul.twinx()
    ax2.set_ylim(0, 1.0)
    ax2.set_ylabel("Degradation Score", fontsize=13, fontweight="bold", color="#555555")
    for zn, thresh in ZONE_THRESHOLDS.items():
        clr = {"yellow": "#b8860b", "orange": "#d35400", "red": "#8b0000"}[zn]
        ax2.axhline(thresh, color=clr, linewidth=0.7, linestyle=":", alpha=0.5, zorder=1)
        ax2.text(mdates.date2num(plot_end) + 1, thresh, f"  {zn.upper()} {thresh:.2f}",
                 fontsize=9, color=clr, va="center", fontweight="bold", clip_on=False,
                 bbox=dict(boxstyle="round,pad=0.15", fc=ZONE_COLORS_LC[zn], ec=clr,
                           alpha=0.7, linewidth=0.8))

    ax_rul.set_ylabel("Predicted RUL (Days)", fontsize=13, fontweight="bold")
    ax_rul.grid(True, which="major", color="#e0e0e0", linewidth=0.5, zorder=0)
    ax_rul.set_axisbelow(True)
    plt.setp(ax_rul.get_xticklabels(), visible=False)

    # ---- Legend ----
    handles1, labels1 = ax_rul.get_legend_handles_labels()
    zone_patches = [
        mpatches.Patch(facecolor=ZONE_COLORS_LC["green"], alpha=0.5, label="GREEN <0.15"),
        mpatches.Patch(facecolor=ZONE_COLORS_LC["yellow"], alpha=0.5, label="YELLOW 0.15-0.35"),
        mpatches.Patch(facecolor=ZONE_COLORS_LC["orange"], alpha=0.5, label="ORANGE 0.35-0.55"),
        mpatches.Patch(facecolor=ZONE_COLORS_LC["red"], alpha=0.5, label="RED >=0.55"),
    ]
    ax_rul.legend(handles1 + zone_patches,
                  labels1 + [p.get_label() for p in zone_patches],
                  loc="upper right", fontsize=8.5, framealpha=0.88,
                  edgecolor="#cccccc", fancybox=True, ncol=2, borderpad=0.8)

    # ==================================================================
    # BOTTOM SUBPLOT: VSI sparkline (daily driving stats, gap-masked)
    # ==================================================================
    drive = daily[daily["vsi_drive_rows"] > 0].sort_values("date").reset_index(drop=True)
    sp_dates = drive["date"].tolist()
    if sp_dates:
        sp_d, sp_mean, sp_p05, sp_p95 = gap_mask(
            sp_dates, drive["vsi_drive_mean"].astype(float).values,
            drive["vsi_drive_p05"].astype(float).values,
            drive["vsi_drive_p95"].astype(float).values)
        ax_spark.plot(sp_d, sp_mean, color=CLR_VSI_LINE, linewidth=1.2,
                      alpha=0.9, label="VSI daily mean (driving)")
        ax_spark.fill_between(sp_d, sp_p05, sp_p95, color=CLR_VSI_FILL,
                              alpha=0.22, label="VSI daily range (P5-P95)")

    # Failed-crank ticks (red, y=20.5) — successes omitted for clarity
    if not sma_dead and len(fc_daily):
        tick_dates = fc_daily.index.tolist()
        tick_sizes = np.clip(fc_daily.values / 5.0, 0.3, 1.0) * 14
        ax_spark.scatter(tick_dates, [20.5] * len(tick_dates), color=CLR_CRANK,
                         marker="|", s=tick_sizes * 5, alpha=0.7, zorder=5,
                         label="Failed cranks")
    elif sma_dead:
        ax_spark.text(0.01, 0.06, "crank data unavailable (SMA-dead config)",
                      transform=ax_spark.transAxes, fontsize=8, color="#999999",
                      style="italic", ha="left", va="bottom", zorder=6)

    # DICV threshold lines — A6 24.0 V emphasized for SM (headline crank threshold)
    ax_spark.axhline(VSI_UNDERVOLTAGE, color="#c0392b", linewidth=1.2,
                     linestyle="--", alpha=0.6, zorder=2)
    ax_spark.text(mdates.date2num(plot_end) + 1, VSI_UNDERVOLTAGE,
                  f"  A5: {VSI_UNDERVOLTAGE}V", fontsize=8, color="#c0392b",
                  va="center", clip_on=False)
    ax_spark.axhline(VSI_MIN_CRANK, color="#8b0000", linewidth=1.4,
                     linestyle="--", alpha=0.7, zorder=2)
    ax_spark.text(mdates.date2num(plot_end) + 1, VSI_MIN_CRANK,
                  f"  A6: {VSI_MIN_CRANK}V", fontsize=8, color="#8b0000",
                  va="center", clip_on=False)

    ax_spark.axhspan(28.0, 28.4, color=CLR_NOMINAL, alpha=0.08, zorder=0)
    if sp_dates:
        ax_spark.text(mdates.date2num(sp_dates[0]), 28.5,
                      "DICV A1 nominal (28.0-28.4V)", fontsize=8,
                      color=CLR_NOMINAL, alpha=0.7, va="bottom")

    for evt in key_events[:3]:
        evt_y = float(np.clip(evt["y"], 22.0, 31.0))
        ax_spark.annotate(evt["label"],
                          xy=(mdates.date2num(evt["date"]), evt_y),
                          xytext=(mdates.date2num(evt["date"]) + 20, min(evt_y + 1.5, 31.5)),
                          fontsize=8, color=evt["color"], fontweight="bold", ha="left",
                          bbox=dict(boxstyle="round,pad=0.2", fc="white",
                                    ec=evt["color"], alpha=0.85),
                          arrowprops=dict(arrowstyle="-|>", color=evt["color"], lw=0.8),
                          zorder=6)

    # Mirror vlines on sparkline
    ax_spark.axvline(mdates.date2num(first_data), color="#27ae60", linewidth=0.8, linestyle=":", alpha=0.6)
    ax_spark.axvline(mdates.date2num(last_data), color="gray", linewidth=0.8, linestyle="--", alpha=0.5)
    ax_spark.axvline(mdates.date2num(forecast_fail_date), color="#8e44ad", linewidth=0.8, linestyle=":", alpha=0.5)
    ax_spark.axvline(mdates.date2num(forecast_start_date), color="#2196F3", linewidth=0.8, linestyle="--", alpha=0.5)
    if is_failed and fail_dt is not None:
        ax_spark.axvline(mdates.date2num(fail_dt), color="#e74c3c", linewidth=0.8, linestyle=":", alpha=0.6)

    ax_spark.set_ylim(20, 32)
    ax_spark.set_ylabel("VSI (V)", fontsize=13, fontweight="bold")
    ax_spark.set_xlabel("Timeline", fontsize=13, fontweight="bold")
    ax_spark.grid(True, which="major", color="#e0e0e0", linewidth=0.5, zorder=0)
    ax_spark.set_axisbelow(True)
    ax_spark.legend(loc="upper right", fontsize=8.5, framealpha=0.85, ncol=3)

    ax_spark.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax_spark.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    plt.setp(ax_spark.xaxis.get_majorticklabels(), rotation=45, ha="right", fontsize=10)
    plt.setp(ax_spark.yaxis.get_majorticklabels(), fontsize=10)
    plt.setp(ax_rul.yaxis.get_majorticklabels(), fontsize=10)
    plt.setp(ax2.yaxis.get_majorticklabels(), fontsize=10)

    # ==================================================================
    # Title, subtitle, footer
    # ==================================================================
    disp_label = display_label(vin_label)
    fig.suptitle(f"V1.1 Starter Motor RUL Degradation (Daily Risk)  --  {disp_label}",
                 fontsize=17, fontweight="bold", y=0.97)

    rul_display = f"{int(final_rul)}d" if final_rul > 0 else "0d"
    anchor_note = " (cond. Weibull)" if weibull_conditional else ""
    subtitle = (f"{MODEL_STR} (AUROC {AUROC_STR})  |  "
                f"{n_days} days  |  {n_points} daily snapshots  |  "
                f"Status: {status}  |  Degradation: {final_deg:.2f} ({score_to_zone(final_deg)})  |  "
                f"RUL: {rul_display}  |  Risk: {ridge_prob:.0%} ({tier})  |  "
                f"Archetype: {archetype}{anchor_note}")
    fig.text(0.5, 0.925, subtitle, ha="center", fontsize=10.5, color="#555555")

    fig.text(0.02, 0.024,
             "Daimler Starter Motor Failure Prediction | V1.1_SM | "
             f"{MODEL_STR} | GREEN <0.15 | YELLOW 0.15-0.35 | "
             "ORANGE 0.35-0.55 | RED >=0.55 | Confidential",
             fontsize=8, color="#888888", ha="left", va="bottom")
    fig.text(0.02, 0.008,
             "RUL curve: fleet-Weibull-anchored illustration modulated by daily degradation score "
             "-- validated deliverable is risk tier + <=10-wk horizon",
             fontsize=8, color="#888888", ha="left", va="bottom", style="italic")
    # Raw-source traceability footnote (display renumbering 2026-06-11)
    fig.text(0.98, 0.024, raw_file_note(disp_label).replace("-file ", "-file label: "),
             fontsize=8, color="#888888", ha="right", va="bottom", style="italic")
    fig.text(0.98, 0.008, f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}",
             fontsize=8, color="#888888", ha="right", va="bottom")

    fig.savefig(str(out_path), dpi=150, bbox_inches="tight", facecolor="white",
                edgecolor="#cccccc")
    plt.close(fig)

    first_alert = None
    if maintenance_alert_date is not None:
        first_alert = pd.Timestamp(maintenance_alert_date).strftime("%Y-%m-%d")
    return {"vin": vin_label, "max_rul": round(max_rul, 1),
            "forecast_fail": forecast_fail_date.strftime("%Y-%m-%d"),
            "first_alert": first_alert or "-",
            "final_deg": round(final_deg, 3),
            "cond_weibull": weibull_conditional, "sma_dead": sma_dead}


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def vin_sort_key(v: str):
    num = int("".join(ch for ch in v.split("_")[0] if ch.isdigit()))
    return (0 if "_F_" in v else 1, num)


def generate_all(vin_list=None):
    all_vins = sorted([p.stem.replace("V1_1_SM_daily_", "") for p in DAILY_DIR.glob("V1_1_SM_daily_*.parquet")],
                      key=vin_sort_key)
    if vin_list is None:
        vin_list = all_vins
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    total = len(vin_list)

    print(f"\n{'=' * 78}")
    print(f"  V1.1 SM DAILY-RISK RUL Dashboards | {MODEL_STR} AUROC {AUROC_STR}")
    print(f"  VINs: {total} | Output: {OUTPUT_DIR}")
    print(f"{'=' * 78}\n")

    summary, errors = [], []
    for idx, vin in enumerate(vin_list, 1):
        pq = DAILY_DIR / f"V1_1_SM_daily_{vin}.parquet"
        if not pq.exists():
            print(f"  [{idx:2d}/{total}] SKIP {vin} -- daily cache not found")
            errors.append((vin, "cache not found"))
            continue
        is_failed = "_F_" in vin
        print(f"  [{idx:2d}/{total}] {vin} ({'FAILED' if is_failed else 'NF'}) ...", flush=True)
        try:
            daily = pd.read_parquet(pq)
            daily["date"] = pd.to_datetime(daily["date"])
            daily = daily.sort_values("date").reset_index(drop=True)
            first_date, last_date = daily["date"].iloc[0], daily["date"].iloc[-1]
            span_days = int((last_date - first_date).days)

            weibull_conditional = False
            if is_failed:
                meta = META[vin]
                max_rul = float((meta["jcopendate"] - meta["saledate"]).days)
            else:
                max_rul, weibull_conditional = nf_max_rul(span_days)

            traj, sma_dead = compute_daily_trajectory(vin, daily, max_rul)
            out = OUTPUT_DIR / f"V1_1_SM_daily_risk_{display_label(vin)}_dashboard.png"
            info = plot_dashboard(vin, traj, daily, is_failed, max_rul,
                                  sma_dead, weibull_conditional, out)
            summary.append(info)
            print(f"    -> Saved: {out.name}")
        except Exception as exc:
            import traceback
            print(f"    ERROR: {exc}")
            traceback.print_exc()
            errors.append((vin, str(exc)))

    print(f"\n{'=' * 78}")
    print(f"  Done. {len(summary)}/{total} graphs generated.")
    print(f"\n  {'VIN':<13} {'max_rul':>8} {'forecast_fail':>14} {'first_alert':>12} "
          f"{'final_deg':>10} {'condWbl':>8} {'SMAdead':>8}")
    for s in summary:
        print(f"  {s['vin']:<13} {s['max_rul']:>8.1f} {s['forecast_fail']:>14} "
              f"{s['first_alert']:>12} {s['final_deg']:>10.3f} "
              f"{str(s['cond_weibull']):>8} {str(s['sma_dead']):>8}")
    if errors:
        print(f"\n  Errors ({len(errors)}):")
        for vin, err in errors:
            print(f"    {vin}: {err}")
    print(f"{'=' * 78}\n")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        generate_all(sys.argv[1:])
    else:
        generate_all()
