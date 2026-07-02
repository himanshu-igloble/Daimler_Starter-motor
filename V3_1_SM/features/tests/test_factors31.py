# STARTER MOTOR/V3.1/features/tests/test_factors31.py
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _factors31 as X


def _px(vin="V", win="2025-01-06", t90="2025-06-02"):
    return pd.DataFrame({"vin_label": [vin], "t_end_approx": [pd.Timestamp("2025-08-31")],
                         "t_90_cutoff": [pd.Timestamp(t90)], "win_start_l40": [pd.Timestamp(win)]
                         }).set_index("vin_label")


def _ev(vin="V"):
    """20 baseline events (10 good-V fails) + 10 last-90 events (5 good-V fails)."""
    rows = []
    for i in range(20):
        rows.append({"vin_label": vin, "ts_start": pd.Timestamp("2025-02-03") + pd.Timedelta(days=i * 5),
                     "success": i % 2 == 0, "baseline_vsi": 28.0, "dip_depth": 5.0 + 0.0 * i})
    for i in range(10):
        rows.append({"vin_label": vin, "ts_start": pd.Timestamp("2025-06-09") + pd.Timedelta(days=i * 7),
                     "success": i % 2 == 0, "baseline_vsi": 28.0, "dip_depth": 5.0})
    return pd.DataFrame(rows)


def _wk(vin="V"):
    weeks = pd.date_range("2025-01-06", "2025-08-25", freq="7D")
    return pd.DataFrame({"vin_label": vin, "week": weeks, "active_days": 5,
                         "vsi_rest_median": 28.0})


def test_a1_hard_start_goodv_rate_delta90():
    v = X.hard_start_goodv_rate_delta90(_ev(), _wk(), _px(), "V")
    # base: 10 fails/(21 wks*5 d) = 0.0952...; last: 5 fails/(13 wks*5 d) = 0.0769...  -> negative delta
    assert np.isfinite(v) and v < 0


def test_a3_lowv_share_delta90_null_when_no_lowv():
    v = X.lowv_crank_share_delta90(_ev(), _px(), "V")
    assert abs(v) < 1e-12          # no event below 26.0 V on either side -> delta 0


def test_a2_dip_resid_trend_needs_min_events():
    ev = _ev().iloc[:10]           # only 10 baseline events < 30 -> NaN
    v = X.dip_resid_trend_12w(ev, _wk(), _px(), "V")
    assert np.isnan(v)


def _roll(vin="V"):
    weeks = pd.date_range("2025-01-06", "2025-08-25", freq="7D")
    n = len(weeks)
    return pd.DataFrame({"vin_label": vin, "week": weeks, "active_days": 5,
                         "engine_hours": 40.0, "observed_hours": 60.0,
                         "dropout_hours": [0.0] * (n - 6) + [6.0] * 6})


def test_b1_starts_per_engine_hour_delta90():
    v = X.starts_per_engine_hour_delta90(_ev(), _roll(), _px(), "V")
    # base 20 cranks / (21w*40h)=0.0238; last 10 / (13w*40h)=0.0192 -> negative
    assert np.isfinite(v) and v < 0


def test_c1_dropout_share_delta90_positive_when_tail_heavy():
    v = X.dropout_share_delta90(_roll(), _px(), "V")
    assert np.isfinite(v) and v > 0


def test_c2_seasonal_needs_both_windows():
    v = X.dip_seasonal_contrast(_ev(), _px(), "V")   # _ev has no Dec-Feb events with >=15 -> NaN
    assert np.isnan(v)


def test_a2_finite_on_dense_events():
    """Reindex alignment insurance: events landing in the masked weeks must yield a finite slope."""
    rows = []
    for i in range(40):                                   # 40 baseline events, varied baseline_vsi
        rows.append({"vin_label": "V", "ts_start": pd.Timestamp("2025-01-08") + pd.Timedelta(days=i * 3),
                     "success": True, "baseline_vsi": 27.0 + (i % 5) * 0.4, "dip_depth": 5.0 + (i % 3) * 0.2})
    for wk_i in range(12):                                # >=1 event in each of the last 12 weeks
        for j in range(2):
            rows.append({"vin_label": "V", "ts_start": pd.Timestamp("2025-06-09") + pd.Timedelta(days=wk_i * 7 + j),
                         "success": True, "baseline_vsi": 27.5 + j * 0.5, "dip_depth": 5.5 + 0.1 * wk_i})
    ev = pd.DataFrame(rows)
    v = X.dip_resid_trend_12w(ev, _wk(), _px(), "V")
    assert np.isfinite(v) and v > 0                       # injected +0.1/wk residual trend
