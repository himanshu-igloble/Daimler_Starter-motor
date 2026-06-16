"""
V1_SM_production_graphs.py  —  Phase 6: Production Dashboards
BharatBenz Starter Motor predictive maintenance pipeline.

Produces: STARTER MOTOR/graphs/V1_SM_{VIN_LABEL}_dashboard.png  (34 files)

4-panel professional layout per VIN (graph-design conventions from the ALT
project: no trend connector between sparse points; reference lines on ALL
VINs, failed and non-failed alike):

  Panel 1 — weekly vsi_drive_mean ± 1 std band, 24V/21V/32V reference lines.
  Panel 2 — monthly crank physics: mean dur_s + mean dip_depth grouped bars
            (left axis), monthly failed-crank rate line (right axis, %).
            Non-artifact events only; None-success excluded from the rate.
  Panel 3 — horizontal risk gauge: GREEN (<0.35) / AMBER (0.35–0.55) /
            RED (>=0.55), needle at the VIN's LOVO y_prob, annotation with
            tier, correctness, AUROC + winner features.
  Panel 4 — weekly crank-event strip (artifacts as grey stacked segment);
            silent-gap region hatched for the 5 GAP_VINS; JCOPENDATE marker
            on ALL failed VINs (= t_end + gap_days; gap_days = 0 if no gap).

Anchoring: t_end = last week in that VIN's weekly cache.  JCOPENDATE is
NEVER in the telemetry — for GAP_VINS it lies gap_days after t_end.
"""

from pathlib import Path
from importlib.util import spec_from_file_location, module_from_spec
import json
import warnings
warnings.filterwarnings("ignore")

# ── Config import (directory has a space) ────────────────────────────────────
_spec = spec_from_file_location(
    "v1_sm_config",
    Path(__file__).resolve().parent / "V1_SM_config.py"
)
cfg = module_from_spec(_spec)
_spec.loader.exec_module(cfg)

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import FancyArrow

# ── Style constants ──────────────────────────────────────────────────────────
TIER_COLORS = {"GREEN": "#2e7d32", "AMBER": "#ef6c00", "RED": "#c62828"}
TIER_BAND = {"GREEN": "#a5d6a7", "AMBER": "#ffcc80", "RED": "#ef9a9a"}
GREEN_LT, AMBER_LT = 0.35, 0.55          # exact tier boundaries
C_VSI = "#1565c0"
C_DUR = "#5e88c2"
C_DIP = "#8e6bb5"
C_FCR = "#c62828"
C_EVT = "#4e79a7"
C_ART = "#9e9e9e"
C_JCO = "#b71c1c"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "axes.titlesize": 11.5,
    "axes.titleweight": "bold",
    "axes.labelsize": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.18,
    "grid.linewidth": 0.6,
})


def monday_week(ts: pd.Series) -> pd.Series:
    """Floor timestamps to Monday week-start (matches weekly cache 'week')."""
    d = ts.dt.normalize()
    return d - pd.to_timedelta(d.dt.weekday, unit="D")


# ─────────────────────────────────────────────────────────────────────────────
# Load inputs
# ─────────────────────────────────────────────────────────────────────────────
print("Loading weekly cache, crank events, LOVO predictions, ridge spec...")
weekly_files = sorted(cfg.CACHE_WEEKLY.glob("V1_SM_weekly_*.parquet"))
weekly = pd.concat([pd.read_parquet(f) for f in weekly_files], ignore_index=True)
events = pd.read_parquet(cfg.CACHE_EVENTS / "V1_SM_crank_events.parquet")
preds = pd.read_csv(cfg.RESULTS / "V1_SM_lovo_predictions.csv").set_index("vin_label")
spec = json.loads((cfg.RESULTS / "V1_SM_ridge_spec.json").read_text())

