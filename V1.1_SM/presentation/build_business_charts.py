"""
build_business_charts.py - IP-safe executive charts for the DICV deck.

All values come from validated V1.1 result artifacts:
  results/V1_1_SM_nested_lovo_predictions.csv  (per-VIN probability + tier)
  results/V1_1_SM_alert_policy.csv             (per-VIN alert channel, date, lead)
  reports/V1_1_SM_daily_graph_verification.md  (VIN6_F zone dates, hardcoded below)

Outputs (presentation/assets/):
  BIZ_fleet_risk_bars.png    - 34-vehicle final risk ranking, tier colors
  BIZ_tier_donut.png         - fleet tier distribution donut
  BIZ_warning_runway.png     - early-warning runway (first alert -> failure)
  BIZ_zone_progression_vin6.png - VIN6_F zone milestone strip

Run:  py -3 "STARTER MOTOR/V1.1/presentation/build_business_charts.py"
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR\V1.1")
sys.path.insert(0, str(ROOT / "src"))
from V1_1_SM_vin_display_map import display_label  # noqa: E402

RES = ROOT / "results"
OUT = ROOT / "presentation" / "assets"
OUT.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "font.family": "Segoe UI",
    "axes.edgecolor": "#c9d1d9",
    "axes.linewidth": 0.8,
    "figure.facecolor": "white",
})

NAVY = "#14263A"
SLATE = "#5B6B7C"
GREEN_D, GREEN_L = "#1b7a3d", "#a5d6a7"
AMBER_D, AMBER_L = "#d35400", "#ffb74d"
RED_D, RED_L = "#8b0000", "#ef9a9a"
CLR_PERS, CLR_A1, CLR_A2 = "#8e44ad", "#1565c0", "#c62828"

TIER_FILL = {"GREEN": GREEN_L, "AMBER": AMBER_L, "RED": RED_L}
TIER_EDGE = {"GREEN": GREEN_D, "AMBER": AMBER_D, "RED": RED_D}

preds = pd.read_csv(RES / "V1_1_SM_nested_lovo_predictions.csv")
alerts = pd.read_csv(RES / "V1_1_SM_alert_policy.csv")

preds["disp"] = preds["vin_label"].map(display_label)
alerts["disp"] = alerts["vin_label"].map(display_label)


def _dispnum(lbl: str) -> int:
    return int(lbl.replace("VIN", "").split("_")[0])


# ===========================================================================
# 1. Fleet risk ranking bars (failed VIN1-14, then healthy VIN15-34)
# ===========================================================================
df = preds.copy()
df["num"] = df["disp"].map(_dispnum)
df = df.sort_values(["failed", "num"], ascending=[False, True]).reset_index(drop=True)

fig, ax = plt.subplots(figsize=(13.4, 4.4), dpi=200)
x = np.arange(len(df))
for i, r in df.iterrows():
    ax.bar(i, r["prob_recal"], width=0.72, color=TIER_FILL[r["tier"]],
           edgecolor=TIER_EDGE[r["tier"]], linewidth=1.1, zorder=3)
    if r["failed"] == 1:
        ax.plot(i, min(r["prob_recal"] + 0.045, 1.03), marker="x", color=NAVY,
                markersize=6, markeredgewidth=1.8, zorder=4)

ax.axhline(0.55, color=RED_D, linewidth=1.0, linestyle="--", alpha=0.75, zorder=2)
ax.axhline(0.35, color=AMBER_D, linewidth=1.0, linestyle="--", alpha=0.75, zorder=2)
ax.text(24.6, 0.565, "RED threshold 0.55", fontsize=8.5, color=RED_D,
        ha="left", va="bottom", fontweight="bold")
ax.text(24.6, 0.365, "AMBER threshold 0.35", fontsize=8.5, color=AMBER_D,
        ha="left", va="bottom", fontweight="bold")

ax.axvline(13.5, color=SLATE, linewidth=1.0, linestyle=":", alpha=0.9)
ax.text(6.5, 1.10, "FAILED VEHICLES (14)", fontsize=10.5, color=RED_D,
        ha="center", fontweight="bold")
ax.text(23.5, 1.10, "HEALTHY VEHICLES (20, still in service)", fontsize=10.5,
        color=GREEN_D, ha="center", fontweight="bold")

ax.set_xticks(x)
ax.set_xticklabels([d.replace("_SM", "") for d in df["disp"]], rotation=60,
                   ha="right", fontsize=7.5)
ax.set_ylim(0, 1.18)
ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
ax.set_ylabel("Failure-risk score (validation)", fontsize=10, fontweight="bold")
ax.grid(axis="y", color="#e8ecef", linewidth=0.6, zorder=0)
ax.set_axisbelow(True)

handles = [
    mpatches.Patch(fc=RED_L, ec=RED_D, label="RED - inspect in 2-4 weeks"),
    mpatches.Patch(fc=AMBER_L, ec=AMBER_D, label="AMBER - plan at next service"),
    mpatches.Patch(fc=GREEN_L, ec=GREEN_D, label="GREEN - normal operation"),
    plt.Line2D([], [], marker="x", color=NAVY, linestyle="", markersize=6,
               markeredgewidth=1.8, label="confirmed failure"),
]
fig.legend(handles=handles, loc="upper center", fontsize=9, ncol=4,
           framealpha=0.95, edgecolor="#c9d1d9", bbox_to_anchor=(0.5, 1.045))
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
fig.tight_layout(rect=(0, 0, 1, 0.94))
fig.savefig(OUT / "BIZ_fleet_risk_bars.png", dpi=200, bbox_inches="tight")
plt.close(fig)
print("BIZ_fleet_risk_bars.png")

# ===========================================================================
# 2. Tier distribution donut
# ===========================================================================
tc = preds.groupby("tier").size()
fig, ax = plt.subplots(figsize=(4.4, 4.4), dpi=200)
sizes = [tc.get("GREEN", 0), tc.get("AMBER", 0), tc.get("RED", 0)]
cols = [GREEN_L, AMBER_L, RED_L]
edges = [GREEN_D, AMBER_D, RED_D]
wedges, _ = ax.pie(sizes, colors=cols, startangle=90, counterclock=False,
                   wedgeprops=dict(width=0.42, edgecolor="white", linewidth=2))
for w, e in zip(wedges, edges):
    w.set_edgecolor(e)
    w.set_linewidth(1.4)
labels = [f"GREEN\n{sizes[0]} vehicles", f"AMBER\n{sizes[1]}", f"RED\n{sizes[2]}"]
for w, lab, e in zip(wedges, labels, edges):
    ang = np.deg2rad((w.theta1 + w.theta2) / 2)
    ax.text(1.28 * np.cos(ang), 1.28 * np.sin(ang), lab, ha="center", va="center",
            fontsize=11, fontweight="bold", color=e)
ax.text(0, 0.08, "34", ha="center", va="center", fontsize=34, fontweight="bold",
        color=NAVY)
ax.text(0, -0.22, "vehicles\nmonitored", ha="center", va="center", fontsize=10,
        color=SLATE)
ax.set(aspect="equal")
fig.savefig(OUT / "BIZ_tier_donut.png", dpi=200, bbox_inches="tight",
            transparent=True)
plt.close(fig)
print("BIZ_tier_donut.png")

# ===========================================================================
# 3. Early-warning runway (days before failure, first alert -> failure)
# ===========================================================================
CH_STYLE = {
    "persistence": (CLR_PERS, "Sustained electrical-volatility alert"),
    "A1_crank_burst": (CLR_A1, "Crank-anomaly alert"),
}
# A2 battery-cascade confirmation leads (days before failure), from
# V1_1_SM_alerts_horizon.md (fires on 4 battery-signature vehicles)
A2_LEADS = {"VIN3_F_SM": 91, "VIN6_F_SM": 70, "VIN13_F_SM": 63, "VIN14_F_SM": 28}

fa = alerts[alerts["failed"] == 1].copy()
fa["lead"] = fa["lead_vs_jcopen_d"]
det = fa[fa["first_channel"] != "NONE"].sort_values("lead").reset_index(drop=True)
miss = fa[fa["first_channel"] == "NONE"]

fig, ax = plt.subplots(figsize=(9.4, 6.2), dpi=200)
ypos = np.arange(len(det))
for i, r in det.iterrows():
    col, _ = CH_STYLE[r["first_channel"]]
    ax.barh(i, r["lead"], left=-r["lead"], height=0.62, color=col, alpha=0.28,
            edgecolor=col, linewidth=1.3, zorder=3)
    ax.plot(-r["lead"], i, marker="o", color=col, markersize=7, zorder=5)
    ax.text(-r["lead"] - 8, i, f"{int(r['lead'])} d", ha="right", va="center",
            fontsize=9, fontweight="bold", color=NAVY)
    a2 = A2_LEADS.get(r["vin_label"])
    if a2:
        ax.plot(-a2, i, marker="v", color=CLR_A2, markersize=8,
                markeredgecolor="white", markeredgewidth=0.8, zorder=6)

# the one undetected failure, shown honestly
yi = len(det)
ax.barh(yi, 142, left=-142, height=0.62, color="none", edgecolor=SLATE,
        linewidth=1.2, linestyle="--", zorder=3)
ax.text(-150, yi, "no alert", ha="right", va="center", fontsize=9,
        fontweight="bold", color=SLATE)
ax.text(-71, yi, "vehicle stopped transmitting 142 d before failure",
        ha="center", va="center", fontsize=8, color=SLATE, style="italic")

ax.axvline(0, color=RED_D, linewidth=1.6, zorder=4)
ax.text(3, len(det) + 0.72, "FAILURE", fontsize=10, color=RED_D,
        fontweight="bold", ha="left", va="center")
ax.axvline(-168, color=NAVY, linewidth=1.1, linestyle=":", alpha=0.8, zorder=2)
ax.text(-168, -1.15, "median first warning: 168 days", fontsize=9.5, color=NAVY,
        fontweight="bold", ha="center", va="top")

labels = [d.replace("_SM", "") for d in det["disp"]] + \
         [miss["disp"].iloc[0].replace("_SM", "")]
ax.set_yticks(list(ypos) + [yi])
ax.set_yticklabels(labels, fontsize=9.5)
ax.set_ylim(-0.8, len(det) + 1.0)
ax.invert_yaxis()
ax.set_xlim(-450, 40)
ax.set_xticks([-420, -360, -300, -240, -180, -120, -60, 0])
ax.set_xticklabels([420, 360, 300, 240, 180, 120, 60, 0], fontsize=9)
ax.set_xlabel("Days before failure", fontsize=10.5, fontweight="bold")
ax.grid(axis="x", color="#e8ecef", linewidth=0.6, zorder=0)
ax.set_axisbelow(True)

handles = [
    plt.Line2D([], [], marker="o", color=CLR_PERS, linestyle="", markersize=7,
               label="First alert: sustained electrical volatility"),
    plt.Line2D([], [], marker="o", color=CLR_A1, linestyle="", markersize=7,
               label="First alert: crank anomaly"),
    plt.Line2D([], [], marker="v", color=CLR_A2, linestyle="", markersize=8,
               label="Battery-cascade confirmation (zero false alarms)"),
]
ax.legend(handles=handles, loc="upper left", fontsize=8.5, framealpha=0.95,
          edgecolor="#c9d1d9")
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
fig.tight_layout()
fig.savefig(OUT / "BIZ_warning_runway.png", dpi=200, bbox_inches="tight")
plt.close(fig)
print("BIZ_warning_runway.png")

# ===========================================================================
# 4. VIN6_F zone-progression strip (verified milestone dates)
# ===========================================================================
# Zone transition dates verified in V1_1_SM_daily_graph_verification.md;
# alert dates and 168 d lead from V1_1_SM_alert_policy.csv.
t0 = pd.Timestamp("2025-01-01")
yellow = pd.Timestamp("2025-05-25")
orange = pd.Timestamp("2025-08-31")
red = pd.Timestamp("2025-10-19")
fail = pd.Timestamp("2025-11-03")
pers_alert = pd.Timestamp("2025-05-19")
a2_alert = pd.Timestamp("2025-08-25")

fig, ax = plt.subplots(figsize=(11.8, 2.5), dpi=200)
spans = [(t0, yellow, "#a5d6a7", "#1b7a3d", "GREEN"),
         (yellow, orange, "#fff59d", "#b7950b", "YELLOW"),
         (orange, red, "#ffb74d", "#d35400", "ORANGE"),
         (red, fail, "#ef9a9a", "#8b0000", "RED")]
for a, b, fc, ec, lab in spans:
    ax.axvspan(mdates.date2num(a), mdates.date2num(b), ymin=0.30, ymax=0.72,
               facecolor=fc, edgecolor=ec, linewidth=1.2, alpha=0.9)
    mid = a + (b - a) / 2
    ax.text(mdates.date2num(mid), 0.51, lab, ha="center", va="center",
            fontsize=10.5, fontweight="bold", color=ec,
            transform=ax.get_xaxis_transform())

for d, txt, col, above in [
        (pers_alert, "Volatility alert\n19 May", CLR_PERS, True),
        (a2_alert, "Battery-cascade alert\n25 Aug", CLR_A2, True),
        (yellow, "Yellow\n25 May", "#b7950b", False),
        (orange, "Orange\n31 Aug", "#d35400", False),
        (red, "Red\n19 Oct", "#8b0000", False)]:
    ax.axvline(mdates.date2num(d), ymin=0.30, ymax=0.72, color=col,
               linewidth=1.4, linestyle="-" if above else ":")
    y, va = (0.88, "center") if above else (0.13, "center")
    ax.text(mdates.date2num(d), y, txt, ha="center", va=va, fontsize=8.5,
            fontweight="bold", color=col, transform=ax.get_xaxis_transform())

ax.plot(mdates.date2num(fail + pd.Timedelta(days=4)), 0.51, marker="*",
        markersize=20, color="#8b0000", markeredgecolor="white",
        markeredgewidth=1.2, zorder=6, transform=ax.get_xaxis_transform())
ax.text(mdates.date2num(fail) + 3, 0.88, "Failure\n03 Nov", ha="left",
        va="center", fontsize=9, fontweight="bold", color="#8b0000",
        transform=ax.get_xaxis_transform())

ax.annotate("", xy=(mdates.date2num(fail), 0.035),
            xytext=(mdates.date2num(pers_alert), 0.035),
            xycoords=ax.get_xaxis_transform(),
            arrowprops=dict(arrowstyle="<->", color=NAVY, lw=1.3))
ax.text(mdates.date2num(pers_alert - pd.Timedelta(days=10)), 0.035,
        "168 days of maintenance opportunity", ha="right", va="center",
        fontsize=9.5, fontweight="bold", color=NAVY,
        transform=ax.get_xaxis_transform())

ax.set_xlim(mdates.date2num(t0 - pd.Timedelta(days=8)),
            mdates.date2num(fail + pd.Timedelta(days=28)))
ax.set_ylim(0, 1)
ax.yaxis.set_visible(False)
ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
plt.setp(ax.xaxis.get_majorticklabels(), fontsize=9)
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
fig.subplots_adjust(top=0.98, bottom=0.30)
fig.savefig(OUT / "BIZ_zone_progression_vin6.png", dpi=200, bbox_inches="tight")
plt.close(fig)
print("BIZ_zone_progression_vin6.png")

print("All business charts written to", OUT)
