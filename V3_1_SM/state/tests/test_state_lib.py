import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _state_lib as SL


def test_vin_routing():
    p, raw = SL.vin_source("VIN3_F_SM")
    assert p == SL.FAILED_PQ and raw == "VIN3"
    p, raw = SL.vin_source("VIN17_NF_SM")
    assert p == SL.NONFAILED_PQ and raw == "VIN17"


def test_clean_signals_sentinels_and_scale():
    df = pd.DataFrame({
        "RPM": [650.0, 65535.0, np.nan, 0.0],
        "CSP": [10.0, 65535.0, 3.0, 0.0],
        "VSI": [28.0, 255.0, 140.0, 0.0],   # 140 -> 28.0 via x0.2 ; 255/0 -> NaN
        "SMA": [0.0, 1.0, 0.0, 0.0],
    })
    out = SL.clean_signals(df.copy())
    assert np.isnan(out["RPM"].iloc[1]) and out["RPM"].iloc[3] == 0.0
    assert np.isnan(out["CSP"].iloc[1])
    assert np.isnan(out["VSI"].iloc[1]) and np.isnan(out["VSI"].iloc[3])
    assert abs(out["VSI"].iloc[2] - 28.0) < 1e-9


def test_week_start_is_monday():
    ts = pd.Series(pd.to_datetime(["2025-01-01 07:00:00", "2025-01-06 00:00:01"]))  # Wed, Mon
    w = SL.week_start(ts)
    assert str(w.iloc[0].date()) == "2024-12-30" and str(w.iloc[1].date()) == "2025-01-06"
    assert all(w.dt.weekday == 0)


def test_all_vin_labels_shape():
    labels = SL.all_vin_labels()
    assert len(labels) == 34 and labels.count("VIN1_F_SM") == 1 and labels.count("VIN1_NF_SM") == 1
