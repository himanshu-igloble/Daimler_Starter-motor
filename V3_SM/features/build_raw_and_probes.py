import sys
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
import _v3_lib as L
import _factors as FA
sys.path.insert(0, str(L.SMROOT / "src"))
import V1_SM_config as cfg      # SM_FAILED / SM_NONFAIL paths + sentinels

ANR_HI, ANR_NEG, WIN_S = 65535.0, -5000.0, 60

def anr_pre_crank_last90(ev, px, vin):
    if (vin not in px.index) or px.loc[vin].isna().any(): return np.nan
    failed = vin.endswith("_F_SM")
    base_vin = vin.replace("_F_SM", "").replace("_NF_SM", "")
    src = cfg.SM_FAILED if failed else cfg.SM_NONFAIL
    raw = pd.read_parquet(src, filters=[("VIN", "==", base_vin)], columns=["VIN", "timestamp", "ANR"])
    if raw.empty: return np.nan
    raw["timestamp"] = pd.to_datetime(raw["timestamp"]); raw = raw.sort_values("timestamp")
    raw.loc[(raw["ANR"] >= ANR_HI) | (raw["ANR"] <= ANR_NEG), "ANR"] = np.nan
    tarr = raw["timestamp"].values.astype("datetime64[ns]"); anr = raw["ANR"].values.astype(float)
    e = ev[ev["vin_label"] == vin]; t90 = pd.Timestamp(px.loc[vin, "t_90_cutoff"])
    starts = e.loc[e["ts_start"] >= t90, "ts_start"].values.astype("datetime64[ns]")
    means = []
    for s in starts:
        lo = np.searchsorted(tarr, s - np.timedelta64(WIN_S, "s")); hi = np.searchsorted(tarr, s)
        if hi > lo:
            w = anr[lo:hi]; w = w[np.isfinite(w)]
            if len(w): means.append(w.mean())
    return float(np.mean(means)) if len(means) >= 5 else np.nan

def ged3_rate_delta90(wk, px, vin):
    if (vin not in px.index) or px.loc[vin].isna().any(): return np.nan
    w = wk[wk["vin_label"] == vin].copy()
    w["rate"] = w["ged3_rows"] / w["n_rows"].replace(0, np.nan)
    t90 = pd.Timestamp(px.loc[vin, "t_90_cutoff"]); win = pd.Timestamp(px.loc[vin, "win_start_l40"])
    w = w[w["week"] >= win]; last = w.loc[w["week"] >= t90, "rate"]; base = w.loc[w["week"] < t90, "rate"]
    if last.notna().sum() < 3 or base.notna().sum() < 3: return np.nan
    return float(last.mean() - base.mean())

def night_start_fraction_delta90(ev, px, vin, night=(0,1,2,3,4), min_side=3, min_base=6):
    if (vin not in px.index) or px.loc[vin].isna().any(): return np.nan
    e = ev[ev["vin_label"] == vin].copy()
    e["hr"] = pd.to_datetime(e["ts_start"]).dt.hour; e["is_night"] = e["hr"].isin(night)
    win = pd.Timestamp(px.loc[vin, "win_start_l40"]); t90 = pd.Timestamp(px.loc[vin, "t_90_cutoff"])
    e = e[e["ts_start"] >= win]; last = e[e["ts_start"] >= t90]; base = e[e["ts_start"] < t90]
    if len(last) < min_side or len(base) < min_base: return np.nan
    return float(last["is_night"].mean() - base["is_night"].mean())

def main():
    order = L.vins_in_order(); px = L.build_px(); ev = L.load_events(); wk = L.load_weekly()
    mat = pd.read_csv(L.SMROOT / "V1.1" / "results" / "V1_1_SM_feature_matrix.csv").set_index("vin_label")

    anr = {v: anr_pre_crank_last90(ev, px, v) for v in order}
    dip_delta = {v: float(mat.loc[v, "dip_depth_last90_delta"]) if v in mat.index else np.nan for v in order}
    za, zb = L.zscore_across(dip_delta, order), L.zscore_across(anr, order)
    L.write_cache("sag_under_load", {v: za[v]*zb[v] for v in order}, force_dead=True)

    L.write_cache("ged3_rate_delta90", {v: ged3_rate_delta90(wk, px, v) for v in order}, force_dead=False)
    L.write_cache("night_start_fraction_delta90", {v: night_start_fraction_delta90(ev, px, v) for v in order}, force_dead=True)

if __name__ == "__main__":
    main()
