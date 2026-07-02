"""SM operational-state engine (spec §5). Label-blind. Rows -> states -> episodes."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _state_lib as SL

P = SL.P
GAP_STATES = ("OFF_DWELL", "DROPOUT_RUNNING", "OFF_CONFIRMED", "UNKNOWN_GAP", "UNKNOWN_GAP_SHORT")


def classify_rows(df):
    rpm = df["RPM"].values.astype(float)
    csp = np.nan_to_num(df["CSP"].values.astype(float), nan=0.0)   # null CSP -> treated < 5 (low_conf)
    sma = np.nan_to_num(df["SMA"].values.astype(float), nan=0.0)
    off = np.isnan(rpm) | (rpm == 0)
    idle = (~off) & (rpm <= P["idle_rpm_max"]) & (csp < P["idle_csp_max"])
    drive = (~off) & ((rpm > P["idle_rpm_max"]) | (csp >= P["idle_csp_max"]))
    state = np.select([sma == 1, off, idle, drive], ["CRANK", "ENGINE_OFF", "IDLE", "DRIVE"], default="UNKNOWN")
    out = df.copy()
    out["state"] = state
    out["low_conf"] = df["CSP"].isna().values & np.isin(state, ["IDLE", "DRIVE"])
    return out


def _gap_class(dt_s, rpm, sma, ts, j0):
    """Classify a gap that ends before row index j0 (first row after the gap)."""
    if dt_s > P["dropout_min_s"]:
        rows = slice(j0, min(len(ts), j0 + P["dropout_resume_rows"]))
        if np.any(np.nan_to_num(rpm[rows], nan=0.0) > P["dropout_resume_rpm"]):
            return "DROPOUT_RUNNING"
        within = slice(j0, min(len(ts), j0 + 80))
        m = ts[within] - ts[j0] <= P["off_confirm_sma_within_s"]
        return "OFF_CONFIRMED" if np.any(sma[within][m] == 1) else "UNKNOWN_GAP"
    lo, hi = P["heartbeat_band_min"][0] * 60.0, P["heartbeat_band_min"][1] * 60.0
    if lo <= dt_s <= hi:
        return "HEARTBEAT"
    return "UNKNOWN_GAP_SHORT"


def build_episodes(df, heartbeat_confirmed):
    """Episode frame: state, ts_start, ts_end, dur_s, n_rows, cwr, recrank."""
    ts = df["timestamp"].values.astype("datetime64[us]").astype("int64") / 1e6
    rpm, sma = df["RPM"].values.astype(float), np.nan_to_num(df["SMA"].values.astype(float), nan=0.0)
    state = df["state"].values
    dt_prev = np.concatenate([[0.0], np.diff(ts)])
    new_seg = (state != np.roll(state, 1)) | (dt_prev > P["episode_merge_gap_s"])
    new_seg[0] = True
    seg = np.cumsum(new_seg)

    starts = np.flatnonzero(new_seg)                      # segment start rows (sorted)
    ends = np.append(starts[1:] - 1, len(state) - 1)      # segment end rows
    counts = np.diff(np.append(starts, len(state)))       # rows per segment
    tcol = df["timestamp"]                                # .iloc keeps pd.Timestamp type
    eps = [{"state": state[a], "ts_start": tcol.iloc[a], "ts_end": tcol.iloc[b],
            "dur_s": float(ts[b] - ts[a] + 5.0), "n_rows": int(c), "i0": int(a), "i1": int(b)}
           for a, b, c in zip(starts.tolist(), ends.tolist(), counts.tolist())]

    # interleave gap pseudo-episodes
    full = []
    for k, e in enumerate(eps):
        if k > 0:
            gap_s = ts[e["i0"]] - ts[eps[k - 1]["i1"]]
            if gap_s > P["episode_merge_gap_s"]:
                g = _gap_class(gap_s, rpm, sma, ts, e["i0"])
                full.append({"state": g, "ts_start": eps[k - 1]["ts_end"], "ts_end": e["ts_start"],
                             "dur_s": float(gap_s), "n_rows": 0, "i0": -1, "i1": -1})
        full.append(e)

    # merge HEARTBEAT chains (+ tiny intervening observed segments) into OFF_DWELL
    target = "OFF_DWELL" if heartbeat_confirmed else "UNKNOWN_GAP"
    merged, k = [], 0
    while k < len(full):
        e = full[k]
        if e["state"] == "HEARTBEAT":
            j, t0, t1 = k, e["ts_start"], e["ts_end"]
            while j + 1 < len(full):
                nxt = full[j + 1]
                if nxt["state"] == "HEARTBEAT":
                    t1 = nxt["ts_end"]; j += 1; continue
                if (nxt["state"] != "CRANK"
                        and nxt["dur_s"] <= P["heartbeat_chain_intervening_max_s"] and j + 2 < len(full)
                        and full[j + 2]["state"] == "HEARTBEAT"):
                    t1 = full[j + 2]["ts_end"]; j += 2; continue
                break
            merged.append({"state": target, "ts_start": t0, "ts_end": t1,
                           "dur_s": float((t1 - t0).total_seconds()), "n_rows": 0, "i0": -1, "i1": -1})
            k = j + 1
        else:
            merged.append(e); k += 1

    ep = pd.DataFrame(merged)
    # CWR + recrank flags on CRANK episodes
    cwr, rec, last_crank_end = [], [], None
    for _, e in ep.iterrows():
        if e["state"] != "CRANK":
            cwr.append(False); rec.append(False); continue
        i0 = int(e["i0"])
        c = False
        if i0 > 0 and (ts[i0] - ts[i0 - 1]) <= P["cwr_gap_max_s"]:
            c = bool(np.nan_to_num(rpm[i0 - 1], nan=0.0) > P["cwr_rpm"])
        r = last_crank_end is not None and (e["ts_start"] - last_crank_end).total_seconds() <= P["recrank_within_s"]
        last_crank_end = e["ts_end"]
        cwr.append(c); rec.append(bool(r))
    ep["cwr"], ep["recrank"] = cwr, rec
    return ep.drop(columns=["i0", "i1"])


def crank_table(ep):
    """One row per CRANK episode with backward-summed soak over OFF/OFF_DWELL episodes."""
    rows = []
    for i, e in ep.iterrows():
        if e["state"] != "CRANK":
            continue
        soak, j = 0.0, i - 1
        seen = False
        while j >= 0 and ep["state"].iloc[j] in ("ENGINE_OFF", "OFF_DWELL"):
            soak += ep["dur_s"].iloc[j]; seen = True; j -= 1
        rows.append({"ts_start": e["ts_start"], "soak_h": (soak / 3600.0) if seen else np.nan,
                     "cwr": bool(e["cwr"]), "recrank": bool(e["recrank"])})
    return pd.DataFrame(rows, columns=["ts_start", "soak_h", "cwr", "recrank"])


def derive_trips(rowdf, ep):
    """Trip = run segment between a CRANK/OFF boundary and the next OFF/OFF_DWELL/DROPOUT episode."""
    ts = rowdf["timestamp"].values.astype("datetime64[us]").astype("int64") / 1e6
    rpm = np.nan_to_num(rowdf["RPM"].values.astype(float), nan=0.0)
    csp = np.nan_to_num(rowdf["CSP"].values.astype(float), nan=0.0)
    dt_next = np.concatenate([np.diff(ts), [5.0]])
    dt_c = np.clip(dt_next, 0, P["engine_dt_cap_s"])
    run = rpm >= P["run_start_rpm"]
    tvals = rowdf["timestamp"].values                     # sorted datetime64; O(log n) first-row lookup below

    trips, cur = [], None
    boundary = ("ENGINE_OFF", "OFF_DWELL", "DROPOUT_RUNNING", "OFF_CONFIRMED", "UNKNOWN_GAP", "CRANK")
    for _, e in ep.iterrows():
        if pd.isna(e["ts_start"]):
            continue
        if cur is None and e["state"] in ("IDLE", "DRIVE"):
            i0 = int(np.searchsorted(tvals, np.datetime64(e["ts_start"]), side="left"))  # was O(n) == scan; RangeIndex -> pos==label
            if run[i0] and (i0 + 1 < len(run)) and run[i0 + 1]:
                cur = {"ts_start": e["ts_start"], "i0": i0}
        if cur is not None and e["state"] in boundary and e["ts_start"] > cur["ts_start"]:
            i1 = rowdf["timestamp"].searchsorted(e["ts_start"], side="left") - 1
            sl = slice(cur["i0"], max(cur["i0"], i1) + 1)
            dur_min = (ts[sl.stop - 1] - ts[sl.start]) / 60.0
            km = float(np.sum(csp[sl] * dt_c[sl]) / 3600.0)
            idle_share = float(np.mean(csp[sl] < P["idle_csp_max"])) if sl.stop > sl.start else np.nan
            trips.append({"ts_start": cur["ts_start"], "ts_end": rowdf["timestamp"].iloc[sl.stop - 1],
                          "dur_min": dur_min, "km": km, "idle_share": idle_share,
                          "vmax": float(np.max(csp[sl])), "vmean": float(np.mean(csp[sl]))})
            cur = None
    return pd.DataFrame(trips, columns=["ts_start", "ts_end", "dur_min", "km", "idle_share", "vmax", "vmean"])


def weekly_rollup(vin_label, rowdf, ep, trips, cranks):
    ts = rowdf["timestamp"]
    dt_next = np.concatenate([np.diff(ts.values.astype("datetime64[us]").astype("int64") / 1e6), [5.0]])
    dt_c = np.clip(dt_next, 0, P["engine_dt_cap_s"])
    base = pd.DataFrame({"week": SL.week_start(ts), "date": ts.dt.date,
                         "run_h": np.where(np.isin(rowdf["state"], ["IDLE", "DRIVE"]), dt_c, 0.0) / 3600.0,
                         "idle_h": np.where(rowdf["state"] == "IDLE", dt_c, 0.0) / 3600.0,
                         "obs_h": dt_c / 3600.0,
                         "km": np.nan_to_num(rowdf["CSP"].astype(float), nan=0.0) * dt_c / 3600.0})
    wk = base.groupby("week").agg(active_days=("date", "nunique"), engine_hours=("run_h", "sum"),
                                  idle_hours=("idle_h", "sum"), observed_hours=("obs_h", "sum"),
                                  km=("km", "sum")).reset_index()

    def _epw(states, col):
        e = ep[ep["state"].isin(states)].copy()
        if len(e) == 0:
            return pd.Series(dtype=float)
        e["week"] = SL.week_start(pd.to_datetime(e["ts_start"]))
        return e.groupby("week")["dur_s"].sum() / 3600.0

    for states, col in [(["OFF_DWELL"], "off_dwell_hours"), (["ENGINE_OFF"], "off_hours"),
                        (["DROPOUT_RUNNING"], "dropout_hours"),
                        (["UNKNOWN_GAP", "UNKNOWN_GAP_SHORT", "OFF_CONFIRMED"], "unknown_gap_hours")]:
        s = _epw(states, col)
        wk[col] = wk["week"].map(s).fillna(0.0)

    if len(cranks):
        c = cranks.copy(); c["week"] = SL.week_start(pd.to_datetime(c["ts_start"]))
        g = c.groupby("week")
        wk["n_cranks"] = wk["week"].map(g.size()).fillna(0).astype(int)
        wk["soak_median_h"] = wk["week"].map(g["soak_h"].median())
        wk["soak_p90_h"] = wk["week"].map(g["soak_h"].quantile(0.9))
        wk["n_overnight_starts"] = wk["week"].map(c[c["soak_h"] >= P["soak_overnight_h"]].groupby("week").size()).fillna(0).astype(int)
        wk["n_hot_restarts"] = wk["week"].map(c[c["soak_h"] * 60 < P["soak_hot_restart_min"]].groupby("week").size()).fillna(0).astype(int)
    else:
        wk[["n_cranks", "n_overnight_starts", "n_hot_restarts"]] = 0
        wk[["soak_median_h", "soak_p90_h"]] = np.nan
    if len(trips):
        t = trips.copy(); t["week"] = SL.week_start(pd.to_datetime(t["ts_start"]))
        g = t.groupby("week")
        wk["n_trips"] = wk["week"].map(g.size()).fillna(0).astype(int)
        wk["n_short_trips"] = wk["week"].map(t[t["dur_min"] < P["trip_short_min"]].groupby("week").size()).fillna(0).astype(int)
    else:
        wk[["n_trips", "n_short_trips"]] = 0
    wk.insert(0, "vin_label", vin_label)
    return wk
