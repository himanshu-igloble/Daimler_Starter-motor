# V2.1 Starter Motor — Richer Heuristics & Feature Screen — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build & backtest new SM operational heuristics (directional CUSUM/EWMA, conjunction pagers, H4 terminal-state fix, graded RUL) and screen three untouched candidate features, then emit one honest ship/no-ship verdict against the accept-bar.

**Architecture:** Three independent work-streams read-only over frozen artifacts (`walking_scores.csv`, V1.1 alert CSVs, weekly cache, crank-events parquet, feature matrix). Heuristics reuse `H_eval_heuristics.py` metric machinery; feature screens reuse the frozen `V2_incremental_feature_eval.py` nested-LOVO gate. A synthesis task applies the accept-bar (NF < 0.19 ep/truck-yr at recall ≥ 10/14, lead ≳ 116 d) and feature gate (E2 ΔAUROC ≥ +0.01).

**Tech Stack:** Python via `py -3` (NOT `.venv` — it lacks pandas), pandas + numpy + scipy + polars. Windows paths. All scripts run from repo root.

**Spec:** `STARTER MOTOR/V2.1/Plan/V2_1_SM_spec.md`

---

## Conventions for every task

- Run interpreter: `py -3 "<script path>"` (paths contain spaces — always quote).
- Repo root: `D:\Daimler-starter_motor_alternator_battery`
- "Reconciliation gate" is the test-first discipline here: a script must reproduce a **known** number before its new analysis is trusted. If a reconciliation assertion fails, STOP and debug — do not proceed.
- Commit after each task with the message shown. Stage only that task's files.
- All params are **pre-registered in Task 0 and committed before any run** — never edit a param after seeing an outcome.

---

## File Structure

```
STARTER MOTOR/V2.1/
  Plan/V2_1_SM_spec.md                     (exists)
  Plan/V2_1_SM_implementation_plan.md      (this file)
  params/
    accept_bar.json  A1_cusum_params.json  A2_conjunction_params.json
    A3_h4_params.json  B_gate_params.json
  heuristics/
    _heuristic_lib.py                       shared loaders + metric summarizer
    A1_cusum.py  A2_conjunctions.py  A3_h4_terminal.py  A5_graded_rul.py
    out/                                    *.csv outputs
  features/
    _feature_lib.py                         shared px-window + candidate-cache writer
    B2_intercrank_cv.py  B4_zcold_start.py  B5_anr_load.py
    V2_1_feature_gate.py                    adapted copy of V2_incremental_feature_eval.py
    out/
  appendix/
    C_new_data_appendix.md
  reports/
    V2_1_SM_results.md  V2_1_SM_verdict.md  V2_1_SM_exec_summary.md
```

---

## Task 0: Scaffold + pre-register params

**Files:**
- Create: `STARTER MOTOR/V2.1/params/accept_bar.json`
- Create: `STARTER MOTOR/V2.1/params/A1_cusum_params.json`
- Create: `STARTER MOTOR/V2.1/params/A2_conjunction_params.json`
- Create: `STARTER MOTOR/V2.1/params/A3_h4_params.json`
- Create: `STARTER MOTOR/V2.1/params/B_gate_params.json`

- [ ] **Step 1: Write `accept_bar.json`**

```json
{
  "nf_eps_per_truck_year_max": 0.19,
  "nf_eps_strict_lower": true,
  "recall_min_n": 10,
  "recall_denom": 14,
  "lead_min_days": 116,
  "baseline_rule": "H2_pers_red",
  "baseline_metrics": {"recall_n": 10, "med_lead_d": 116, "nf_ever_fire_n": 5, "nf_eps_per_truck_year": 0.19},
  "note": "A new rule SHIPS only if nf_eps < 0.19 AND recall >= 10/14 AND lead ~>= 116 d."
}
```

- [ ] **Step 2: Write `A1_cusum_params.json`**

```json
{
  "rest_vsi_col": "vsi_rest_median",
  "active_days_min": 2,
  "baseline_weeks": 8,
  "min_usable_weeks": 8,
  "cusum_k_sigma": 0.5,
  "cusum_h_sigma": 4.0,
  "ewma_lambda": 0.3,
  "ewma_L_sigma": 3.0,
  "direction": "down",
  "note": "Standardized tabular CUSUM (k,h in sigma units). DOWN-only to reject NF battery up-steps. Frozen a priori."
}
```

- [ ] **Step 3: Write `A2_conjunction_params.json`**

```json
{
  "alignment_window_weeks": 4,
  "pairs": [["H2_pers_red", "A2"], ["H2_pers_red", "H5_fleet_pctile"], ["A1_cusum", "H2_pers_red"]],
  "persistence_state": "terminal",
  "note": "Conjunction fires at week i if BOTH channels fired within [i-3, i]. Frozen a priori."
}
```

- [ ] **Step 4: Write `A3_h4_params.json`**

```json
{
  "min_count": 2,
  "channels": ["tier_ge_amber", "persistence_terminal", "a1_burst", "a2"],
  "persistence_col": "pers_terminal_fire_start",
  "note": "H4 re-run with persistence = TERMINAL episode start (not first-ever-fire). Frozen a priori."
}
```

- [ ] **Step 5: Write `B_gate_params.json`**

```json
{
  "add_threshold_e2": 0.01,
  "mw_alpha": 0.10,
  "auroc_min": 0.60,
  "proxy_corr_max": 0.5,
  "modal_recon_auroc": 0.9357,
  "recon_tol": 0.002,
  "modal_subset": ["vsi_withinwk_std_ratio_30d_w", "rest_vsi_p05_delta90", "vsi_range_trend", "dip_depth_last90_delta"],
  "note": "Frozen V1.1 protocol. ADD iff E2 delta >= +0.01. Frozen a priori."
}
```

- [ ] **Step 6: Create empty output dirs**

Run:
```
py -3 -c "import os; [os.makedirs(r'D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR\V2.1\\'+d, exist_ok=True) for d in ['heuristics\\out','features\\out','appendix','reports']]"
```
Expected: no output, exit 0.

- [ ] **Step 7: Commit**

