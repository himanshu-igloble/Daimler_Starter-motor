import sys
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
import _v3_lib as L
import _factors as FA

def main():
    order = L.vins_in_order(); px = L.build_px(); ev = L.load_events(); wk = L.load_weekly()
    mat = pd.read_csv(L.SMROOT / "V1.1" / "results" / "V1_1_SM_feature_matrix.csv").set_index("vin_label")

    dip_level   = {v: FA.dip_depth_last90_level(ev, px, v) for v in order}
    starts_day  = {v: FA.starts_per_active_day_last90(ev, wk, px, v) for v in order}
    cold_frac   = {v: FA.cold_start_fraction_last90(ev, px, v) for v in order}
    rest_p05    = {v: FA.rest_vsi_p05_last90(wk, px, v) for v in order}
    cold_delta  = {v: FA.cold_start_fraction_delta90(ev, px, v) for v in order}
    range_trend = {v: float(mat.loc[v, "vsi_range_trend"]) if v in mat.index else np.nan for v in order}

    # F1b standalone usage feature
    L.write_cache("cold_start_fraction_delta90", cold_delta, force_dead=True)

    # F3 interactions: z(A)*z(B) with global nan-aware z
    def interact(a, b):
        za, zb = L.zscore_across(a, order), L.zscore_across(b, order)
        return {v: za[v] * zb[v] for v in order}

    L.write_cache("dose_dip_x_starts",   interact(dip_level, starts_day),   force_dead=True)
    L.write_cache("weakbat_cold_load",   interact(rest_p05, cold_frac),     force_dead=True)
    L.write_cache("reg_instab_x_usage",  interact(range_trend, starts_day), force_dead=True)

if __name__ == "__main__":
    main()
