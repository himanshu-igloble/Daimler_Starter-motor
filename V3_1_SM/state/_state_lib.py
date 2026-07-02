"""Label-blind raw loaders for the V3.1 state engine. READ-ONLY on all inputs."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import polars as pl

SMROOT = Path(__file__).resolve().parents[2]                     # .../STARTER MOTOR
V31 = SMROOT / "V3.1"
STATE_OUT = V31 / "state" / "out"
STATE_OUT.mkdir(parents=True, exist_ok=True)                     # robustness for fresh checkouts
FAILED_PQ = SMROOT.parent / "Data" / "processed" / "starter_motor_complete" / "2026-03-06-12-38-23-starter_motor_failed.parquet"
NONFAILED_PQ = SMROOT.parent / "Data" / "processed" / "starter_motor_complete" / "2026-03-06-12-39-14-starter_motor_non_failed.parquet"
MATRIX = SMROOT / "V1.1" / "results" / "V1_1_SM_feature_matrix.csv"
P = json.loads((V31 / "params" / "V3_1_state_params.json").read_text())


def all_vin_labels():
    return pd.read_csv(MATRIX)["vin_label"].tolist()


def vin_source(vin_label):
    """'VIN3_F_SM' -> (FAILED_PQ, 'VIN3'); 'VIN17_NF_SM' -> (NONFAILED_PQ, 'VIN17')."""
    raw = vin_label.split("_")[0]
    return (FAILED_PQ, raw) if "_F_" in vin_label else (NONFAILED_PQ, raw)


def clean_signals(df):
    """Sentinel masking + VSI scale rule (harmless no-ops on this data, kept as frozen contract)."""
    for c in ("RPM", "CSP"):
        if c in df:
            df.loc[df[c] >= P["rpm_sentinel"], c] = np.nan
    if "VSI" in df:
        v = df["VSI"].astype(float)
        v[(v <= 0.0) | (v >= 255.0)] = np.nan
        big = v > P["vsi_scale_above"]
        v[big] = v[big] * P["vsi_scale_factor"]
        df["VSI"] = v
    return df


def load_vin(vin_label, columns=("timestamp", "RPM", "CSP", "SMA")):
    """Sorted, cleaned per-VIN frame via lazy polars scan.

    null-timestamp rows are dropped (no usable time coordinate).
    """
    path, raw = vin_source(vin_label)
    lf = pl.scan_parquet(str(path)).filter((pl.col("VIN") == raw) & pl.col("timestamp").is_not_null()).select(list(columns))
    df = lf.collect().to_pandas().sort_values("timestamp", kind="stable").reset_index(drop=True)
    return clean_signals(df)


def week_start(ts):
    """Monday-floor a datetime Series (matches V1 weekly cache dt.truncate('1w'))."""
    d = ts.dt.floor("D")
    return d - pd.to_timedelta(ts.dt.weekday, unit="D")
