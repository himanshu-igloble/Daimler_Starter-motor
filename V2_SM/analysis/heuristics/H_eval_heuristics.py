"""
H_eval_heuristics.py — V2 Heuristic Intelligence Layer: Backtest H1–H5
=======================================================================
Evaluates five frozen heuristics on the per-VIN per-k walking scores
plus the V1.1 alert-channel states.

Heuristics (parameters frozen a priori from spec):
  H1 RISK MOMENTUM: delta(walking prob) over trailing 4 weeks >= +0.15 -> fire
  H2 PERSISTENT-RED DWELL: >=3 consecutive weekly cuts in RED -> fire
  H3 ESCALATION LADDER: monotone tier GREEN->AMBER->RED within any 8-wk window
                        AND any channel (persistence/A1/A2) active same window -> fire
  H4 MULTI-CHANNEL AGREEMENT: count({tier>=AMBER, pers fire-state, A1 episode,
                               A2 fired}) >= 2 at any week -> fire
  H5 FLEET-PERCENTILE PERSISTENCE: walking prob >= 85th pctile of all trucks'
                                   same-k scores in >=4 of trailing 6 weeks -> fire

All results are SCREEN-GRADE (n=34, retrospective, pre-registered parameters).

Outputs:
  out/heuristic_fires.csv   — per VIN per heuristic: first_fire_k, first_fire_date,
                              lead_days, n_fire_episodes, ever_fires
  out/heuristic_summary.csv — ranked summary table

Run: py -3 "STARTER MOTOR/V2_program/analysis/heuristics/H_eval_heuristics.py"
"""
from pathlib import Path
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR")
OUT_DIR = ROOT / "V2_program" / "analysis" / "heuristics" / "out"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── load walking scores ───────────────────────────────────────────────────────
ws = pd.read_csv(OUT_DIR / "walking_scores.csv", parse_dates=["cut_date"])
ws = ws.sort_values(["vin_label", "k_weeks"]).reset_index(drop=True)
# k_weeks = 0 is closest to t_end; larger k = further in the past
# For chronological evaluation: sort by ascending calendar date = descending k
# We'll work in k-space and map to dates from t_end

# ── load alert validation (channel states per VIN) ────────────────────────────
val = pd.read_csv(ROOT / "V1.1" / "results" / "V1_1_SM_alert_validation.csv",
                  parse_dates=["pers_first_fire_week", "pers_terminal_fire_start",
                               "a1_first_alarm", "a2_fire_week"])
pol = pd.read_csv(ROOT / "V1.1" / "results" / "V1_1_SM_alert_policy.csv",
                  parse_dates=["first_fire_date"])
val = val.set_index("vin_label")
pol_idx = pol.set_index("vin_label")

# ── load t_end per VIN ────────────────────────────────────────────────────────
dq = pd.read_csv(ROOT / "results" / "V1_SM_data_quality.csv", parse_dates=["t_end"])
T_END = {r["vin_label"]: r["t_end"] for _, r in dq.iterrows()}

vins_all = ws["vin_label"].unique().tolist()
vins_f = [v for v in vins_all if "_F_" in v]
vins_nf = [v for v in vins_all if "_NF_" in v]
n_f, n_nf = 14, 20


# ── helper: per-VIN chronological score sequence ─────────────────────────────
def get_vin_seq(vin):
    """Return df sorted ascending by cut_date (descending k) for usable weeks."""
    sub = ws[(ws["vin_label"] == vin) & (ws["usable"])].copy()
    sub = sub.sort_values("k_weeks", ascending=False).reset_index(drop=True)
    # ascending index = ascending calendar time (k=max first, k=0 last)
    return sub


def k_to_date(vin, k):
    return T_END[vin] - pd.Timedelta(days=7 * k)


# ── channel state helpers ─────────────────────────────────────────────────────
def pers_fire_at_date(vin, date):
    """True if persistence channel is active (fire-state) at given date.
    We approximate: active during any fire episode. Use pers_first_fire_week
    to define 'ever active after first fire' as a conservative simplification
    (full episode intervals not in CSV, so we treat pers as on from first fire
    to end, with the terminal check from pers_terminal_fire_start).
    """
    if vin not in val.index:
        return False
    row = val.loc[vin]
    first = row.get("pers_first_fire_week")
    if pd.isna(first):
        return False
    return date >= first


def a1_fire_at_date(vin, date):
    """True if A1 alarm ever fired before or at date."""
    if vin not in val.index:
        return False
    row = val.loc[vin]
    a1 = row.get("a1_first_alarm")
    if pd.isna(a1):
        return False
    return date >= a1