# Footer values stay current on rerun: AUROC from the ridge spec; NF control
# FP rate = share of NF VINs the lead-time channel flags "trending" (one row
# per VIN after dedup on vin_label).
_verd = (pd.read_csv(cfg.RESULTS / "V1_SM_lead_time_verdicts.csv")
           .drop_duplicates("vin_label"))
_nf = _verd[~_verd["failed"]]
NF_FP_PCT = 100.0 * (_nf["vin_verdict"] == "trending").mean()
FOOTER = (f"Risk from {cfg.N_VINS}-fold LOVO Ridge (AUROC {spec['auroc']:.3f}); "
          f"lead-time channel not validated (NF control FP {NF_FP_PCT:.0f}%)")

assert weekly["vin_label"].nunique() == cfg.N_VINS, "WEEKLY VIN COUNT MISMATCH"
assert events["vin_label"].nunique() == cfg.N_VINS, "EVENT VIN COUNT MISMATCH"
assert len(preds) == cfg.N_VINS, "PREDICTION VIN COUNT MISMATCH"

events["week"] = monday_week(events["ts_start"])
events["month"] = events["ts_start"].dt.to_period("M").dt.to_timestamp()
events["success_num"] = events["success"].map({True: 1.0, False: 0.0})  # None->NaN

cfg.GRAPHS.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Panel renderers
# ─────────────────────────────────────────────────────────────────────────────

def panel1_voltage(ax, wk: pd.DataFrame):
    """Weekly vsi_drive_mean ± 1 std band + DICV reference lines (ALL VINs)."""
    s = wk.dropna(subset=["vsi_drive_mean"]).sort_values("week")
    if len(s):
        # Reindex to the full Monday-week grid so internal telemetry gaps
        # become NaN — NaN breaks both plot and fill_between (no straight
        # bridges across multi-week dead zones). Markers keep isolated
        # real points visible.
        s = (s.set_index("week")[["vsi_drive_mean", "vsi_drive_std"]]
               .resample("W-MON").asfreq().reset_index())
        std = s["vsi_drive_std"].fillna(0.0)   # gap weeks stay NaN via mean
        ax.fill_between(s["week"], s["vsi_drive_mean"] - std,
                        s["vsi_drive_mean"] + std,
                        color=C_VSI, alpha=0.18, linewidth=0,
                        label="±1 std (weekly)")
        ax.plot(s["week"], s["vsi_drive_mean"], color=C_VSI, lw=1.3,
                marker="o", ms=3, label="vsi_drive_mean (weekly)")
    # Reference lines on ALL VINs (graph-design convention)
    ax.axhline(32.0, color="#c62828", lw=1.0, ls="--", alpha=0.85)
    ax.axhline(24.0, color="#2e7d32", lw=1.0, ls="--", alpha=0.85)
    ax.axhline(21.0, color="#e65100", lw=1.0, ls="--", alpha=0.85)
    x_txt = 0.005
    ax.text(x_txt, 32.0, " 32V overcharge (DICV A4)", transform=ax.get_yaxis_transform(),
            va="bottom", fontsize=8, color="#c62828")
    ax.text(x_txt, 24.0, " 24V crank floor (DICV A6)", transform=ax.get_yaxis_transform(),
            va="bottom", fontsize=8, color="#2e7d32")
    ax.text(x_txt, 21.0, " 21V severe-low (DICV A5)", transform=ax.get_yaxis_transform(),
            va="bottom", fontsize=8, color="#e65100")
    ax.set_ylim(18, 34)
    ax.set_ylabel("Drive-regime voltage (V)")
    ax.set_title("Panel 1 — Weekly drive-regime supply voltage (VSI, RPM > 700)",
                 loc="left")
    if len(s):
        ax.legend(loc="lower left", fontsize=8, framealpha=0.6)


