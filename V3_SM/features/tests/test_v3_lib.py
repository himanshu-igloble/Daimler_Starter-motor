import sys, math
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import _v3_lib as L

def test_zscore_nan_aware():
    d = {"a": 1.0, "b": 3.0, "c": np.nan, "d": 5.0}
    z = L.zscore_across({k: d[k] for k in ["a","b","c","d"]}, ["a","b","c","d"])
    vals = np.array([z["a"], z["b"], z["d"]])
    assert abs(np.nanmean(vals)) < 1e-9, "z-mean not ~0"
    assert math.isnan(z["c"]), "NaN factor must stay NaN"
    print("PASS zscore_across")

def test_readers_present():
    assert L.vins_in_order() and len(L.vins_in_order()) == 34
    wk = L.load_weekly()
    assert {"vin_label","week","active_days","vsi_rest_p05","ged3_rows"} <= set(wk.columns)
    print("PASS readers")

if __name__ == "__main__":
    test_zscore_nan_aware(); test_readers_present()
