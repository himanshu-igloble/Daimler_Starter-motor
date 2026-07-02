# STARTER MOTOR/V3.1/heuristics/T1_attribution.py
"""Battery-vs-starter attribution triage (spec §8). SCREEN-GRADE, convergence check only."""
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "features"))
import _v31_lib as L
import _factors31 as X

OUT = HERE / "out"; OUT.mkdir(exist_ok=True)
R = L.CP["t1_rubric"]
ev, wk, px = L.load_events(), L.load_weekly(), L.build_px()
order = L.vins_in_order()
cat = pd.read_csv(L.V31_OUT / "V3_1_SM_catalog.csv").set_index("vin_label")
alerts = pd.read_csv(L.SMROOT / "V1.1" / "results" / "V1_1_SM_alert_validation.csv").set_index("vin_label")

lowv_valid = cat["lowv_crank_share"].dropna()
lowv_med, lowv_p75 = float(lowv_valid.median()), float(lowv_valid.quantile(R["battery_lowv_share_pctl"] / 100))

rows = []
for v in order:
    e = X._evin(ev, v)
    cranks90 = 0
    goodv_weeks = 0
    if v in px.index and not px.loc[v].isna().any() and len(e):
        t90 = pd.Timestamp(px.loc[v, "t_90_cutoff"])
        cranks90 = int((e["ts_start"] >= t90).sum())
        w = wk[(wk["vin_label"] == v) & (wk["active_days"] >= 2)].sort_values("week")
        lookback = pd.to_datetime(w["week"]).tail(R["starter_lookback_weeks"])
        if len(lookback):
            hs = e[(e["success"] == False) & (e["baseline_vsi"] >= X.GOODV) & (e["ts_start"] >= lookback.iloc[0])].copy()  # noqa: E712
            if len(hs):
                hs["week"] = hs["ts_start"].dt.floor("D") - pd.to_timedelta(hs["ts_start"].dt.weekday, unit="D")
                goodv_weeks = int(hs["week"].nunique())
    lowv = cat.loc[v, "lowv_crank_share"] if v in cat.index else np.nan
    rest_tr = cat.loc[v, "rest_vsi_trend_12w"] if v in cat.index else np.nan
    a2 = bool(alerts.loc[v, "a2_fire"]) if (v in alerts.index and pd.notna(alerts.loc[v, "a2_fire"])) else False

    if v in L.SMA_DEAD or cranks90 < R["insufficient_min_cranks_90d"]:
        lab = "INSUFFICIENT"
    else:
        starter = (goodv_weeks >= R["starter_weeks_with_goodv_hardstart_min"]) and (np.isfinite(lowv) and lowv <= lowv_med)
        battery = a2 or (np.isfinite(lowv) and lowv > lowv_p75 and np.isfinite(rest_tr) and rest_tr < 0)
        lab = "MIXED" if (starter and battery) else "STARTER_FIRST" if starter else "BATTERY_FIRST" if battery else "INSUFFICIENT"
    rows.append({"vin_label": v, "attribution": lab, "goodv_hardstart_weeks12": goodv_weeks,
                 "lowv_crank_share": lowv, "rest_vsi_trend_12w": rest_tr, "a2_fired": a2, "cranks_last90": cranks90,
                 "evidence": f"goodv_wk={goodv_weeks}; lowv={lowv if np.isfinite(lowv) else 'NA'}; a2={a2}; rest_trend={rest_tr if np.isfinite(rest_tr) else 'NA'}"})
t1 = pd.DataFrame(rows)
t1.to_csv(OUT / "T1_attribution.csv", index=False)

arch = pd.read_csv(L.SMROOT / "V1.1" / "discovery" / "out" / "E2_failed_vin_archetypes.csv")[["vin_label", "archetype"]]
m = t1.merge(arch, on="vin_label", how="inner")
EXPECT = {"A2_battery_cascade": {"BATTERY_FIRST", "MIXED"}, "A1+A2_mixed": {"BATTERY_FIRST", "MIXED"},
          "A1_solenoid_intermittency": {"STARTER_FIRST", "MIXED"}, "A1_solenoid_then_silent": {"STARTER_FIRST", "MIXED"},
          "A4_silent_abrupt": {"INSUFFICIENT"}}
m["expected"] = m["archetype"].map(lambda a: sorted(EXPECT.get(a, set())) or None)
m["agrees"] = [row["attribution"] in EXPECT.get(row["archetype"], {row["attribution"]}) for _, row in m.iterrows()]
scored = m[m["archetype"].isin(EXPECT)]
conv = {"n_failed_scored": int(len(scored)), "n_agree": int(scored["agrees"].sum()),
        "a3_unscored": int((~m["archetype"].isin(EXPECT)).sum()),
        "nf_distribution": t1[t1["vin_label"].str.contains("_NF_")]["attribution"].value_counts().to_dict(),
        "note": "convergence with telemetry-derived archetypes; NOT ground-truth accuracy (spec §8)"}
(OUT / "T1_convergence.json").write_text(json.dumps(conv, indent=2))
print(json.dumps(conv, indent=2))
