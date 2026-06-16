"""
V1_1_SM_alerts.py — Experiment X3: LOVO-validated alert rules (V1.1 Layer 2).

1. PERSISTENCE ALERT (E3 rule, honestly validated):
   E's in-sample screen: causal within-week VSI-std ratio (trailing-4-wk mean of
   vsi_drive_std / expanding mean, >=8 wk history) above the NF p90 envelope
   (week-of-life-aligned at end-of-observation, positions -40..-1) in >=4 of the
   last 12 weeks -> 13/14 failed vs 2/20 NF IN-SAMPLE.
   Validation here: 34-fold LOVO. For each held-out VIN the envelope is built
   ONLY from the NF trucks in the training fold (19 NF if held-out is NF, 20 if
   failed). Construction choice (stated): E3's week-of-life END-ALIGNED per-position
   envelope is kept exactly (not pooled) — the held-out truck never contributes to
   its own envelope. The frozen rule (>=4 of last 12) gives the validated end-of-
   history fire/no-fire. First-fire week = causal weekly walk: at each observed
   week j (>=12 wks history) the trailing-12-week window is compared to envelope
   positions -12..-1 (the deployable "as if today were end-of-life" reading);
   first week with >=4 above = first fire. Leads vs t_end (last weekly-cache week,
   V1 convention) AND vs JCOPENDATE (= lead + gap_days for the 5 GAP_VINS).
   Sensitivity: m in {3,4,5}-of-12 evaluated INSIDE training folds (reported,
   never used to pick the shipped rule; m=4 frozen from E3).

2. A1 CRANK-BURST ALARM (physics-prior rule, not tuned on outcomes):
   Signal = daily (# failed cranks + # retry-within-120s events), 7-day rolling
   sum S7. Own baseline = mean/sd of S7 over the FIRST HALF of the truck's event
   history. Alarm when S7 > mu + 3*sd for >=2 consecutive days, with an absolute
   physics floor S7 >= 3 (a "burst" is at least 3 failure/retry events per week —
   set a priori, prevents zero-variance baselines from firing on single events).
   Episodes merged if <7 d apart; evaluated on the second half only (baseline
   period excluded). Cohort-masked: SMA-dead trucks (VIN8_F, VIN9_F + 5 NF)
   excluded — stated wherever counts are reported.

3. A2 BATTERY-CASCADE TRIPLE DETECTOR (causal):
   (i) sustained rest-VSI (vsi_rest_median) step DOWN <= -0.5 V with SNR >= 2,
   (ii) sustained drive-VSI (vsi_drive_mean) step UP >= +0.3 V with SNR >= 2,
   step centers within +/-8 weeks of each other,
   (iii) dip-depth widening: mean dip_depth last 60 d > earlier-history mean + 1 V
   (>=10 events each side; only where crank data exists).
   Steps detected causally: at scoring week i, median-split scan on data <= i
   requiring >=8 pre / >=4 post weeks (E5 used 8/8 retrospectively; 4 post = the
   minimum confirmation latency, stated). SNR = |step| / pooled MAD (E5 formula).
   Fire week = first week all three hold. Trucks without crank data cannot
   satisfy (iii) -> A2 not applicable (protects against the artifact-suspect
   2024-02-26 steps in the sparse cohort, E5). Battery REPLACEMENTS are rest-VSI
   steps UP -> must not fire; verified explicitly.

4. COMBINED POLICY TABLE: Layer-1 tier (X2 nested predictions) + persistence +
   A1 + A2 per truck; first-firing channel + lead per failed VIN; false-alarm
   burden per NF truck.

Outputs:
  STARTER MOTOR/V1.1/results/V1_1_SM_alert_validation.csv   (per-VIN, all rules)
  STARTER MOTOR/V1.1/results/V1_1_SM_alert_policy.csv        (operations table)
  STARTER MOTOR/V1.1/results/V1_1_SM_alert_sensitivity.csv   (3/4/5-of-12 sweep)
Run: py -3 "STARTER MOTOR/V1.1/src/V1_1_SM_alerts.py"
"""
from pathlib import Path
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR")
OUT = ROOT / "V1.1" / "results"
ALIGN, LAST, M_FROZEN = 40, 12, 4
SMA_DEAD = {"VIN8_F_SM", "VIN9_F_SM", "VIN10_NF_SM", "VIN11_NF_SM",
            "VIN12_NF_SM", "VIN13_NF_SM", "VIN20_NF_SM"}