```bash
git add "STARTER MOTOR/V2.1/params"
git commit -m "chore(v2.1-sm): pre-register frozen params (accept-bar, A1/A2/A3, B gate)"
```

---

## Task 1: Shared heuristic library

**Files:**
- Create: `STARTER MOTOR/V2.1/heuristics/_heuristic_lib.py`

This factors out the loaders + the exact metric definitions from `H_eval_heuristics.py` (recall, median lead, NF episodes/truck-yr) so A1/A2/A3 stay DRY and produce numbers directly comparable to `heuristic_summary.csv`.

- [ ] **Step 1: Write the library**

```python
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
```

- [ ] **Step 2: Verify the library imports and reconciles the H2 baseline**

Run:
```
py -3 -c "import sys; sys.path.insert(0, r'D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR\V2.1\heuristics'); import _heuristic_lib as L; ws=L.load_walking(); t,y=L.load_tend_years(); print('walking rows', len(ws), '| vins', len(ws.vin_label.unique()), '| years loaded', len(y)); rv=L.load_rest_vsi_series(); print('rest-vsi series VINs', len(rv))"
```
Expected: `walking rows` > 800, `vins` = 34, `years loaded` ≥ 34, `rest-vsi series VINs` close to 34 (a few SMA/empty VINs may drop).

- [ ] **Step 3: Commit**

```bash
git add "STARTER MOTOR/V2.1/heuristics/_heuristic_lib.py"
git commit -m "feat(v2.1-sm): shared heuristic lib (loaders + H_eval-identical metrics)"
```

---

## Task 2: A1 — directional CUSUM/EWMA change-point on rest-VSI (headline)

**Files:**
- Create: `STARTER MOTOR/V2.1/heuristics/A1_cusum.py`
- Read (ground truth): `STARTER MOTOR/V1.1/discovery/out/E5_step_changes_all.csv`
- Output: `STARTER MOTOR/V2.1/heuristics/out/A1_cusum_fires.csv`, `A1_cusum_summary.csv`

- [ ] **Step 1: Write `A1_cusum.py`**

