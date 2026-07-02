# STARTER MOTOR/V3.1/features/build_catalog.py
"""Spec §6.1 catalog. VALUES ONLY - no label stats here (Task 11 discipline)."""
import sys, glob, json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import theilslopes
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _v31_lib as L
import _factors31 as X
from _factors import dip_depth_last90_level

SMROOT = L.SMROOT
SOUT = SMROOT / "V3.1" / "state" / "out"
ev, wk, px = L.load_events(), L.load_weekly(), L.build_px()
roll = L.load_state_weekly()
order = L.vins_in_order()


def _r(vin):
    return roll[roll["vin_label"] == vin].sort_values("week")


def _cranks(vin):
    p = SOUT / f"V3_1_cranks_{vin}.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame(columns=["ts_start", "soak_h", "cwr", "recrank"])


def _trips(vin):
    p = SOUT / f"V3_1_trips_{vin}.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame(columns=["ts_start", "dur_min", "km", "idle_share"])


rows = []
for v in order:
    r, c, t = _r(v), _cranks(v), _trips(v)
    e = X._evin(ev, v)
    days = max(1.0, float(r["active_days"].sum()))
    run_h = float(r["engine_hours"].sum())
    d = {"vin_label": v,
         "engine_hours_per_day": run_h / days,
         "km_per_day": float(r["km"].sum()) / days,
         "trips_per_day": float(r["n_trips"].sum()) / days,
         "mean_trip_duration_min": float(t["dur_min"].mean()) if len(t) else np.nan,
         "mean_trip_km": float(t["km"].mean()) if len(t) else np.nan,
         "short_trip_share": float(r["n_short_trips"].sum() / r["n_trips"].sum()) if r["n_trips"].sum() else np.nan,
         "idle_share": float(r["idle_hours"].sum() / run_h) if run_h else np.nan,
         "stop_density": float(r["n_trips"].sum() / run_h) if run_h else np.nan,
         "overnight_off_share": float((c["soak_h"] >= 8).mean()) if len(c) else np.nan,
         "soak_before_crank_median": float(c["soak_h"].median()) if len(c) else np.nan,
         "soak_before_crank_p90": float(c["soak_h"].quantile(0.9)) if len(c) else np.nan,
         "overnight_start_share": float(r["n_overnight_starts"].sum() / max(1, r["n_cranks"].sum())),
         "hot_restart_share": float(r["n_hot_restarts"].sum() / max(1, r["n_cranks"].sum())),
         "starts_per_active_day": float(len(e)) / days,
         "starts_per_100km": float(len(e) / (r["km"].sum() / 100.0)) if r["km"].sum() > 0 else np.nan,
         "crank_success_ratio": float(e["success"].mean()) if len(e) else np.nan,
         "crank_dur_p95": float(e["dur_s"].quantile(0.95)) if len(e) else np.nan,
         "cranks_per_trip": float(len(e) / r["n_trips"].sum()) if r["n_trips"].sum() else np.nan,
         "weekly_crank_rate": float(r["n_cranks"].sum() / max(1, len(r))),
         "pre_crank_vsi_median": float(e["baseline_vsi"].median()) if len(e) else np.nan,
         "hard_start_goodv_rate": np.nan, "lowv_crank_share": np.nan,   # filled below
         "dip_resid_last90_median": X.dip_resid_last90_median(ev, wk, px, v),
         "dropout_hours_per_week": float(r["dropout_hours"].mean()) if len(r) else np.nan,
         "heartbeat_coverage_share": float(r["off_dwell_hours"].sum() /
                                           max(1e-9, r["off_dwell_hours"].sum() + r["unknown_gap_hours"].sum() + r["dropout_hours"].sum())),
         "vsi_valid_share": float(np.isfinite(e["baseline_vsi"]).mean()) if len(e) else np.nan,
         "monsoon_start_share": float(e["ts_start"].dt.month.isin([6, 7, 8, 9]).mean()) if len(e) else np.nan,
         "dip_depth_last90_level": dip_depth_last90_level(ev, px, v)}
    if v in px.index and not px.loc[v].isna().any() and len(e):
        t90 = pd.Timestamp(px.loc[v, "t_90_cutoff"])
        last = e[(e["ts_start"] >= t90) & np.isfinite(e["baseline_vsi"])]
        if len(last) >= 3:
            d["hard_start_goodv_rate"] = float(((last["success"] == False) & (last["baseline_vsi"] >= X.GOODV)).mean())  # noqa: E712
            d["lowv_crank_share"] = float((last["baseline_vsi"] < X.LOWV).mean())
        # #27 longest run of consecutive low-voltage cranks (full L40 window)
        bv = e[np.isfinite(e["baseline_vsi"])]["baseline_vsi"].values
        lv = (bv < X.LOWV).astype(int)
        run_max, cur = 0, 0
        for b in lv:
            cur = cur + 1 if b else 0
            run_max = max(run_max, cur)
        d["lowv_consecutive_events_max"] = float(run_max)
        # #21 longest run of consecutive days above own p75 daily crank count, last 90 d
        daily = e[e["ts_start"] >= t90].groupby(e["ts_start"].dt.date).size()
        if len(daily) >= 5:
            thr = float(e.groupby(e["ts_start"].dt.date).size().quantile(0.75))
            days_sorted = daily.sort_index()
            hi = (days_sorted > thr).astype(int).values
            run_max, cur = 0, 0
            for b in hi:
                cur = cur + 1 if b else 0
                run_max = max(run_max, cur)
            d["consecutive_high_crank_days_max90"] = float(run_max)
        else:
            d["consecutive_high_crank_days_max90"] = np.nan
    else:
        d["lowv_consecutive_events_max"] = np.nan
        d["consecutive_high_crank_days_max90"] = np.nan
    # trends
    if len(r) >= 12:
        yv = r["engine_hours"].tail(12).values.astype(float)
        d["weekly_engine_hours_trend"] = float(theilslopes(yv, np.arange(12.0))[0])
    else:
        d["weekly_engine_hours_trend"] = np.nan
    w = wk[(wk["vin_label"] == v) & (wk["active_days"] >= 2)].sort_values("week")
    if len(w) >= 12 and "vsi_rest_median" in w:
        yv = w["vsi_rest_median"].tail(12).values.astype(float)
        m = np.isfinite(yv)
        d["rest_vsi_trend_12w"] = float(theilslopes(yv[m], np.arange(12.0)[m])[0]) if m.sum() >= 6 else np.nan
    else:
        d["rest_vsi_trend_12w"] = np.nan
    rows.append(d)

cat = pd.DataFrame(rows)
# #28 composite: z-sum of (lowv share, dip level, negated rest-floor trend) — Experimental by spec
for c in ("lowv_crank_share", "dip_depth_last90_level", "rest_vsi_trend_12w"):
    mu, sd = cat[c].mean(), cat[c].std()
    cat[f"_z_{c}"] = (cat[c] - mu) / sd if sd and np.isfinite(sd) else np.nan
cat["voltage_stress_index"] = cat["_z_lowv_crank_share"] + cat["_z_dip_depth_last90_level"] - cat["_z_rest_vsi_trend_12w"]
cat = cat.drop(columns=[c for c in cat.columns if c.startswith("_z_")])
cat.to_csv(L.V31_OUT / "V3_1_SM_catalog.csv", index=False)
print(f"catalog: {cat.shape[0]} VINs x {cat.shape[1]-1} features")
# NOT computed by design (plan Refinement 7): post_trip_recovery_delta (#29, graveyard-WEAK),
# rest_vsi_overnight_p05 (#30, predicted-redundant). Documented in the catalog report.