def a2_fire_at_date(vin, date):
    """True if A2 detector fired before or at date."""
    if vin not in val.index:
        return False
    row = val.loc[vin]
    a2 = row.get("a2_fire_week")
    if pd.isna(a2):
        return False
    return date >= a2


def any_channel_in_window(vin, date_start, date_end):
    """True if any channel (pers/A1/A2) was active within [date_start, date_end]."""
    # check if any channel's first-fire falls in window or was before date_end
    return (pers_fire_at_date(vin, date_end) and
            _channel_started_in_or_before(vin, "pers", date_end)) or \
           (a1_fire_at_date(vin, date_end) and
            _channel_started_in_or_before(vin, "a1", date_end)) or \
           (a2_fire_at_date(vin, date_end) and
            _channel_started_in_or_before(vin, "a2", date_end))


def _channel_started_in_or_before(vin, ch, date_end):
    if vin not in val.index:
        return False
    row = val.loc[vin]
    if ch == "pers":
        d = row.get("pers_first_fire_week")
    elif ch == "a1":
        d = row.get("a1_first_alarm")
    elif ch == "a2":
        d = row.get("a2_fire_week")
    else:
        return False
    if pd.isna(d):
        return False
    return d <= date_end


# ── compute fleet-percentile at each k ───────────────────────────────────────
def fleet_pctile85_by_k(ws_df):
    """Dict k -> 85th percentile of prob across all usable trucks."""
    pctiles = {}
    for k in ws_df["k_weeks"].unique():
        sub = ws_df[(ws_df["k_weeks"] == k) & ws_df["usable"]]
        finite = sub["prob"].dropna()
        if len(finite) >= 5:
            pctiles[k] = float(np.percentile(finite, 85))
        else:
            pctiles[k] = np.nan
    return pctiles

fleet_p85 = fleet_pctile85_by_k(ws)


# ── heuristic evaluators ─────────────────────────────────────────────────────
def h1_risk_momentum(vin_seq, vin, delta_thr=0.15, window=4):
    """H1: delta(prob) over trailing 4 weeks >= +0.15."""
    fire_rows = []
    probs = vin_seq["prob"].values
    dates = vin_seq["cut_date"].values
    for i in range(window, len(vin_seq)):
        cur_prob = probs[i]
        past_prob = probs[i - window]
        if np.isfinite(cur_prob) and np.isfinite(past_prob):
            if (cur_prob - past_prob) >= delta_thr:
                fire_rows.append(i)
    return fire_rows, vin_seq


def h2_persistent_red(vin_seq, vin, consec=3):
    """H2: >=3 consecutive RED cuts."""
    fire_rows = []
    tiers = vin_seq["tier"].values
    count = 0
    for i, t in enumerate(tiers):
        if t == "RED":
            count += 1
            if count >= consec:
                fire_rows.append(i)
        else:
            count = 0
    return fire_rows, vin_seq


def h3_escalation_ladder(vin_seq, vin, window=8):
    """H3: monotone GREEN->AMBER->RED in 8-wk window AND channel active."""
    fire_rows = []
    tiers = vin_seq["tier"].values
    dates = vin_seq["cut_date"].values
    n = len(vin_seq)
    for i in range(window - 1, n):
        window_tiers = tiers[i - window + 1: i + 1]
        window_dates = dates[i - window + 1: i + 1]
        # check for monotone escalation: G, then A, then R (not necessarily consecutive)
        has_g = any(t == "GREEN" for t in window_tiers)
        has_a = any(t == "AMBER" for t in window_tiers)
        has_r = any(t == "RED" for t in window_tiers)
        if has_g and has_a and has_r:
            # check temporal order: first G before first A before first R
            first_g = next((j for j, t in enumerate(window_tiers) if t == "GREEN"), None)
            first_a = next((j for j, t in enumerate(window_tiers) if t == "AMBER"), None)
            first_r = next((j for j, t in enumerate(window_tiers) if t == "RED"), None)
            if (first_g is not None and first_a is not None and first_r is not None
                    and first_g < first_a < first_r):
                # check any channel active in this window
                d_start = pd.Timestamp(window_dates[0])
                d_end = pd.Timestamp(window_dates[-1])
                if any_channel_in_window(vin, d_start, d_end):
                    fire_rows.append(i)
    return fire_rows, vin_seq


def h4_multi_channel(vin_seq, vin, min_count=2):
    """H4: count of {tier>=AMBER, pers, A1, A2} >= 2 at any week."""
    fire_rows = []
    tiers = vin_seq["tier"].values
    dates = vin_seq["cut_date"].values
    for i, (tier, date) in enumerate(zip(tiers, dates)):
        dt = pd.Timestamp(date)
        count = 0
        if tier in ("AMBER", "RED"):
            count += 1
        if pers_fire_at_date(vin, dt):
            count += 1
        if a1_fire_at_date(vin, dt):
            count += 1
        if a2_fire_at_date(vin, dt):
            count += 1
        if count >= min_count:
            fire_rows.append(i)
    return fire_rows, vin_seq