```python
"""A1_cusum.py — directional (downward) CUSUM + EWMA change-point on per-VIN
weekly rest-VSI median. Detects battery-cascade step-downs while ignoring NF
battery-replacement step-ups. Params frozen in params/A1_cusum_params.json.

Sanity gate: must alarm on the known E5 rest-VSI down-steps (VIN14_F, VIN6_F,
VIN2_F, VIN3_F) and is checked against NF down-steps (e.g. VIN10_NF -3.0 V).

Run: py -3 "STARTER MOTOR/V2.1/heuristics/A1_cusum.py"
"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR\V2.1")
sys.path.insert(0, str(HERE / "heuristics"))
import _heuristic_lib as L  # noqa: E402

P = json.loads((HERE / "params" / "A1_cusum_params.json").read_text())
OUT = HERE / "heuristics" / "out"


def cusum_down(x, baseline_weeks, k, h):
    """Standardized one-sided downward CUSUM. x: weekly series (nan allowed).
    Returns (first_alarm_pos_in_finite_index_space, n_episodes, alarm_finite_idxs).
    Alarm positions are indices into the ORIGINAL x array."""
    fin = np.where(np.isfinite(x))[0]
    if len(fin) < baseline_weeks + 1:
        return None, 0, []
    base = x[fin[:baseline_weeks]]
    mu0, sd0 = float(np.mean(base)), float(np.std(base))
    if sd0 == 0:
        sd0 = 1e-6
    C = 0.0
    in_alarm = False
    n_ep = 0
    first = None
    alarms = []
    for i in fin[baseline_weeks:]:
        z = (x[i] - mu0) / sd0
        C = max(0.0, C - z - k)          # accumulates on downward deviation
        if C > h:
            if not in_alarm:
                n_ep += 1
                in_alarm = True
            if first is None:
                first = int(i)
            alarms.append(int(i))
        if C == 0.0:
            in_alarm = False
    return first, n_ep, alarms


def ewma_down(x, baseline_weeks, lam, Lsig):
    """Downward EWMA control chart. Returns first alarm index into x or None."""
    fin = np.where(np.isfinite(x))[0]
    if len(fin) < baseline_weeks + 1:
        return None
    base = x[fin[:baseline_weeks]]
    mu0, sd0 = float(np.mean(base)), float(np.std(base))
    if sd0 == 0:
        sd0 = 1e-6
    z = mu0
    for t, i in enumerate(fin[baseline_weeks:], start=1):
        z = lam * x[i] + (1 - lam) * z
        sd_ewma = sd0 * np.sqrt(lam / (2 - lam) * (1 - (1 - lam) ** (2 * t)))
        if z < mu0 - Lsig * sd_ewma:
            return int(i)
    return None


def main():
    tend, years = L.load_tend_years()
    series = L.load_rest_vsi_series(active_days_min=P["active_days_min"])

    cusum_recs, ewma_recs = [], []
    for vin, df in series.items():
        label = 1 if "_F_" in vin else 0
        x = df[P["rest_vsi_col"]].astype(float).values
        weeks = df["week"].values
        # Build a seq frame with cut_date = week for fires_to_record compatibility
        seq = pd.DataFrame({"cut_date": weeks})

        first_c, n_ep_c, _ = cusum_down(x, P["baseline_weeks"], P["cusum_k_sigma"], P["cusum_h_sigma"])
        rows_c = [first_c] if first_c is not None else []
        rec_c = L.fires_to_record(vin, label, seq, rows_c, tend)
        rec_c["n_episodes"] = n_ep_c  # override with true episode count
        cusum_recs.append(rec_c)

        first_e = ewma_down(x, P["baseline_weeks"], P["ewma_lambda"], P["ewma_L_sigma"])
        rows_e = [first_e] if first_e is not None else []
        rec_e = L.fires_to_record(vin, label, seq, rows_e, tend)
        ewma_recs.append(rec_e)

    df_c = pd.DataFrame(cusum_recs)
    df_e = pd.DataFrame(ewma_recs)
    df_c.to_csv(OUT / "A1_cusum_fires.csv", index=False)

    sum_c = L.summarize(df_c, years, "A1_cusum")
    sum_e = L.summarize(df_e, years, "A1_ewma")
    pd.DataFrame([sum_c, sum_e]).to_csv(OUT / "A1_cusum_summary.csv", index=False)

    print("=== A1 CUSUM (down) ===", sum_c)
    print("=== A1 EWMA  (down) ===", sum_e)

    # --- Sanity gate vs E5 ground truth ---
    e5 = pd.read_csv(L.ROOT / "V1.1" / "discovery" / "out" / "E5_step_changes_all.csv")
    gt_down = e5[(e5.signal == "vsi_rest_median") & (e5.step_V <= -1.0) & (e5.snr >= 3)
                 & (e5.vin_label.str.contains("_F_"))]["vin_label"].tolist()
    fired = set(df_c[df_c.ever_fires]["vin_label"])
    hit = [v for v in gt_down if v in fired]
    print(f"\nSANITY: E5 strong F down-steps {gt_down}")
    print(f"        A1 CUSUM fired on {len(hit)}/{len(gt_down)} of them: {hit}")
    if len(gt_down) and len(hit) < max(1, len(gt_down) - 1):
        print("  WARNING: A1 misses most E5 ground-truth down-steps — inspect baseline/threshold.")

    # --- Accept-bar ---
    ok, reason = L.accept(sum_c)
    print(f"\nACCEPT-BAR (A1_cusum): {'SHIP-CANDIDATE' if ok else 'DOES NOT CLEAR'} | {reason}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run A1 and verify reconciliation + sanity**

Run: `py -3 "STARTER MOTOR/V2.1/heuristics/A1_cusum.py"`
Expected:
- Prints A1 CUSUM and EWMA summary dicts with `recall_n_of_14`, `nf_eps_per_truck_year`, `med_lead_d`.
- `SANITY:` line lists the E5 strong failed down-steps and how many A1 fired on. **A1 should fire on most of them** (these are the real battery-cascade failures).
- `ACCEPT-BAR` line states SHIP-CANDIDATE or DOES NOT CLEAR with the numeric reason.

If the sanity gate shows A1 misses most ground-truth down-steps, debug the CUSUM (likely the baseline window or sigma estimate) before continuing — do not tune `h`/`k` (they are pre-registered); instead verify the series alignment and NaN handling.

- [ ] **Step 3: Commit**

```bash
git add "STARTER MOTOR/V2.1/heuristics/A1_cusum.py" "STARTER MOTOR/V2.1/heuristics/out/A1_cusum_fires.csv" "STARTER MOTOR/V2.1/heuristics/out/A1_cusum_summary.csv"
git commit -m "feat(v2.1-sm): A1 directional CUSUM/EWMA change-point on rest-VSI + E5 sanity gate"
```

---

## Task 3: A2 — conjunction pagers

**Files:**
- Create: `STARTER MOTOR/V2.1/heuristics/A2_conjunctions.py`
- Output: `STARTER MOTOR/V2.1/heuristics/out/A2_conjunction_summary.csv`

A2 AND-combines per-week fire states. H2 and H5 fire states are recomputed per-VIN from `walking_scores.csv` (using the exact rules in `H_eval_heuristics.py`). A2-channel and A1 states come from the alert CSV / Task-2 output.

- [ ] **Step 1: Write `A2_conjunctions.py`**

```python
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

    # fleet 85th pctile per k (for H5)
    p85 = {}
    for k in ws["k_weeks"].unique():
        sub = ws[(ws["k_weeks"] == k) & ws["usable"]]["prob"].dropna()
        p85[k] = float(np.percentile(sub, 85)) if len(sub) >= 5 else np.nan

    # A1 fire dates (from Task 2 output): on-from first CUSUM alarm date
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
```

- [ ] **Step 2: Run and verify**

Run: `py -3 "STARTER MOTOR/V2.1/heuristics/A2_conjunctions.py"`
Expected: one line per pair with recall/lead/NF-fire/NF-eps and `SHIP`/`no`. Sanity: every conjunction's `nf_ever_fire_n` must be **≤ each component's** NF-fire count (ANDing cannot increase NF firing). If a conjunction shows MORE NF fires than H2's 5, there is a bug in `conjoin`.

- [ ] **Step 3: Commit**

```bash
git add "STARTER MOTOR/V2.1/heuristics/A2_conjunctions.py" "STARTER MOTOR/V2.1/heuristics/out/A2_conjunction_summary.csv"
git commit -m "feat(v2.1-sm): A2 conjunction pagers (H2&A2, H2&H5, A1&H2) with accept-bar"
```

---

## Task 4: A3 — H4 with terminal-state persistence

**Files:**
- Create: `STARTER MOTOR/V2.1/heuristics/A3_h4_terminal.py`
- Output: `STARTER MOTOR/V2.1/heuristics/out/A3_h4_summary.csv`

Re-runs H4 (≥2 of {tier≥AMBER, persistence, A1-burst, A2}) with persistence read from `pers_terminal_fire_start` instead of `pers_first_fire_week`. The only change vs the original H4 is the persistence column.

- [ ] **Step 1: Write `A3_h4_terminal.py`**

```python
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
```

- [ ] **Step 2: Run and verify**

Run: `py -3 "STARTER MOTOR/V2.1/heuristics/A3_h4_terminal.py"`
Expected: prints the A3 summary. Sanity: `nf_ever_fire_n` should be **< 20** (the whole point of the fix); if it is still 20/20, confirm `pers_terminal_fire_start` is populated and parsed as a date (not all-NaT).

- [ ] **Step 3: Commit**

```bash
git add "STARTER MOTOR/V2.1/heuristics/A3_h4_terminal.py" "STARTER MOTOR/V2.1/heuristics/out/A3_h4_summary.csv"
git commit -m "feat(v2.1-sm): A3 H4 re-run with terminal-state persistence (fixes NF inflation)"
```

---

## Task 5: A5 — graded RUL escalation table

**Files:**
- Create: `STARTER MOTOR/V2.1/heuristics/A5_graded_rul.py`
- Output: `STARTER MOTOR/V2.1/heuristics/out/A5_graded_rul_policy.csv`, `A5_per_truck_bands.csv`

Productizes V2's D6 evidence-window matrix into a lookup + per-truck band assignment. No new modeling — the windows are fixed constants from the spec.

- [ ] **Step 1: Write `A5_graded_rul.py`**

```python
"""A5_graded_rul.py — graded inspection-window policy from V2 D6 evidence matrix.
Maps the strongest currently-active signal -> a recommended inspection window.
No new modeling; windows are fixed constants from the V2 D6 finding.

Run: py -3 "STARTER MOTOR/V2.1/heuristics/A5_graded_rul.py"
"""
import sys
from pathlib import Path
import pandas as pd

