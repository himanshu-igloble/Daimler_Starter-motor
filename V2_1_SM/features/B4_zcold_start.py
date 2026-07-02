"""B4_zcold_start.py — candidate feature: per-VIN z-scored cold-start (>=8h rest)
dip-depth delta, last-90d vs L40 baseline. Distinct from held P3 cold_dip (6h,raw).

Run: py -3 "STARTER MOTOR/V2.1/features/B4_zcold_start.py"
"""
import sys
from pathlib import Path
import numpy as np

HERE = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR\V2.1")
sys.path.insert(0, str(HERE / "features"))
import _feature_lib as F  # noqa: E402

REST_GAP_S = 8 * 3600  # >= 8 hours


def main():
    px = F.build_px()
    ev = F.load_events_nonartifact()
    out = {}
    for vin in F.vins_in_order():
        if vin in F.SMA_DEAD:
            out[vin] = np.nan
            continue
        e = ev[ev["vin_label"] == vin].sort_values("ts_start").reset_index(drop=True)
        if len(e) < 8 or vin not in px.index or px.loc[vin].isna().any():
            out[vin] = np.nan
            continue
        win_start = px.loc[vin, "win_start_l40"]
        t90 = px.loc[vin, "t_90_cutoff"]
        ts = e["ts_start"].values
        gaps = np.diff(ts).astype("timedelta64[s]").astype(float)
        is_cold = np.concatenate([[True], gaps >= REST_GAP_S])
        cold = e[is_cold].copy()
        cold = cold[cold["ts_start"] >= win_start]
        dip = cold["dip_depth"].astype(float).values
        cts = cold["ts_start"].values
        m = np.isfinite(dip)
        dip, cts = dip[m], cts[m]
        if len(dip) < 6:
            out[vin] = np.nan
            continue
        mu, sd = dip.mean(), dip.std()
        if sd == 0:
            out[vin] = np.nan
            continue
        z = (dip - mu) / sd
        last90 = z[cts >= np.datetime64(t90)]
        base = z[cts < np.datetime64(t90)]
        out[vin] = (last90.mean() - base.mean()) if (len(last90) >= 3 and len(base) >= 3) else np.nan
    F.write_candidate_cache("z_cold_dip_delta90", out)


if __name__ == "__main__":
    main()
