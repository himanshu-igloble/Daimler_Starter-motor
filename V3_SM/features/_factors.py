import numpy as np, pandas as pd

def _evin(ev, vin):
    return ev[ev["vin_label"] == vin].sort_values("ts_start").reset_index(drop=True)

def _ok_px(px, vin):
    return (vin in px.index) and (not px.loc[vin].isna().any())

def dip_depth_last90_level(ev, px, vin, min_events=10):
    if not _ok_px(px, vin): return np.nan
    e = _evin(ev, vin); t90 = pd.Timestamp(px.loc[vin, "t_90_cutoff"])
    d = e.loc[e["ts_start"] >= t90, "dip_depth"].astype(float).values
    d = d[np.isfinite(d)]
    return float(d.mean()) if len(d) >= min_events else np.nan

def starts_per_active_day_last90(ev, wk, px, vin):
    if not _ok_px(px, vin): return np.nan
    e = _evin(ev, vin); t90 = pd.Timestamp(px.loc[vin, "t_90_cutoff"])
    n_starts = int((e["ts_start"] >= t90).sum())
    w = wk[wk["vin_label"] == vin]; active = float(w.loc[w["week"] >= t90, "active_days"].sum())
    return (n_starts / active) if active > 0 else np.nan

def cold_start_fraction_last90(ev, px, vin, rest_gap_s=6*3600, min_events=3):
    if not _ok_px(px, vin): return np.nan
    e = _evin(ev, vin)
    if len(e) < 2: return np.nan
    gaps = np.diff(e["ts_start"].values).astype("timedelta64[s]").astype(float)
    e["is_cold"] = np.concatenate([[True], gaps >= rest_gap_s])
    t90 = pd.Timestamp(px.loc[vin, "t_90_cutoff"])
    last = e[e["ts_start"] >= t90]
    return float(last["is_cold"].mean()) if len(last) >= min_events else np.nan

def cold_start_fraction_delta90(ev, px, vin, rest_gap_s=6*3600, min_side=3, min_base=6):
    if not _ok_px(px, vin): return np.nan
    e = _evin(ev, vin)
    if len(e) < 2: return np.nan
    gaps = np.diff(e["ts_start"].values).astype("timedelta64[s]").astype(float)
    e["is_cold"] = np.concatenate([[True], gaps >= rest_gap_s])
    win = pd.Timestamp(px.loc[vin, "win_start_l40"]); t90 = pd.Timestamp(px.loc[vin, "t_90_cutoff"])
    e = e[e["ts_start"] >= win]
    last = e[e["ts_start"] >= t90]; base = e[e["ts_start"] < t90]
    if len(last) < min_side or len(base) < min_base: return np.nan
    return float(last["is_cold"].mean() - base["is_cold"].mean())

def rest_vsi_p05_last90(wk, px, vin, min_weeks=3):
    if not _ok_px(px, vin): return np.nan
    w = wk[wk["vin_label"] == vin]; t90 = pd.Timestamp(px.loc[vin, "t_90_cutoff"])
    v = w.loc[w["week"] >= t90, "vsi_rest_p05"].astype(float).values; v = v[np.isfinite(v)]
    return float(v.mean()) if len(v) >= min_weeks else np.nan
