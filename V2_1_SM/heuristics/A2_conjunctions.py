"""A2_conjunctions.py — conjunction pagers: H2&A2, H2&H5, A1&H2.
A conjunction fires at week i if BOTH channels fired within [i-3, i] (4-wk align).
Channel weekly fire-states recomputed from walking_scores + alert CSVs + A1 output.
Params frozen in params/A2_conjunction_params.json.

Run: py -3 "STARTER MOTOR/V2.1/heuristics/A2_conjunctions.py"
"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR\V2.1")
sys.path.insert(0, str(HERE / "heuristics"))
import _heuristic_lib as L  # noqa: E402

P = json.loads((HERE / "params" / "A2_conjunction_params.json").read_text())
W = P["alignment_window_weeks"]
OUT = HERE / "heuristics" / "out"


def h2_fire_rows(seq):
    """>=3 consecutive RED cuts (verbatim H2 rule)."""
    rows, count = [], 0
    for i, t in enumerate(seq["tier"].values):
        count = count + 1 if t == "RED" else 0
        if count >= 3:
            rows.append(i)
    return rows


def h5_fire_rows(seq, p85_by_k):
    """prob >= 85th fleet pctile in >=4 of trailing 6 weeks (verbatim H5 rule)."""
    rows = []
    probs, ks = seq["prob"].values, seq["k_weeks"].values
    for i in range(5, len(seq)):
        cnt = 0
        for p, k in zip(probs[i - 5:i + 1], ks[i - 5:i + 1]):
            p85 = p85_by_k.get(k, np.nan)
            if np.isfinite(p) and np.isfinite(p85) and p >= p85:
                cnt += 1
        if cnt >= 4:
            rows.append(i)
    return rows


def date_rows_from_alert(seq, vin, val, col):
    """Rows in seq whose cut_date >= the alert date in column `col` (channel on-from-date)."""
    if vin not in val.index or pd.isna(val.loc[vin, col]):
        return []
    d = val.loc[vin, col]
    return [i for i, cd in enumerate(seq["cut_date"]) if pd.Timestamp(cd) >= d]


def conjoin(rows_a, rows_b, n, w):
    """Fire at i if a fired in [i-w+1, i] AND b fired in [i-w+1, i]."""
    sa, sb = set(rows_a), set(rows_b)
    out = []
    for i in range(n):
        win = range(max(0, i - w + 1), i + 1)
        if any(j in sa for j in win) and any(j in sb for j in win):
            out.append(i)
    return out


def main():
    ws = L.load_walking()
    tend, years = L.load_tend_years()
    val = L.load_alert_validation()
    vins_all, _, _ = L.all_vins(ws)

    p85 = {}
    for k in ws["k_weeks"].unique():
        sub = ws[(ws["k_weeks"] == k) & ws["usable"]]["prob"].dropna()
        p85[k] = float(np.percentile(sub, 85)) if len(sub) >= 5 else np.nan

    a1 = pd.read_csv(OUT / "A1_cusum_fires.csv", parse_dates=["first_fire_date"])
    a1_first = dict(zip(a1["vin_label"], a1["first_fire_date"]))

    pair_records = {f"{a}__AND__{b}": [] for a, b in P["pairs"]}
    for vin in vins_all:
        seq = L.vin_seq(ws, vin)
        n = len(seq)
        label = 1 if "_F_" in vin else 0
        rows = {
            "H2_pers_red": h2_fire_rows(seq),
            "H5_fleet_pctile": h5_fire_rows(seq, p85),
            "A2": date_rows_from_alert(seq, vin, val, "a2_fire_week"),
            "A1_cusum": [i for i, cd in enumerate(seq["cut_date"])
                         if vin in a1_first and pd.notna(a1_first[vin])
                         and pd.Timestamp(cd) >= a1_first[vin]],
        }
        for a, b in P["pairs"]:
            fr = conjoin(rows[a], rows[b], n, W)
            pair_records[f"{a}__AND__{b}"].append(
                L.fires_to_record(vin, label, seq, fr, tend))

    summaries = []
    for name, recs in pair_records.items():
        df = pd.DataFrame(recs)
        s = L.summarize(df, years, name)
        ok, reason = L.accept(s)
        s["accept"] = ok
        s["accept_reason"] = reason
        summaries.append(s)
        print(name, "->", {k: s[k] for k in ["recall_n_of_14", "med_lead_d",
              "nf_ever_fire_n", "nf_eps_per_truck_year"]}, "| SHIP" if ok else "| no")

    pd.DataFrame(summaries).to_csv(OUT / "A2_conjunction_summary.csv", index=False)
    print("\nSaved A2_conjunction_summary.csv")


if __name__ == "__main__":
    main()