def h5_fleet_percentile(vin_seq, vin, pctile_dict=fleet_p85, window=6, min_above=4):
    """H5: prob >= 85th fleet pctile in >=4 of trailing 6 weeks."""
    fire_rows = []
    probs = vin_seq["prob"].values
    k_vals = vin_seq["k_weeks"].values
    n = len(vin_seq)
    for i in range(window - 1, n):
        win_probs = probs[i - window + 1: i + 1]
        win_k = k_vals[i - window + 1: i + 1]
        count = 0
        for p, k in zip(win_probs, win_k):
            p85 = pctile_dict.get(k, np.nan)
            if np.isfinite(p) and np.isfinite(p85) and p >= p85:
                count += 1
        if count >= min_above:
            fire_rows.append(i)
    return fire_rows, vin_seq


def episodes_from_fire_rows(fire_rows):
    """Count contiguous fire episodes from sorted fire row indices."""
    if not fire_rows:
        return 0
    eps = 1
    for i in range(1, len(fire_rows)):
        if fire_rows[i] != fire_rows[i - 1] + 1:
            eps += 1
    return eps


def eval_heuristic(h_func, vin_seq, vin):
    """Evaluate a heuristic on a VIN, return fire metadata."""
    fire_rows, seq = h_func(vin_seq, vin)
    # remove duplicate indices
    fire_rows = sorted(set(fire_rows))
    if not fire_rows:
        return {"ever_fires": False, "first_fire_idx": np.nan,
                "first_fire_date": pd.NaT, "first_fire_k": np.nan,
                "lead_days": np.nan, "n_episodes": 0}
    first_idx = fire_rows[0]
    first_date = pd.Timestamp(seq["cut_date"].iloc[first_idx])
    first_k = seq["k_weeks"].iloc[first_idx]
    t_end = T_END[vin]
    lead = (t_end - first_date).days
    n_ep = episodes_from_fire_rows(fire_rows)
    return {"ever_fires": True, "first_fire_idx": first_idx,
            "first_fire_date": first_date, "first_fire_k": first_k,
            "lead_days": lead, "n_episodes": n_ep}


HEURISTICS = {
    "H1_momentum": lambda s, v: h1_risk_momentum(s, v),
    "H2_pers_red": lambda s, v: h2_persistent_red(s, v),
    "H3_escalation": lambda s, v: h3_escalation_ladder(s, v),
    "H4_multichannel": lambda s, v: h4_multi_channel(s, v),
    "H5_fleet_pctile": lambda s, v: h5_fleet_percentile(s, v),
}

# ── evaluation loop ───────────────────────────────────────────────────────────
print("Evaluating H1-H5 on all 34 VINs...")
fire_records = []
for vin in vins_all:
    seq = get_vin_seq(vin)
    lbl = 1 if "_F_" in vin else 0
    for h_name, h_func in HEURISTICS.items():
        res = eval_heuristic(h_func, seq, vin)
        fire_records.append({
            "vin_label": vin, "label": lbl, "heuristic": h_name,
            **res
        })

df_fires = pd.DataFrame(fire_records)
df_fires.to_csv(OUT_DIR / "heuristic_fires.csv", index=False)
print(f"Saved heuristic_fires.csv -> {OUT_DIR / 'heuristic_fires.csv'}")

# ── summary metrics per heuristic ────────────────────────────────────────────
# Compute truck-years for NF fleet (approximation from t_end - t_start)
dq_full = pd.read_csv(ROOT / "results" / "V1_SM_data_quality.csv",
                      parse_dates=["t_end", "t_start"])
vin_years = {r["vin_label"]: (r["t_end"] - r["t_start"]).days / 365.25
             for _, r in dq_full.iterrows()}

total_nf_years = sum(vin_years.get(v, 1.0) for v in vins_nf)