HERE = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR\V2.1")
sys.path.insert(0, str(HERE / "heuristics"))
import _heuristic_lib as L  # noqa: E402

OUT = HERE / "heuristics" / "out"

# D6 evidence-window matrix (fixed constants from V2 program)
POLICY = [
    {"signal": "A2_battery_cascade", "window_days_lo": 28, "window_days_hi": 91,
     "action": "Inspect within 4-13 weeks; battery-first triage", "n_support": 4},
    {"signal": "persistence_AND_RED", "window_days_lo": 126, "window_days_hi": 284,
     "action": "Schedule inspection ~6 months (median 206 d)", "n_support": 10},
    {"signal": "AMBER_only", "window_days_lo": None, "window_days_hi": None,
     "action": "Monitor; no failed truck observed in AMBER-only (empirically empty)", "n_support": 0},
]


def main():
    pd.DataFrame(POLICY).to_csv(OUT / "A5_graded_rul_policy.csv", index=False)

    # Assign each currently-RED/alarmed truck a band, using the latest cut (k=0).
    ws = L.load_walking()
    val = L.load_alert_validation()
    latest = ws[ws["k_weeks"] == 0].set_index("vin_label")
    rows = []
    for vin in ws["vin_label"].unique():
        tier = latest.loc[vin, "tier"] if vin in latest.index else "NA"
        a2_on = vin in val.index and pd.notna(val.loc[vin, "a2_fire_week"])
        if a2_on:
            band = "A2_battery_cascade"
        elif tier == "RED":
            band = "persistence_AND_RED"
        elif tier == "AMBER":
            band = "AMBER_only"
        else:
            band = "GREEN_no_action"
        rows.append({"vin_label": vin, "tier_k0": tier, "a2_active": a2_on, "band": band})
    pd.DataFrame(rows).to_csv(OUT / "A5_per_truck_bands.csv", index=False)
    print("Saved A5 policy + per-truck bands. Band counts:")
    print(pd.DataFrame(rows)["band"].value_counts().to_string())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run and verify**

Run: `py -3 "STARTER MOTOR/V2.1/heuristics/A5_graded_rul.py"`
Expected: prints band counts; both CSVs written. Sanity: every VIN appears exactly once in `A5_per_truck_bands.csv` (34 rows).

- [ ] **Step 3: Commit**

```bash
git add "STARTER MOTOR/V2.1/heuristics/A5_graded_rul.py" "STARTER MOTOR/V2.1/heuristics/out/A5_graded_rul_policy.csv" "STARTER MOTOR/V2.1/heuristics/out/A5_per_truck_bands.csv"
git commit -m "feat(v2.1-sm): A5 graded RUL escalation policy + per-truck band assignment"
```

---

## Task 6: Shared feature library (px window + candidate cache)

**Files:**
- Create: `STARTER MOTOR/V2.1/features/_feature_lib.py`

Provides the L40-window construction (verbatim from `V2_incremental_feature_eval.py` lines 222-242) so B2/B4/B5 window their candidates identically to production, and a helper to write a candidate cache CSV.

- [ ] **Step 1: Write the library**

```python
"""_feature_lib.py — shared windowing + candidate-cache helpers for V2.1 B-screens.
px (per-VIN L40 window) is built identically to V2_incremental_feature_eval.py so
candidate deltas are windowed exactly like the production features.
"""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR")
EVENTS = ROOT / "cache" / "events" / "V1_SM_crank_events.parquet"
WEEKLY_DIR = ROOT / "cache" / "weekly"
MATRIX = ROOT / "V1.1" / "results" / "V1_1_SM_feature_matrix.csv"
OUT = ROOT / "V2.1" / "features" / "out"

SMA_DEAD = ["VIN8_F_SM", "VIN9_F_SM", "VIN10_NF_SM", "VIN11_NF_SM",
            "VIN12_NF_SM", "VIN13_NF_SM", "VIN20_NF_SM"]


def vins_in_order():
    return pd.read_csv(MATRIX)["vin_label"].tolist()


def build_px():
    """Per-VIN proxy/window frame (verbatim from V2_incremental_feature_eval.py)."""
    wk_all = pd.concat(
        [pd.read_parquet(f) for f in sorted(WEEKLY_DIR.glob("V1_SM_weekly_*.parquet"))],
        ignore_index=True)
    wk_all["week"] = pd.to_datetime(wk_all["week"])
    rows = []
    for vin in vins_in_order():
        w = wk_all[wk_all["vin_label"] == vin]
        wmf = w[w["active_days"] >= 2]
        wm40 = wmf.sort_values("week").tail(40)
        t_end_approx = wmf["week"].max() + pd.Timedelta(days=6)
        rows.append({
            "vin_label": vin,
            "t_end_approx": t_end_approx,
            "t_90_cutoff": t_end_approx - pd.Timedelta(days=90),
            "win_start_l40": wm40["week"].iloc[0] if len(wm40) else pd.NaT,
        })
    return pd.DataFrame(rows).set_index("vin_label")


def load_events_nonartifact():
    ev = pd.read_parquet(EVENTS)
    ev = ev[ev["artifact"] == False].copy()
    ev["ts_start"] = pd.to_datetime(ev["ts_start"])
    return ev


def write_candidate_cache(name, value_by_vin):
    """value_by_vin: dict vin_label -> float (NaN allowed). Forces SMA-dead -> NaN."""
    vins = vins_in_order()
    vals = []
    for v in vins:
        x = value_by_vin.get(v, np.nan)
        vals.append(np.nan if v in SMA_DEAD else x)
    df = pd.DataFrame({"vin_label": vins, name: vals})
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / f"{name}_cache.csv", index=False)
    print(f"  wrote {OUT / (name + '_cache.csv')} "
          f"({int(np.isfinite(vals).sum())}/34 non-NaN, SMA-dead forced NaN)")
    return df
```