def panel2_crank_physics(ax, ev: pd.DataFrame):
    """Monthly crank physics from NON-ARTIFACT events: dur/dip bars + rate line."""
    e = ev[~ev["artifact"]]
    axr = ax.twinx()
    axr.spines["right"].set_visible(True)
    axr.grid(False)
    if len(e):
        g = e.groupby("month")
        m = pd.DataFrame({
            "dur": g["dur_s"].mean(),
            "dip": g["dip_depth"].mean(),
            "fcr": (1.0 - g["success_num"].mean()) * 100.0,  # None excluded
        }).reset_index()
        off = pd.Timedelta(days=6)
        w = 11  # bar width (days)
        ax.bar(m["month"] + pd.Timedelta(days=9) - off, m["dur"], width=w,
               color=C_DUR, alpha=0.85, label="mean crank duration (s)",
               zorder=2)
        ax.bar(m["month"] + pd.Timedelta(days=9) + off, m["dip"], width=w,
               color=C_DIP, alpha=0.85, label="mean voltage dip depth (V)",
               zorder=2)
        # Gap-aware rate line: reindex to the full monthly grid so missing
        # months become NaN (breaks the line instead of bridging gaps);
        # markers keep isolated real months visible.
        fcr = m.set_index("month")["fcr"].asfreq("MS")
        axr.plot(fcr.index + pd.Timedelta(days=9), fcr, color=C_FCR,
                 lw=1.2, marker="s", ms=3.5, label="failed-crank rate (%)",
                 zorder=3)
    ax.set_ylabel("Duration (s)  /  Dip depth (V)")
    axr.set_ylabel("Failed-crank rate (%)", color=C_FCR)
    axr.tick_params(axis="y", labelcolor=C_FCR)
    # headroom so the legend never sits on top of the tallest bars / line
    ax.set_ylim(0, max(ax.get_ylim()[1], 1e-6) * 1.30)
    axr.set_ylim(0, max(axr.get_ylim()[1], 1e-6) * 1.30)
    ax.set_title("Panel 2 — Monthly crank physics (non-artifact events; "
                 "None-success excluded from rate)", loc="left")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = axr.get_legend_handles_labels()
    if h1 or h2:
        ax.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=8,
                  framealpha=0.6, ncol=3)
    return axr