GAP_DAYS = {"VIN1_F_SM": 72, "VIN4_F_SM": 97, "VIN5_F_SM": 32,
            "VIN8_F_SM": 37, "VIN9_F_SM": 142}          # V1_SM_config GAP_VINS
A1_FLOOR = 3.0          # physics prior: burst >= 3 failed/retry events per week
A2_REST_STEP, A2_DRIVE_STEP, A2_SNR = -0.5, 0.3, 2.0
A2_PAIR_DAYS, A2_DIP_DELTA = 56, 1.0
A2_PRE_MIN, A2_POST_MIN = 8, 4

# ── load ─────────────────────────────────────────────────────────────────────
wk_all = pd.concat([pd.read_parquet(f) for f in
                    sorted((ROOT / "cache/weekly").glob("V1_SM_weekly_*.parquet"))],
                   ignore_index=True)
wk_all["week"] = pd.to_datetime(wk_all["week"])
ev_all = pd.read_parquet(ROOT / "cache/events/V1_SM_crank_events.parquet")
ev_all = ev_all[ev_all["artifact"] == False].copy()
ev_all["ts_start"] = pd.to_datetime(ev_all["ts_start"])
ev_all["succ_b"] = ev_all["success"].map(
    lambda x: bool(x) if x is not None and x == x else np.nan)

fm = pd.read_csv(ROOT / "results" / "V1_SM_feature_matrix.csv")
vins = fm["vin_label"].tolist()
FAILED = {v: bool(f) for v, f in zip(fm["vin_label"], fm["failed"])}
f_vins = [v for v in vins if FAILED[v]]
nf_vins = [v for v in vins if not FAILED[v]]

preds = pd.read_csv(OUT / "V1_1_SM_nested_lovo_predictions.csv")
TIER = dict(zip(preds["vin_label"], preds["tier"]))

# E3-faithful weekly series (n_rows > 0, sorted)
WKS, RATIO, T_END = {}, {}, {}
for v in vins:
    w = wk_all[(wk_all["vin_label"] == v) & (wk_all["n_rows"] > 0)] \
        .sort_values("week").reset_index(drop=True)
    WKS[v] = w
    s = w["vsi_drive_std"].astype(float)
    RATIO[v] = (s.rolling(4, min_periods=2).mean()
                / s.expanding(min_periods=8).mean()).values
    T_END[v] = w["week"].max()           # V1 convention: last weekly-cache week


def last_align(a, k=ALIGN):
    out = np.full(k, np.nan)
    m = min(k, len(a))
    if m:
        out[-m:] = np.asarray(a, float)[-m:]
    return out


AL = {v: last_align(RATIO[v]) for v in vins}

