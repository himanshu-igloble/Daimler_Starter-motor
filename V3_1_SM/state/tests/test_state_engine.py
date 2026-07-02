import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sm_state_engine as SE


def mkdf(rows):
    t0 = pd.Timestamp("2025-01-06 06:00:00")
    ts, rpm, csp, sma = [], [], [], []
    t = t0
    for dt_s, r, c, s in rows:
        t = t + pd.Timedelta(seconds=dt_s)
        ts.append(t); rpm.append(r); csp.append(c); sma.append(s)
    return pd.DataFrame({"timestamp": ts, "RPM": rpm, "CSP": csp, "SMA": sma})


def test_row_states_priority():
    df = mkdf([(0, 800, 20, 1),      # SMA wins -> CRANK even with RPM/CSP high
               (5, 0, 0, 0),         # ENGINE_OFF
               (5, np.nan, 0, 0),    # ENGINE_OFF (null RPM)
               (5, 600, 0, 0),       # IDLE
               (5, 600, 10, 0),      # DRIVE (CSP >= 5)
               (5, 900, 0, 0)])      # DRIVE (RPM > 700)
    st = SE.classify_rows(df)["state"].tolist()
    assert st == ["CRANK", "ENGINE_OFF", "ENGINE_OFF", "IDLE", "DRIVE", "DRIVE"]


def test_episodes_merge_and_heartbeat_chain():
    rows = [(0, 0, 0, 0), (5, 0, 0, 0)]            # OFF, 2 rows
    rows += [(900, 0, 0, 0)]                       # 15-min hb gap -> wake row
    rows += [(900, 0, 0, 0)]                       # another hb gap -> wake row
    rows += [(910, np.nan, 0, 1)]                  # hb gap then CRANK
    rows += [(5, 650, 0, 0), (5, 660, 0, 0)]       # IDLE run (trip start material)
    df = mkdf(rows)
    ep = SE.build_episodes(SE.classify_rows(df), heartbeat_confirmed=True)
    states = ep["state"].tolist()
    assert "OFF_DWELL" in states                    # chain of hb gaps merged
    ix = states.index("OFF_DWELL")
    assert states[ix + 1] == "CRANK" and ep["dur_s"].iloc[ix] >= 2700 - 10
    assert states[-1] == "IDLE" and ep["n_rows"].iloc[-1] == 2


def test_dropout_running_classification():
    rows = [(0, 800, 40, 0), (5, 810, 42, 0)]      # DRIVE
    rows += [(7200, 820, 45, 0), (5, 815, 44, 0)]  # 2h gap resuming at speed -> DROPOUT_RUNNING
    df = mkdf(rows)
    ep = SE.build_episodes(SE.classify_rows(df), heartbeat_confirmed=True)
    assert "DROPOUT_RUNNING" in ep["state"].tolist()


def test_cwr_and_recrank_flags():
    rows = [(0, 800, 30, 0), (5, 800, 30, 1)]      # crank while running -> cwr
    rows += [(5, 0, 0, 0), (30, 100, 0, 1)]        # re-crank 35s after previous crank end
    df = mkdf(rows)
    ep = SE.build_episodes(SE.classify_rows(df), heartbeat_confirmed=True)
    cr = ep[ep["state"] == "CRANK"].reset_index(drop=True)
    assert bool(cr["cwr"].iloc[0]) is True
    assert bool(cr["recrank"].iloc[1]) is True


def test_chain_preserves_intervening_crank():
    rows = [(0, 0, 0, 0), (5, 0, 0, 0)]        # OFF
    rows += [(900, np.nan, 0, 1)]              # hb gap -> CRANK wake row (failed crank while parked)
    rows += [(900, 0, 0, 0)]                   # hb gap -> OFF wake row
    rows += [(5, 0, 0, 0)]                     # OFF
    ep = SE.build_episodes(SE.classify_rows(mkdf(rows)), heartbeat_confirmed=True)
    states = ep["state"].tolist()
    assert "CRANK" in states                   # the crank must survive chain merging
    ci = states.index("CRANK")
    assert states[ci - 1] == "OFF_DWELL"       # chain before the crank still becomes OFF_DWELL


def test_gap_class_boundaries():
    def gap_states(gap_s, confirmed=True):
        rows = [(0, 0, 0, 0), (gap_s, 0, 0, 0)]
        ep = SE.build_episodes(SE.classify_rows(mkdf(rows)), heartbeat_confirmed=confirmed)
        return ep["state"].tolist()
    assert "UNKNOWN_GAP_SHORT" in gap_states(839)
    assert "OFF_DWELL" in gap_states(840)              # inclusive lower bound, single-gap chain
    assert "OFF_DWELL" in gap_states(1080)             # inclusive upper bound
    assert "UNKNOWN_GAP_SHORT" in gap_states(1081)
    assert "UNKNOWN_GAP" in gap_states(900, confirmed=False)   # refuted heartbeat -> UNKNOWN_GAP


def test_trips_soak_and_engine_hours():
    rows = [(0, 0, 0, 0)] * 2                                  # OFF 2 rows
    rows += [(910, np.nan, 0, 1)]                              # hb gap then CRANK
    rows += [(5, 600, 0, 0)] + [(5, 620, 0, 0)]                # IDLE x2 (run start: >=550 x2)
    rows += [(5, 900, 30, 0)] * 10                             # DRIVE x10
    rows += [(5, 0, 0, 0)] * 2                                 # OFF -> trip end
    df = mkdf(rows)
    rowdf = SE.classify_rows(df)
    ep = SE.build_episodes(rowdf, heartbeat_confirmed=True)
    cranks = SE.crank_table(ep)
    assert len(cranks) == 1 and cranks["soak_h"].iloc[0] > 0.2          # OFF(+hb) soak measured
    trips = SE.derive_trips(rowdf, ep)
    assert len(trips) == 1
    assert 0.3 < trips["km"].iloc[0] < 0.6                              # 10 rows x 30 km/h x 5 s = 0.4167 km
    wk = SE.weekly_rollup("SYN_VIN", rowdf, ep, trips, cranks)
    assert abs(wk["engine_hours"].sum() - (12 * 5) / 3600.0) < 0.01     # 12 run rows x 5s
    assert wk["n_cranks"].sum() == 1 and wk["n_trips"].sum() == 1


def test_nat_timestamps_do_not_crash_trips():
    df = mkdf([(0, 800, 30, 0), (5, 810, 30, 0), (5, 0, 0, 0)])
    df.loc[len(df)] = {"timestamp": pd.NaT, "RPM": 700.0, "CSP": 10.0, "SMA": 0.0}
    rowdf = SE.classify_rows(df)
    ep = SE.build_episodes(rowdf.dropna(subset=["timestamp"]).reset_index(drop=True), heartbeat_confirmed=False)
    trips = SE.derive_trips(rowdf.dropna(subset=["timestamp"]).reset_index(drop=True), ep)
    assert isinstance(trips, pd.DataFrame)          # no crash is the contract


def test_duplicate_timestamps_same_instant_state():
    rows = [(0, 800, 30, 0), (0, 800, 30, 0), (5, 820, 31, 0), (5, 0, 0, 0)]   # dup instant
    ep = SE.build_episodes(SE.classify_rows(mkdf(rows)), heartbeat_confirmed=False)
    d = ep[ep["state"] == "DRIVE"]
    assert len(d) == 1 and int(d["n_rows"].iloc[0]) == 3                        # dups merge into one episode
