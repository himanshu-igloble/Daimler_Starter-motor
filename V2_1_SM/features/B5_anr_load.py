"""B5_anr_load.py — candidate feature: ANR (engine-torque) load-context delta.
anr_pos_mean (weekly cache) last-90d vs L40 baseline. Weakest physics link to
starter failure; screened for completeness only.

Run: py -3 "STARTER MOTOR/V2.1/features/B5_anr_load.py"
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR\V2.1")
sys.path.insert(0, str(HERE / "features"))
import _feature_lib as F  # noqa: E402


def main():
    px = F.build_px()
    wk = pd.concat([pd.read_parquet(f) for f in sorted(F.WEEKLY_DIR.glob("V1_SM_weekly_*.parquet"))],
                   ignore_index=True)
    wk["week"] = pd.to_datetime(wk["week"])
    out = {}
    for vin in F.vins_in_order():
        if vin in F.SMA_DEAD:
            out[vin] = np.nan
            continue
        w = wk[(wk["vin_label"] == vin) & (wk["active_days"] >= 2)].sort_values("week")
        if len(w) < 8 or vin not in px.index or px.loc[vin].isna().any():
            out[vin] = np.nan
            continue
        win_start, t90 = px.loc[vin, "win_start_l40"], px.loc[vin, "t_90_cutoff"]
        w = w[w["week"] >= win_start]
        a = w["anr_pos_mean"].astype(float)
        last90 = a[w["week"] >= t90].dropna()
        base = a[w["week"] < t90].dropna()
        out[vin] = (last90.mean() - base.mean()) if (len(last90) >= 2 and len(base) >= 2) else np.nan
    F.write_candidate_cache("anr_pos_mean_delta90", out)


if __name__ == "__main__":
    main()