# ── 1. persistence alert, 34-fold LOVO ───────────────────────────────────────
print("=" * 78)
print("1. PERSISTENCE ALERT — 34-fold LOVO validation of E3's >=4-of-12 rule")
print("=" * 78)
pers_rows, sens_rows = [], []
for held in vins:
    tr_nf = [v for v in nf_vins if v != held]
    env = np.nanpercentile(np.vstack([AL[v] for v in tr_nf]), 90, axis=0)
    env12 = env[-LAST:]
    # frozen end-of-history rule on held-out VIN
    cnt_end = int(np.nansum(AL[held][-LAST:] > env12))
    fire_end = cnt_end >= M_FROZEN
    # causal weekly walk: fire-state weeks (deployed alarm = currently >=4 of
    # trailing 12 above envelope). First-ever fire measures lifetime noise
    # burden; the TERMINAL episode (fire-state run that persists to the last
    # week) is the deployable failure lead.
    r, wkdates = RATIO[held], WKS[held]["week"].values
    fire_weeks = []
    for j in range(LAST - 1, len(r)):
        cnt = int(np.nansum(r[j - LAST + 1: j + 1] > env12))
        if cnt >= M_FROZEN:
            fire_weeks.append(j)
    first_fire = pd.Timestamp(wkdates[fire_weeks[0]]) if fire_weeks else pd.NaT
    n_episodes = 0
    if fire_weeks:
        n_episodes = 1 + int(np.sum(np.diff(fire_weeks) > 1))
    lead = (T_END[held] - first_fire).days if fire_weeks else np.nan
    # terminal episode: contiguous run of fire weeks ending at the last week
    term_start = pd.NaT
    if fire_weeks and fire_weeks[-1] == len(r) - 1:
        js = fire_weeks[-1]
        for j in reversed(fire_weeks):
            if js - j <= 1:
                js = j
            else:
                break
        term_start = pd.Timestamp(wkdates[js])
    term_lead = (T_END[held] - term_start).days if term_start is not pd.NaT else np.nan
    n_eval_weeks = max(len(r) - (LAST - 1), 1)
    pers_rows.append({
        "vin_label": held, "failed": int(FAILED[held]),
        "pers_weeks_above_of12": cnt_end, "pers_fire_end": fire_end,
        "pers_fire_any_causal": bool(fire_weeks),
        "pers_first_fire_week": (str(first_fire.date()) if fire_weeks else ""),
        "pers_n_fire_episodes": n_episodes,
        "pers_fire_week_frac": round(len(fire_weeks) / n_eval_weeks, 3),
        "pers_first_lead_vs_t_end_d": lead,
        "pers_terminal_fire_start": (str(term_start.date())
                                     if term_start is not pd.NaT else ""),
        "pers_lead_vs_t_end_d": term_lead,
        "pers_lead_vs_jcopen_d": (term_lead + GAP_DAYS.get(held, 0)
                                  if np.isfinite(term_lead) else np.nan)})
    # sensitivity sweep INSIDE the training fold (m = 3/4/5; diagnostic only)
    tr = [v for v in vins if v != held]
    for m in (3, 4, 5):
        rec = np.mean([np.nansum(AL[v][-LAST:] > env12) >= m
                       for v in tr if FAILED[v]])
        fp = np.mean([np.nansum(AL[v][-LAST:] > env12) >= m
                      for v in tr if not FAILED[v]])
        sens_rows.append({"held_out": held, "m_of_12": m,
                          "train_recall": round(rec, 4), "train_fp_rate": round(fp, 4)})

pers = pd.DataFrame(pers_rows)
sens = pd.DataFrame(sens_rows)
val_rec = pers[pers.failed == 1]["pers_fire_end"].sum()
val_fp = pers[pers.failed == 0]["pers_fire_end"].sum()
any_fp = pers[pers.failed == 0]["pers_fire_any_causal"].sum()
nf_wk_frac = pers[pers.failed == 0]["pers_fire_week_frac"].mean()
print(f"VALIDATED end-rule: recall {val_rec}/14, NF FP {val_fp}/20  "
      f"(in-sample screen was 13/14, 2/20)")
print(f"Deployed weekly-alarm burden: {any_fp}/20 NF trucks fire at least once "
      f"in their history; mean NF in-fire week fraction {nf_wk_frac:.3f}")
print("\nSensitivity (training-fold means across 34 folds):")
print(sens.groupby("m_of_12")[["train_recall", "train_fp_rate"]].mean().round(3))
print("\nPer-VIN (failed) — lead = TERMINAL fire episode (alert active at t_end):")
cols = ["vin_label", "pers_weeks_above_of12", "pers_fire_end",
        "pers_terminal_fire_start", "pers_lead_vs_t_end_d",
        "pers_lead_vs_jcopen_d", "pers_first_fire_week",
        "pers_first_lead_vs_t_end_d", "pers_n_fire_episodes"]
print(pers[pers.failed == 1][cols].to_string(index=False))
print("\nNF trucks with any causal fire (noise burden):")
print(pers[(pers.failed == 0) & (pers.pers_fire_any_causal)][
    ["vin_label", "pers_weeks_above_of12", "pers_fire_end",
     "pers_first_fire_week", "pers_n_fire_episodes", "pers_fire_week_frac"]]
    .to_string(index=False))

