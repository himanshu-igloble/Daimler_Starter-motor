"""
V1.1_SM per-VIN "Risk + Physics Evidence Stack".

Ports the V11.2_ALT evidence-stack design (V11.2_ALT/src/V11_2_ALT_rul_evidence_stack.py)
to the Starter Motor V1.1 fleet.  SM has NO fleet-age RUL schedule, so the honest headline
is the *validated walking risk score* (the ML clock) rather than a Weibull remaining-life curve.

Six time-aligned, calendar-x panels per VIN (all 34):
  1) Walking failure-risk score  — recalibrated prob vs cut_date, GREEN/AMBER/RED bands, RED dwell,
                                    t_end / JCOPENDATE lines + telemetry-silent-gap hatch, persistence-lead chip
  2) Remaining life (RUL) window — banded maintenance window anchored at the fired alert (T2 policy);
                                    actual failure date overlaid with an inside/outside verdict chip
  3) Alert-channel evidence lanes — Persistence / A1 crank-burst / A2 battery-cascade fire dates + spans
  4) Voltage health               — resting VSI (median + p05 floor) & driving VSI (p05-p95 band + mean); battery steps
  5) Precursor physics            — 4 champion features as weekly z vs the VIN's own first-half baseline
  6) Crank signature              — dip depth early vs late life; failed cranks as red x

House style (ported): 15x18 fig, white bg, no top/right spines, subtle y-grid, left-aligned panel
titles, soft zone bands, direct labels, NO trend connectors between raw points, PNG(dpi160)+SVG.

Read-only inputs.  Run:  py -3 "STARTER MOTOR/V1.1/src/V1_1_SM_evidence_stack.py"
Optional QA subset:      py -3 ...V1_1_SM_evidence_stack.py VIN13_F_SM VIN9_F_SM VIN2_NF_SM
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import matplotlib.dates as mdates

ROOT = r"D:/Daimler-starter_motor_alternator_battery"
SM = os.path.join(ROOT, "STARTER MOTOR")
sys.path.insert(0, os.path.join(SM, "V1.1", "src"))
try:
    from V1_1_SM_vin_display_map import display_label   # NF +14 fleet-display remap (graphs/decks)
except Exception:
    def display_label(x):  # graceful fallback
        return x

OUT = os.path.join(SM, "V1.1", "visualizations", "rul_evidence_stack")
os.makedirs(OUT, exist_ok=True)

# ---- data sources -----------------------------------------------------------
WALK_CSV = os.path.join(SM, "V2_program", "analysis", "heuristics", "out", "walking_scores.csv")
ALERT_CSV = os.path.join(SM, "V1.1", "results", "V1_1_SM_alert_validation.csv")
FEAT_CSV = os.path.join(SM, "V1.1", "results", "V1_1_SM_feature_matrix.csv")
WINDOWS_CSV = os.path.join(SM, "V3.1", "heuristics", "out", "T2_windows.csv")  # validated maintenance windows
WEEKLY_DIR = os.path.join(SM, "cache", "weekly")
CRANK_PARQUET = os.path.join(SM, "cache", "events", "V1_SM_crank_events.parquet")
FAILED_PARQUET = os.path.join(ROOT, "Data", "processed", "starter_motor_complete",
                              "2026-03-06-12-38-23-starter_motor_failed.parquet")

# ---- palette (ported from V11.2_ALT) ----------------------------------------
DK = "#1B2838"
VOLT = "#0B5394"; REST = "#674ea7"; SAGC = "#B71C1C"
ZG = "#27AE60"; ZY = "#F5A623"; ZO = "#E67E22"; ZB = "#2C3E50"
BAND_GREEN = "#27AE60"; BAND_AMBER = "#E67E22"; BAND_RED = "#C0392B"
PT_GREEN = "#2E7D32"; PT_AMBER = "#EF8E00"; PT_RED = "#C0392B"
WALK_STEP = "#37474F"
LANE = {"pers": "#1565C0", "a1": "#E67E22", "a2": "#6A1B9A"}
GAP_HATCH_EC = "#9AA7B0"
TITLE_KW = dict(loc="left", fontsize=11.5, fontweight="bold", color=DK, pad=6)

# 4 champion precursor features (weekly z; invert=True => a DROP scores higher/worse)
PREC_FEATS = [
    ("vsi_drive_std", "drive-VSI volatility", False, VOLT),
    ("vsi_rest_p05",  "resting-VSI floor",    True,  REST),
    ("vsi_range",     "drive-VSI range",      False, ZO),
    ("dip_depth_med", "crank dip depth",      False, SAGC),
]

RED_THR, AMBER_THR = 0.55, 0.35


# =============================================================================
# PURE HELPERS
# =============================================================================
def _dt(x):
    return pd.to_datetime(x, errors="coerce")


def band_of(p):
    if p >= RED_THR:
        return "RED"
    if p >= AMBER_THR:
        return "AMBER"
    return "GREEN"


_PT = {"RED": PT_RED, "AMBER": PT_AMBER, "GREEN": PT_GREEN}


def consecutive_runs(mask):
    """Yield (start_idx, end_idx_inclusive) of runs of True in a boolean sequence."""
    mask = list(mask)
    i, n = 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j + 1 < n and mask[j + 1]:
                j += 1
            yield i, j
            i = j + 1
        else:
            i += 1


def z_first_half(values, invert=False):
    """z of each weekly value vs the VIN's own FIRST-HALF baseline (mean/sd).
    invert=True => a DROP scores higher (worse). Light 3-week centred smoothing applied."""
    v = np.asarray(values, float)
    n = v.size
    h = max(n // 2, 3)
    base = v[:h]
    base = base[np.isfinite(base)]
    mu = float(np.nanmean(base)) if base.size else float(np.nanmean(v))
    sd = float(np.nanstd(base)) if base.size else float(np.nanstd(v))
    if not np.isfinite(sd) or sd == 0:
        allv = v[np.isfinite(v)]
        sd = float(np.nanstd(allv)) if allv.size else 1.0
        sd = sd or 1.0
    z = (v - mu) / sd
    z = -z if invert else z
    z = pd.Series(z).rolling(3, min_periods=1, center=True).mean().values
    return z


def parse_window_days(s):
    """Parse a T2 window_days cell ('[28, 91]' / 'None') into (lo, hi) ints or None."""
    if s is None:
        return None
    t = str(s).strip()
    if t in ("", "None", "nan", "NaN"):
        return None
    try:
        lo, hi = [int(float(x)) for x in t.strip("[]").split(",")]
        return lo, hi
    except Exception:
        return None


def build_rul(vin, av, wr, failed, jc):
    """Resolve the validated maintenance-WINDOW state for a VIN.

    Window + band come from T2_windows.csv (wr); anchor dates come from the alert file (av):
      - A2_battery_cascade  -> anchor at a2_fire_week
      - persistence_AND_RED -> anchor at pers_terminal_fire_start, else pers_first_fire_week (transient)
    Band colour follows *attribution* (BATTERY_FIRST -> A2 lane colour, else persistence lane colour).
    For failed trucks we compute whether JCOPENDATE fell INSIDE [anchor+lo, anchor+hi] (honest, not assumed).
    """
    if wr is None:
        return dict(state="none", text="no maintenance-window record")
    band = str(wr.get("band"))
    attribution = str(wr.get("attribution"))
    win = parse_window_days(wr.get("window_days"))

    if win is None:  # no active window -> centered-text state
        if vin == "VIN9_F_SM":
            txt, state = "MISSED - no window was ever active", "missed"
        elif band == "GREEN_no_action":
            txt, state = "GREEN - no active window (fleet-clock maintenance only)", "green"
        elif band == "AMBER_only":
            txt, state = "AMBER - monitor only, no window", "amber"
        else:
            txt, state = f"{band} - no active window", "none"
        note = "this truck FAILED - window rule did not fire (missed)" if (failed and vin != "VIN9_F_SM") else None
        return dict(state=state, text=txt, note=note, band=band)

    lo, hi = win
    if band == "A2_battery_cascade":
        anchor = _dt(av.get("a2_fire_week")) if av is not None else pd.NaT
        channel, transient = "A2 battery-cascade", False
    else:  # persistence_AND_RED (persistence-anchored)
        anchor = _dt(av.get("pers_terminal_fire_start")) if av is not None else pd.NaT
        channel, transient = "persistence", False
        if pd.isna(anchor):
            anchor = _dt(av.get("pers_first_fire_week")) if av is not None else pd.NaT
            transient = True
    color = LANE["a2"] if attribution == "BATTERY_FIRST" else LANE["pers"]
    if pd.isna(anchor):
        return dict(state="none", text="active window but anchor date missing", band=band)

    w_start = anchor + pd.Timedelta(days=lo)
    w_end = anchor + pd.Timedelta(days=hi)
    w_mid = anchor + pd.Timedelta(days=(lo + hi) / 2.0)
    verdict, days_out = None, None
    if failed and jc is not None and pd.notna(jc):
        if w_start <= jc <= w_end:
            verdict, days_out = "inside", 0
        elif jc < w_start:
            verdict, days_out = "early", (w_start - jc).days   # failure before the window opened
        else:
            verdict, days_out = "late", (jc - w_end).days       # failure after the window closed
    return dict(state="window", band=band, attribution=attribution, channel=channel,
                transient=transient, color=color, lo=lo, hi=hi, anchor=anchor,
                w_start=w_start, w_end=w_end, w_mid=w_mid, verdict=verdict, days_out=days_out)


# =============================================================================
# STATIC LOOKUPS (loaded once)
# =============================================================================
def load_jcopen():
    fp = pd.read_parquet(FAILED_PARQUET, columns=["VIN", "JCOPENDATE"])
    out = {}
    for vin, sub in fp.groupby("VIN"):
        dates = _dt(sub["JCOPENDATE"]).dropna().unique()
        if len(dates):
            out[f"{vin}_F_SM"] = pd.Timestamp(sorted(dates)[0])
    return out


# =============================================================================
# DATA BUNDLE
# =============================================================================
def build_bundle(vin, walk, alert, crank_all, jcopen, windows):
    failed = vin.endswith("_F_SM")

    # -- walking scores (usable rows, sorted ascending by cut_date) -----------
    w = walk[(walk["vin_label"] == vin) & (walk["usable"] == True)].copy()
    w["cut_date"] = _dt(w["cut_date"])
    w = w.dropna(subset=["cut_date", "prob"]).sort_values("cut_date").reset_index(drop=True)

    # -- t_end = last telemetry (== max walking cut == crank-derived end) ------
    ck = crank_all[crank_all["vin_label"] == vin].copy()
    ck["ts_start"] = _dt(ck["ts_start"])
    tend_candidates = []
    if len(w):
        tend_candidates.append(w["cut_date"].max())
    if len(ck):
        tend_candidates.append((ck["ts_start"] + pd.to_timedelta(ck["days_before_t_end"], unit="D")).max())
    t_end = max(tend_candidates) if tend_candidates else pd.NaT

    jc = jcopen.get(vin) if failed else None
    silent_gap = bool(jc is not None and pd.notna(t_end) and (jc - t_end).days > 3)
    ref_end = jc if (failed and jc is not None) else t_end

    # -- alert-channel row ----------------------------------------------------
    av = alert.loc[vin] if vin in alert.index else None
    tier = str(av["tier"]) if av is not None else "GREEN"

    # -- weekly cache (masked active_days >= 2) -------------------------------
    wk_path = os.path.join(WEEKLY_DIR, f"V1_SM_weekly_{vin}.parquet")
    wk = pd.read_parquet(wk_path)
    wk["week"] = _dt(wk["week"])
    wk = wk[wk["active_days"] >= 2].sort_values("week").reset_index(drop=True)

    # -- crank events (artifact == False) -------------------------------------
    ck = ck[ck["artifact"] == False].sort_values("ts_start").reset_index(drop=True)

    # -- precursor weekly series ---------------------------------------------
    prec = {}
    if len(wk) >= 4:
        weeks = wk["week"]
        vsi_range = (wk["vsi_drive_p95"] - wk["vsi_drive_p05"]).values
        # weekly-median dip_depth aligned to the weekly grid (backward as-of)
        dip_series = pd.Series(np.nan, index=range(len(wk)))
        cok = ck.dropna(subset=["dip_depth", "ts_start"])
        if len(cok):
            asof = pd.merge_asof(
                cok[["ts_start", "dip_depth"]].sort_values("ts_start"),
                pd.DataFrame({"wk": weeks.values, "idx": np.arange(len(weeks))}).sort_values("wk"),
                left_on="ts_start", right_on="wk", direction="backward")
            med = asof.dropna(subset=["idx"]).groupby("idx")["dip_depth"].median()
            for i, v in med.items():
                dip_series.iloc[int(i)] = v
        raw = {"vsi_drive_std": wk["vsi_drive_std"].values,
               "vsi_rest_p05": wk["vsi_rest_p05"].values,
               "vsi_range": vsi_range,
               "dip_depth_med": dip_series.values}
        for col, lab, inv, c in PREC_FEATS:
            prec[col] = dict(label=lab, color=c, z=z_first_half(raw[col], invert=inv))

    # -- validated maintenance-window (banded RUL) ----------------------------
    wr = windows.loc[vin] if vin in windows.index else None
    rul = build_rul(vin, av, wr, failed, jc)

    return dict(vin=vin, disp=display_label(vin), failed=failed, tier=tier,
                t_end=t_end, jc=jc, ref_end=ref_end, silent_gap=silent_gap,
                walk=w, av=av, weekly=wk, crank=ck, prec=prec, rul=rul)


# =============================================================================
# PANELS
# =============================================================================
def panel_walking(ax, b):
    w = b["walk"]
    ax.axhspan(RED_THR, 1.03, color=BAND_RED, alpha=0.07)
    ax.axhspan(AMBER_THR, RED_THR, color=BAND_AMBER, alpha=0.07)
    ax.axhspan(0.0, AMBER_THR, color=BAND_GREEN, alpha=0.07)
    for y in (AMBER_THR, RED_THR):
        ax.axhline(y, color="#bbb", lw=0.6, ls="--", alpha=0.6)
    ax.text(0.004, RED_THR + 0.01, "RED >=0.55", transform=ax.get_yaxis_transform(),
            fontsize=6.5, color=BAND_RED, va="bottom")
    ax.text(0.004, AMBER_THR + 0.01, "AMBER", transform=ax.get_yaxis_transform(),
            fontsize=6.5, color="#B9770E", va="bottom")

    if len(w) >= 2:
        ax.step(w["cut_date"], w["prob"], where="mid", color=WALK_STEP, lw=1.3, alpha=0.85, zorder=4)
        cols = [_PT[band_of(p)] for p in w["prob"]]
        ax.scatter(w["cut_date"], w["prob"], c=cols, s=30, zorder=6,
                   edgecolors="white", linewidths=0.5)
        # RED dwell: runs of >=3 consecutive cuts with prob >= 0.55
        red = (w["prob"] >= RED_THR).values
        for s, e in consecutive_runs(red):
            if e - s + 1 >= 3:
                ax.axvspan(w["cut_date"].iloc[s], w["cut_date"].iloc[e],
                           color=BAND_RED, alpha=0.10, zorder=1)
        ax.scatter([w["cut_date"].iloc[-1]], [w["prob"].iloc[-1]], s=95, marker="o",
                   facecolor="white", edgecolors=WALK_STEP, lw=1.6, zorder=7)
    else:
        ax.text(0.5, 0.5, "insufficient history for walking scores",
                transform=ax.transAxes, ha="center", fontsize=11, color="#888", style="italic")

    # persistence-lead chip (failed, if the validated persistence channel fired)
    if b["failed"] and b["av"] is not None and pd.notna(b["av"].get("pers_lead_vs_jcopen_d")):
        lead = int(b["av"]["pers_lead_vs_jcopen_d"])
        ax.text(0.013, 0.90, f"RED persistence lead  -{lead} d", transform=ax.transAxes,
                fontsize=9.5, fontweight="bold", color="#0B3D91", va="top", ha="left",
                bbox=dict(boxstyle="round,pad=0.4", fc="#EAF2FB", ec="#1565C0", lw=1.0))
    elif b["failed"] and b["tier"] == "GREEN":
        ax.text(0.013, 0.90, "no persistence lead  (below alert line)", transform=ax.transAxes,
                fontsize=8.5, fontweight="bold", color="#8A6D00", va="top", ha="left",
                bbox=dict(boxstyle="round,pad=0.35", fc="#FFF8E1", ec="#E0A800", lw=0.9))

    ax.set_ylim(0, 1.03)
    ax.set_ylabel("Walking failure-risk\n(recalibrated prob)", fontsize=10, fontweight="bold")
    ax.set_title("1 . Walking failure-risk score - validated ML clock  (points + step; no smoothing)", **TITLE_KW)


def panel_rul(ax, b):
    """Panel 2 - validated maintenance WINDOW (banded RUL anchored at an alert).

    Honest-by-construction: SM's validated RUL deliverable is a *banded window anchored at an
    alert*, not a point estimate - per-truck point-RUL regression underperforms the fleet clock
    (V2 finding).  For failed trucks we draw the actual JCOPENDATE (global line) and state, in
    words, whether it fell inside the predicted window."""
    r = b["rul"]
    ax.set_ylim(0, 1)
    ax.set_yticks([])
    ax.set_ylabel("Maintenance\nwindow", fontsize=10, fontweight="bold")
    ax.set_title("2 . Remaining life (RUL) - validated maintenance WINDOW  (banded window anchored at an alert)",
                 **TITLE_KW)
    ax.text(0.012, 0.93,
            "RUL as validated maintenance window (banded) - point RUL is less accurate than the "
            "fleet clock on this data",
            transform=ax.transAxes, fontsize=8.0, color="#7A8A99", style="italic", va="top", ha="left")

    # ---- no active window -> centered state text --------------------------------------------
    if r.get("state") != "window":
        col = {"missed": "#8B0000", "amber": "#B9770E", "green": "#1B5E20"}.get(r.get("state"), "#5D6D7E")
        ax.text(0.5, 0.50, r.get("text", "no active window"), transform=ax.transAxes,
                ha="center", va="center", fontsize=12.5, fontweight="bold", color=col)
        if r.get("note"):
            ax.text(0.5, 0.30, r["note"], transform=ax.transAxes, ha="center", va="center",
                    fontsize=9.5, color="#8B0000", style="italic")
        return

    # ---- active banded window ---------------------------------------------------------------
    c = r["color"]; anchor = r["anchor"]; ws = r["w_start"]; we = r["w_end"]; wm = r["w_mid"]
    y0, y1, ym = 0.42, 0.58, 0.50

    # lead segment (anchor -> window opens) as a dotted runway approach
    ax.plot([anchor, ws], [ym, ym], color=c, lw=1.3, ls=(0, (2, 2)), alpha=0.55, zorder=3)
    ax.annotate(f"lead {r['lo']} d", xy=(anchor + (ws - anchor) / 2, ym), xytext=(0, -11),
                textcoords="offset points", ha="center", fontsize=7.0, color=c, alpha=0.9)

    # runway band [anchor+lo, anchor+hi]
    ax.fill_between([ws, we], y0, y1, color=c, alpha=0.20, edgecolor=c, linewidth=1.1, zorder=2)
    ax.annotate(f"validated service window  {ws:%b %d} - {we:%b %d}", xy=(wm, ym),
                textcoords="offset points", xytext=(0, 0), ha="center", va="center", fontsize=7.6,
                color="white", fontweight="bold", zorder=7,
                bbox=dict(boxstyle="round,pad=0.22", fc=c, ec="none", alpha=0.9))

    # midpoint (median) tick
    ax.plot([wm, wm], [y0 - 0.07, y1 + 0.07], color=c, lw=1.6, zorder=6)
    ax.annotate("median", xy=(wm, y1 + 0.07), xytext=(0, 3), textcoords="offset points",
                ha="center", fontsize=7.5, color=c, fontweight="bold")

    # anchor marker + channel label
    ax.scatter([anchor], [ym], s=95, color=c, edgecolors="white", lw=1.1, zorder=8)
    chlab = r["channel"] + (" (transient)" if r["transient"] else "") + " alert"
    ax.annotate(f"{chlab}\n{anchor:%Y-%m-%d}", xy=(anchor, ym), xytext=(0, 15),
                textcoords="offset points", ha="center", va="bottom", fontsize=7.6,
                color=c, fontweight="bold")

    # window bound day-labels below the band
    ax.annotate(f"+{r['lo']} d", xy=(ws, y0), xytext=(0, -6), textcoords="offset points",
                ha="center", va="top", fontsize=7.0, color="#5D6D7E")
    ax.annotate(f"+{r['hi']} d", xy=(we, y0), xytext=(0, -6), textcoords="offset points",
                ha="center", va="top", fontsize=7.0, color="#5D6D7E")

    # verdict chip (failed = validated against JCOPENDATE; non-failed = forward projection)
    if r.get("verdict") == "inside":
        ax.text(0.986, 0.93, "failure INSIDE predicted window ✓", transform=ax.transAxes,
                ha="right", va="top", fontsize=9.5, fontweight="bold", color="#1B5E20",
                bbox=dict(boxstyle="round,pad=0.4", fc="#EAF7EE", ec="#1B5E20", lw=1.0))
    elif r.get("verdict") in ("early", "late"):
        ax.text(0.986, 0.93, f"failure outside window ({r['verdict']} by {r['days_out']} d)",
                transform=ax.transAxes, ha="right", va="top", fontsize=9.5, fontweight="bold",
                color="#B71C1C", bbox=dict(boxstyle="round,pad=0.4", fc="#FDECEA", ec="#B71C1C", lw=1.0))
    elif not b["failed"]:
        ax.text(0.986, 0.93, "non-failed - forward projection (censored)", transform=ax.transAxes,
                ha="right", va="top", fontsize=8.0, color="#5D6D7E", style="italic")


def panel_channels(ax, b):
    ypos = {"pers": 3, "a1": 2, "a2": 1}
    labels = {3: "Persistence", 2: "A1 crank-burst", 1: "A2 battery-cascade"}
    end = b["ref_end"]
    av = b["av"]
    nf = not b["failed"]
    lead_col = (lambda ch: f"{ch}_lead_vs_t_end_d") if nf else (lambda ch: f"{ch}_lead_vs_jcopen_d")

    def draw_span(y, ch, fire_date):
        c = LANE[ch]
        ax.plot([fire_date, end], [y, y], lw=7, color=c, alpha=0.30,
                solid_capstyle="butt", zorder=2)
        ax.scatter([fire_date], [y], s=95, color=c, edgecolors="white", lw=1.0, zorder=5)
        ld = av.get(lead_col(ch)) if av is not None else None
        if ld is None or pd.isna(ld):
            ld = (end - pd.Timestamp(fire_date)).days
        ax.annotate(f"{int(ld)} d", xy=(fire_date, y), xytext=(6, 9), textcoords="offset points",
                    fontsize=8, fontweight="bold", color=c)

    def no_fire(y):
        ax.text(end, y, "  no fire", va="center", ha="left", fontsize=8, color="#9AA7B0", style="italic")

    fired = 0
    if av is not None:
        # --- Persistence ---
        pt = _dt(av.get("pers_terminal_fire_start"))
        pf = _dt(av.get("pers_first_fire_week"))
        if bool(av.get("pers_fire_end")) and pd.notna(pt):
            draw_span(ypos["pers"], "pers", pt); fired += 1
            if pd.notna(pf) and pf < pt:  # earlier transient touch
                ax.scatter([pf], [ypos["pers"]], s=55, facecolor="none",
                           edgecolors=LANE["pers"], lw=1.1, zorder=4)
        elif pd.notna(pf):
            ax.scatter([pf], [ypos["pers"]], s=55, facecolor="none", edgecolors=LANE["pers"], lw=1.1, zorder=4)
            ax.annotate("transient (recovered)", xy=(pf, ypos["pers"]), xytext=(6, 8),
                        textcoords="offset points", fontsize=7.5, color="#7A8A99", style="italic")
        else:
            no_fire(ypos["pers"])
        # --- A1 crank-burst ---
        if bool(av.get("a1_fire")) and pd.notna(_dt(av.get("a1_first_alarm"))):
            draw_span(ypos["a1"], "a1", _dt(av.get("a1_first_alarm"))); fired += 1
        else:
            no_fire(ypos["a1"])
        # --- A2 battery-cascade ---
        if bool(av.get("a2_fire")) and pd.notna(_dt(av.get("a2_fire_week"))):
            draw_span(ypos["a2"], "a2", _dt(av.get("a2_fire_week"))); fired += 1
        else:
            no_fire(ypos["a2"])
    else:
        for y in (1, 2, 3):
            no_fire(y)

    b["_channels_fired"] = fired
    ax.set_ylim(0.4, 3.7)
    ax.set_yticks([1, 2, 3]); ax.set_yticklabels([labels[1], labels[2], labels[3]], fontsize=9)
    ax.set_ylabel("Alert channel", fontsize=10, fontweight="bold")
    ax.set_title("3 . Alert-channel evidence lanes - when each validated channel fired  (span -> data end)", **TITLE_KW)


def panel_voltage(ax, b):
    wk = b["weekly"]
    ax.axhspan(26, 29, color=ZG, alpha=0.10)
    ax.axhline(28.2, ls=":", color="#888", lw=0.8)
    ax.axhline(24, ls="--", color=SAGC, lw=0.9, alpha=0.7)
    if len(wk):
        wks = wk["week"]
        # driving VSI band + mean
        ax.fill_between(wks, wk["vsi_drive_p05"], wk["vsi_drive_p95"], color=VOLT, alpha=0.12, zorder=2)
        ax.plot(wks, wk["vsi_drive_mean"], color=VOLT, lw=1.6, zorder=5, label="drive VSI (mean, p05-p95)")
        # resting VSI median + p05 floor shading
        ax.fill_between(wks, wk["vsi_rest_p05"], wk["vsi_rest_median"], color=REST, alpha=0.14, zorder=2)
        ax.plot(wks, wk["vsi_rest_median"], color=REST, lw=1.5, ls="--", zorder=5, label="resting VSI (median, p05 floor)")
        # under-voltage (<21 V) weeks as ticks
        uv = wks[wk["vsi_below_21_rows"].values > 0]
        if len(uv):
            ax.scatter(uv, np.full(len(uv), 20.4), marker="|", s=26, color=SAGC, alpha=0.7, zorder=4)
    # battery-step events from the validated alert file
    av = b["av"]
    if av is not None:
        for scol, dcol, base_y in [("rest_step_V", "rest_step_date", 25.0), ("drive_step_V", "drive_step_date", 28.5)]:
            sv, sd = av.get(scol), _dt(av.get(dcol))
            if pd.notna(sv) and pd.notna(sd) and abs(float(sv)) >= 0.5:
                lbl = "battery service?" if float(sv) >= 0.5 else "rest-V drop"
                ax.axvline(sd, color="#455A64", lw=1.0, ls=(0, (3, 2)), alpha=0.7, zorder=3)
                ax.annotate(f"{lbl} {float(sv):+.1f}V", xy=(sd, base_y), xytext=(5, 0),
                            textcoords="offset points", fontsize=7.5, color="#37474F",
                            fontweight="bold", va="center",
                            bbox=dict(boxstyle="round,pad=0.2", fc="#ECEFF1", ec="#90A4AE", lw=0.5))
    ax.set_ylim(20, 30)
    ax.set_ylabel("VSI (V)", fontsize=10, fontweight="bold")
    ax.set_title("4 . Voltage health - resting & driving VSI  (charging band 26-29 V; ticks = <21 V weeks)", **TITLE_KW)
    ax.legend(loc="lower left", fontsize=7.5, framealpha=0.9, ncol=2)


def panel_precursors(ax, b):
    ax.axhline(2.0, ls="--", color="#999", lw=1.0)
    ax.axhline(0, color="#ddd", lw=0.6)
    prec = b["prec"]
    if not prec:
        ax.text(0.5, 0.5, "insufficient weekly history for precursor z-scores",
                transform=ax.transAxes, ha="center", fontsize=11, color="#888", style="italic")
        ax.set_ylim(-3, 5)
        ax.set_ylabel("Deviation\n(sigma, up=worse)", fontsize=10, fontweight="bold")
        ax.set_title("5 . Precursor physics - 4 champion features (weekly z vs first-half baseline)", **TITLE_KW)
        return
    wks = b["weekly"]["week"].values
    handles, zmax = [], 2.5
    worst = np.full(len(wks), -np.inf)
    for col, lab, inv, c in PREC_FEATS:
        z = prec[col]["z"]
        ax.plot(wks, z, lw=1.0, color="#c7c7c7", alpha=0.75, zorder=3)  # muted base
        zb = np.where(np.abs(z) >= 2.0, z, np.nan)                       # bold where breaching
        ax.plot(wks, zb, lw=2.3, color=c, zorder=5)
        handles.append(Line2D([], [], color=c, lw=2.2, label=lab))
        fin = z[np.isfinite(z)]
        if fin.size:
            zmax = max(zmax, float(np.nanmax(fin)))
        worst = np.fmax(worst, np.nan_to_num(z, nan=-np.inf))

    # first sustained breach (failed only)
    if b["failed"] and pd.notna(b["ref_end"]):
        idx = None
        for i in range(len(worst)):
            if worst[i] >= 2.0 and (i == len(worst) - 1 or worst[i + 1] >= 1.5):
                idx = i; break
        if idx is not None:
            wd = pd.Timestamp(wks[idx]); lead = (b["ref_end"] - wd).days
            drv = max(PREC_FEATS, key=lambda f: (prec[f[0]]["z"][idx] if np.isfinite(prec[f[0]]["z"][idx]) else -9))
            ax.axvline(wd, color=BAND_RED, lw=1.1, ls="-", alpha=0.55, zorder=4)
            ax.annotate(f"first physics deviation  -{lead} d before failure\n(driver: {drv[1]})",
                        xy=(wd, 2.0), xytext=(8, 20), textcoords="offset points",
                        fontsize=8, fontweight="bold", color="#B71C1C",
                        bbox=dict(boxstyle="round,pad=0.28", fc="#FFF5F5", ec=BAND_RED, lw=0.8),
                        arrowprops=dict(arrowstyle="->", color=BAND_RED, lw=0.9))

    ax.set_ylim(-3, min(max(5.0, zmax + 0.6), 10.0))  # cap top for cross-VIN comparability
    ax.set_ylabel("Deviation\n(sigma, up=worse)", fontsize=10, fontweight="bold")
    ax.set_title("5 . Precursor physics - 4 champion features  (weekly z vs first-half baseline; bold = |z|>=2)", **TITLE_KW)
    ax.legend(handles=handles, loc="upper left", fontsize=7.5, framealpha=0.9, ncol=2)


def panel_crank(ax, b):
    ck = b["crank"].dropna(subset=["dip_depth"]).copy()
    if len(ck) < 4:
        ax.text(0.5, 0.5, "insufficient crank events for signature",
                transform=ax.transAxes, ha="center", fontsize=11, color="#888", style="italic")
        ax.set_ylabel("VSI dip depth (V)", fontsize=10, fontweight="bold")
        ax.set_title("6 . Crank signature - dip depth, early vs late life", **TITLE_KW)
        return
    ck = ck.sort_values("ts_start").reset_index(drop=True)
    x = ck["ts_start"]; y = ck["dip_depth"].values
    ax.scatter(x, y, s=9, color="#9AA7B0", alpha=0.55, zorder=2, label="crank dip")
    # failed cranks as red x
    fc = ck[ck["success"] == False]
    if len(fc):
        ax.scatter(fc["ts_start"], fc["dip_depth"], marker="x", s=34, color=SAGC,
                   lw=1.1, alpha=0.85, zorder=4, label=f"failed crank (n={len(fc)})")
    # early (first 25%) vs late (last 25%) median segments
    n = len(ck); q = max(int(0.25 * n), 3)
    early, late = ck.iloc[:q], ck.iloc[-q:]
    em, lm = float(np.nanmedian(early["dip_depth"])), float(np.nanmedian(late["dip_depth"]))
    ax.plot([early["ts_start"].iloc[0], early["ts_start"].iloc[-1]], [em, em],
            color=ZG, lw=3.0, zorder=6, solid_capstyle="round", label=f"early-life median {em:.1f}V")
    ax.plot([late["ts_start"].iloc[0], late["ts_start"].iloc[-1]], [lm, lm],
            color=SAGC, lw=3.0, zorder=6, solid_capstyle="round", label=f"late-life median {lm:.1f}V")
    lo = float(np.nanpercentile(y, 1)) - 1; hi = float(np.nanpercentile(y, 99)) + 1
    ax.set_ylim(min(lo, -1), max(hi, 6))
    ax.set_ylabel("VSI dip depth (V)\n(deeper = worse)", fontsize=10, fontweight="bold")
    ax.set_title("6 . Crank signature - dip depth, early vs late life", **TITLE_KW)
    ax.legend(loc="upper left", fontsize=7.5, framealpha=0.9, ncol=2)


# =============================================================================
# ASSEMBLE
# =============================================================================
def _footer(b):
    fired = b.get("_channels_fired", 0)
    if b["vin"] == "VIN9_F_SM":
        return ("MISSED - structurally invisible (SMA-dead + 142 d telemetry-silent gap): "
                "0/3 channels fired, walking risk stayed GREEN"), "#8B0000"
    parts = [f"final tier {b['tier']}", f"channels fired {fired}/3"]
    av = b["av"]
    if b["failed"] and av is not None:
        if pd.notna(av.get("pers_lead_vs_jcopen_d")):
            parts.append(f"persistence lead {int(av['pers_lead_vs_jcopen_d'])} d")
        if bool(av.get("a2_fire")) and pd.notna(av.get("a2_lead_vs_jcopen_d")):
            parts.append(f"A2 lead {int(av['a2_lead_vs_jcopen_d'])} d")
        if bool(av.get("a1_fire")) and pd.notna(av.get("a1_lead_vs_jcopen_d")):
            parts.append(f"A1 lead {int(av['a1_lead_vs_jcopen_d'])} d")
    col = "#1B5E20" if (not b["failed"] or fired > 0) else "#8A6D00"
    return "   .   ".join(parts), col


def build_figure(vin, walk, alert, crank_all, jcopen, windows):
    b = build_bundle(vin, walk, alert, crank_all, jcopen, windows)

    fig = plt.figure(figsize=(15, 22))
    gs = GridSpec(6, 1, height_ratios=[2.3, 2.0, 1.55, 2.05, 2.15, 2.0], hspace=0.5,
                  left=0.075, right=0.925, top=0.93, bottom=0.05)
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax3 = fig.add_subplot(gs[2], sharex=ax1)
    ax4 = fig.add_subplot(gs[3], sharex=ax1)
    ax5 = fig.add_subplot(gs[4], sharex=ax1)
    ax6 = fig.add_subplot(gs[5], sharex=ax1)

    panel_walking(ax1, b)
    panel_rul(ax2, b)
    panel_channels(ax3, b)
    panel_voltage(ax4, b)
    panel_precursors(ax5, b)
    panel_crank(ax6, b)

    # x-range: full life -> ref_end
    starts = []
    if len(b["weekly"]):
        starts.append(b["weekly"]["week"].min())
    if len(b["walk"]):
        starts.append(b["walk"]["cut_date"].min())
    if len(b["crank"]):
        starts.append(b["crank"]["ts_start"].min())
    t0 = min(starts) if starts else (b["t_end"] - pd.Timedelta(days=180))
    end = b["ref_end"] if pd.notna(b["ref_end"]) else b["t_end"]
    # extend the (shared) right edge to show the full RUL window when it runs past data end
    x_right = end
    r = b.get("rul", {})
    if r.get("state") == "window" and pd.notna(r.get("w_end")):
        x_right = max(x_right, r["w_end"])
    ax1.set_xlim(t0 - pd.Timedelta(days=10), x_right + pd.Timedelta(days=18))

    # global reference lines: t_end, JCOPENDATE, silent-gap hatch.
    # When failed with NO gap, t_end == JCOPENDATE -> draw only the JCOPENDATE line (avoid overlap).
    show_tend = pd.notna(b["t_end"]) and not (b["failed"] and b["jc"] is not None and not b["silent_gap"])
    for ax in (ax1, ax2, ax3, ax4, ax5, ax6):
        if show_tend:
            ax.axvline(b["t_end"], color="#5D6D7E", lw=1.0, ls=":", alpha=0.6, zorder=8)
        if b["silent_gap"]:
            ax.axvspan(b["t_end"], b["jc"], facecolor="none", hatch="/////",
                       edgecolor=GAP_HATCH_EC, linewidth=0.0, alpha=0.9, zorder=1)
        if b["failed"] and b["jc"] is not None:
            ax.axvline(b["jc"], color="#8B0000", lw=1.3, ls="-.", alpha=0.7, zorder=8)
    if b["silent_gap"]:
        gapd = (b["jc"] - b["t_end"]).days
        ax1.annotate(f"telemetry-silent gap  {gapd} d", xy=(b["t_end"], 1.0),
                     xytext=(4, -12), textcoords="offset points", fontsize=7.5,
                     color="#6D4C41", style="italic", fontweight="bold")
    # end-marker labels (top panel)
    if show_tend:
        ax1.annotate("data end", xy=(b["t_end"], 0.0), xytext=(2, 4), textcoords="offset points",
                     fontsize=7, color="#5D6D7E", rotation=90, va="bottom")
    if b["failed"] and b["jc"] is not None:
        jlab = "JCOPENDATE (failure)" if b["silent_gap"] else "JCOPENDATE = data end"
        ax1.annotate(jlab, xy=(b["jc"], 0.0), xytext=(2, 4),
                     textcoords="offset points", fontsize=7, color="#8B0000", rotation=90, va="bottom")

    # date axis on the bottom panel only
    loc = mdates.AutoDateLocator(minticks=6, maxticks=13)
    ax6.xaxis.set_major_locator(loc)
    ax6.xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc))
    ax6.set_xlabel("Timeline (calendar)", fontsize=10, fontweight="bold")
    for ax in (ax1, ax2, ax3, ax4, ax5):
        ax.tick_params(labelbottom=False)
    for ax in (ax1, ax2, ax3, ax4, ax5, ax6):
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.grid(True, axis="y", color="#E8ECEF", lw=0.5, alpha=0.7)

    # header
    fig.suptitle(f"Starter Motor Risk + Physics Evidence - {b['vin']}", fontsize=18,
                 fontweight="bold", color=DK, x=0.075, ha="left", y=0.972)
    if b["failed"]:
        best = []
        av = b["av"]
        if av is not None:
            for ch in ("pers", "a1", "a2"):
                v = av.get(f"{ch}_lead_vs_jcopen_d")
                if pd.notna(v):
                    best.append(int(v))
        lead_txt = f"best-channel lead {max(best)} d" if best else "no channel lead (miss)"
        jc_txt = b["jc"].strftime("%Y-%m-%d") if b["jc"] is not None else "n/a"
        sub = (f"final tier {b['tier'].upper()}   .   FAILED (JCOPENDATE {jc_txt})   .   {lead_txt}")
    else:
        de = b["t_end"].strftime("%Y-%m-%d") if pd.notna(b["t_end"]) else "n/a"
        sub = f"final tier {b['tier'].upper()}   .   non-failed (censored at data end {de})"
    if b["disp"] != b["vin"]:
        sub += f"   .   fleet-display: {b['disp']}"
    fig.text(0.075, 0.948, sub, fontsize=10.5, color="#5D6D7E", style="italic")

    # footer strip
    ftxt, fcol = _footer(b)
    fig.text(0.075, 0.02, ftxt, fontsize=9, color=fcol, fontweight="bold")
    fig.text(0.075, 0.006,
             "Panel 1 = validated walking-risk ML clock; Panel 2 = validated maintenance WINDOW "
             "(banded RUL, not a point estimate - SM has no fleet-age RUL schedule). "
             "Panels 3-6 are this truck's condition/physics evidence. n=34 SM fleet. Confidential.",
             fontsize=7.5, color="#95A5A6", style="italic")

    png = os.path.join(OUT, f"sm_{b['vin']}_evidence_stack.png")
    fig.savefig(png, dpi=160, bbox_inches="tight", facecolor="white")
    fig.savefig(os.path.join(OUT, f"sm_{b['vin']}_evidence_stack.svg"), bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return b


def main():
    walk = pd.read_csv(WALK_CSV)
    alert = pd.read_csv(ALERT_CSV).set_index("vin_label")
    windows = pd.read_csv(WINDOWS_CSV).set_index("vin_label")
    crank_all = pd.read_parquet(CRANK_PARQUET)
    jcopen = load_jcopen()
    vins = list(pd.read_csv(FEAT_CSV)["vin_label"])
    if len(sys.argv) > 1:
        vins = [v for v in vins if v in set(sys.argv[1:])]

    ok, skip, bundles = [], [], []
    for vin in vins:
        try:
            b = build_figure(vin, walk, alert, crank_all, jcopen, windows)
            ok.append(vin); bundles.append(b)
            print(f"  {vin:<13} tier={b['tier']:<6} fired={b.get('_channels_fired',0)}/3 "
                  f"gap={'Y' if b['silent_gap'] else '-'}  saved")
        except Exception as ex:
            import traceback
            skip.append((vin, str(ex)))
            print(f"  {vin}: SKIP {ex}")
            traceback.print_exc()
    print(f"\nDone: {len(ok)}/{len(vins)} figures -> {OUT}")
    if skip:
        print("Skipped:", skip)

    # ---- window-validation table (failed trucks with an active window) ------------
    val = [b for b in bundles if b["failed"] and b.get("rul", {}).get("state") == "window"]
    if val:
        print("\nWindow-validation - did JCOPENDATE fall inside the predicted maintenance window?")
        hdr = (f"  {'vin':<12}{'band':<22}{'anchor':<12}{'w_start':<12}{'w_end':<12}"
               f"{'JCOPEN':<12}{'verdict':<8}{'days_out':>9}")
        print(hdr); print("  " + "-" * (len(hdr) - 2))
        inside = 0
        for b in sorted(val, key=lambda z: z["vin"]):
            r = b["rul"]; inside += (r["verdict"] == "inside")
            print(f"  {b['vin']:<12}{r['band']:<22}{r['anchor'].strftime('%Y-%m-%d'):<12}"
                  f"{r['w_start'].strftime('%Y-%m-%d'):<12}{r['w_end'].strftime('%Y-%m-%d'):<12}"
                  f"{b['jc'].strftime('%Y-%m-%d'):<12}{r['verdict']:<8}{str(r['days_out']):>9}")
        print(f"  => {inside}/{len(val)} windowed failures had JCOPENDATE INSIDE the predicted window")
    misses = [b for b in bundles if b["failed"] and b.get("rul", {}).get("state") != "window"]
    if misses:
        print("\nFailed trucks with NO active window (missed by the window rule):")
        for b in sorted(misses, key=lambda z: z["vin"]):
            print(f"  {b['vin']:<12}{b['rul'].get('band', ''):<20}{b['rul'].get('text', '')}")


if __name__ == "__main__":
    main()