- [ ] **Step 2: Verify px builds**

Run:
```
py -3 -c "import sys; sys.path.insert(0, r'D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR\V2.1\features'); import _feature_lib as F; px=F.build_px(); print('px rows', len(px)); print(px[['t_end_approx','win_start_l40']].head(3).to_string()); ev=F.load_events_nonartifact(); print('non-artifact events', len(ev), '| cols', list(ev.columns))"
```
Expected: `px rows` = 34; `non-artifact events` ~17-20k; columns include `ts_start`, `dip_depth`, `days_before_t_end`.

- [ ] **Step 3: Commit**

```bash
git add "STARTER MOTOR/V2.1/features/_feature_lib.py"
git commit -m "feat(v2.1-sm): shared feature lib (L40 px window + candidate cache writer)"
```

---

## Task 7: B2 — inter-crank-interval CV feature

**Files:**
- Create: `STARTER MOTOR/V2.1/features/B2_intercrank_cv.py`
- Output: `STARTER MOTOR/V2.1/features/out/intercrank_cv_delta90_cache.csv`

- [ ] **Step 1: Write `B2_intercrank_cv.py`**

```python
"""B2_intercrank_cv.py — candidate feature: change in coefficient-of-variation of
inter-crank intervals, last-90d vs L40 baseline. Timing-burstiness of cranks
(solenoid intermittency proxy). Writes a candidate cache for the V2.1 gate.

Run: py -3 "STARTER MOTOR/V2.1/features/B2_intercrank_cv.py"
"""
import sys
from pathlib import Path
import numpy as np

HERE = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR\V2.1")
sys.path.insert(0, str(HERE / "features"))
import _feature_lib as F  # noqa: E402


def cv(intervals_s):
    x = np.asarray(intervals_s, dtype=float)
    x = x[np.isfinite(x) & (x > 0)]
    if len(x) < 3:
        return np.nan
    m = x.mean()
    return float(x.std() / m) if m > 0 else np.nan


def main():
    px = F.build_px()
    ev = F.load_events_nonartifact()
    out = {}
    for vin in F.vins_in_order():
        if vin in F.SMA_DEAD:
            out[vin] = np.nan
            continue
        e = ev[ev["vin_label"] == vin].sort_values("ts_start")
        if len(e) < 8 or vin not in px.index or px.loc[vin].isna().any():
            out[vin] = np.nan
            continue
        win_start = px.loc[vin, "win_start_l40"]
        t90 = px.loc[vin, "t_90_cutoff"]
        e = e[e["ts_start"] >= win_start]
        ts = e["ts_start"].values
        if len(ts) < 6:
            out[vin] = np.nan
            continue
        intervals = np.diff(ts).astype("timedelta64[s]").astype(float)
        starts = ts[1:]  # interval attributed to its end-event start
        last90 = intervals[starts >= np.datetime64(t90)]
        base = intervals[starts < np.datetime64(t90)]
        cv90, cvb = cv(last90), cv(base)
        out[vin] = (cv90 - cvb) if (np.isfinite(cv90) and np.isfinite(cvb)) else np.nan
    F.write_candidate_cache("intercrank_cv_delta90", out)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run and verify**

Run: `py -3 "STARTER MOTOR/V2.1/features/B2_intercrank_cv.py"`
Expected: prints `wrote ...intercrank_cv_delta90_cache.csv (N/34 non-NaN ...)` with N roughly 20-27 (SMA-dead + short-history VINs are NaN).

- [ ] **Step 3: Commit**

```bash
git add "STARTER MOTOR/V2.1/features/B2_intercrank_cv.py" "STARTER MOTOR/V2.1/features/out/intercrank_cv_delta90_cache.csv"
git commit -m "feat(v2.1-sm): B2 inter-crank-interval CV candidate feature"
```

---

## Task 8: B4 — ≥8h cold-start dip, per-VIN z-scored

**Files:**
- Create: `STARTER MOTOR/V2.1/features/B4_zcold_start.py`
- Output: `STARTER MOTOR/V2.1/features/out/z_cold_dip_delta90_cache.csv`

Cold = first crank after ≥ 8 h (28800 s) since the previous event end. Per-VIN z-score each cold event's `dip_depth` using the VIN's own baseline mean/sd, then delta = mean(z, last90) − mean(z, baseline). The ≥8h gate + z-scoring is what distinguishes this from the held P3 `cold_dip_delta90` (6h, raw).

- [ ] **Step 1: Write `B4_zcold_start.py`**

```python
"""B4_zcold_start.py — candidate feature: per-VIN z-scored cold-start (>=8h rest)
dip-depth delta, last-90d vs L40 baseline. Distinct from held P3 cold_dip (6h,raw).

Run: py -3 "STARTER MOTOR/V2.1/features/B4_zcold_start.py"
"""
import sys
from pathlib import Path
import numpy as np

HERE = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR\V2.1")
sys.path.insert(0, str(HERE / "features"))
import _feature_lib as F  # noqa: E402

REST_GAP_S = 8 * 3600  # >= 8 hours


def main():
    px = F.build_px()
    ev = F.load_events_nonartifact()
    out = {}
    for vin in F.vins_in_order():
        if vin in F.SMA_DEAD:
            out[vin] = np.nan
            continue
        e = ev[ev["vin_label"] == vin].sort_values("ts_start").reset_index(drop=True)
        if len(e) < 8 or vin not in px.index or px.loc[vin].isna().any():
            out[vin] = np.nan
            continue
        win_start = px.loc[vin, "win_start_l40"]
        t90 = px.loc[vin, "t_90_cutoff"]
        ts = e["ts_start"].values
        # gap from previous event start (proxy for rest) — first event is cold by default
        gaps = np.diff(ts).astype("timedelta64[s]").astype(float)
        is_cold = np.concatenate([[True], gaps >= REST_GAP_S])
        cold = e[is_cold].copy()
        cold = cold[cold["ts_start"] >= win_start]
        dip = cold["dip_depth"].astype(float).values
        cts = cold["ts_start"].values
        m = np.isfinite(dip)
        dip, cts = dip[m], cts[m]
        if len(dip) < 6:
            out[vin] = np.nan
            continue
        mu, sd = dip.mean(), dip.std()
        if sd == 0:
            out[vin] = np.nan
            continue
        z = (dip - mu) / sd
        last90 = z[cts >= np.datetime64(t90)]
        base = z[cts < np.datetime64(t90)]
        out[vin] = (last90.mean() - base.mean()) if (len(last90) >= 3 and len(base) >= 3) else np.nan
    F.write_candidate_cache("z_cold_dip_delta90", out)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run and verify**