# ── 2. A1 crank-burst alarm ──────────────────────────────────────────────────
print("\n" + "=" * 78)
print("2. A1 CRANK-BURST ALARM (cohort-masked: SMA-dead excluded = "
      "VIN8_F, VIN9_F + VIN10/11/12/13/20_NF)")
print("=" * 78)
a1_rows = []
for v in vins:
    if v in SMA_DEAD:
        a1_rows.append({"vin_label": v, "failed": int(FAILED[v]),
                        "a1_applicable": False, "a1_fire": False,
                        "a1_first_alarm": "", "a1_lead_vs_t_end_d": np.nan,
                        "a1_lead_vs_jcopen_d": np.nan, "a1_n_episodes": 0,
                        "a1_eval_years": np.nan})
        continue
    e = ev_all[ev_all["vin_label"] == v].sort_values("ts_start")
    if len(e) < 20:
        a1_rows.append({"vin_label": v, "failed": int(FAILED[v]),
                        "a1_applicable": False, "a1_fire": False,
                        "a1_first_alarm": "", "a1_lead_vs_t_end_d": np.nan,
                        "a1_lead_vs_jcopen_d": np.nan, "a1_n_episodes": 0,
                        "a1_eval_years": np.nan})
        continue
    d0, d1 = e["ts_start"].min().normalize(), e["ts_start"].max().normalize()
    days = pd.date_range(d0, d1, freq="D")
    day = e["ts_start"].dt.normalize()
    n_fail = day[(e["succ_b"] == False)].value_counts().reindex(days).fillna(0)
    n_retry = day[e["retry_within_120s"] == True].value_counts().reindex(days).fillna(0)
    s7 = (n_fail + n_retry).rolling(7, min_periods=1).sum()
    half = d0 + (d1 - d0) / 2
    base = s7[s7.index <= half]
    mu, sd = float(base.mean()), float(base.std())
    thr = max(mu + 3 * sd, A1_FLOOR)
    post = s7[s7.index > half]
    above = (post > thr).values
    # episodes: >=2 consecutive alarm days; merge if gap < 7 d
    idx = np.where(above)[0]
    episodes = []
    if len(idx):
        runs, start = [], idx[0]
        for a, b in zip(idx[:-1], idx[1:]):
            if b - a > 1:
                runs.append((start, a)); start = b
        runs.append((start, idx[-1]))
        runs = [r for r in runs if r[1] - r[0] + 1 >= 2]
        for r in runs:
            if episodes and (r[0] - episodes[-1][1]) < 7:
                episodes[-1] = (episodes[-1][0], r[1])
            else:
                episodes.append(r)
    fire = len(episodes) > 0
    first = post.index[episodes[0][0]] if fire else pd.NaT
    lead = (T_END[v] - first).days if fire else np.nan
    a1_rows.append({"vin_label": v, "failed": int(FAILED[v]), "a1_applicable": True,
                    "a1_fire": fire,
                    "a1_first_alarm": (str(first.date()) if fire else ""),
                    "a1_lead_vs_t_end_d": lead,
                    "a1_lead_vs_jcopen_d": (lead + GAP_DAYS.get(v, 0)
                                            if np.isfinite(lead) else np.nan),
                    "a1_n_episodes": len(episodes),
                    "a1_eval_years": round(len(post) / 365.25, 2)})
a1 = pd.DataFrame(a1_rows)
a1f = a1[(a1.failed == 1) & a1.a1_fire]
print("Failed VINs fired:")
print(a1f[["vin_label", "a1_first_alarm", "a1_lead_vs_t_end_d",
           "a1_lead_vs_jcopen_d", "a1_n_episodes"]].to_string(index=False))
nf_a1 = a1[(a1.failed == 0) & a1.a1_applicable]
fp_eps = nf_a1["a1_n_episodes"].sum()
fp_yrs = nf_a1["a1_eval_years"].sum()
print(f"\nNF (n={len(nf_a1)} applicable): {fp_eps} FP episodes over "
      f"{fp_yrs:.1f} truck-years = {fp_eps / fp_yrs:.2f} episodes/truck-year")
print(nf_a1[nf_a1.a1_n_episodes > 0][
    ["vin_label", "a1_first_alarm", "a1_n_episodes", "a1_eval_years"]]
    .to_string(index=False))

