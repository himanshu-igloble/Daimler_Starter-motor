"""_heuristic_lib.py — shared read-only loaders + metric summarizer for V2.1 A1-A3.
Reuses frozen V2 walking_scores.csv + V1.1 alert CSVs + weekly cache. Never writes them.
Metric definitions are copied verbatim from H_eval_heuristics.py so outputs are
directly comparable to heuristic_summary.csv (H2 baseline = 10/14, 116 d, 5/20, 0.19).
"""
from pathlib import Path
import glob
import numpy as np
import pandas as pd

ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR")
WS_PATH = ROOT / "V2_program" / "analysis" / "heuristics" / "out" / "walking_scores.csv"
VAL_PATH = ROOT / "V1.1" / "results" / "V1_1_SM_alert_validation.csv"
DQ_PATH = ROOT / "results" / "V1_SM_data_quality.csv"
WEEKLY_GLOB = str(ROOT / "cache" / "weekly" / "V1_SM_weekly_*.parquet")

N_F, N_NF = 14, 20


def load_walking():
    ws = pd.read_csv(WS_PATH, parse_dates=["cut_date"])
    return ws.sort_values(["vin_label", "k_weeks"]).reset_index(drop=True)


def load_tend_years():
    dq = pd.read_csv(DQ_PATH, parse_dates=["t_end", "t_start"])
    tend = {r.vin_label: r.t_end for r in dq.itertuples()}
    years = {r.vin_label: (r.t_end - r.t_start).days / 365.25 for r in dq.itertuples()}
    return tend, years


def load_alert_validation():
    return pd.read_csv(
        VAL_PATH,
        parse_dates=["pers_first_fire_week", "pers_terminal_fire_start",
                     "a1_first_alarm", "a2_fire_week"],
    ).set_index("vin_label")


def vin_seq(ws, vin):
    """Per-VIN usable weeks, ascending calendar time (k descending)."""
    sub = ws[(ws["vin_label"] == vin) & (ws["usable"])].copy()
    return sub.sort_values("k_weeks", ascending=False).reset_index(drop=True)


def all_vins(ws):
    v = ws["vin_label"].unique().tolist()
    return v, [x for x in v if "_F_" in x], [x for x in v if "_NF_" in x]


def episodes_from_rows(fire_rows):
    """Count contiguous fire episodes from sorted unique row indices."""
    fr = sorted(set(int(i) for i in fire_rows))
    if not fr:
        return 0
    eps = 1
    for i in range(1, len(fr)):
        if fr[i] != fr[i - 1] + 1:
            eps += 1
    return eps


def fires_to_record(vin, label, seq, fire_rows, tend):
    """Build one heuristic_fires-style record from per-VIN fire row indices.
    seq must carry a 'cut_date' column aligned to fire_rows indices."""
    fr = sorted(set(int(i) for i in fire_rows))
    if not fr:
        return {"vin_label": vin, "label": label, "ever_fires": False,
                "first_fire_date": pd.NaT, "lead_days": np.nan, "n_episodes": 0}
    first_idx = fr[0]
    first_date = pd.Timestamp(seq["cut_date"].iloc[first_idx])
    lead = (tend[vin] - first_date).days
    return {"vin_label": vin, "label": label, "ever_fires": True,
            "first_fire_date": first_date, "lead_days": lead,
            "n_episodes": episodes_from_rows(fr)}


def summarize(df_fires, years, rule_name):
    """df_fires: rows with [label, ever_fires, lead_days, n_episodes].
    Returns one summary dict matching heuristic_summary.csv columns."""
    f = df_fires[df_fires["label"] == 1]
    nf = df_fires[df_fires["label"] == 0]
    recall_n = int(f["ever_fires"].sum())
    f_leads = f[f["ever_fires"]]["lead_days"].dropna()
    med_lead = float(np.median(f_leads)) if len(f_leads) else np.nan
    nf_fire_n = int(nf["ever_fires"].sum())
    nf_eps = nf[nf["ever_fires"]]["n_episodes"].sum()
    total_nf_years = sum(years.get(v, 1.0) for v in nf["vin_label"])
    nf_eps_py = float(nf_eps) / total_nf_years if total_nf_years > 0 else np.nan
    return {"heuristic": rule_name, "recall_n_of_14": recall_n,
            "recall_frac": round(recall_n / N_F, 3),
            "med_lead_d": round(med_lead, 0) if np.isfinite(med_lead) else np.nan,
            "nf_ever_fire_n": nf_fire_n, "nf_ever_fire_frac": round(nf_fire_n / N_NF, 3),
            "nf_eps_per_truck_year": round(nf_eps_py, 3) if np.isfinite(nf_eps_py) else np.nan}


def load_rest_vsi_series(active_days_min=2):
    """Per-VIN weekly rest-VSI median series (same source E5_maintenance.py uses).
    Returns dict vin_label -> DataFrame[week (datetime, ascending), vsi_rest_median]."""
    out = {}
    for f in sorted(glob.glob(WEEKLY_GLOB)):
        w = pd.read_parquet(f)
        w = w[w["active_days"] >= active_days_min].copy()
        if len(w) == 0:
            continue
        w["week"] = pd.to_datetime(w["week"])
        w = w.sort_values("week").reset_index(drop=True)
        out[w["vin_label"].iloc[0]] = w[["week", "vsi_rest_median"]]
    return out


def accept(summary, nf_max=0.19, recall_min=10, lead_min=116):
    """Apply the pre-registered accept-bar to a summary dict. Returns (bool, reason)."""
    nf = summary["nf_eps_per_truck_year"]
    rc = summary["recall_n_of_14"]
    ld = summary["med_lead_d"]
    ok = (np.isfinite(nf) and nf < nf_max and rc >= recall_min
          and np.isfinite(ld) and ld >= lead_min)
    return ok, (f"nf_eps={nf} (<{nf_max}? {np.isfinite(nf) and nf < nf_max}), "
                f"recall={rc}/14 (>={recall_min}? {rc >= recall_min}), "
                f"lead={ld}d (>={lead_min}? {np.isfinite(ld) and ld >= lead_min})")
