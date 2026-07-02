import sys
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(HERE))
import _factors as FA

def _synth():
    base = pd.Timestamp("2025-01-01")
    ts = [base + pd.Timedelta(days=d) for d in [0, 2, 4, 6, 8, 10,   22, 22.3, 25, 40]]
    ev = pd.DataFrame({"vin_label": "VINX", "ts_start": ts,
                       "dip_depth": [1.0]*6 + [2.0,2.0,2.0,2.0]})
    px = pd.DataFrame({"t_90_cutoff": [pd.Timestamp("2025-01-21")],
                       "win_start_l40": [pd.Timestamp("2024-06-01")],
                       "t_end_approx": [pd.Timestamp("2025-03-01")]}, index=["VINX"])
    return ev, px

def test_dip_level_last90():
    ev, px = _synth()
    v = FA.dip_depth_last90_level(ev, px, "VINX", min_events=1)
    assert abs(v - 2.0) < 1e-9, v
    print("PASS dip_depth_last90_level")

def test_cold_fraction_delta():
    ev, px = _synth()
    v = FA.cold_start_fraction_delta90(ev, px, "VINX", rest_gap_s=6*3600, min_side=1, min_base=1)
    assert v is not None and np.isfinite(v), v
    print(f"PASS cold_start_fraction_delta90 = {v:.3f}")

if __name__ == "__main__":
    test_dip_level_last90(); test_cold_fraction_delta()