Run: `py -3 "STARTER MOTOR/V2.1/features/B4_zcold_start.py"`
Expected: prints `wrote ...z_cold_dip_delta90_cache.csv (N/34 non-NaN ...)`. N may be lower than B2 (the ≥8h gate + ≥6 cold events per window is strict); N ≥ 12 is acceptable. If N < 8, the screen is underpowered — note it in the report rather than relaxing the pre-registered 8h gate.

- [ ] **Step 3: Commit**

```bash
git add "STARTER MOTOR/V2.1/features/B4_zcold_start.py" "STARTER MOTOR/V2.1/features/out/z_cold_dip_delta90_cache.csv"
git commit -m "feat(v2.1-sm): B4 >=8h per-VIN z-scored cold-start dip candidate feature"
```

---

## Task 9: B5 — ANR engine-torque / load-context screen

**Files:**
- Create: `STARTER MOTOR/V2.1/features/B5_anr_load.py`
- Output: `STARTER MOTOR/V2.1/features/out/anr_pos_mean_delta90_cache.csv`

Weakest physics link — kept for completeness. Uses the weekly cache `anr_pos_mean` (already computed), no raw scan needed. Candidate = change in mean positive engine-torque (load level), last-90d vs L40 baseline.

- [ ] **Step 1: Write `B5_anr_load.py`**

```python
"""B5_anr_load.py — candidate feature: ANR (engine-torque) load-context delta.
anr_pos_mean (weekly cache) last-90d vs L40 baseline. Weakest physics link to
starter failure; screened for completeness only.

Run: py -3 "STARTER MOTOR/V2.1/features/B5_anr_load.py"
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR\V2.1")
sys.path.insert(0, str(HERE / "features"))
import _feature_lib as F  # noqa: E402


def main():
    px = F.build_px()
    wk = pd.concat([pd.read_parquet(f) for f in sorted(F.WEEKLY_DIR.glob("V1_SM_weekly_*.parquet"))],
                   ignore_index=True)
    wk["week"] = pd.to_datetime(wk["week"])
    out = {}
    for vin in F.vins_in_order():
        if vin in F.SMA_DEAD:
            out[vin] = np.nan
            continue
        w = wk[(wk["vin_label"] == vin) & (wk["active_days"] >= 2)].sort_values("week")
        if len(w) < 8 or vin not in px.index or px.loc[vin].isna().any():
            out[vin] = np.nan
            continue
        win_start, t90 = px.loc[vin, "win_start_l40"], px.loc[vin, "t_90_cutoff"]
        w = w[w["week"] >= win_start]
        a = w["anr_pos_mean"].astype(float)
        last90 = a[w["week"] >= t90].dropna()
        base = a[w["week"] < t90].dropna()
        out[vin] = (last90.mean() - base.mean()) if (len(last90) >= 2 and len(base) >= 2) else np.nan
    F.write_candidate_cache("anr_pos_mean_delta90", out)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run and verify**

Run: `py -3 "STARTER MOTOR/V2.1/features/B5_anr_load.py"`
Expected: prints `wrote ...anr_pos_mean_delta90_cache.csv (N/34 non-NaN ...)` with N ~24-27.

- [ ] **Step 3: Commit**

```bash
git add "STARTER MOTOR/V2.1/features/B5_anr_load.py" "STARTER MOTOR/V2.1/features/out/anr_pos_mean_delta90_cache.csv"
git commit -m "feat(v2.1-sm): B5 ANR load-context candidate feature (completeness screen)"
```

---

## Task 10: B feature gate (adapt the frozen V1.1 protocol)

**Files:**
- Create: `STARTER MOTOR/V2.1/features/V2_1_feature_gate.py` (copy of `V2_program/analysis/features/V2_incremental_feature_eval.py` with candidate loading swapped)
- Output: `STARTER MOTOR/V2.1/features/out/V2_1_gate_summary.json`

This reuses the EXACT frozen protocol (ridge/LOVO, modal-4 reconciliation = 0.9357, E1/E2/E3) — do not re-derive the math.

- [ ] **Step 1: Copy the frozen eval script**

Run:
```
py -3 -c "import shutil; shutil.copy(r'D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR\V2_program\analysis\features\V2_incremental_feature_eval.py', r'D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR\V2.1\features\V2_1_feature_gate.py')"
```

- [ ] **Step 2: Edit candidate loading**

In `V2_1_feature_gate.py`:

1. Change `OUT` (near line 28) to:
```python
OUT = ROOT / "V2.1" / "features" / "out"
```

2. **Delete** the cold_dip block (lines ~244-257) and the rpm_rise computation block (lines ~259-387). **Replace** with loading the three V2.1 candidate caches:
```python
# ── V2.1 candidates from cached CSVs ────────────────────────────────────────
CAND_FEATS = ["intercrank_cv_delta90", "z_cold_dip_delta90", "anr_pos_mean_delta90"]
for cand in CAND_FEATS:
    c = pd.read_csv(OUT / f"{cand}_cache.csv")
    cmap = dict(zip(c["vin_label"], c[cand]))
    arr = np.array([cmap.get(v, np.nan) for v in vins], dtype=float)
    for i, v in enumerate(vins):
        if v in SMA_DEAD:
            arr[i] = np.nan
    mat_ext = mat.copy() if cand == CAND_FEATS[0] and "mat_ext" not in dir() else mat_ext
    mat_ext[cand] = arr
    print(f"  {cand}: {np.isfinite(arr).sum()}/34 non-NaN")
