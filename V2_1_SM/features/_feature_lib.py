"""_feature_lib.py — shared windowing + candidate-cache helpers for V2.1 B-screens.
px (per-VIN L40 window) is built identically to V2_incremental_feature_eval.py so
candidate deltas are windowed exactly like the production features.
"""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR")
EVENTS = ROOT / "cache" / "events" / "V1_SM_crank_events.parquet"
WEEKLY_DIR = ROOT / "cache" / "weekly"
MATRIX = ROOT / "V1.1" / "results" / "V1_1_SM_feature_matrix.csv"
OUT = ROOT / "V2.1" / "features" / "out"

SMA_DEAD = ["VIN8_F_SM", "VIN9_F_SM", "VIN10_NF_SM", "VIN11_NF_SM",
            "VIN12_NF_SM", "VIN13_NF_SM", "VIN20_NF_SM"]


def vins_in_order():
    return pd.read_csv(MATRIX)["vin_label"].tolist()


def build_px():
    """Per-VIN proxy/window frame (verbatim from V2_incremental_feature_eval.py)."""
    wk_all = pd.concat(
        [pd.read_parquet(f) for f in sorted(WEEKLY_DIR.glob("V1_SM_weekly_*.parquet"))],
        ignore_index=True)
    wk_all["week"] = pd.to_datetime(wk_all["week"])
    rows = []
    for vin in vins_in_order():
        w = wk_all[wk_all["vin_label"] == vin]
        wmf = w[w["active_days"] >= 2]
        wm40 = wmf.sort_values("week").tail(40)
        t_end_approx = wmf["week"].max() + pd.Timedelta(days=6)
        rows.append({
            "vin_label": vin,
            "t_end_approx": t_end_approx,
            "t_90_cutoff": t_end_approx - pd.Timedelta(days=90),
            "win_start_l40": wm40["week"].iloc[0] if len(wm40) else pd.NaT,
        })
    return pd.DataFrame(rows).set_index("vin_label")


def load_events_nonartifact():
    ev = pd.read_parquet(EVENTS)
    ev = ev[ev["artifact"] == False].copy()
    ev["ts_start"] = pd.to_datetime(ev["ts_start"])
    return ev


def write_candidate_cache(name, value_by_vin):
    """value_by_vin: dict vin_label -> float (NaN allowed). Forces SMA-dead -> NaN."""
    vins = vins_in_order()
    vals = []
    for v in vins:
        x = value_by_vin.get(v, np.nan)
        vals.append(np.nan if v in SMA_DEAD else x)
    df = pd.DataFrame({"vin_label": vins, name: vals})
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / f"{name}_cache.csv", index=False)
    print(f"  wrote {OUT / (name + '_cache.csv')} "
          f"({int(np.isfinite(vals).sum())}/34 non-NaN, SMA-dead forced NaN)")
    return df
