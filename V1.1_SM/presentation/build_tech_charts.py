"""
build_tech_charts.py - internal technical charts for the V1.1 SM deep-dive deck.

Sources:
  results/V1_1_SM_horizon_curve.csv   (prequential AUROC vs k weeks before t_end)
  results/V1_1_SM_model_spec.json     (headline, restated baseline, ablation)
  results/V1_1_SM_gates.json          (G4 feature frequency)

Outputs (presentation/assets/):
  TECH_horizon_curve.png   TECH_v1_bridge.png   TECH_feature_freq.png

Run:  py -3 "STARTER MOTOR/V1.1/presentation/build_tech_charts.py"
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR\V1.1")
RES = ROOT / "results"
OUT = ROOT / "presentation" / "assets"

plt.rcParams.update({"font.family": "Segoe UI", "axes.edgecolor": "#c9d1d9",
                     "axes.linewidth": 0.8, "figure.facecolor": "white"})
NAVY = "#14263A"
SLATE = "#5B6B7C"
ORANGE = "#d35400"
GREEN = "#1b7a3d"
RED = "#8b0000"
BLUE = "#1565c0"

# ===========================================================================
# 1. Prequential horizon curve
# ===========================================================================
hz = pd.read_csv(RES / "V1_1_SM_horizon_curve.csv")

fig, ax = plt.subplots(figsize=(9.6, 5.0), dpi=200)
ax.axvspan(-0.5, 10.5, color="#e8f2ec", zorder=0)
ax.text(5.0, 0.99, "validated horizon k* = 10 weeks", fontsize=10.5,
        color=GREEN, fontweight="bold", ha="center")

ax.fill_between(hz["k_weeks"], hz["ci95_lo"], hz["ci95_hi"], color=ORANGE,
                alpha=0.15, zorder=2, label="95% CI (bootstrap)")
ax.plot(hz["k_weeks"], hz["auroc"], color=ORANGE, linewidth=2.0, marker="o",
        markersize=4.5, zorder=4, label="prequential test-time AUROC")

ax.axhline(0.75, color=NAVY, linewidth=1.2, linestyle="--", alpha=0.8, zorder=3)
ax.text(25.8, 0.755, "AUROC 0.75 validity threshold", fontsize=9, color=NAVY,
        ha="right", va="bottom", fontweight="bold")
ax.axhline(0.5, color=SLATE, linewidth=1.0, linestyle=":", alpha=0.8, zorder=3)
ax.text(25.8, 0.505, "chance", fontsize=9, color=SLATE, ha="right", va="bottom")

k11 = hz.loc[hz["k_weeks"] == 11, "auroc"].iloc[0]
ax.annotate(f"collapse at k=11\n(AUROC {k11:.3f})",
            xy=(11, k11), xytext=(14.5, 0.86), fontsize=9.5, color=RED,
            fontweight="bold", ha="center",
            arrowprops=dict(arrowstyle="->", color=RED, lw=1.2),
            bbox=dict(boxstyle="round,pad=0.35", fc="white", ec=RED, alpha=0.9))
k0 = hz.loc[hz["k_weeks"] == 0, "auroc"].iloc[0]
ax.annotate(f"k=0: {k0:.4f}\n(reconciles to frozen matrix)",
            xy=(0, k0), xytext=(3.4, 1.035), fontsize=9, color=NAVY,
            fontweight="bold", ha="center",
            arrowprops=dict(arrowstyle="->", color=NAVY, lw=1.0),
            bbox=dict(boxstyle="round,pad=0.35", fc="white", ec=NAVY, alpha=0.9))

ax.text(20.5, 0.30, "head mean (k=0-10): 0.929\ntail mean (k=23-26): 0.592\n"
        "decay CONFIRMED - score is failure-locked,\nnot epoch/length-locked "
        "(no leak signature)", fontsize=9, color=SLATE, ha="center",
        bbox=dict(boxstyle="round,pad=0.5", fc="#f4f6f8", ec="#c9d1d9"))

ax.set_xlim(-0.5, 26.5)
ax.set_ylim(0.25, 1.09)
ax.set_xticks(range(0, 27, 2))
ax.set_xlabel("k = weeks before end of history (features re-anchored at cut)",
              fontsize=10.5, fontweight="bold")
ax.set_ylabel("LOVO AUROC (frozen 4-feature model)", fontsize=10.5,
              fontweight="bold")
ax.grid(color="#e8ecef", linewidth=0.6, zorder=0)
ax.set_axisbelow(True)
ax.legend(loc="lower left", fontsize=9, framealpha=0.95, edgecolor="#c9d1d9")
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
fig.tight_layout()
fig.savefig(OUT / "TECH_horizon_curve.png", dpi=200, bbox_inches="tight")
plt.close(fig)
print("TECH_horizon_curve.png")

# ===========================================================================
# 2. V1 -> V1.1 AUROC bridge (waterfall)
# ===========================================================================
fig, ax = plt.subplots(figsize=(9.6, 4.6), dpi=200)

bars = [
    ("V1\nas reported", 0.9214, "#b9c6d2", "nested-LOVO not applied;\n"
     "includes vsi_dominant_freq"),
    ("honest\nrestatement", 0.8929, "#e5b8b8", "-0.0285: selection optimism\n"
     "+ banned 1/n_weeks artifact"),
    ("V1.1 new features\n(battery-step baseline,\nwithin-week noise, dips)",
     0.9321, "#bfe0cb", "+0.0392 from features,\nnot protocol"),
]
x = np.arange(3)
for i, (lab, v, c, note) in enumerate(bars):
    ax.bar(i, v - 0.80, bottom=0.80, width=0.55, color=c,
           edgecolor=NAVY, linewidth=1.2, zorder=3)
    ax.text(i, v + 0.004, f"{v:.4f}", ha="center", fontsize=12,
            fontweight="bold", color=NAVY)
    ax.text(i, 0.812, note, ha="center", fontsize=8.2, color=SLATE)

ax.annotate("", xy=(0.75, 0.8945), xytext=(0, 0.9214),
            arrowprops=dict(arrowstyle="->", color=RED, lw=1.6,
                            connectionstyle="arc3,rad=-0.25"))
ax.text(0.5, 0.923, "-0.0285", ha="center", fontsize=10, color=RED,
        fontweight="bold")
ax.annotate("", xy=(2, 0.9321), xytext=(1, 0.8929),
            arrowprops=dict(arrowstyle="->", color=GREEN, lw=1.6,
                            connectionstyle="arc3,rad=-0.25"))
ax.text(1.5, 0.930, "+0.0392", ha="center", fontsize=10, color=GREEN,
        fontweight="bold")

ax.axhline(0.8429, color=BLUE, linewidth=1.2, linestyle="--", alpha=0.85)
ax.text(2.62, 0.8429, "ablation: V1-era 22 features\nunder nested protocol = "
        "0.8429", fontsize=8.5, color=BLUE, va="center")
ax.axhline(0.9357, color=SLATE, linewidth=1.0, linestyle=":", alpha=0.85)
ax.text(2.62, 0.9357, "non-nested modal subset = 0.9357\n(nesting optimism "
        "+0.0036)", fontsize=8.5, color=SLATE, va="center")

ax.set_xticks(x)
ax.set_xticklabels([b[0] for b in bars], fontsize=9.5)
ax.set_xlim(-0.55, 4.4)
ax.set_ylim(0.80, 0.965)
ax.set_ylabel("nested-LOVO AUROC", fontsize=10.5, fontweight="bold")
ax.grid(axis="y", color="#e8ecef", linewidth=0.6, zorder=0)
ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
fig.tight_layout()
fig.savefig(OUT / "TECH_v1_bridge.png", dpi=200, bbox_inches="tight")
plt.close(fig)
print("TECH_v1_bridge.png")

# ===========================================================================
# 3. Winner-subset stability (G4)
# ===========================================================================
fig, ax = plt.subplots(figsize=(9.6, 3.2), dpi=200)
feats = [
    ("vsi_withinwk_std_ratio_30d_w", 34, "within-week drive-VSI noise ratio "
     "(30 d vs L40 baseline)"),
    ("vsi_range_trend", 34, "Theil-Sen trend of weekly p95-p05 drive-VSI "
     "envelope"),
    ("rest_vsi_p05_delta90", 28, "rest-voltage floor shift, battery-step "
     "re-baselined"),
    ("dip_depth_last90_delta", 20, "crank dip-depth deepening vs L40 baseline"),
]
ypos = np.arange(len(feats))[::-1]
for y, (name, n, desc) in zip(ypos, feats):
    ax.barh(y, n, height=0.58, color="#bfd3e6" if n < 34 else "#9dc3e0",
            edgecolor=NAVY, linewidth=1.1, zorder=3)
    ax.text(n + 0.4, y, f"{n}/34 folds", va="center", fontsize=10,
            fontweight="bold", color=NAVY)
    ax.text(0.4, y + 0.02, f" {name}", va="center", fontsize=9.5,
            fontweight="bold", color=NAVY, family="Consolas")
    ax.text(0.4, y - 0.21, f" {desc}", va="center", fontsize=8, color=SLATE)

ax.axvline(34, color=GREEN, linewidth=1.2, linestyle="--", alpha=0.8)
ax.text(34.5, 3.62, "selected in every fold", fontsize=8.5, color=GREEN,
        ha="left", fontweight="bold")
ax.set_xlim(0, 40.5)
ax.set_ylim(-0.55, 3.95)
ax.set_yticks([])
ax.set_xlabel("outer folds selecting the feature (nested inner selection, "
              "34 LOVO folds)", fontsize=10, fontweight="bold")
ax.grid(axis="x", color="#e8ecef", linewidth=0.6, zorder=0)
ax.set_axisbelow(True)
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
fig.tight_layout()
fig.savefig(OUT / "TECH_feature_freq.png", dpi=200, bbox_inches="tight")
plt.close(fig)
print("TECH_feature_freq.png")

print("All technical charts written to", OUT)
