# STARTER MOTOR/V3.1/state/run_state_fleet.py
"""Runs the state engine over all 34 VINs; adjudicates SV-1..SV-4 (SV-5 runs in Task 9)."""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _state_lib as SL
import sm_state_engine as SE

P = SL.P
OUT = SL.STATE_OUT
HB = json.loads((OUT / "P0_heartbeat.json").read_text())["verdict"]["confirmed"]


def one(vin):
    rowdf = SE.classify_rows(SL.load_vin(vin))
    ep = SE.build_episodes(rowdf, heartbeat_confirmed=HB)
    cranks = SE.crank_table(ep)
    trips = SE.derive_trips(rowdf, ep)
    wk = SE.weekly_rollup(vin, rowdf, ep, trips, cranks)
    for df, tag in [(ep, "state_episodes"), (wk, "state_weekly"), (trips, "trips"), (cranks, "cranks")]:
        d = df.copy()
        if "vin_label" not in d.columns:
            d.insert(0, "vin_label", vin)
        d.to_parquet(OUT / f"V3_1_{tag}_{vin}.parquet", index=False)
    # SV-1 material: crank preceded by off-ish episode within window, or flagged
    ok = tot = 0
    states, ends = ep["state"].tolist(), ep["ts_end"].tolist()
    for i, s in enumerate(states):
        if s != "CRANK":
            continue
        tot += 1
        e = ep.iloc[i]
        if e["cwr"] or e["recrank"]:
            ok += 1; continue
        if i > 0 and states[i - 1] in ("ENGINE_OFF", "OFF_DWELL", "UNKNOWN_GAP", "OFF_CONFIRMED", "UNKNOWN_GAP_SHORT"):
            ok += 1; continue
    soak_frac = float(np.isfinite(cranks["soak_h"]).mean()) if len(cranks) else np.nan
    print(f"done {vin}: rows={len(rowdf)} eps={len(ep)} cranks={tot} trips={len(trips)}", flush=True)
    return {"vin": vin, "sv1_ok": ok, "sv1_tot": tot, "soak_frac": soak_frac, "wk": wk}


def main():
    res = [one(v) for v in SL.all_vin_labels()]
    wk_all = pd.concat([r.pop("wk") for r in res], ignore_index=True)
    wk_all.to_parquet(OUT / "V3_1_state_weekly_ALL.parquet", index=False)

    sv1_frac = sum(r["sv1_ok"] for r in res) / max(1, sum(r["sv1_tot"] for r in res))
    m = wk_all[wk_all["active_days"] >= 2].copy()
    kmd = m["km"] / m["active_days"]; ehd = m["engine_hours"] / m["active_days"]
    sv3_frac = float(((kmd >= P["sv3_km_day"][0]) & (kmd <= P["sv3_km_day"][1]) &
                      (ehd >= P["sv3_eh_day"][0]) & (ehd <= P["sv3_eh_day"][1])).mean())
    soaks = [r["soak_frac"] for r in res if np.isfinite(r["soak_frac"])]
    sv4_frac = float(np.mean(soaks)) if soaks else 0.0
    sv = {"heartbeat_confirmed": HB,
          "SV1": {"frac": round(sv1_frac, 4), "pass": sv1_frac >= P["sv1_min_frac"]},
          "SV2": {"note": "per-VIN dwell report", "per_vin": [{k: r[k] for k in ("vin", "sv1_ok", "sv1_tot", "soak_frac")} for r in res]},
          "SV3": {"frac": round(sv3_frac, 4), "pass": sv3_frac >= P["sv3_min_frac"]},
          "SV4": {"mean_soak_frac": round(sv4_frac, 4), "pass": (sv4_frac >= P["sv4_min_soak_frac"]) if HB else None}}
    (OUT / "V3_1_sv_gates.json").write_text(json.dumps(sv, indent=2))
    print(json.dumps({k: sv[k] for k in ("heartbeat_confirmed", "SV1", "SV3", "SV4")}, indent=2))


if __name__ == "__main__":
    main()
