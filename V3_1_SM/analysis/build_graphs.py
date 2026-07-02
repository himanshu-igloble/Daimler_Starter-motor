# STARTER MOTOR/V3.1/analysis/build_graphs.py
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "features"))
import _v31_lib as L

G = L.SMROOT / "V3.1" / "graphs"; G.mkdir(exist_ok=True)
SOUT = L.SMROOT / "V3.1" / "state" / "out"
COLORS = {"CRANK": "#d62728", "ENGINE_OFF": "#bbbbbb", "OFF_DWELL": "#8c8c8c", "IDLE": "#ff7f0e",
          "DRIVE": "#2ca02c", "DROPOUT_RUNNING": "#9467bd", "UNKNOWN_GAP": "#e0e0e0",
          "UNKNOWN_GAP_SHORT": "#eeeeee", "OFF_CONFIRMED": "#aaaaaa", "UNKNOWN": "#f0f0f0"}


def style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(alpha=0.25, linewidth=0.5)


def g1():
    import matplotlib.dates as mdates
    fig, axes = plt.subplots(2, 1, figsize=(14, 5), sharex=False)
    for ax, vin in zip(axes, ["VIN2_F_SM", "VIN2_NF_SM"]):
        ep = pd.read_parquet(SOUT / f"V3_1_state_episodes_{vin}.parquet")
        ep = ep[ep["ts_start"] >= ep["ts_start"].max() - pd.Timedelta(days=14)]
        for _, e in ep.iterrows():
            x0 = mdates.date2num(e["ts_start"])                     # matplotlib date floats (days)
            wdt = (e["ts_end"] - e["ts_start"]).total_seconds() / 86400.0
            ax.barh(0, wdt, left=x0, height=0.6, color=COLORS.get(e["state"], "#000"), linewidth=0)
        ax.xaxis_date(); ax.set_yticks([])
        ax.set_title(f"{vin} — last 14 days of operational states", loc="left", fontsize=10)
        style(ax)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in COLORS.values()]
    fig.legend(handles, COLORS.keys(), ncol=5, loc="lower center", frameon=False, fontsize=8)
    fig.tight_layout(rect=(0, 0.08, 1, 1)); fig.savefig(G / "G1_state_timelines.png", dpi=160); plt.close(fig)


def g2():
    soaks = []
    for v in L.vins_in_order():
        p = SOUT / f"V3_1_cranks_{v}.parquet"
        if p.exists():
            soaks.append(pd.read_parquet(p)["soak_h"].dropna())
    s = pd.concat(soaks)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.hist(np.log10(s[s > 0]), bins=60, color="#4878a8")
    ax.set_xlabel("log10(soak hours before crank)"); ax.set_ylabel("cranks")
    ax.set_title("Fleet soak-duration distribution (measurable soaks only — heartbeat refuted)", loc="left")
    style(ax); fig.tight_layout(); fig.savefig(G / "G2_soak_distribution.png", dpi=160); plt.close(fig)


def g3():
    h = pd.read_csv(SOUT / "P0_gap_hist.csv")
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.bar(h["gap_min_bin_lo"], h["count"], width=1.0, color="#4878a8")
    ax.axvspan(14, 18, color="#d62728", alpha=0.15)
    ax.set_yscale("log"); ax.set_xlabel("gap length (min)"); ax.set_ylabel("count (log)")
    ax.set_title("Telemetry gap lengths with heartbeat band [14,18] min highlighted", loc="left")
    style(ax); fig.tight_layout(); fig.savefig(G / "G3_gap_histogram.png", dpi=160); plt.close(fig)


def g4():
    t1 = pd.read_csv(L.SMROOT / "V3.1" / "heuristics" / "out" / "T1_attribution.csv")
    arch = pd.read_csv(L.SMROOT / "V1.1" / "discovery" / "out" / "E2_failed_vin_archetypes.csv")[["vin_label", "archetype"]]
    t1 = t1.merge(arch, on="vin_label", how="left"); t1["archetype"] = t1["archetype"].fillna("NF")
    fig, ax = plt.subplots(figsize=(8, 6))
    for a, g in t1.groupby("archetype"):
        ax.scatter(g["lowv_crank_share"], g["goodv_hardstart_weeks12"], label=a, s=45, alpha=0.85)
    ax.set_xlabel("battery evidence: low-voltage crank share (last 90 d)")
    ax.set_ylabel("starter evidence: weeks with hard-start @ good V (last 12 wk)")
    ax.set_title("T1 attribution quadrant, archetype-colored", loc="left")
    ax.legend(frameon=False, fontsize=8); style(ax)
    fig.tight_layout(); fig.savefig(G / "G4_attribution_quadrant.png", dpi=160); plt.close(fig)


