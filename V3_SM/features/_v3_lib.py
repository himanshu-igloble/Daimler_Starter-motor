import sys, glob
from pathlib import Path
import numpy as np
import pandas as pd

SMROOT = Path(__file__).resolve().parents[2]          # .../STARTER MOTOR
V3_OUT = SMROOT / "V3" / "features" / "out"
V3_OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(SMROOT / "V2.1" / "features"))
import _feature_lib as F                              # side-effect-free readers

SMA_DEAD = ["VIN8_F_SM","VIN9_F_SM","VIN10_NF_SM","VIN11_NF_SM","VIN12_NF_SM","VIN13_NF_SM","VIN20_NF_SM"]

def vins_in_order():  return F.vins_in_order()
def build_px():       return F.build_px()
def load_events():    return F.load_events_nonartifact()

def load_weekly():
    files = sorted(glob.glob(str(SMROOT / "cache" / "weekly" / "V1_SM_weekly_*.parquet")))
    wk = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    wk["week"] = pd.to_datetime(wk["week"])
    return wk

def zscore_across(value_by_vin, order):
    vals = np.array([value_by_vin.get(v, np.nan) for v in order], dtype=float)
    mu, sd = np.nanmean(vals), np.nanstd(vals)
    if not np.isfinite(sd) or sd == 0:
        return {v: np.nan for v in order}
    return {v: (value_by_vin.get(v, np.nan) - mu) / sd for v in order}

def write_cache(name, value_by_vin, force_dead=True):
    order = vins_in_order(); rows = []
    for v in order:
        val = np.nan if (force_dead and v in SMA_DEAD) else value_by_vin.get(v, np.nan)
        rows.append({"vin_label": v, name: val})
    df = pd.DataFrame(rows); path = V3_OUT / f"{name}_cache.csv"; df.to_csv(path, index=False)
    print(f"wrote {path.name} ({len(df)} rows, {df[name].notna().sum()} non-null)"); return path