```
(Place `mat_ext = mat.copy()` once before the loop instead of the inline trick if clearer.)

3. In the E1 loop, `CAND_FEATS` is already defined above — keep the E1 admissibility loop as-is (it iterates `CAND_FEATS`). The proxy flag uses `abs(r) > 0.5` per `B_gate_params.json` (`proxy_corr_max: 0.5`) — already matches.

4. In E2 (lines ~508-524), replace the three hardcoded candidate blocks with a loop:
```python
e2 = {}
for cand in CAND_FEATS:
    p_c = plain_lovo(make_X_with(mat_ext, [cand]), y)
    a_c = rank_auroc(p_c, y)
    e2[cand] = {"auroc": round(float(a_c), 4), "delta": round(float(a_c - a_modal), 4)}
    print(f"  modal-4 + {cand}: AUROC={a_c:.4f} delta={a_c - a_modal:+.4f}")
```

5. **E3 conditional:** only run the nested expansion if ANY candidate cleared E2 (`delta >= 0.01`). Replace the E3 block guard:
```python
ADD_THR = 0.01
passers = [c for c in CAND_FEATS if e2[c]["delta"] >= ADD_THR]
if not passers:
    print("\nE3 SKIPPED — no candidate cleared E2 (+0.01). All HOLD.")
    a_nested_exp = None
else:
    EXPANDED_POOL = V1_1_POOL + passers
    p_nested_exp, details_exp = nested_lovo(mat_ext, y, EXPANDED_POOL)
    a_nested_exp = rank_auroc(p_nested_exp, y)
    print(f"  Expanded nested AUROC = {a_nested_exp:.4f} (V1.1 = {V1_1_NESTED_AUROC})")
```

6. Replace the E4/verdict + JSON dump at the end with:
```python
verdicts = {}
for cand in CAND_FEATS:
    flag = adm_df[adm_df.feature == cand]["proxy_flags"].iloc[0]
    d = e2[cand]["delta"]
    if flag:
        verdicts[cand] = ("HOLD", f"proxy flag: {flag}")
    elif d >= ADD_THR:
        verdicts[cand] = ("ADD", f"E2 delta={d:+.4f} >= +0.01")
    elif d > 0:
        verdicts[cand] = ("HOLD", f"real but weak: E2 delta={d:+.4f}")
    else:
        verdicts[cand] = ("REJECT", f"E2 delta={d:+.4f} <= 0")
    print(f"  {cand}: {verdicts[cand][0]} — {verdicts[cand][1]}")

import json
summary = {"reconciliation": {"computed": round(float(a_modal), 4), "expected": MODAL_NONNESTED_AUROC_EXPECTED, "pass": diff <= 0.002},
           "E1": adm_df.to_dict(orient="records"), "E2": e2,
           "E3_expanded_nested_auroc": (round(float(a_nested_exp), 4) if a_nested_exp is not None else None),
           "verdicts": {k: {"verdict": v[0], "reason": v[1]} for k, v in verdicts.items()}}
(OUT / "V2_1_gate_summary.json").write_text(json.dumps(summary, indent=2, default=str))
print("\nSaved V2_1_gate_summary.json")
```

- [ ] **Step 3: Run the gate and verify reconciliation**

Run: `py -3 "STARTER MOTOR/V2.1/features/V2_1_feature_gate.py"`
Expected:
- `Modal-4 LOVO AUROC = 0.9357 (expected 0.9357) ... Reconciliation OK` — **if this fails (diff > 0.002) the script exits 1; STOP and debug the candidate merge, not the protocol.**
- E1 admissibility lines for all three candidates.
- E2 delta lines (most likely all < +0.01 → HOLD, consistent with the data ceiling).
- Verdict lines for each candidate; `V2_1_gate_summary.json` written.

- [ ] **Step 4: Commit**

```bash
git add "STARTER MOTOR/V2.1/features/V2_1_feature_gate.py" "STARTER MOTOR/V2.1/features/out/V2_1_gate_summary.json"
git commit -m "feat(v2.1-sm): B feature gate (frozen V1.1 nested-LOVO protocol, 3 candidates)"
```

---

## Task 11: C — new-data acquisition appendix (documentation)

**Files:**
- Create: `STARTER MOTOR/V2.1/appendix/C_new_data_appendix.md`

No modeling. DICV-facing. For each path: signal unlocked, why current 6-signal/5s data cannot reach it, cost, integration effort, expected payoff.

- [ ] **Step 1: Write the appendix**

Write `C_new_data_appendix.md` with this structure (fill each section with the content below — these are the established facts, not placeholders):

```markdown
---
title: "V2.1 SM — New-Data Acquisition Appendix (what actually breaks the data ceiling)"
status: "complete"
created: "2026-06-22"
audience: "DICV"
---

# New-Data Acquisition Appendix

The supervised classifier is at a **data ceiling** (0.9321 nested AUROC, 10-wk
horizon, n=14 failed). No feature engineered from the current 6 signals at 5 s
sampling has beaten it. The only way to materially improve detection is new data.

## C1 — Intelligent Battery Sensor / current clamp
- **Signal unlocked:** crank in-rush current waveform → brush wear, solenoid
  contact resistance, mechanical drag. These are the actual SM failure modes;
  voltage at 5 s only sees the secondary battery-cascade effect.
- **Why current data can't reach it:** 5 s VSI cannot resolve the sub-second
  crank current transient; SMA is a binary flag, not a load measurement.
- **Cost:** ₹2–15k/truck. **Effort:** hardware fit + CAN integration.
- **Expected payoff:** direct brush/solenoid degradation channel; plausibly the
  missing 60–120 d lead-time signal for the abrupt-failure archetypes (A4).

## C2 — High-rate VSI firmware trigger during SMA=1
- **Signal unlocked:** crank voltage waveform sampled > 0.2 Hz only while
  SMA=1 → dip shape, recovery transient, brush-wear micro-structure.
- **Why current data can't reach it:** the 5 s grid quantizes 93% of cranks to a
  single sample (the KT "+48% duration" finding collapsed for this reason).
- **Cost:** firmware-only (no hardware). **Effort:** telematics firmware change.
- **Expected payoff:** revives the 60–120 d brush-wear channel shelved in V1.1.

