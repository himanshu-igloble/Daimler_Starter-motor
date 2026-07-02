"""B2_intercrank_cv.py — candidate feature: change in coefficient-of-variation of
inter-crank intervals, last-90d vs L40 baseline. Timing-burstiness of cranks
(solenoid intermittency proxy). Writes a candidate cache for the V2.1 gate.

Run: py -3 "STARTER MOTOR/V2.1/features/B2_intercrank_cv.py"
"""
import sys
from pathlib import Path
import numpy as np

HERE = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR\V2.1")
sys.path.insert(0, str(HERE / "features"))
import _feature_lib as F  # noqa: E402


def cv(intervals_s):
    x = np.asarray(intervals_s, dtype=float)
    x = x[np.isfinite(x) & (x > 0)]
    if len(x) < 3:
        return np.nan
    m = x.mean()
    return float(x.std() / m) if m > 0 else np.nan


def main():
    px = F.build_px()
    ev = F.load_events_nonartifact()
    out = {}
    for vin in F.vins_in_order():
        if vin in F.SMA_DEAD:
            out[vin] = np.nan
            continue
        e = ev[ev["vin_label"] == vin].sort_values("ts_start")
        if len(e) < 8 or vin not in px.index or px.loc[vin].isna().any():
            out[vin] = np.nan
            continue
        win_start = px.loc[vin, "win_start_l40"]
        t90 = px.loc[vin, "t_90_cutoff"]
        e = e[e["ts_start"] >= win_start]
        ts = e["ts_start"].values
        if len(ts) < 6:
            out[vin] = np.nan
            continue
        intervals = np.diff(ts).astype("timedelta64[s]").astype(float)
        starts = ts[1:]  # interval attributed to its end-event start
        last90 = intervals[starts >= np.datetime64(t90)]
        base = intervals[starts < np.datetime64(t90)]
        cv90, cvb = cv(last90), cv(base)
        out[vin] = (cv90 - cvb) if (np.isfinite(cv90) and np.isfinite(cvb)) else np.nan
    F.write_candidate_cache("intercrank_cv_delta90", out)


if __name__ == "__main__":
    main()
