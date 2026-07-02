# STARTER MOTOR/V3.1/features/build_candidate_caches.py
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _v31_lib as L
import _factors31 as X
from _factors import dip_depth_last90_level          # V3 factor, reused verbatim (B2 ingredient)

ev, wk, px = L.load_events(), L.load_weekly(), L.build_px()
roll = L.load_state_weekly()
order = L.vins_in_order()

L.write_cache("hard_start_goodv_rate_delta90", {v: X.hard_start_goodv_rate_delta90(ev, wk, px, v) for v in order})
L.write_cache("dip_resid_trend_12w",           {v: X.dip_resid_trend_12w(ev, wk, px, v) for v in order})
L.write_cache("lowv_crank_share_delta90",      {v: X.lowv_crank_share_delta90(ev, px, v) for v in order})
L.write_cache("starts_per_engine_hour_delta90", {v: X.starts_per_engine_hour_delta90(ev, roll, px, v) for v in order})

dipz = L.zscore_across({v: dip_depth_last90_level(ev, px, v) for v in order}, order)
sehz = L.zscore_across({v: X.starts_per_engine_hour_last90(ev, roll, px, v) for v in order}, order)
L.write_cache("dose_dip_x_intensity", {v: (dipz[v] * sehz[v]) if np.isfinite(dipz[v]) and np.isfinite(sehz[v]) else np.nan for v in order})

L.write_cache("dropout_share_delta90", {v: X.dropout_share_delta90(roll, px, v) for v in order})
L.write_cache("dip_seasonal_contrast", {v: X.dip_seasonal_contrast(ev, px, v) for v in order})
print("done")