# ── 3. A2 battery-cascade triple detector (causal) ───────────────────────────
print("\n" + "=" * 78)
print("3. A2 BATTERY-CASCADE TRIPLE DETECTOR (causal weekly scan)")
print("=" * 78)


def causal_steps(vals, dates, i, sign, mag, snr_min):
    """Best qualifying median-split step on vals[:i+1] (>=8 pre / >=4 post).
    Returns (step, snr, split_date) of the largest-|step| qualifying split."""
    s, d = vals[:i + 1], dates[:i + 1]
    m = np.isfinite(s)
    s, d = s[m], d[m]
    best = None
    if len(s) < A2_PRE_MIN + A2_POST_MIN:
        return None
    for sp in range(A2_PRE_MIN, len(s) - A2_POST_MIN + 1):
        a, b = s[:sp], s[sp:]
        step = np.median(b) - np.median(a)
        pmad = (np.median(np.abs(a - np.median(a)))
                + np.median(np.abs(b - np.median(b)))) / 2 + 1e-6
        snr = abs(step) / pmad
        ok = (step <= mag if sign < 0 else step >= mag) and snr >= snr_min
        if ok and (best is None or abs(step) > abs(best[0])):
            best = (step, snr, d[sp])
    return best


a2_rows = []
for v in vins:
    w = WKS[v]
    rest = w["vsi_rest_median"].values.astype(float)
    drive = w["vsi_drive_mean"].values.astype(float)
    wkd = w["week"].values
    e = ev_all[(ev_all["vin_label"] == v) & ev_all["dip_depth"].notna()] \
        .sort_values("ts_start")
    has_crank = len(e) >= 20
    fire, fire_wk, det = False, pd.NaT, {}
    if has_crank:
        for i in range(A2_PRE_MIN + A2_POST_MIN - 1, len(w)):
            cut = pd.Timestamp(wkd[i]) + pd.Timedelta(days=6)
            rd = causal_steps(rest, wkd, i, -1, A2_REST_STEP, A2_SNR)
            if rd is None:
                continue
            du = causal_steps(drive, wkd, i, +1, A2_DRIVE_STEP, A2_SNR)
            if du is None:
                continue
            if abs((pd.Timestamp(rd[2]) - pd.Timestamp(du[2])).days) > A2_PAIR_DAYS:
                continue
            e_cut = e[e["ts_start"] <= cut]
            last60 = e_cut[e_cut["ts_start"] > cut - pd.Timedelta(days=60)]["dip_depth"]
            basee = e_cut[e_cut["ts_start"] <= cut - pd.Timedelta(days=60)]["dip_depth"]
            if len(last60) < 10 or len(basee) < 10:
                continue
            if last60.mean() > basee.mean() + A2_DIP_DELTA:
                fire, fire_wk = True, pd.Timestamp(wkd[i])
                det = {"rest_step_V": round(rd[0], 3), "rest_step_date": str(pd.Timestamp(rd[2]).date()),
                       "drive_step_V": round(du[0], 3), "drive_step_date": str(pd.Timestamp(du[2]).date()),
                       "dip_widen_V": round(float(last60.mean() - basee.mean()), 3)}
                break
    lead = (T_END[v] - fire_wk).days if fire else np.nan
    a2_rows.append({"vin_label": v, "failed": int(FAILED[v]),
                    "a2_applicable": has_crank, "a2_fire": fire,
                    "a2_fire_week": (str(fire_wk.date()) if fire else ""),
                    "a2_lead_vs_t_end_d": lead,
                    "a2_lead_vs_jcopen_d": (lead + GAP_DAYS.get(v, 0)
                                            if np.isfinite(lead) else np.nan),
                    **{k: det.get(k, "") for k in
                       ["rest_step_V", "rest_step_date", "drive_step_V",
                        "drive_step_date", "dip_widen_V"]}})
a2 = pd.DataFrame(a2_rows)
print("Fired:")
print(a2[a2.a2_fire][["vin_label", "failed", "a2_fire_week", "a2_lead_vs_t_end_d",
                      "a2_lead_vs_jcopen_d", "rest_step_V", "drive_step_V",
                      "dip_widen_V"]].to_string(index=False))
