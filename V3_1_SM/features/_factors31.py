# STARTER MOTOR/V3.1/features/_factors31.py
"""V3.1 pre-registered candidate factors. Window conventions match V3 _factors.py:
pooled ratios over the L40 window split at t_90_cutoff (plan Refinement 1)."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import theilslopes

CP = json.loads((Path(__file__).resolve().parents[1] / "params" / "V3_1_candidates.json").read_text())
GOODV, LOWV = CP["goodv_threshold_V"], CP["lowv_threshold_V"]
MIN_LAST, MIN_BASE = CP["delta90_min_last_events"], CP["delta90_min_base_events"]


def _evin(ev, vin):
    return ev[ev["vin_label"] == vin].sort_values("ts_start").reset_index(drop=True)


def _ok_px(px, vin):
    return (vin in px.index) and (not px.loc[vin].isna().any())


def _windows(px, vin):
    return pd.Timestamp(px.loc[vin, "win_start_l40"]), pd.Timestamp(px.loc[vin, "t_90_cutoff"])


def _active_days(wk, vin, lo, hi):
    w = wk[(wk["vin_label"] == vin) & (wk["active_days"] >= 2)]
    return float(w.loc[(w["week"] >= lo) & (w["week"] < hi), "active_days"].sum())


def hard_start_goodv_rate_delta90(ev, wk, px, vin):
    """A1: pooled rate of (failed crank & baseline_vsi >= 27.0 V) per active day, last90 minus baseline."""
    if not _ok_px(px, vin):
        return np.nan
    win, t90 = _windows(px, vin)
    e = _evin(ev, vin); e = e[e["ts_start"] >= win]
    n_ev_last = int((e["ts_start"] >= t90).sum()); n_ev_base = int((e["ts_start"] < t90).sum())
    if n_ev_last < MIN_LAST or n_ev_base < MIN_BASE:
        return np.nan
    hs = e[(e["success"] == False) & (e["baseline_vsi"] >= GOODV)]  # noqa: E712
    far = pd.Timestamp.max                                   # naive sentinel upper bound
    ad_last = _active_days(wk, vin, t90, far); ad_base = _active_days(wk, vin, win, t90)
    if ad_last <= 0 or ad_base <= 0:
        return np.nan
    return float((hs["ts_start"] >= t90).sum() / ad_last - (hs["ts_start"] < t90).sum() / ad_base)


def lowv_crank_share_delta90(ev, px, vin):
    """A3: share of cranks (with valid baseline_vsi) below 26.0 V, last90 minus baseline."""
    if not _ok_px(px, vin):
        return np.nan
    win, t90 = _windows(px, vin)
    e = _evin(ev, vin)
    e = e[(e["ts_start"] >= win) & np.isfinite(e["baseline_vsi"])]
    last, base = e[e["ts_start"] >= t90], e[e["ts_start"] < t90]
    if len(last) < MIN_LAST or len(base) < MIN_BASE:
        return np.nan
    return float((last["baseline_vsi"] < LOWV).mean() - (base["baseline_vsi"] < LOWV).mean())


def dip_resid_trend_12w(ev, wk, px, vin):
    """A2: Theil-Sen slope of weekly median dip-residuals (dip ~ OLS(baseline_vsi) fit on pre-tail events)."""
    if not _ok_px(px, vin):
        return np.nan
    win, _ = _windows(px, vin)
    e = _evin(ev, vin)
    e = e[(e["ts_start"] >= win) & np.isfinite(e["dip_depth"]) & np.isfinite(e["baseline_vsi"])].copy()
    if len(e) == 0:
        return np.nan
    e["week"] = e["ts_start"].dt.floor("D") - pd.to_timedelta(e["ts_start"].dt.weekday, unit="D")
    w = wk[(wk["vin_label"] == vin) & (wk["active_days"] >= 2)].sort_values("week")
    masked = pd.to_datetime(w["week"]).tail(CP["a2_trend_weeks"]).reset_index(drop=True)
    if len(masked) < CP["a2_trend_weeks"]:
        return np.nan
    cut = masked.iloc[0]
    fit, tail = e[e["week"] < cut], e[e["week"] >= cut].copy()
    if len(fit) < CP["a2_baseline_min_events"]:
        return np.nan
    if float(np.nanstd(fit["baseline_vsi"])) == 0.0:        # zero-variance predictor: OLS -> mean(dip); avoids RankWarning
        b1, b0 = 0.0, float(fit["dip_depth"].mean())
    else:
        b1, b0 = np.polyfit(fit["baseline_vsi"].values.astype(float), fit["dip_depth"].values.astype(float), 1)
    tail["resid"] = tail["dip_depth"] - (b0 + b1 * tail["baseline_vsi"])
    med = tail.groupby("week")["resid"].median().reindex(masked.values)
    yv = med.values.astype(float); x = np.arange(len(yv), dtype=float); m = np.isfinite(yv)
    if m.sum() < CP["a2_min_weekly_medians"]:
        return np.nan
    return float(theilslopes(yv[m], x[m])[0])


def _roll_sum(roll, vin, col, lo, hi):
    r = roll[roll["vin_label"] == vin]
    return float(r.loc[(r["week"] >= lo) & (r["week"] < hi), col].sum())


def starts_per_engine_hour_delta90(ev, roll, px, vin):
    """B1: pooled valid cranks per engine-hour, last90 minus baseline (state-engine denominator)."""
    if not _ok_px(px, vin):
        return np.nan
    win, t90 = _windows(px, vin)
    far = pd.Timestamp.max
    e = _evin(ev, vin); e = e[e["ts_start"] >= win]
    n_last = int((e["ts_start"] >= t90).sum()); n_base = int((e["ts_start"] < t90).sum())
    eh_last = _roll_sum(roll, vin, "engine_hours", t90, far)
    eh_base = _roll_sum(roll, vin, "engine_hours", win, t90)
    if (eh_last < CP["b1_min_engine_hours_side"] or eh_base < CP["b1_min_engine_hours_side"]
            or n_base < CP["b1_min_base_cranks"]):
        return np.nan
    return float(n_last / eh_last - n_base / eh_base)


def starts_per_engine_hour_last90(ev, roll, px, vin):
    """Level form (B2 ingredient)."""
    if not _ok_px(px, vin):
        return np.nan
    win, t90 = _windows(px, vin)
    far = pd.Timestamp.max
    e = _evin(ev, vin)
    n_last = int((e["ts_start"] >= t90).sum())
    eh_last = _roll_sum(roll, vin, "engine_hours", t90, far)
    return float(n_last / eh_last) if eh_last >= CP["b1_min_engine_hours_side"] else np.nan


def dropout_share_delta90(roll, px, vin):
    """C1: pooled DROPOUT_RUNNING hours / (dropout + observed) hours, last90 minus baseline. All-34."""
    if not _ok_px(px, vin):
        return np.nan
    win, t90 = _windows(px, vin)
    far = pd.Timestamp.max
    dl, ol = (_roll_sum(roll, vin, "dropout_hours", t90, far), _roll_sum(roll, vin, "observed_hours", t90, far))
    db, ob = (_roll_sum(roll, vin, "dropout_hours", win, t90), _roll_sum(roll, vin, "observed_hours", win, t90))
    if (dl + ol) <= 0 or (db + ob) <= 0:
        return np.nan
    return float(dl / (dl + ol) - db / (db + ob))


def dip_seasonal_contrast(ev, px, vin):
    """C2: median dip Dec-Feb minus Apr-Jun within the L40 window (pooled across years)."""
    if not _ok_px(px, vin):
        return np.nan
    win, _ = _windows(px, vin)
    e = _evin(ev, vin)
    e = e[(e["ts_start"] >= win) & np.isfinite(e["dip_depth"])]
    cold = e[e["ts_start"].dt.month.isin(CP["c2_months_cold"])]
    hot = e[e["ts_start"].dt.month.isin(CP["c2_months_hot"])]
    if len(cold) < CP["c2_min_events_side"] or len(hot) < CP["c2_min_events_side"]:
        return np.nan
    return float(cold["dip_depth"].median() - hot["dip_depth"].median())


def dip_resid_last90_median(ev, wk, px, vin):
    """Catalog #26 level form: median dip residual over the last 12 masked weeks (same fit as A2)."""
    if not _ok_px(px, vin):
        return np.nan
    win, _ = _windows(px, vin)
    e = _evin(ev, vin)
    e = e[(e["ts_start"] >= win) & np.isfinite(e["dip_depth"]) & np.isfinite(e["baseline_vsi"])].copy()
    if len(e) == 0:
        return np.nan
    e["week"] = e["ts_start"].dt.floor("D") - pd.to_timedelta(e["ts_start"].dt.weekday, unit="D")
    w = wk[(wk["vin_label"] == vin) & (wk["active_days"] >= 2)].sort_values("week")
    masked = pd.to_datetime(w["week"]).tail(CP["a2_trend_weeks"]).reset_index(drop=True)
    if len(masked) < CP["a2_trend_weeks"]:
        return np.nan
    cut = masked.iloc[0]
    fit, tail = e[e["week"] < cut], e[e["week"] >= cut].copy()
    if len(fit) < CP["a2_baseline_min_events"] or len(tail) == 0:
        return np.nan
    if float(np.nanstd(fit["baseline_vsi"])) == 0.0:
        b1, b0 = 0.0, float(fit["dip_depth"].mean())
    else:
        b1, b0 = np.polyfit(fit["baseline_vsi"].values.astype(float), fit["dip_depth"].values.astype(float), 1)
    return float((tail["dip_depth"] - (b0 + b1 * tail["baseline_vsi"])).median())
