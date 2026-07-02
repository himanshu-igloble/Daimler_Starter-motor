# STARTER MOTOR/V3.1/state/P0_probes.py
"""Phase-0 probes P0-1/2/3/5. Label-blind. Writes JSONs to state/out."""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _state_lib as SL

P = SL.P
OUT = SL.STATE_OUT
HB_LO, HB_HI = P["heartbeat_band_min"][0] * 60.0, P["heartbeat_band_min"][1] * 60.0


def probe_vin(vin):
    df = SL.load_vin(vin)
    ts = df["timestamp"].values.astype("datetime64[us]").astype("int64") / 1e6  # seconds
    rpm, csp, sma = df["RPM"].values, df["CSP"].values, df["SMA"].values
    dt = np.diff(ts)                                # gap AFTER row i (len n-1)
    res = {"vin": vin, "n_rows": int(len(df))}

    # --- P0-2 duplicates
    res["n_dup_ts"] = int((dt == 0).sum())

    # --- gap census + histogram material
    res["gaps_gt15m"] = int((dt > 900).sum()); res["gaps_gt1h"] = int((dt > 3600).sum())
    res["gaps_gt8h"] = int((dt > 28800).sum())
    res["gaps_hb_band"] = int(((dt >= HB_LO) & (dt <= HB_HI)).sum())
    hist, edges = np.histogram(dt[(dt > 60) & (dt < 7200)] / 60.0, bins=np.arange(1, 121, 1))
    res["gap_hist_min"] = hist.tolist()

    # --- P0-1 heartbeat chains
    is_hb = (dt >= HB_LO) & (dt <= HB_HI)
    idx = np.where(is_hb)[0]
    chains, cur = [], None
    for i in idx:
        if cur is not None and i > cur[-1]:
            span = ts[i] - ts[cur[-1] + 1]          # observed time between prior hb-gap end and this gap start
            if span <= P["heartbeat_chain_intervening_max_s"]:
                cur.append(i); continue
        if cur is not None:
            chains.append(cur)
        cur = [i]
    if cur is not None:
        chains.append(cur)
    n_eval = min(len(chains), P["p01_max_chains_per_vin"])
    start_ok = end_ok = 0
    w = P["p01_boundary_window_s"]
    for ch in chains[:n_eval]:
        i0, i1 = ch[0], ch[-1]                      # gap i0 follows row i0; chain ends before row i1+1
        pre = slice(max(0, i0 - 3), i0 + 1)         # last rows before chain
        pre_off = np.any(np.isnan(rpm[pre]) | (rpm[pre] == 0))
        start_ok += bool(pre_off)
        post = slice(i1 + 1, min(len(ts), i1 + 1 + 25))   # ~2 min of 5s rows
        post_in_w = post.start + np.where(ts[post] - ts[i1 + 1] <= w)[0]
        crank = np.any(sma[post_in_w] == 1) if len(post_in_w) else False
        rise = np.any(rpm[post_in_w] >= P["run_start_rpm"]) if len(post_in_w) else False
        end_ok += bool(crank or rise)
    res["hb_chains"] = len(chains); res["hb_eval"] = n_eval
    res["hb_start_ok"] = int(start_ok); res["hb_end_ok"] = int(end_ok)

    # --- P0-3 dropout taxonomy (> 1 h gaps)
    tax = {"DROPOUT_RUNNING": 0, "OFF_CONFIRMED": 0, "UNKNOWN_GAP": 0}
    for i in np.where(dt > P["dropout_min_s"])[0]:
        j0 = i + 1
        rows = slice(j0, min(len(ts), j0 + P["dropout_resume_rows"]))
        if np.any(rpm[rows] > P["dropout_resume_rpm"]):
            tax["DROPOUT_RUNNING"] += 1
        else:
            within = slice(j0, min(len(ts), j0 + 80))
            m = ts[within] - ts[j0] <= P["off_confirm_sma_within_s"]
            tax["OFF_CONFIRMED" if np.any(sma[within][m] == 1) else "UNKNOWN_GAP"] += 1
    res["dropout_taxonomy"] = tax

    # --- P0-5 SMA observability: run-starts without a preceding crank
    run = np.nan_to_num(rpm, nan=0.0) >= P["run_start_rpm"]
    run2 = run[:-1] & run[1:]                       # sustained 2 rows, aligned to row i
    prev_off = np.concatenate([[True], ~run[:-1]])[:-1]
    starts = np.where(run2 & prev_off)[0]
    miss = 0
    for i in starts:
        lo = ts[i] - 120.0
        back = slice(max(0, i - 40), i + 1)
        m = ts[back] >= lo
        if not np.any(sma[back][m] == 1):
            miss += 1
    res["run_starts"] = int(len(starts)); res["run_starts_no_sma"] = int(miss)
    return res


def main(vins=None):
    vins = vins or SL.all_vin_labels()
    rows = [probe_vin(v) for v in vins]
    hist = np.sum([r.pop("gap_hist_min") for r in rows], axis=0)
    pd.DataFrame({"gap_min_bin_lo": np.arange(1, 120), "count": hist}).to_csv(OUT / "P0_gap_hist.csv", index=False)
    ev = sum(r["hb_eval"] for r in rows); s = sum(r["hb_start_ok"] for r in rows); e = sum(r["hb_end_ok"] for r in rows)
    verdict = {"eval_chains": ev, "start_ok_frac": round(s / ev, 4) if ev else None,
               "end_ok_frac": round(e / ev, 4) if ev else None}
    verdict["confirmed"] = bool(ev and verdict["start_ok_frac"] >= P["p01_confirm_frac"]
                                and verdict["end_ok_frac"] >= P["p01_confirm_frac"])
    (OUT / "P0_heartbeat.json").write_text(json.dumps({"verdict": verdict, "per_vin": rows}, indent=2))
    (OUT / "P0_gap_census.json").write_text(json.dumps(
        [{k: r[k] for k in ("vin", "gaps_gt15m", "gaps_gt1h", "gaps_gt8h", "gaps_hb_band")} for r in rows], indent=2))
    (OUT / "P0_duplicates.json").write_text(json.dumps({r["vin"]: r["n_dup_ts"] for r in rows}, indent=2))
    (OUT / "P0_dropout_taxonomy.json").write_text(json.dumps({r["vin"]: r["dropout_taxonomy"] for r in rows}, indent=2))
    (OUT / "P0_sma_observability.json").write_text(json.dumps(
        {r["vin"]: {"run_starts": r["run_starts"], "no_sma": r["run_starts_no_sma"],
                    "undercount_frac": round(r["run_starts_no_sma"] / r["run_starts"], 4) if r["run_starts"] else None}
         for r in rows}, indent=2))
    print(json.dumps(verdict, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:] or None)