def g5():
    mat = pd.read_csv(L.SMROOT / "V1.1" / "results" / "V1_1_SM_feature_matrix.csv")
    S = json.loads((L.V31_OUT / "V3_1_gate_summary.json").read_text())
    feats = [e["feature"] for e in S["E1"]]
    fig, axes = plt.subplots(1, len(feats), figsize=(3 * len(feats), 4), sharey=False)
    for ax, c in zip(np.atleast_1d(axes), feats):
        cache = pd.read_csv(L.V31_OUT / f"{c}_cache.csv").merge(mat[["vin_label", "failed"]], on="vin_label")
        for lab, x in [(0, 0), (1, 1)]:
            v = cache.loc[cache["failed"] == bool(lab), c].dropna()
            ax.scatter(np.full(len(v), x) + np.random.default_rng(42).uniform(-0.08, 0.08, len(v)), v, s=18, alpha=0.8,
                       color="#2ca02c" if lab == 0 else "#d62728")
        e1 = next(e for e in S["E1"] if e["feature"] == c)
        ax.set_xticks([0, 1]); ax.set_xticklabels(["NF", "F"])
        ax.set_title(f"{c}\nAUROC={e1['auroc']} p={e1['mw_p']}\n{S['verdicts'][c]['verdict']}", fontsize=7)
        style(ax)
    fig.tight_layout(); fig.savefig(G / "G5_gate_panels.png", dpi=160); plt.close(fig)


def g6():
    r = L.load_state_weekly(); m = r[r["active_days"] >= 2]
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.scatter(m["km"] / m["active_days"], m["engine_hours"] / m["active_days"], s=6, alpha=0.25, color="#4878a8")
    for x in (10, 800):
        ax.axvline(x, color="#d62728", linewidth=0.8, linestyle="--")
    for yv in (0.5, 22):
        ax.axhline(yv, color="#d62728", linewidth=0.8, linestyle="--")
    ax.set_xscale("log"); ax.set_xlabel("km per active day"); ax.set_ylabel("engine-hours per active day")
    ax.set_title("SV-3 plausibility: masked VIN-weeks vs registered bands", loc="left")
    style(ax); fig.tight_layout(); fig.savefig(G / "G6_sv3_plausibility.png", dpi=160); plt.close(fig)


def g7():
    t3 = pd.read_csv(L.SMROOT / "V3.1" / "heuristics" / "out" / "T3_data_health.csv", parse_dates=["week"])
    sil = ["VIN1_F_SM", "VIN4_F_SM", "VIN5_F_SM", "VIN8_F_SM", "VIN9_F_SM"]
    fig, axes = plt.subplots(5, 1, figsize=(11, 9), sharex=False)
    for ax, v in zip(axes, sil):
        g = t3[t3["vin_label"] == v]
        ax.plot(g["week"], g["dropout_share"], linewidth=1.0, color="#4878a8")
        fires = g[g["escalation"]]
        ax.scatter(fires["week"], fires["dropout_share"], color="#d62728", s=14, zorder=3)
        ax.set_title(v, loc="left", fontsize=9); ax.set_ylabel("dropout share", fontsize=7); style(ax)
    fig.suptitle("T3 dropout-share timelines, silent-gap VINs (red = escalation flag)", x=0.01, ha="left")
    fig.tight_layout(); fig.savefig(G / "G7_dropout_timelines.png", dpi=160); plt.close(fig)


def g8():
    nodes = {  # (x, y, label)
        "RAW": (0, 2, "6 signals + ts"), "EVT": (0, 0.8, "crank events\n(frozen)"),
        "SE": (1, 2, "state engine"), "EP": (2, 2, "episodes/trips\nsoak/engine-hrs"),
        "A": (2, 0.8, "A1 A2 A3"), "B": (3, 1.4, "B1 B2"), "C": (3, 2.4, "C1 C2"),
        "GATE": (4, 1.4, "E0-E3 gate"), "T1": (4, 0.4, "T1 triage"), "CAT": (4, 2.6, "catalog")}
    edges = [("RAW", "SE"), ("SE", "EP"), ("EVT", "A"), ("EP", "B"), ("EP", "C"), ("EP", "CAT"),
             ("A", "GATE"), ("B", "GATE"), ("C", "GATE"), ("A", "T1"), ("EVT", "B")]
    fig, ax = plt.subplots(figsize=(10, 5))
    for a, b in edges:
        (x0, y0, _), (x1, y1, _) = nodes[a], nodes[b]
        ax.annotate("", xy=(x1 - 0.18, y1), xytext=(x0 + 0.18, y0),
                    arrowprops=dict(arrowstyle="->", color="#888", lw=1.0))
    for k, (x, y, lab) in nodes.items():
        ax.text(x, y, lab, ha="center", va="center", fontsize=8,
                bbox=dict(boxstyle="round,pad=0.35", fc="#eef3f8", ec="#4878a8"))
    ax.set_xlim(-0.5, 4.7); ax.set_ylim(0, 3.2); ax.axis("off")
    ax.set_title("V3.1 feature dependency DAG", loc="left")
    fig.tight_layout(); fig.savefig(G / "G8_dependency_dag.png", dpi=160); plt.close(fig)


for f in (g1, g2, g3, g4, g5, g6, g7, g8):
    f(); print(f.__name__, "ok")