def panel3_risk_gauge(ax, pred: pd.Series, is_failed: bool):
    """Horizontal risk gauge with LOVO probability needle."""
    prob = float(pred["y_prob"])
    tier = str(pred["alert_tier"])
    correct = bool(pred["correct"])

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.grid(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_visible(True)
    ax.set_yticks([])

    band_y, band_h = 0.30, 0.34
    ax.axhspan(band_y, band_y + band_h, 0.0, GREEN_LT,
               facecolor=TIER_BAND["GREEN"], zorder=1)
    ax.axhspan(band_y, band_y + band_h, GREEN_LT, AMBER_LT,
               facecolor=TIER_BAND["AMBER"], zorder=1)
    ax.axhspan(band_y, band_y + band_h, AMBER_LT, 1.0,
               facecolor=TIER_BAND["RED"], zorder=1)
    for lab, x0, x1 in (("GREEN", 0.0, GREEN_LT), ("AMBER", GREEN_LT, AMBER_LT),
                        ("RED", AMBER_LT, 1.0)):
        ax.text((x0 + x1) / 2, band_y + band_h / 2, lab, ha="center",
                va="center", fontsize=9, fontweight="bold",
                color=TIER_COLORS[lab], alpha=0.85, zorder=2)
    # tier boundary ticks + Youden threshold
    for b in (GREEN_LT, AMBER_LT):
        ax.plot([b, b], [band_y - 0.04, band_y + band_h + 0.04],
                color="black", lw=0.8, alpha=0.5, zorder=3)
    thr = float(spec["youden_threshold"])
    ax.plot([thr, thr], [band_y - 0.06, band_y + band_h + 0.06], color="black",
            lw=1.0, ls=":", zorder=3)
    ax.text(thr, band_y - 0.10, f"Youden thr {thr:.3f}", ha="center",
            va="top", fontsize=7.5, color="black", alpha=0.8)

    # needle
    ax.add_patch(FancyArrow(prob, band_y + band_h + 0.26, 0, -0.20,
                            width=0.006, head_width=0.022, head_length=0.07,
                            length_includes_head=True, color="black", zorder=5))
    ax.text(prob, band_y + band_h + 0.30, f"{prob:.3f}", ha="center",
            va="bottom", fontsize=10, fontweight="bold")

    actual = "FAILED" if is_failed else "NON-FAILED"
    verdict = "correct" if correct else "INCORRECT"
    ax.text(0.0, -0.28,
            f"LOVO out-of-fold probability = {prob:.4f}  ->  tier {tier}  "
            f"({verdict} vs actual: {actual})",
            transform=ax.transAxes, fontsize=9.5,
            color=TIER_COLORS.get(tier, "black"), fontweight="bold")
    ax.text(0.0, -0.50,
            f"Model: Ridge, AUROC {spec['auroc']:.3f} (34-fold LOVO)  |  "
            f"features: {', '.join(spec['features'])}",
            transform=ax.transAxes, fontsize=8, color="#444444")
    # Tick set built from the loaded spec threshold (not hardcoded)
    ticks = sorted({0.0, 0.2, GREEN_LT, round(thr, 3), AMBER_LT, 0.8, 1.0})
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{t:g}" for t in ticks], fontsize=8)
    ax.set_title("Panel 3 — Failure-risk gauge (out-of-fold Ridge probability)",
                 loc="left")


def panel4_event_strip(ax, ev: pd.DataFrame, t_end: pd.Timestamp,
                       is_failed: bool, gap_days: int):
    """Weekly crank-event counts; artifacts grey-stacked; gap hatch; JCOPENDATE."""
    cnt = (ev.groupby(["week", "artifact"]).size().unstack(fill_value=0)
             .reindex(columns=[False, True], fill_value=0).sort_index())
    if len(cnt):
        ax.bar(cnt.index, cnt[False], width=5.5, color=C_EVT, alpha=0.9,
               label="crank events / week", zorder=2)
        if cnt[True].sum() > 0:
            ax.bar(cnt.index, cnt[True], width=5.5, bottom=cnt[False],
                   color=C_ART, alpha=0.9, label="artifact events (>60 s)",
                   zorder=2)
    ax.set_ylabel("Crank events / week")
    ax.set_ylim(bottom=0)
    ax.set_xlabel("Date")

    jcopen = t_end + pd.Timedelta(days=gap_days)
    if gap_days > 0:
        ax.axvspan(t_end, jcopen, facecolor="none", edgecolor="#b71c1c",
                   hatch="///", lw=0.0, alpha=0.45, zorder=1)
        gap_txt = f"silent gap: {gap_days}d\n(no telemetry before JCOPENDATE)"
        box = dict(boxstyle="round,pad=0.3", fc="white", ec="#b71c1c",
                   alpha=0.9)
        if gap_days >= 60:        # wide gap: annotation fits inside the hatch
            ax.text(t_end + (jcopen - t_end) / 2, 0.62, gap_txt,
                    transform=ax.get_xaxis_transform(), ha="center",
                    va="center", fontsize=8.5, color="#b71c1c",
                    fontweight="bold", bbox=box)
        else:                     # narrow gap: annotate outside, arrow in
            ax.annotate(gap_txt,
                        xy=(mdates.date2num(t_end + (jcopen - t_end) / 2),
                            0.62),
                        xycoords=ax.get_xaxis_transform(),
                        xytext=(mdates.date2num(t_end
                                                - pd.Timedelta(days=18)),
                                0.78),
                        textcoords=ax.get_xaxis_transform(),
                        ha="right", va="center", fontsize=8.5,
                        color="#b71c1c", fontweight="bold", bbox=box,
                        arrowprops=dict(arrowstyle="->", color="#b71c1c",
                                        lw=1.0))
    if is_failed:
        ax.axvline(jcopen, color=C_JCO, lw=1.6, ls="--", zorder=4)
        ax.text(jcopen, 0.97, " JCOPENDATE ", rotation=90,
                transform=ax.get_xaxis_transform(), ha="right", va="top",
                fontsize=8, color=C_JCO, fontweight="bold")
    ax.set_title("Panel 4 — Crank-event strip (weekly counts"
                 + (", silent gap hatched" if gap_days > 0 else "") + ")",
                 loc="left")
    ax.legend(loc="upper left", fontsize=8, framealpha=0.6)


# ─────────────────────────────────────────────────────────────────────────────
# Per-VIN dashboard
# ─────────────────────────────────────────────────────────────────────────────

def make_dashboard(vin: str) -> Path:
    wk = weekly[weekly["vin_label"] == vin].sort_values("week")
    ev = events[events["vin_label"] == vin]
    pred = preds.loc[vin]
    is_failed = bool(wk["failed"].iloc[0])
    gap_days = cfg.GAP_VINS.get(vin, 0)
    tier = str(pred["alert_tier"])

    t_start, t_end = wk["week"].min(), wk["week"].max()
    span_d = int((t_end - t_start).days) + 7          # inclusive of last week
    active = int(wk["active_days"].sum())

    fig = plt.figure(figsize=(14, 16), dpi=150)
    gs = fig.add_gridspec(4, 1, height_ratios=[3.0, 2.6, 1.5, 2.2],
                          hspace=0.42, left=0.07, right=0.93,
                          top=0.925, bottom=0.05)
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax3 = fig.add_subplot(gs[2])              # gauge: not time-based
    ax4 = fig.add_subplot(gs[3], sharex=ax1)

    panel1_voltage(ax1, wk)
    panel2_crank_physics(ax2, ev)
    panel3_risk_gauge(ax3, pred, is_failed)
    panel4_event_strip(ax4, ev, t_end, is_failed, gap_days)

    # Shared time axis: extend to JCOPENDATE so gap hatch is visible
    x_max = t_end + pd.Timedelta(days=gap_days)
    ax1.set_xlim(t_start - pd.Timedelta(days=10), x_max + pd.Timedelta(days=14))
    for ax in (ax1, ax2, ax4):
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(
            ax.xaxis.get_major_locator()))
    for ax in (ax1, ax2):
        plt.setp(ax.get_xticklabels(), visible=True)

    # Title block — tier color-coded
    cohort = "FAILED" if is_failed else "NON-FAILED"
    fig.suptitle(
        f"{vin}  —  {cohort} cohort  |  "
        f"telemetry {t_start:%Y-%m-%d} -> {t_end:%Y-%m-%d} ({span_d}d span, "
        f"{active} active days)",
        fontsize=14, fontweight="bold", y=0.975)
    fig.text(0.5, 0.952, f"risk tier: {tier}  (p = {float(pred['y_prob']):.3f})",
             ha="center", fontsize=12, fontweight="bold",
             color=TIER_COLORS.get(tier, "black"))
    fig.text(0.5, 0.012, FOOTER, ha="center", fontsize=8.5,
             color="#666666", style="italic")

    out = cfg.GRAPHS / f"V1_SM_{vin}_dashboard.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Run
# ─────────────────────────────────────────────────────────────────────────────
vins = sorted(weekly["vin_label"].unique(),
              key=lambda v: ("NF" in v, int(v.replace("VIN", "").split("_")[0])))
print(f"Rendering {len(vins)} dashboards -> {cfg.GRAPHS} ...")
written = []
for vin in vins:
    p = make_dashboard(vin)
    written.append(p)
    print(f"  {p.name}")

assert len(written) == cfg.N_VINS, "DASHBOARD COUNT MISMATCH"
print(f"\nDone: {len(written)} dashboards written to {cfg.GRAPHS}")