n_appl_nf = a2[(a2.failed == 0) & a2.a2_applicable].shape[0]
print(f"\nNF false alarms: {a2[(a2.failed == 0)]['a2_fire'].sum()}/{n_appl_nf} "
      f"applicable NF trucks (not applicable: "
      f"{sorted(a2[(a2.failed == 0) & ~a2.a2_applicable]['vin_label'])})")
bat_up = ["VIN18_NF_SM", "VIN12_NF_SM", "VIN3_NF_SM", "VIN5_NF_SM", "VIN17_NF_SM"]
print("Battery-replacement NF trucks (rest-step UP, must NOT fire):",
      {b: bool(a2.loc[a2.vin_label == b, "a2_fire"].iloc[0]) for b in bat_up})

# ── 4. combined policy table ─────────────────────────────────────────────────
print("\n" + "=" * 78)
print("4. COMBINED ALERTING POLICY (Layer1 tier + persistence + A1 + A2)")
print("=" * 78)
val = pers.merge(a1, on=["vin_label", "failed"]).merge(a2, on=["vin_label", "failed"])
val["tier"] = val["vin_label"].map(TIER)
val.to_csv(OUT / "V1_1_SM_alert_validation.csv", index=False)
sens.to_csv(OUT / "V1_1_SM_alert_sensitivity.csv", index=False)

pol_rows = []
for _, r in val.iterrows():
    chans = {}
    if r["pers_fire_end"] and r["pers_terminal_fire_start"]:
        chans["persistence"] = pd.Timestamp(r["pers_terminal_fire_start"])
    if r["a1_fire"] and r["a1_first_alarm"]:
        chans["A1_crank_burst"] = pd.Timestamp(r["a1_first_alarm"])
    if r["a2_fire"] and r["a2_fire_week"]:
        chans["A2_battery_cascade"] = pd.Timestamp(r["a2_fire_week"])
    first_ch = min(chans, key=chans.get) if chans else "NONE"
    first_dt = chans[first_ch] if chans else pd.NaT
    lead = (T_END[r["vin_label"]] - first_dt).days if chans else np.nan
    pol_rows.append({
        "vin_label": r["vin_label"], "failed": r["failed"], "tier": r["tier"],
        "pers_end_fire": bool(r["pers_fire_end"]),
        "a1_fire": bool(r["a1_fire"]) if r["a1_applicable"] else "n/a (SMA-dead)",
        "a2_fire": bool(r["a2_fire"]) if r["a2_applicable"] else "n/a (no crank data)",
        "first_channel": first_ch,
        "first_fire_date": (str(first_dt.date()) if chans else ""),
        "lead_vs_t_end_d": lead,
        "lead_vs_jcopen_d": (lead + GAP_DAYS.get(r["vin_label"], 0)
                             if np.isfinite(lead) else np.nan),
        "nf_alarm_channels": (int(bool(r["pers_fire_end"]))
                              + int(bool(r["a1_fire"])) + int(bool(r["a2_fire"]))
                              + int(r["tier"] in ("RED", "AMBER"))
                              if not r["failed"] else np.nan),
        "nf_lifetime_pers_episodes": (r["pers_n_fire_episodes"]
                                      if not r["failed"] else np.nan)})
pol = pd.DataFrame(pol_rows)
pol.to_csv(OUT / "V1_1_SM_alert_policy.csv", index=False)
print("\nFAILED trucks:")
print(pol[pol.failed == 1].drop(columns="nf_alarm_channels").to_string(index=False))
print("\nNON-FAILED trucks (false-alarm burden):")
print(pol[pol.failed == 0][["vin_label", "tier", "pers_end_fire", "a1_fire",
                            "a2_fire", "first_channel", "nf_alarm_channels"]]
      .to_string(index=False))
print(f"\nNF with ZERO alarm channels: "
      f"{(pol[pol.failed == 0]['nf_alarm_channels'] == 0).sum()}/20")
print("\nSaved:", OUT / "V1_1_SM_alert_validation.csv")
print("Saved:", OUT / "V1_1_SM_alert_policy.csv")
print("Saved:", OUT / "V1_1_SM_alert_sensitivity.csv")