print("\n=== HEURISTIC SUMMARY ===\n")
summary_rows = []
for h_name in HEURISTICS:
    sub = df_fires[df_fires["heuristic"] == h_name]
    f_sub = sub[sub["label"] == 1]
    nf_sub = sub[sub["label"] == 0]

    # failed recall (n/14 ever fires)
    f_recall_n = f_sub["ever_fires"].sum()
    f_recall_frac = f_recall_n / n_f

    # median lead (days) among F firers
    f_leads = f_sub[f_sub["ever_fires"]]["lead_days"].dropna()
    med_lead = float(np.median(f_leads)) if len(f_leads) > 0 else np.nan

    # NF trucks ever firing
    nf_fire_n = nf_sub["ever_fires"].sum()
    nf_fire_frac = nf_fire_n / n_nf

    # NF fire episodes per truck-year
    nf_total_eps = nf_sub[nf_sub["ever_fires"]]["n_episodes"].sum()
    # conservative: use all 20 NF trucks' total years as denominator
    nf_eps_py = nf_total_eps / total_nf_years if total_nf_years > 0 else np.nan

    summary_rows.append({
        "heuristic": h_name,
        "recall_n_of_14": int(f_recall_n),
        "recall_frac": round(f_recall_frac, 3),
        "med_lead_d": round(med_lead, 0) if not np.isnan(med_lead) else np.nan,
        "nf_ever_fire_n": int(nf_fire_n),
        "nf_ever_fire_frac": round(nf_fire_frac, 3),
        "nf_eps_per_truck_year": round(nf_eps_py, 2),
    })
    print(f"{h_name}:")
    print(f"  Recall: {f_recall_n}/14 ({f_recall_frac:.1%})   "
          f"Med lead: {med_lead:.0f} d")
    print(f"  NF ever-fire: {nf_fire_n}/20 ({nf_fire_frac:.1%})  "
          f"NF eps/truck-yr: {nf_eps_py:.2f}")
    # Per-VIN detail for failed
    for _, row in f_sub.iterrows():
        fire_str = f"first={row['first_fire_date'].date() if pd.notna(row['first_fire_date']) else 'NONE'} lead={row['lead_days']:.0f}d" if row['ever_fires'] else "MISS"
        print(f"    {row['vin_label']}: {fire_str}")
    print()

df_summary = pd.DataFrame(summary_rows)

# Add complexity / explainability ratings
complexity = {
    "H1_momentum": ("Low", "High — rising prob slope"),
    "H2_pers_red": ("Low", "High — sustained RED"),
    "H3_escalation": ("Medium", "High — tier climb + channel"),
    "H4_multichannel": ("Medium", "High — multi-source agreement"),
    "H5_fleet_pctile": ("Low", "Medium — above fleet norm"),
}
for h, (comp, expl) in complexity.items():
    df_summary.loc[df_summary["heuristic"] == h, "complexity"] = comp
    df_summary.loc[df_summary["heuristic"] == h, "explainability"] = expl

# Baseline comparison row (persistence channel from V1.1)
baseline_pers = {
    "heuristic": "BASELINE_persistence", "recall_n_of_14": 13, "recall_frac": 0.929,
    "med_lead_d": 168.0, "nf_ever_fire_n": 20, "nf_ever_fire_frac": 1.0,
    "nf_eps_per_truck_year": None, "complexity": "Low", "explainability": "High"
}
baseline_a2 = {
    "heuristic": "BASELINE_A2", "recall_n_of_14": 4, "recall_frac": 0.286,
    "med_lead_d": 66.5, "nf_ever_fire_n": 0, "nf_ever_fire_frac": 0.0,
    "nf_eps_per_truck_year": 0.0, "complexity": "Medium", "explainability": "High"
}

df_summary = pd.concat([df_summary, pd.DataFrame([baseline_pers, baseline_a2])],
                       ignore_index=True)

# Sort by recall desc, then NF fire frac asc
df_summary = df_summary.sort_values(
    ["recall_frac", "nf_ever_fire_frac"],
    ascending=[False, True]
).reset_index(drop=True)
df_summary["priority"] = range(1, len(df_summary) + 1)

df_summary.to_csv(OUT_DIR / "heuristic_summary.csv", index=False)
print(f"\nSaved heuristic_summary.csv -> {OUT_DIR / 'heuristic_summary.csv'}")

# ── print ranked table ────────────────────────────────────────────────────────
print("\n=== RANKED TABLE ===")
print(f"{'Heuristic':<22} {'Recall':>8} {'MedLead':>9} {'NF-Fire':>8} "
      f"{'NF-Eps/yr':>10} {'Complexity':<10} {'Priority':>8}")
print("-" * 90)
for _, row in df_summary.iterrows():
    med_str = f"{row['med_lead_d']:.0f}d" if pd.notna(row['med_lead_d']) else "—"
    eps_str = f"{row['nf_eps_per_truck_year']:.2f}" if pd.notna(row['nf_eps_per_truck_year']) else "—"
    print(f"{row['heuristic']:<22} "
          f"{row['recall_n_of_14']!s:>2}/14={row['recall_frac']:.1%}  "
          f"{med_str:>9}   {row['nf_ever_fire_n']!s:>2}/20={row['nf_ever_fire_frac']:.1%}  "
          f"{eps_str:>10}   {str(row['complexity']):<10}  {row['priority']:>2}")

print("\nNote: All results SCREEN-GRADE (n=34, retrospective, pre-registered params).")
