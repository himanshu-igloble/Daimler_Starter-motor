"""A3_h4_terminal.py — H4 multichannel re-run with TERMINAL-state persistence.
Channel count >=2 of {tier>=AMBER, persistence_terminal, A1 burst, A2} -> fire.
The fix: persistence uses pers_terminal_fire_start (currently-firing episode),
not pers_first_fire_week (which fired on all 20 NF -> 100% NF inflation).
Params frozen in params/A3_h4_params.json.

Run: py -3 "STARTER MOTOR/V2.1/heuristics/A3_h4_terminal.py"
"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR\V2.1")
sys.path.insert(0, str(HERE / "heuristics"))
import _heuristic_lib as L  # noqa: E402

P = json.loads((HERE / "params" / "A3_h4_params.json").read_text())
PCOL = P["persistence_col"]
OUT = HERE / "heuristics" / "out"


def on_from(val, vin, col, date):
    if vin not in val.index or pd.isna(val.loc[vin, col]):
        return False
    return date >= val.loc[vin, col]


def h4_rows(seq, vin, val):
    rows = []
    for i, (tier, cd) in enumerate(zip(seq["tier"].values, seq["cut_date"].values)):
        d = pd.Timestamp(cd)
        c = 0
        c += 1 if tier in ("AMBER", "RED") else 0
        c += 1 if on_from(val, vin, PCOL, d) else 0
        c += 1 if on_from(val, vin, "a1_first_alarm", d) else 0
        c += 1 if on_from(val, vin, "a2_fire_week", d) else 0
        if c >= P["min_count"]:
            rows.append(i)
    return rows


def main():
    ws = L.load_walking()
    tend, years = L.load_tend_years()
    val = L.load_alert_validation()
    vins_all, _, _ = L.all_vins(ws)

    recs = []
    for vin in vins_all:
        seq = L.vin_seq(ws, vin)
        label = 1 if "_F_" in vin else 0
        recs.append(L.fires_to_record(vin, label, seq, h4_rows(seq, vin, val), tend))

    df = pd.DataFrame(recs)
    s = L.summarize(df, years, "A3_h4_terminal")
    ok, reason = L.accept(s)
    s["accept"], s["accept_reason"] = ok, reason
    pd.DataFrame([s]).to_csv(OUT / "A3_h4_summary.csv", index=False)
    print("A3 H4 terminal-state:", s)
    print("vs original H4 (heuristic_summary.csv): recall 14/14, NF 20/20, 1.00 ep/yr")
    print("ACCEPT-BAR:", "SHIP-CANDIDATE" if ok else "DOES NOT CLEAR", "|", reason)


if __name__ == "__main__":
    main()