## C3 — Full true-CWR scan + SALEDATE/odometer/maintenance ingest
- **Signal unlocked:** age/mileage normalization; completes the partial B5 true
  crank-while-running scan (only 9/15 active NF processed in V2).
- **Why current data can't reach it:** SALEDATE present only on failed files;
  no odometer in telemetry; maintenance events unlabeled.
- **Cost:** data request (specs already drafted in v2_system/specs/).
- **Expected payoff:** removes the n_weeks/t_start recruitment-epoch confounders
  that cap honest AUROC; enables per-age hazard normalization.

## Priority
C2 (firmware-only, cheapest) → C1 (direct failure-mode channel) → C3 (removes
confounders). C1+C2 together are the realistic path to beating 0.932.
```

- [ ] **Step 2: Commit**

```bash
git add "STARTER MOTOR/V2.1/appendix/C_new_data_appendix.md"
git commit -m "docs(v2.1-sm): C new-data acquisition appendix (DICV-facing)"
```

---

## Task 12: Synthesis — comparison table, verdict, exec summary

**Files:**
- Create: `STARTER MOTOR/V2.1/reports/V2_1_SM_results.md`
- Create: `STARTER MOTOR/V2.1/reports/V2_1_SM_verdict.md`
- Create: `STARTER MOTOR/V2.1/reports/V2_1_SM_exec_summary.md`
- Helper: `STARTER MOTOR/V2.1/reports/build_comparison.py`

- [ ] **Step 1: Write `build_comparison.py` to assemble the master comparison table**

```python
"""build_comparison.py — assemble the V2.1 recall/FP/lead comparison vs H2 baseline.
Reads all A-rule summaries + the B gate summary, applies the accept-bar,
writes reports/V2_1_comparison.csv.

Run: py -3 "STARTER MOTOR/V2.1/reports/build_comparison.py"
"""
import json
from pathlib import Path
import pandas as pd

HO = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR\V2.1\heuristics\out")
RO = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR\V2.1\reports")

baseline = {"heuristic": "H2_baseline", "recall_n_of_14": 10, "med_lead_d": 116,
            "nf_ever_fire_n": 5, "nf_eps_per_truck_year": 0.19, "accept": "—"}
frames = [pd.DataFrame([baseline])]
for f in ["A1_cusum_summary.csv", "A2_conjunction_summary.csv", "A3_h4_summary.csv"]:
    p = HO / f
    if p.exists():
        frames.append(pd.read_csv(p))
cmp = pd.concat(frames, ignore_index=True)
cols = ["heuristic", "recall_n_of_14", "med_lead_d", "nf_ever_fire_n", "nf_eps_per_truck_year"]
cmp = cmp[[c for c in cols if c in cmp.columns] + [c for c in cmp.columns if c not in cols]]
cmp.to_csv(RO / "V2_1_comparison.csv", index=False)
print(cmp[cols].to_string(index=False))

gate = json.loads((RO.parent / "features" / "out" / "V2_1_gate_summary.json").read_text())
print("\nFeature verdicts:")
for k, v in gate["verdicts"].items():
    print(f"  {k}: {v['verdict']} — {v['reason']}")
```

- [ ] **Step 2: Run it**

Run: `py -3 "STARTER MOTOR/V2.1/reports/build_comparison.py"`
Expected: prints the comparison table (every A-rule vs H2) and the three feature verdicts. `V2_1_comparison.csv` written.

- [ ] **Step 3: Write `V2_1_SM_results.md`**

Document each work-stream's numbers from the out/ CSVs: A1 CUSUM/EWMA summary + E5 sanity result; A2 each conjunction; A3 terminal-state H4 vs original; A5 band counts; B2/B4/B5 E1+E2 + verdicts (with the Benjamini-Hochberg note for the ~7 tests); reference the C appendix. Include the SCREEN-GRADE caveat and the n_weeks/t_start leak ceilings.

- [ ] **Step 4: Write `V2_1_SM_verdict.md`**

State the ship decision per the accept-bar: which (if any) A-rule clears NF < 0.19 ep/yr at recall ≥ 10/14 and lead ≳ 116 d. Explicitly allow "NO IMPROVEMENT / all HOLD" if nothing clears. If A1 or a conjunction ships, note the follow-on (integrate into `v2_system/`). List feature verdicts (expected HOLD). Paste the comparison table.

- [ ] **Step 5: Write `V2_1_SM_exec_summary.md`**

One page: the question (richer heuristics + more features?), the honest answer (data ceiling; wins are operational), the single shipped change (or "none — H2 remains best"), and the new-data ask (C).

- [ ] **Step 6: Commit**

```bash
git add "STARTER MOTOR/V2.1/reports"
git commit -m "docs(v2.1-sm): synthesis — comparison table, ship verdict, exec summary"
```

---

## Self-Review (completed by plan author)

**Spec coverage:** A1→Task 2; A2→Task 3; A3→Task 4; A5→Task 5; B2→Task 7; B4→Task 8; B5→Task 9; B gate→Task 10; C→Task 11; synthesis/accept-bar→Task 12; pre-registration/rigor→Task 0; shared libs→Tasks 1 & 6. All spec sections mapped.

**Placeholder scan:** no TBD/TODO; novel code is complete; reuse points cite exact files + edits.

**Type/name consistency:** `_heuristic_lib` functions (`load_walking`, `vin_seq`, `fires_to_record`, `summarize`, `accept`, `load_rest_vsi_series`) are used identically across A1/A2/A3; `_feature_lib` (`build_px`, `load_events_nonartifact`, `write_candidate_cache`, `vins_in_order`, `SMA_DEAD`) used identically across B2/B4/B5; candidate cache names (`intercrank_cv_delta90`, `z_cold_dip_delta90`, `anr_pos_mean_delta90`) match between producer scripts and the gate's `CAND_FEATS`.

**Known risks flagged in-plan:** A1 DOWN-only is not automatically clean (VIN10_NF −3.0V) — the accept-bar backtest is the real test (Task 2 sanity gate); B-screens are expected to HOLD (data ceiling); reconciliation gates (H2 baseline, modal-4=0.9357) guard against silent drift.
