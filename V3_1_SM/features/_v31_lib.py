# STARTER MOTOR/V3.1/features/_v31_lib.py
import sys, json, glob
from pathlib import Path
import numpy as np
import pandas as pd

SMROOT = Path(__file__).resolve().parents[2]
V31_OUT = SMROOT / "V3.1" / "features" / "out"
V31_OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(SMROOT / "V2.1" / "features"))
sys.path.insert(0, str(SMROOT / "V3" / "features"))
import _feature_lib as F                      # vins_in_order, build_px, load_events_nonartifact

GP = json.loads((SMROOT / "V3.1" / "params" / "V3_1_gate_params.json").read_text())
CP = json.loads((SMROOT / "V3.1" / "params" / "V3_1_candidates.json").read_text())
SMA_DEAD = set(GP["sma_dead"]); EXEMPT = set(GP["sma_dead_exempt"])

def vins_in_order(): return F.vins_in_order()
def build_px():      return F.build_px()
def load_events():   return F.load_events_nonartifact()

def load_weekly():
    files = sorted(glob.glob(str(SMROOT / "cache" / "weekly" / "V1_SM_weekly_*.parquet")))
    wk = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    wk["week"] = pd.to_datetime(wk["week"])
    return wk

def load_state_weekly():
    r = pd.read_parquet(SMROOT / "V3.1" / "state" / "out" / "V3_1_state_weekly_ALL.parquet")
    r["week"] = pd.to_datetime(r["week"])
    return r

def zscore_across(value_by_vin, order):
    vals = np.array([value_by_vin.get(v, np.nan) for v in order], dtype=float)
    mu, sd = np.nanmean(vals), np.nanstd(vals)
    if not np.isfinite(sd) or sd == 0:
        return {v: np.nan for v in order}
    return {v: (value_by_vin.get(v, np.nan) - mu) / sd for v in order}

def write_cache(name, value_by_vin):
    order = vins_in_order(); force = name not in EXEMPT; rows = []
    for v in order:
        val = np.nan if (force and v in SMA_DEAD) else value_by_vin.get(v, np.nan)
        rows.append({"vin_label": v, name: val})
    df = pd.DataFrame(rows); path = V31_OUT / f"{name}_cache.csv"; df.to_csv(path, index=False)
    print(f"wrote {path.name} ({df[name].notna().sum()}/34 non-null)")
    return path
