# V3.1 Starter Motor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the SM operational-state engine, run the 7 pre-registered candidates through the frozen E0→E3 gate, and ship the battery-vs-starter attribution triage channel — per the approved spec `STARTER MOTOR/V3.1/Plan/V3_1_SM_spec.md`.

**Architecture:** Phase 0 probes freeze empirical parameters → rule-based state engine (row states → episodes → trips/soak/engine-hours → weekly rollups, never touching frozen caches) → candidate factor caches → cloned V3 gate machinery (E0 reconciliation 0.9357 ± 0.002) → descriptive catalog + channels + reports. Pre-registration: all `params/` JSONs are committed in Task 0 before any result exists.

**Tech Stack:** Python via `py -3` (NOT `.venv`), polars (lazy scans) + pandas + numpy + scipy + scikit-learn + matplotlib, pytest.

---

## Read this first (context you must have)

1. **Interpreter & console:** run everything with `py -3`. On this Windows box the console is cp1252 — polars box-drawing output crashes prints. Prefix every python run with `$env:PYTHONIOENCODING='utf-8';` in PowerShell.
2. **Paths have spaces** (`STARTER MOTOR`). Quote every path in every command.
3. **READ-ONLY inputs — never modify:**
   - `Data/processed/starter_motor_complete/2026-03-06-12-38-23-starter_motor_failed.parquet` (30,925,573 rows, 14 VINs, extra cols SALEDATE/JCOPENDATE/Failure_type)
   - `Data/processed/starter_motor_complete/2026-03-06-12-39-14-starter_motor_non_failed.parquet` (76,250,496 rows, 20 VINs)
   - `STARTER MOTOR/cache/events/V1_SM_crank_events.parquet` — columns: `vin_label, event_id, ts_start, dur_s, artifact, baseline_vsi, min_vsi_crank, dip_depth, rpm_max_15s, success, recovery_slope, retry_within_120s, days_before_t_end`
   - `STARTER MOTOR/cache/weekly/V1_SM_weekly_*.parquet` — per-VIN weekly cache incl. `vin_label, week, active_days, vsi_rest_median, vsi_rest_p05, vsi_drive_std, ...`
   - `STARTER MOTOR/V1.1/results/V1_1_SM_feature_matrix.csv` — canonical VIN order (`vin_label`), label (`failed`), modal-4 columns
   - `STARTER MOTOR/V1.1/results/V1_1_SM_alert_validation.csv` — per-VIN alert channel results; T1 uses `a2_fire` (bool)
   - `STARTER MOTOR/V1.1/discovery/out/E2_failed_vin_archetypes.csv` — columns `vin_label, archetype, ...` (14 failed VINs)
   - `STARTER MOTOR/V2.1/heuristics/out/A5_per_truck_bands.csv` — columns `vin_label, tier_k0, a2_active, band`
   - `STARTER MOTOR/V2.1/features/_feature_lib.py` — reused helpers: `vins_in_order()`, `build_px()` (per-VIN `t_end_approx, t_90_cutoff, win_start_l40`), `load_events_nonartifact()`
   - `STARTER MOTOR/V3/features/_gate_core.py` — gate math: `plain_lovo(X, y)`, `nested_lovo(Xdf, y, feats)`, `rank_auroc(s, y)`, `mw_p(a, b)` (copied verbatim in Task 9, never edited)
   - `STARTER MOTOR/V3/features/_factors.py` — reused: `dip_depth_last90_level(ev, px, vin)`
4. **Data facts** (verified 2026-07-02): 5-second cadence; duplicate timestamps common (dt=0 rows — keep, treat as same instant); VSI already in volts (masking ≤0/≥255 and ×0.2 rescale >36 V are harmless no-ops, kept for contract); RPM/CSP 65535 sentinels absent but masked anyway; timestamps tz-naive = vehicle-local (IST assumption).
5. **Discipline:** seeds 42/43; SMA-dead cohort → NaN for event-rate candidates (exempt: `dropout_share_delta90`); no label access in Tasks 1–5 (probes/state engine are label-blind); catalog label-separation stats only AFTER the gate (Task 11 asserts the gate summary exists).
6. **Frozen numbers:** E0 must reproduce non-nested modal-4 LOVO AUROC = 0.9357 (|Δ| ≤ 0.002); nested reference 0.9321; E2 bar +0.01; E1: MW p ≤ 0.10, oriented AUROC ≥ 0.60, proxy Spearman |ρ| ≤ 0.5 vs {n_weeks, t_start, span}, redundancy Pearson |r| < 0.85 vs modal-4.

### Refinements vs committed spec (pre-execution clarifications, V3 precedent)

1. **Δ90 realized as window-pooled ratios** (count/denominator pooled over each side of the L40 window, split at `t_90_cutoff`), matching the V3 `_factors.py` convention (`starts_per_active_day_last90`, `cold_start_fraction_delta90`) — not per-week means. Spec §7.2 "weekly rate … Δ90" wording maps to this.
2. **B2 z-scores are fleet-wide at cache build** (`zscore_across`), exactly as V3 built `dose_dip_x_starts`; per-fold StandardScaler still applies downstream in the gate.
3. **C1 dropout = `DROPOUT_RUNNING` class hours only** (gaps > 1 h that resume at speed). `UNKNOWN_GAP` hours are excluded (conservative).
4. **A2 stability guards:** OLS via `np.polyfit` on baseline events; ≥ 30 fit events; Theil–Sen over the last 12 masked weeks requires ≥ 6 finite weekly medians.
5. **B1/C1 window denominators** use rollup-week sums over the full week range (no active-day masking of denominators; masking is a numerator-reliability device and pooled sums make it moot).
6. **SV-3 measured per masked VIN-week** on active-day-normalized values: `km/active_day ∈ [10, 800]` and `engine_hrs/active_day ∈ [0.5, 22]`, pass if ≥ 90% of masked VIN-weeks fleet-wide comply.
7. **Catalog scope:** spec §6.1 items #29 `post_trip_recovery_delta` (graveyard-WEAK basis, Low) and #30 `rest_vsi_overnight_p05` (predicted redundant r > 0.85 with champion) are **documented-not-computed** — both need an extra raw-VSI fleet pass their confidence class does not justify. All other computable catalog items are computed. #18 stays graveyard-not-recomputed; lifetime totals stay banned.

### Canonical literals (copy-paste into code)

```python
SMROOT   = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR")
V31      = SMROOT / "V3.1"
FAILED_PQ    = Path(r"D:\Daimler-starter_motor_alternator_battery\Data\processed\starter_motor_complete\2026-03-06-12-38-23-starter_motor_failed.parquet")
NONFAILED_PQ = Path(r"D:\Daimler-starter_motor_alternator_battery\Data\processed\starter_motor_complete\2026-03-06-12-39-14-starter_motor_non_failed.parquet")
MODAL    = ["vsi_withinwk_std_ratio_30d_w","rest_vsi_p05_delta90","vsi_range_trend","dip_depth_last90_delta"]
SMA_DEAD = ["VIN8_F_SM","VIN9_F_SM","VIN10_NF_SM","VIN11_NF_SM","VIN12_NF_SM","VIN13_NF_SM","VIN20_NF_SM"]
CANDS    = ["hard_start_goodv_rate_delta90","dip_resid_trend_12w","lowv_crank_share_delta90",
            "starts_per_engine_hour_delta90","dose_dip_x_intensity","dropout_share_delta90","dip_seasonal_contrast"]
SILENT_GAP_VINS = ["VIN1_F_SM","VIN4_F_SM","VIN5_F_SM","VIN8_F_SM","VIN9_F_SM"]
```

Test runner (from repo root, always):

```powershell
$env:PYTHONIOENCODING='utf-8'; py -3 -m pytest "STARTER MOTOR/V3.1" -q
```

---

## Task 0: Scaffold + pre-registration params (COMMIT BEFORE ANY RESULT)

**Files:**
- Create: `STARTER MOTOR/V3.1/params/V3_1_gate_params.json`
- Create: `STARTER MOTOR/V3.1/params/V3_1_state_params.json`
- Create: `STARTER MOTOR/V3.1/params/V3_1_candidates.json`

- [ ] **Step 1: Create the directory tree**

```powershell
$b = "STARTER MOTOR/V3.1"
foreach ($d in @("params","state/tests","state/out","features/tests","features/out","analysis/out","heuristics/out","reports","graphs","appendix")) {
  New-Item -ItemType Directory -Force "$b/$d" | Out-Null }
Get-ChildItem $b -Directory | Select-Object Name
```

Expected: 10 directories listed (Plan already exists).

- [ ] **Step 2: Write `params/V3_1_gate_params.json`** (exact content)

```json
{
  "reconcile_expected_nonnested": 0.9357, "reconcile_nested": 0.9321, "reconcile_tol": 0.002,
  "alpha_mw": 0.10, "auroc_min": 0.60, "corr_max_redundancy": 0.85,
  "proxy_leak_spearman_max": 0.5, "e2_add_threshold": 0.01, "ridge_alpha": 1.0,
  "proxy_targets": ["n_weeks", "t_start", "span"],
  "modal_subset": ["vsi_withinwk_std_ratio_30d_w", "rest_vsi_p05_delta90", "vsi_range_trend", "dip_depth_last90_delta"],
  "sma_dead": ["VIN8_F_SM", "VIN9_F_SM", "VIN10_NF_SM", "VIN11_NF_SM", "VIN12_NF_SM", "VIN13_NF_SM", "VIN20_NF_SM"],
  "candidates": ["hard_start_goodv_rate_delta90", "dip_resid_trend_12w", "lowv_crank_share_delta90",
                 "starts_per_engine_hour_delta90", "dose_dip_x_intensity", "dropout_share_delta90", "dip_seasonal_contrast"],
  "sma_dead_exempt": ["dropout_share_delta90"],
  "seeds": {"bootstrap": 42, "permutation": 43}
}
```

- [ ] **Step 3: Write `params/V3_1_state_params.json`** (exact content)

```json
{
  "episode_merge_gap_s": 60,
  "heartbeat_band_min": [14, 18],
  "heartbeat_chain_intervening_max_s": 60,
  "dropout_min_s": 3600,
  "dropout_resume_rows": 5, "dropout_resume_rpm": 500,
  "off_confirm_sma_within_s": 300,
  "idle_rpm_max": 700, "idle_csp_max": 5.0,
  "run_start_rpm": 550, "run_start_rows": 2,
  "cwr_rpm": 400, "cwr_gap_max_s": 10,
  "recrank_within_s": 120,
  "engine_dt_cap_s": 10,
  "trip_short_min": 15,
  "soak_overnight_h": 8, "soak_hot_restart_min": 30,
  "sv1_min_frac": 0.90, "sv1_window_s": 120,
  "sv3_km_day": [10, 800], "sv3_eh_day": [0.5, 22], "sv3_min_frac": 0.90,
  "sv4_min_soak_frac": 0.60,
  "p01_confirm_frac": 0.70, "p01_boundary_window_s": 120, "p01_max_chains_per_vin": 200,
  "rpm_sentinel": 65535, "csp_sentinel": 65535,
  "vsi_scale_above": 36.0, "vsi_scale_factor": 0.2
}
```

- [ ] **Step 4: Write `params/V3_1_candidates.json`** (exact content)

```json
{
  "goodv_threshold_V": 27.0, "lowv_threshold_V": 26.0, "threshold_sensitivity_V": 0.5,
  "a2_baseline_min_events": 30, "a2_trend_weeks": 12, "a2_min_weekly_medians": 6,
  "b1_min_engine_hours_side": 20.0, "b1_min_base_cranks": 10, "b1_weekly_min_engine_hours": 5.0,
  "c2_months_cold": [12, 1, 2], "c2_months_hot": [4, 5, 6], "c2_min_events_side": 15,
  "delta90_min_last_events": 3, "delta90_min_base_events": 6,
  "t1_rubric": {
    "starter_weeks_with_goodv_hardstart_min": 2, "starter_lookback_weeks": 12,
    "battery_lowv_share_pctl": 75, "insufficient_min_cranks_90d": 10, "rest_trend_weeks": 12
  },
  "t2_windows_days": {"battery_first": [28, 91], "starter_first": [126, 284], "mixed": [28, 91]},
  "t3_escalation": {"trailing_weeks": 4, "ratio_vs_own_median": 2.0, "min_hours": 5.0}
}
```

- [ ] **Step 5: Commit (pre-registration gate)**

```powershell
git add "STARTER MOTOR/V3.1/params"
git commit -m "feat(v3.1-sm): Task 0 - pre-registered params (gate, state, candidates) committed before any result"
```

---

## Task 1: `state/_state_lib.py` — loaders + cleaning + week helper

**Files:**
- Create: `STARTER MOTOR/V3.1/state/_state_lib.py`
- Test: `STARTER MOTOR/V3.1/state/tests/test_state_lib.py`

- [ ] **Step 1: Write the failing test**

```python
# STARTER MOTOR/V3.1/state/tests/test_state_lib.py
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _state_lib as SL


def test_vin_routing():
    p, raw = SL.vin_source("VIN3_F_SM")
    assert p == SL.FAILED_PQ and raw == "VIN3"
    p, raw = SL.vin_source("VIN17_NF_SM")
    assert p == SL.NONFAILED_PQ and raw == "VIN17"


def test_clean_signals_sentinels_and_scale():
    df = pd.DataFrame({
        "RPM": [650.0, 65535.0, np.nan, 0.0],
        "CSP": [10.0, 65535.0, 3.0, 0.0],
        "VSI": [28.0, 255.0, 140.0, 0.0],   # 140 -> 28.0 via x0.2 ; 255/0 -> NaN
        "SMA": [0.0, 1.0, 0.0, 0.0],
    })
    out = SL.clean_signals(df.copy())
    assert np.isnan(out["RPM"].iloc[1]) and out["RPM"].iloc[3] == 0.0
    assert np.isnan(out["CSP"].iloc[1])
    assert np.isnan(out["VSI"].iloc[1]) and np.isnan(out["VSI"].iloc[3])
    assert abs(out["VSI"].iloc[2] - 28.0) < 1e-9


def test_week_start_is_monday():
    ts = pd.Series(pd.to_datetime(["2025-01-01 07:00:00", "2025-01-06 00:00:01"]))  # Wed, Mon
    w = SL.week_start(ts)
    assert str(w.iloc[0].date()) == "2024-12-30" and str(w.iloc[1].date()) == "2025-01-06"
    assert all(w.dt.weekday == 0)


def test_all_vin_labels_shape():
    labels = SL.all_vin_labels()
    assert len(labels) == 34 and labels.count("VIN1_F_SM") == 1 and labels.count("VIN1_NF_SM") == 1
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
$env:PYTHONIOENCODING='utf-8'; py -3 -m pytest "STARTER MOTOR/V3.1/state/tests/test_state_lib.py" -q
```

Expected: FAIL / ERROR with `ModuleNotFoundError: No module named '_state_lib'`.

- [ ] **Step 3: Write the implementation**

```python
# STARTER MOTOR/V3.1/state/_state_lib.py
"""Label-blind raw loaders for the V3.1 state engine. READ-ONLY on all inputs."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import polars as pl

SMROOT = Path(__file__).resolve().parents[2]                     # .../STARTER MOTOR
V31 = SMROOT / "V3.1"
STATE_OUT = V31 / "state" / "out"
FAILED_PQ = SMROOT.parent / "Data" / "processed" / "starter_motor_complete" / "2026-03-06-12-38-23-starter_motor_failed.parquet"
NONFAILED_PQ = SMROOT.parent / "Data" / "processed" / "starter_motor_complete" / "2026-03-06-12-39-14-starter_motor_non_failed.parquet"
MATRIX = SMROOT / "V1.1" / "results" / "V1_1_SM_feature_matrix.csv"
P = json.loads((V31 / "params" / "V3_1_state_params.json").read_text())


def all_vin_labels():
    return pd.read_csv(MATRIX)["vin_label"].tolist()


def vin_source(vin_label):
    """'VIN3_F_SM' -> (FAILED_PQ, 'VIN3'); 'VIN17_NF_SM' -> (NONFAILED_PQ, 'VIN17')."""
    raw = vin_label.split("_")[0]
    return (FAILED_PQ, raw) if "_F_" in vin_label else (NONFAILED_PQ, raw)


def clean_signals(df):
    """Sentinel masking + VSI scale rule (harmless no-ops on this data, kept as frozen contract)."""
    for c in ("RPM", "CSP"):
        if c in df:
            df.loc[df[c] >= P["rpm_sentinel"], c] = np.nan
    if "VSI" in df:
        v = df["VSI"].astype(float)
        v[(v <= 0.0) | (v >= 255.0)] = np.nan
        big = v > P["vsi_scale_above"]
        v[big] = v[big] * P["vsi_scale_factor"]
        df["VSI"] = v
    return df


def load_vin(vin_label, columns=("timestamp", "RPM", "CSP", "SMA")):
    """Sorted, cleaned per-VIN frame via lazy polars scan."""
    path, raw = vin_source(vin_label)
    lf = pl.scan_parquet(str(path)).filter(pl.col("VIN") == raw).select(list(columns))
    df = lf.collect().to_pandas().sort_values("timestamp", kind="stable").reset_index(drop=True)
    return clean_signals(df)


def week_start(ts):
    """Monday-floor a datetime Series (matches V1 weekly cache dt.truncate('1w'))."""
    d = ts.dt.floor("D")
    return d - pd.to_timedelta(ts.dt.weekday, unit="D")
```

- [ ] **Step 4: Run test to verify it passes**

Same command as Step 2. Expected: `4 passed` (the two data-touching tests read only the small matrix CSV; no parquet scan happens).

- [ ] **Step 5: Commit**

```powershell
git add "STARTER MOTOR/V3.1/state"
git commit -m "feat(v3.1-sm): Task 1 - state lib (routing, sentinel cleaning, Monday weeks) with tests"
```

---

## Task 2: `state/P0_probes.py` — Phase-0 probes, fleet run

**Files:**
- Create: `STARTER MOTOR/V3.1/state/P0_probes.py`
- Output: `state/out/P0_heartbeat.json`, `P0_gap_census.json`, `P0_gap_hist.csv`, `P0_duplicates.json`, `P0_dropout_taxonomy.json`, `P0_sma_observability.json`

No unit test (fleet probe script); verification = run + assert outputs. Label-blind: never reads `failed`.

- [ ] **Step 1: Write the probe script**

```python
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
```

- [ ] **Step 2: Smoke-run on 2 VINs, then full fleet**

```powershell
$env:PYTHONIOENCODING='utf-8'; py -3 "STARTER MOTOR/V3.1/state/P0_probes.py" VIN2_F_SM VIN2_NF_SM
```

Expected: JSON verdict printed (fractions between 0 and 1), 6 output files in `state/out/`. Then the full run (budget ~30–60 min):

```powershell
$env:PYTHONIOENCODING='utf-8'; py -3 "STARTER MOTOR/V3.1/state/P0_probes.py"
```

Expected: verdict JSON with `"eval_chains"` in the thousands and an explicit `"confirmed": true|false`.

- [ ] **Step 3: Record the heartbeat verdict**

Whatever `confirmed` is, it is now frozen. If `false`, heartbeat chains become `UNKNOWN_GAP` in Task 3 and soak-dependent catalog features degrade per spec §12 (B1 unaffected). Do NOT tune anything except within the pre-registered band [14, 18] min.

- [ ] **Step 4: Commit**

```powershell
git add "STARTER MOTOR/V3.1/state"
git commit -m "feat(v3.1-sm): Task 2 - P0 probes (heartbeat verdict, dup, dropout taxonomy, SMA observability)"
```

---

## Task 3: `state/sm_state_engine.py` — row states + episodes

**Files:**
- Create: `STARTER MOTOR/V3.1/state/sm_state_engine.py`
- Test: `STARTER MOTOR/V3.1/state/tests/test_state_engine.py`

- [ ] **Step 1: Write the failing tests**

```python
# STARTER MOTOR/V3.1/state/tests/test_state_engine.py
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sm_state_engine as SE


def mkdf(rows):
    t0 = pd.Timestamp("2025-01-06 06:00:00")
    ts, rpm, csp, sma = [], [], [], []
    t = t0
    for dt_s, r, c, s in rows:
        t = t + pd.Timedelta(seconds=dt_s)
        ts.append(t); rpm.append(r); csp.append(c); sma.append(s)
    return pd.DataFrame({"timestamp": ts, "RPM": rpm, "CSP": csp, "SMA": sma})


def test_row_states_priority():
    df = mkdf([(0, 800, 20, 1),      # SMA wins -> CRANK even with RPM/CSP high
               (5, 0, 0, 0),         # ENGINE_OFF
               (5, np.nan, 0, 0),    # ENGINE_OFF (null RPM)
               (5, 600, 0, 0),       # IDLE
               (5, 600, 10, 0),      # DRIVE (CSP >= 5)
               (5, 900, 0, 0)])      # DRIVE (RPM > 700)
    st = SE.classify_rows(df)["state"].tolist()
    assert st == ["CRANK", "ENGINE_OFF", "ENGINE_OFF", "IDLE", "DRIVE", "DRIVE"]


def test_episodes_merge_and_heartbeat_chain():
    rows = [(0, 0, 0, 0), (5, 0, 0, 0)]            # OFF, 2 rows
    rows += [(900, 0, 0, 0)]                       # 15-min hb gap -> wake row
    rows += [(900, 0, 0, 0)]                       # another hb gap -> wake row
    rows += [(910, np.nan, 0, 1)]                  # hb gap then CRANK
    rows += [(5, 650, 0, 0), (5, 660, 0, 0)]       # IDLE run (trip start material)
    df = mkdf(rows)
    ep = SE.build_episodes(SE.classify_rows(df), heartbeat_confirmed=True)
    states = ep["state"].tolist()
    assert "OFF_DWELL" in states                    # chain of hb gaps merged
    ix = states.index("OFF_DWELL")
    assert states[ix + 1] == "CRANK" and ep["dur_s"].iloc[ix] >= 2700 - 10
    assert states[-1] == "IDLE" and ep["n_rows"].iloc[-1] == 2


def test_dropout_running_classification():
    rows = [(0, 800, 40, 0), (5, 810, 42, 0)]      # DRIVE
    rows += [(7200, 820, 45, 0), (5, 815, 44, 0)]  # 2h gap resuming at speed -> DROPOUT_RUNNING
    df = mkdf(rows)
    ep = SE.build_episodes(SE.classify_rows(df), heartbeat_confirmed=True)
    assert "DROPOUT_RUNNING" in ep["state"].tolist()


def test_cwr_and_recrank_flags():
    rows = [(0, 800, 30, 0), (5, 800, 30, 1)]      # crank while running -> cwr
    rows += [(5, 0, 0, 0), (30, 100, 0, 1)]        # re-crank 35s after previous crank end
    df = mkdf(rows)
    ep = SE.build_episodes(SE.classify_rows(df), heartbeat_confirmed=True)
    cr = ep[ep["state"] == "CRANK"].reset_index(drop=True)
    assert bool(cr["cwr"].iloc[0]) is True
    assert bool(cr["recrank"].iloc[1]) is True
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
$env:PYTHONIOENCODING='utf-8'; py -3 -m pytest "STARTER MOTOR/V3.1/state/tests/test_state_engine.py" -q
```

Expected: FAIL with `No module named 'sm_state_engine'`.

- [ ] **Step 3: Write the implementation**

```python
# STARTER MOTOR/V3.1/state/sm_state_engine.py
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

    eps = []
    for s in np.unique(seg):
        m = seg == s
        i0, i1 = np.argmax(m), len(m) - 1 - np.argmax(m[::-1])
        eps.append({"state": state[i0], "ts_start": df["timestamp"].iloc[i0], "ts_end": df["timestamp"].iloc[i1],
                    "dur_s": float(ts[i1] - ts[i0] + 5.0), "n_rows": int(m.sum()), "i0": i0, "i1": i1})

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
                if (nxt["dur_s"] <= P["heartbeat_chain_intervening_max_s"] and j + 2 < len(full)
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
```

- [ ] **Step 4: Run tests to verify they pass**

Same command as Step 2. Expected: `4 passed`.

- [ ] **Step 5: Commit**

```powershell
git add "STARTER MOTOR/V3.1/state"
git commit -m "feat(v3.1-sm): Task 3 - state engine row classifier + gap-aware episodes with tests"
```

---

## Task 4: trips, soaks, weekly rollups

**Files:**
- Modify: `STARTER MOTOR/V3.1/state/sm_state_engine.py` (append functions)
- Test: append to `STARTER MOTOR/V3.1/state/tests/test_state_engine.py`

- [ ] **Step 1: Write the failing tests (append to test file)**

```python
def test_trips_soak_and_engine_hours():
    rows = [(0, 0, 0, 0)] * 2                                  # OFF 2 rows
    rows += [(910, np.nan, 0, 1)]                              # hb gap then CRANK
    rows += [(5, 600, 0, 0)] + [(5, 620, 0, 0)]                # IDLE x2 (run start: >=550 x2)
    rows += [(5, 900, 30, 0)] * 10                             # DRIVE x10
    rows += [(5, 0, 0, 0)] * 2                                 # OFF -> trip end
    df = mkdf(rows)
    rowdf = SE.classify_rows(df)
    ep = SE.build_episodes(rowdf, heartbeat_confirmed=True)
    cranks = SE.crank_table(ep)
    assert len(cranks) == 1 and cranks["soak_h"].iloc[0] > 0.2          # OFF(+hb) soak measured
    trips = SE.derive_trips(rowdf, ep)
    assert len(trips) == 1
    assert 0.3 < trips["km"].iloc[0] < 0.6                              # 10 rows x 30 km/h x 5 s = 0.4167 km
    wk = SE.weekly_rollup("SYN_VIN", rowdf, ep, trips, cranks)
    assert abs(wk["engine_hours"].sum() - (12 * 5) / 3600.0) < 0.01     # 12 run rows x 5s
    assert wk["n_cranks"].sum() == 1 and wk["n_trips"].sum() == 1
```

- [ ] **Step 2: Run to verify failure**

Expected: FAIL with `AttributeError: ... 'crank_table'`.

- [ ] **Step 3: Append the implementation**

```python
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

    trips, cur = [], None
    boundary = ("ENGINE_OFF", "OFF_DWELL", "DROPOUT_RUNNING", "OFF_CONFIRMED", "UNKNOWN_GAP", "CRANK")
    for _, e in ep.iterrows():
        if cur is None and e["state"] in ("IDLE", "DRIVE"):
            i0 = rowdf.index[rowdf["timestamp"] == e["ts_start"]][0]
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
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
$env:PYTHONIOENCODING='utf-8'; py -3 -m pytest "STARTER MOTOR/V3.1/state/tests" -q
```

Expected: `9 passed` across the `state/tests` folder (4 in `test_state_lib.py` + 5 in `test_state_engine.py`).

- [ ] **Step 5: Commit**

```powershell
git add "STARTER MOTOR/V3.1/state"
git commit -m "feat(v3.1-sm): Task 4 - trips, soak, weekly rollups with synthetic tests"
```

---

## Task 5: `state/run_state_fleet.py` — full-fleet run + SV gates

**Files:**
- Create: `STARTER MOTOR/V3.1/state/run_state_fleet.py`
- Output: `state/out/V3_1_state_episodes_<vin>.parquet`, `V3_1_state_weekly_<vin>.parquet`, `V3_1_trips_<vin>.parquet`, `V3_1_cranks_<vin>.parquet`, `V3_1_sv_gates.json`

- [ ] **Step 1: Write the driver**

```python
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
        d = df.copy(); d.insert(0, "vin_label", vin) if "vin_label" not in d.columns else None
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
        if i > 0 and (e["ts_start"] - ends[i - 1]).total_seconds() <= P["sv1_window_s"]:
            pass  # preceded by non-off state within window -> not ok
    soak_frac = float(np.isfinite(cranks["soak_h"]).mean()) if len(cranks) else np.nan
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
```

- [ ] **Step 2: Run the fleet (budget ~45–90 min)**

```powershell
$env:PYTHONIOENCODING='utf-8'; py -3 "STARTER MOTOR/V3.1/state/run_state_fleet.py"
```

Expected: SV JSON printed; `state/out/` contains 4×34 per-VIN parquets + `V3_1_state_weekly_ALL.parquet` + `V3_1_sv_gates.json`.

- [ ] **Step 3: Adjudicate SV gates (drop-not-replace)**

- SV-1 fail (< 0.90) → investigate segmentation before proceeding; do not tune registered params.
- SV-3 fail → **drop B1 and B2** from the gate run (record in gate summary as `DROPPED_SV3`).
- SV-4 fail or heartbeat refuted → soak catalog features are Experimental; candidates unaffected.

- [ ] **Step 4: Commit**

```powershell
git add "STARTER MOTOR/V3.1/state"
git commit -m "feat(v3.1-sm): Task 5 - fleet state run, episode/weekly/trip/crank parquets, SV gates"
```

---

## Task 6: A-family factors (event-catalog only)

**Files:**
- Create: `STARTER MOTOR/V3.1/features/_v31_lib.py`
- Create: `STARTER MOTOR/V3.1/features/_factors31.py`
- Test: `STARTER MOTOR/V3.1/features/tests/test_factors31.py`

- [ ] **Step 1: Write `_v31_lib.py`** (thin adapter, mirrors V3's `_v3_lib.py`)

```python
# STARTER MOTOR/V3.1/features/_v31_lib.py
import sys, json, glob
from pathlib import Path
import numpy as np
import pandas as pd

SMROOT = Path(__file__).resolve().parents[2]
V31_OUT = SMROOT / "V3.1" / "features" / "out"
V31_OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(SMROOT / "V2.1" / "features"))
sys.path.insert(0, str(SMROOT / "V3" / "features"))
import _feature_lib as F                      # vins_in_order, build_px, load_events_nonartifact

GP = json.loads((SMROOT / "V3.1" / "params" / "V3_1_gate_params.json").read_text())
CP = json.loads((SMROOT / "V3.1" / "params" / "V3_1_candidates.json").read_text())
SMA_DEAD = set(GP["sma_dead"]); EXEMPT = set(GP["sma_dead_exempt"])

def vins_in_order(): return F.vins_in_order()
def build_px():      return F.build_px()
def load_events():   return F.load_events_nonartifact()

def load_weekly():
    files = sorted(glob.glob(str(SMROOT / "cache" / "weekly" / "V1_SM_weekly_*.parquet")))
    wk = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    wk["week"] = pd.to_datetime(wk["week"])
    return wk

def load_state_weekly():
    r = pd.read_parquet(SMROOT / "V3.1" / "state" / "out" / "V3_1_state_weekly_ALL.parquet")
    r["week"] = pd.to_datetime(r["week"])
    return r

def zscore_across(value_by_vin, order):
    vals = np.array([value_by_vin.get(v, np.nan) for v in order], dtype=float)
    mu, sd = np.nanmean(vals), np.nanstd(vals)
    if not np.isfinite(sd) or sd == 0:
        return {v: np.nan for v in order}
    return {v: (value_by_vin.get(v, np.nan) - mu) / sd for v in order}

def write_cache(name, value_by_vin):
    order = vins_in_order(); force = name not in EXEMPT; rows = []
    for v in order:
        val = np.nan if (force and v in SMA_DEAD) else value_by_vin.get(v, np.nan)
        rows.append({"vin_label": v, name: val})
    df = pd.DataFrame(rows); path = V31_OUT / f"{name}_cache.csv"; df.to_csv(path, index=False)
    print(f"wrote {path.name} ({df[name].notna().sum()}/34 non-null)")
    return path
```

- [ ] **Step 2: Write the failing tests**

```python
# STARTER MOTOR/V3.1/features/tests/test_factors31.py
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _factors31 as X


def _px(vin="V", win="2025-01-06", t90="2025-06-02"):
    return pd.DataFrame({"vin_label": [vin], "t_end_approx": [pd.Timestamp("2025-08-31")],
                         "t_90_cutoff": [pd.Timestamp(t90)], "win_start_l40": [pd.Timestamp(win)]
                         }).set_index("vin_label")


def _ev(vin="V"):
    """20 baseline events (10 good-V fails) + 10 last-90 events (5 good-V fails)."""
    rows = []
    for i in range(20):
        rows.append({"vin_label": vin, "ts_start": pd.Timestamp("2025-02-03") + pd.Timedelta(days=i * 5),
                     "success": i % 2 == 0, "baseline_vsi": 28.0, "dip_depth": 5.0 + 0.0 * i})
    for i in range(10):
        rows.append({"vin_label": vin, "ts_start": pd.Timestamp("2025-06-09") + pd.Timedelta(days=i * 7),
                     "success": i % 2 == 0, "baseline_vsi": 28.0, "dip_depth": 5.0})
    return pd.DataFrame(rows)


def _wk(vin="V"):
    weeks = pd.date_range("2025-01-06", "2025-08-25", freq="7D")
    return pd.DataFrame({"vin_label": vin, "week": weeks, "active_days": 5,
                         "vsi_rest_median": 28.0})


def test_a1_hard_start_goodv_rate_delta90():
    v = X.hard_start_goodv_rate_delta90(_ev(), _wk(), _px(), "V")
    # base: 10 fails/ (21 wks*5 d) = 0.0952...; last: 5 fails/(13 wks*5 d)=0.0769...  -> negative delta
    assert np.isfinite(v) and v < 0


def test_a3_lowv_share_delta90_null_when_no_lowv():
    v = X.lowv_crank_share_delta90(_ev(), _px(), "V")
    assert abs(v) < 1e-12          # no event below 26.0 V on either side -> delta 0


def test_a2_dip_resid_trend_needs_min_events():
    ev = _ev().iloc[:10]           # only 10 baseline events < 30 -> NaN
    v = X.dip_resid_trend_12w(ev, _wk(), _px(), "V")
    assert np.isnan(v)
```

- [ ] **Step 3: Run to verify failure**

```powershell
$env:PYTHONIOENCODING='utf-8'; py -3 -m pytest "STARTER MOTOR/V3.1/features/tests/test_factors31.py" -q
```

Expected: FAIL with `No module named '_factors31'`.

- [ ] **Step 4: Write `_factors31.py` (A-family)**

```python
# STARTER MOTOR/V3.1/features/_factors31.py
"""V3.1 pre-registered candidate factors. Window conventions match V3 _factors.py:
pooled ratios over the L40 window split at t_90_cutoff (see plan Refinement 1)."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import theilslopes

CP = json.loads((Path(__file__).resolve().parents[1] / "params" / "V3_1_candidates.json").read_text())
GOODV, LOWV = CP["goodv_threshold_V"], CP["lowv_threshold_V"]
MIN_LAST, MIN_BASE = CP["delta90_min_last_events"], CP["delta90_min_base_events"]


def _evin(ev, vin):
    return ev[ev["vin_label"] == vin].sort_values("ts_start").reset_index(drop=True)


def _ok_px(px, vin):
    return (vin in px.index) and (not px.loc[vin].isna().any())


def _windows(px, vin):
    return pd.Timestamp(px.loc[vin, "win_start_l40"]), pd.Timestamp(px.loc[vin, "t_90_cutoff"])


def _active_days(wk, vin, lo, hi):
    w = wk[(wk["vin_label"] == vin) & (wk["active_days"] >= 2)]
    return float(w.loc[(w["week"] >= lo) & (w["week"] < hi), "active_days"].sum())


def hard_start_goodv_rate_delta90(ev, wk, px, vin):
    """A1: pooled rate of (failed crank & baseline_vsi >= 27.0 V) per active day, last90 minus baseline."""
    if not _ok_px(px, vin):
        return np.nan
    win, t90 = _windows(px, vin)
    e = _evin(ev, vin); e = e[e["ts_start"] >= win]
    n_ev_last = int((e["ts_start"] >= t90).sum()); n_ev_base = int((e["ts_start"] < t90).sum())
    if n_ev_last < MIN_LAST or n_ev_base < MIN_BASE:
        return np.nan
    hs = e[(e["success"] == False) & (e["baseline_vsi"] >= GOODV)]  # noqa: E712
    far = pd.Timestamp.max                                   # naive sentinel upper bound
    ad_last = _active_days(wk, vin, t90, far); ad_base = _active_days(wk, vin, win, t90)
    if ad_last <= 0 or ad_base <= 0:
        return np.nan
    return float((hs["ts_start"] >= t90).sum() / ad_last - (hs["ts_start"] < t90).sum() / ad_base)


def lowv_crank_share_delta90(ev, px, vin):
    """A3: share of cranks (with valid baseline_vsi) below 26.0 V, last90 minus baseline."""
    if not _ok_px(px, vin):
        return np.nan
    win, t90 = _windows(px, vin)
    e = _evin(ev, vin)
    e = e[(e["ts_start"] >= win) & np.isfinite(e["baseline_vsi"])]
    last, base = e[e["ts_start"] >= t90], e[e["ts_start"] < t90]
    if len(last) < MIN_LAST or len(base) < MIN_BASE:
        return np.nan
    return float((last["baseline_vsi"] < LOWV).mean() - (base["baseline_vsi"] < LOWV).mean())


def dip_resid_trend_12w(ev, wk, px, vin):
    """A2: Theil-Sen slope of weekly median dip-residuals (dip ~ OLS(baseline_vsi) fit on pre-tail events)."""
    if not _ok_px(px, vin):
        return np.nan
    win, _ = _windows(px, vin)
    e = _evin(ev, vin)
    e = e[(e["ts_start"] >= win) & np.isfinite(e["dip_depth"]) & np.isfinite(e["baseline_vsi"])].copy()
    if len(e) == 0:
        return np.nan
    e["week"] = e["ts_start"].dt.floor("D") - pd.to_timedelta(e["ts_start"].dt.weekday, unit="D")
    w = wk[(wk["vin_label"] == vin) & (wk["active_days"] >= 2)].sort_values("week")
    masked = pd.to_datetime(w["week"]).tail(CP["a2_trend_weeks"]).reset_index(drop=True)
    if len(masked) < CP["a2_trend_weeks"]:
        return np.nan
    cut = masked.iloc[0]
    fit, tail = e[e["week"] < cut], e[e["week"] >= cut].copy()
    if len(fit) < CP["a2_baseline_min_events"]:
        return np.nan
    b1, b0 = np.polyfit(fit["baseline_vsi"].values.astype(float), fit["dip_depth"].values.astype(float), 1)
    tail["resid"] = tail["dip_depth"] - (b0 + b1 * tail["baseline_vsi"])
    med = tail.groupby("week")["resid"].median().reindex(masked.values)
    yv = med.values.astype(float); x = np.arange(len(yv), dtype=float); m = np.isfinite(yv)
    if m.sum() < CP["a2_min_weekly_medians"]:
        return np.nan
    return float(theilslopes(yv[m], x[m])[0])
```

- [ ] **Step 5: Run tests to verify they pass**

Same command as Step 3. Expected: `3 passed`.

- [ ] **Step 6: Commit**

```powershell
git add "STARTER MOTOR/V3.1/features"
git commit -m "feat(v3.1-sm): Task 6 - v31 lib + A-family factors (A1 goodV hard-start, A2 dip residual trend, A3 lowV share)"
```

---

## Task 7: B/C-family factors (state rollups + calendar)

**Files:**
- Modify: `STARTER MOTOR/V3.1/features/_factors31.py` (append)
- Test: append to `STARTER MOTOR/V3.1/features/tests/test_factors31.py`

- [ ] **Step 1: Write the failing tests (append)**

```python
def _roll(vin="V"):
    weeks = pd.date_range("2025-01-06", "2025-08-25", freq="7D")
    n = len(weeks)
    return pd.DataFrame({"vin_label": vin, "week": weeks, "active_days": 5,
                         "engine_hours": 40.0, "observed_hours": 60.0,
                         "dropout_hours": [0.0] * (n - 6) + [6.0] * 6})


def test_b1_starts_per_engine_hour_delta90():
    v = X.starts_per_engine_hour_delta90(_ev(), _roll(), _px(), "V")
    # base 20 cranks / (21w*40h)=0.0238; last 10 / (13w*40h)=0.0192 -> negative
    assert np.isfinite(v) and v < 0


def test_c1_dropout_share_delta90_positive_when_tail_heavy():
    v = X.dropout_share_delta90(_roll(), _px(), "V")
    assert np.isfinite(v) and v > 0


def test_c2_seasonal_needs_both_windows():
    v = X.dip_seasonal_contrast(_ev(), _px(), "V")   # _ev has no Dec-Feb events with >=15 -> NaN
    assert np.isnan(v)
```

- [ ] **Step 2: Run to verify failure**

Expected: FAIL with `AttributeError: ... 'starts_per_engine_hour_delta90'`.

- [ ] **Step 3: Append the implementations**

```python
def _roll_sum(roll, vin, col, lo, hi):
    r = roll[roll["vin_label"] == vin]
    return float(r.loc[(r["week"] >= lo) & (r["week"] < hi), col].sum())


def starts_per_engine_hour_delta90(ev, roll, px, vin):
    """B1: pooled valid cranks per engine-hour, last90 minus baseline (state-engine denominator)."""
    if not _ok_px(px, vin):
        return np.nan
    win, t90 = _windows(px, vin)
    far = pd.Timestamp.max
    e = _evin(ev, vin); e = e[e["ts_start"] >= win]
    n_last = int((e["ts_start"] >= t90).sum()); n_base = int((e["ts_start"] < t90).sum())
    eh_last = _roll_sum(roll, vin, "engine_hours", t90, far)
    eh_base = _roll_sum(roll, vin, "engine_hours", win, t90)
    if (eh_last < CP["b1_min_engine_hours_side"] or eh_base < CP["b1_min_engine_hours_side"]
            or n_base < CP["b1_min_base_cranks"]):
        return np.nan
    return float(n_last / eh_last - n_base / eh_base)


def starts_per_engine_hour_last90(ev, roll, px, vin):
    """Level form (B2 ingredient)."""
    if not _ok_px(px, vin):
        return np.nan
    win, t90 = _windows(px, vin)
    far = pd.Timestamp.max
    e = _evin(ev, vin)
    n_last = int((e["ts_start"] >= t90).sum())
    eh_last = _roll_sum(roll, vin, "engine_hours", t90, far)
    return float(n_last / eh_last) if eh_last >= CP["b1_min_engine_hours_side"] else np.nan


def dropout_share_delta90(roll, px, vin):
    """C1: pooled DROPOUT_RUNNING hours / (dropout + observed) hours, last90 minus baseline. All-34."""
    if not _ok_px(px, vin):
        return np.nan
    win, t90 = _windows(px, vin)
    far = pd.Timestamp.max
    dl, ol = (_roll_sum(roll, vin, "dropout_hours", t90, far), _roll_sum(roll, vin, "observed_hours", t90, far))
    db, ob = (_roll_sum(roll, vin, "dropout_hours", win, t90), _roll_sum(roll, vin, "observed_hours", win, t90))
    if (dl + ol) <= 0 or (db + ob) <= 0:
        return np.nan
    return float(dl / (dl + ol) - db / (db + ob))


def dip_seasonal_contrast(ev, px, vin):
    """C2: median dip Dec-Feb minus Apr-Jun within the L40 window (pooled across years)."""
    if not _ok_px(px, vin):
        return np.nan
    win, _ = _windows(px, vin)
    e = _evin(ev, vin)
    e = e[(e["ts_start"] >= win) & np.isfinite(e["dip_depth"])]
    cold = e[e["ts_start"].dt.month.isin(CP["c2_months_cold"])]
    hot = e[e["ts_start"].dt.month.isin(CP["c2_months_hot"])]
    if len(cold) < CP["c2_min_events_side"] or len(hot) < CP["c2_min_events_side"]:
        return np.nan
    return float(cold["dip_depth"].median() - hot["dip_depth"].median())


def dip_resid_last90_median(ev, wk, px, vin):
    """Catalog #26 level form: median dip residual over the last 12 masked weeks (same fit as A2)."""
    if not _ok_px(px, vin):
        return np.nan
    win, _ = _windows(px, vin)
    e = _evin(ev, vin)
    e = e[(e["ts_start"] >= win) & np.isfinite(e["dip_depth"]) & np.isfinite(e["baseline_vsi"])].copy()
    if len(e) == 0:
        return np.nan
    e["week"] = e["ts_start"].dt.floor("D") - pd.to_timedelta(e["ts_start"].dt.weekday, unit="D")
    w = wk[(wk["vin_label"] == vin) & (wk["active_days"] >= 2)].sort_values("week")
    masked = pd.to_datetime(w["week"]).tail(CP["a2_trend_weeks"]).reset_index(drop=True)
    if len(masked) < CP["a2_trend_weeks"]:
        return np.nan
    cut = masked.iloc[0]
    fit, tail = e[e["week"] < cut], e[e["week"] >= cut].copy()
    if len(fit) < CP["a2_baseline_min_events"] or len(tail) == 0:
        return np.nan
    b1, b0 = np.polyfit(fit["baseline_vsi"].values.astype(float), fit["dip_depth"].values.astype(float), 1)
    return float((tail["dip_depth"] - (b0 + b1 * tail["baseline_vsi"])).median())
```

- [ ] **Step 4: Run all factor tests**

```powershell
$env:PYTHONIOENCODING='utf-8'; py -3 -m pytest "STARTER MOTOR/V3.1/features/tests" -q
```

Expected: `6 passed`.

- [ ] **Step 5: Commit**

```powershell
git add "STARTER MOTOR/V3.1/features"
git commit -m "feat(v3.1-sm): Task 7 - B/C-family factors (starts/engine-hr, dropout share, seasonal dip contrast)"
```

---

## Task 8: Build the 7 candidate caches

**Files:**
- Create: `STARTER MOTOR/V3.1/features/build_candidate_caches.py`
- Output: `features/out/<name>_cache.csv` × 7

- [ ] **Step 1: Write the builder**

```python
# STARTER MOTOR/V3.1/features/build_candidate_caches.py
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _v31_lib as L
import _factors31 as X
from _factors import dip_depth_last90_level          # V3 factor, reused verbatim (B2 ingredient)

ev, wk, px = L.load_events(), L.load_weekly(), L.build_px()
roll = L.load_state_weekly()
order = L.vins_in_order()

L.write_cache("hard_start_goodv_rate_delta90", {v: X.hard_start_goodv_rate_delta90(ev, wk, px, v) for v in order})
L.write_cache("dip_resid_trend_12w",           {v: X.dip_resid_trend_12w(ev, wk, px, v) for v in order})
L.write_cache("lowv_crank_share_delta90",      {v: X.lowv_crank_share_delta90(ev, px, v) for v in order})
L.write_cache("starts_per_engine_hour_delta90", {v: X.starts_per_engine_hour_delta90(ev, roll, px, v) for v in order})

dipz = L.zscore_across({v: dip_depth_last90_level(ev, px, v) for v in order}, order)
sehz = L.zscore_across({v: X.starts_per_engine_hour_last90(ev, roll, px, v) for v in order}, order)
L.write_cache("dose_dip_x_intensity", {v: (dipz[v] * sehz[v]) if np.isfinite(dipz[v]) and np.isfinite(sehz[v]) else np.nan for v in order})

L.write_cache("dropout_share_delta90", {v: X.dropout_share_delta90(roll, px, v) for v in order})
L.write_cache("dip_seasonal_contrast", {v: X.dip_seasonal_contrast(ev, px, v) for v in order})
print("done")
```

- [ ] **Step 2: Run and eyeball non-null counts**

```powershell
$env:PYTHONIOENCODING='utf-8'; py -3 "STARTER MOTOR/V3.1/features/build_candidate_caches.py"
```

Expected: 7 `wrote ..._cache.csv (k/34 non-null)` lines; A/B families ~27/34 max (SMA-dead forced NaN); `dropout_share_delta90` up to 34/34; `dip_seasonal_contrast` possibly much lower (season-coverage nulls are expected and honest).

- [ ] **Step 3: Commit**

```powershell
git add "STARTER MOTOR/V3.1/features"
git commit -m "feat(v3.1-sm): Task 8 - 7 candidate caches built (A/B families dead-forced, C1 exempt)"
```

---

## Task 9: Gate — copy core, reconcile test, run E0→E3

**Files:**
- Copy: `STARTER MOTOR/V3/features/_gate_core.py` → `STARTER MOTOR/V3.1/features/_gate_core.py` (verbatim)
- Create: `STARTER MOTOR/V3.1/features/V3_1_feature_gate.py`
- Test: `STARTER MOTOR/V3.1/features/tests/test_reconcile31.py`
- Output: `features/out/V3_1_gate_summary.json`

- [ ] **Step 1: Copy the gate core verbatim**

```powershell
Copy-Item "STARTER MOTOR/V3/features/_gate_core.py" "STARTER MOTOR/V3.1/features/_gate_core.py"
```

- [ ] **Step 2: Write the failing reconcile test**

```python
# STARTER MOTOR/V3.1/features/tests/test_reconcile31.py
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _gate_core as G
import _v31_lib as L
import V3_1_feature_gate as GATE            # import must expose reconcile()


def test_e0_reconciliation_and_sv5():
    recon = GATE.reconcile()
    assert recon["pass"] is True
    assert abs(recon["computed"] - 0.9357) <= 0.002
```

- [ ] **Step 3: Run to verify failure** (`No module named 'V3_1_feature_gate'`)

- [ ] **Step 4: Write the gate driver** (clone of `V3_feature_gate.py`, differences: params path, OUT, CANDS from params, exempt set, SV-3 drop handling)

```python
# STARTER MOTOR/V3.1/features/V3_1_feature_gate.py
import sys, json
from pathlib import Path
import numpy as np, pandas as pd
from scipy import stats
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
import _gate_core as G
import _v31_lib as L

SMROOT = L.SMROOT
OUT = SMROOT / "V3.1" / "features" / "out"
P = L.GP
MODAL = P["modal_subset"]; SMA_DEAD = set(P["sma_dead"]); EXEMPT = set(P["sma_dead_exempt"])
CANDS = list(P["candidates"])
SV = json.loads((SMROOT / "V3.1" / "state" / "out" / "V3_1_sv_gates.json").read_text())
DROPPED = [] if SV["SV3"]["pass"] else ["starts_per_engine_hour_delta90", "dose_dip_x_intensity"]


def proxy_frame(order):
    wk = L.load_weekly(); px = L.build_px(); rows = []
    for v in order:
        w = wk[wk["vin_label"] == v]; w = w[w["active_days"] >= 2].sort_values("week")
        if len(w) == 0 or v not in px.index or px.loc[v].isna().any():
            rows.append({"vin_label": v, "n_weeks": np.nan, "t_start": np.nan, "span": np.nan}); continue
        weeks = w["week"].values
        rows.append({"vin_label": v, "n_weeks": float(len(w)),
                     "t_start": float(pd.Timestamp(weeks[0]).toordinal()),
                     "span": float((pd.Timestamp(weeks[-1]) - pd.Timestamp(weeks[0])).days)})
    return pd.DataFrame(rows).set_index("vin_label")


def spearman(a, b):
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 6: return np.nan
    r = stats.spearmanr(a[m], b[m])[0]
    return float(r) if np.isfinite(r) else np.nan


def _matrix():
    mat = pd.read_csv(SMROOT / "V1.1" / "results" / "V1_1_SM_feature_matrix.csv")
    return mat, mat["vin_label"].tolist(), mat["failed"].astype(int).values


def reconcile():
    mat, order, y = _matrix()
    a = G.rank_auroc(G.plain_lovo(mat[MODAL].values.astype(float), y), y)
    return {"computed": round(float(a), 4), "expected": P["reconcile_expected_nonnested"],
            "pass": bool(abs(a - P["reconcile_expected_nonnested"]) <= P["reconcile_tol"])}


def main():
    mat, order, y = _matrix()
    recon = reconcile()
    if not recon["pass"]:
        print("RECONCILE FAIL", recon); sys.exit(1)
    a_modal = G.rank_auroc(G.plain_lovo(mat[MODAL].values.astype(float), y), y)
    cands = [c for c in CANDS if c not in DROPPED]
    prox = proxy_frame(order); mat_ext = mat.copy(); E1 = []
    for c in cands:
        cache = pd.read_csv(OUT / f"{c}_cache.csv")
        cmap = dict(zip(cache["vin_label"], cache[c]))
        arr = np.array([np.nan if (v in SMA_DEAD and c not in EXEMPT) else cmap.get(v, np.nan)
                        for v in order], dtype=float)
        mat_ext[c] = arr
        fv, nfv = arr[y == 1], arr[y == 0]
        fv, nfv = fv[np.isfinite(fv)], nfv[np.isfinite(nfv)]
        mw = G.mw_p(fv, nfv)
        a_raw = G.rank_auroc(np.nan_to_num(arr, nan=(np.nanmean(arr) if np.isfinite(arr).any() else 0.0)), y)
        auroc = max(a_raw, 1 - a_raw) if np.isfinite(a_raw) else np.nan
        rprx = {t: spearman(arr, prox[t].values.astype(float)) for t in P["proxy_targets"]}
        rmod = {m: (float(pd.Series(arr).corr(mat[m])) if np.isfinite(arr).sum() >= 6 else np.nan) for m in MODAL}
        proxy_flag = any(np.isfinite(v) and abs(v) > P["proxy_leak_spearman_max"] for v in rprx.values())
        redun_flag = any(np.isfinite(v) and abs(v) >= P["corr_max_redundancy"] for v in rmod.values())
        e1_pass = bool(np.isfinite(mw) and mw <= P["alpha_mw"] and np.isfinite(auroc)
                       and auroc >= P["auroc_min"] and not proxy_flag and not redun_flag)
        E1.append({"feature": c, "n_nonnull": int(np.isfinite(arr).sum()),
                   "mw_p": round(float(mw), 4) if np.isfinite(mw) else None,
                   "auroc": round(float(auroc), 4) if np.isfinite(auroc) else None,
                   "r_proxy": {k: (round(v, 3) if np.isfinite(v) else None) for k, v in rprx.items()},
                   "r_vs_modal": {k: (round(v, 3) if np.isfinite(v) else None) for k, v in rmod.items()},
                   "proxy_flag": bool(proxy_flag), "redundancy_flag": bool(redun_flag), "e1_pass": e1_pass})

    E2 = {}
    for c in cands:
        a_c = G.rank_auroc(G.plain_lovo(mat_ext[MODAL + [c]].values.astype(float), y), y)
        E2[c] = {"auroc": round(float(a_c), 4), "delta": round(float(a_c - a_modal), 4)}

    survivors = [c for c in cands
                 if next(e for e in E1 if e["feature"] == c)["e1_pass"] and E2[c]["delta"] >= P["e2_add_threshold"]]
    E3 = None
    if survivors:
        probs, _ = G.nested_lovo(mat_ext, y, MODAL + survivors)
        E3 = {"survivors": survivors, "nested_auroc": round(float(G.rank_auroc(probs, y)), 4),
              "baseline_nested": P["reconcile_nested"]}

    verdicts = {c: {"verdict": "DROPPED_SV3", "reason": "engine-hours failed SV-3 plausibility"} for c in DROPPED}
    for c in cands:
        e1 = next(e for e in E1 if e["feature"] == c); d = E2[c]["delta"]
        if e1["proxy_flag"] or e1["redundancy_flag"]:
            verdicts[c] = {"verdict": "REJECT", "reason": "E1 proxy/redundancy flag"}
        elif not e1["e1_pass"]:
            verdicts[c] = {"verdict": "REJECT", "reason": f"E1 fail (mw_p={e1['mw_p']}, auroc={e1['auroc']})"}
        elif d >= P["e2_add_threshold"]:
            verdicts[c] = {"verdict": "ADD", "reason": f"E2 delta=+{d}"}
        elif d > 0:
            verdicts[c] = {"verdict": "SOFT_SIGNAL", "reason": f"E1-pass, E2 delta=+{d} < +0.01"}
        else:
            verdicts[c] = {"verdict": "REJECT", "reason": f"E2 delta={d} <= 0"}

    summary = {"reconciliation": recon, "modal_nonnested_auroc": round(float(a_modal), 4),
               "sv3_dropped": DROPPED, "n_candidates": len(cands),
               "E1": E1, "E2": E2, "E3": E3, "verdicts": verdicts}
    (OUT / "V3_1_gate_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({"reconcile": recon["pass"], "verdicts": {c: verdicts[c]["verdict"] for c in verdicts}}, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run reconcile test, then the gate**

```powershell
$env:PYTHONIOENCODING='utf-8'; py -3 -m pytest "STARTER MOTOR/V3.1/features/tests/test_reconcile31.py" -q
$env:PYTHONIOENCODING='utf-8'; py -3 "STARTER MOTOR/V3.1/features/V3_1_feature_gate.py"
```

Expected: test `1 passed`; gate prints `"reconcile": true` and one verdict per candidate; `features/out/V3_1_gate_summary.json` exists. **Whatever the verdicts are, they are final — no re-runs with tweaked definitions.**

- [ ] **Step 6: Commit**

```powershell
git add "STARTER MOTOR/V3.1/features"
git commit -m "feat(v3.1-sm): Task 9 - E0 reconciliation passes, E1/E2(/E3) gate run on pre-registered candidates"
```

---

## Task 10: Descriptive catalog (~30 computed features, label-blind values)

**Files:**
- Create: `STARTER MOTOR/V3.1/features/build_catalog.py`
- Output: `features/out/V3_1_SM_catalog.csv` (34 rows × features)

- [ ] **Step 1: Write the builder** (computes the spec §6.1 catalog; graveyard items #18 and banned lifetime totals are NOT computed — they are documented in the report instead)

```python
# STARTER MOTOR/V3.1/features/build_catalog.py
"""Spec §6.1 catalog. VALUES ONLY - no label stats here (see Task 11 discipline)."""
import sys, glob, json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import theilslopes
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _v31_lib as L
import _factors31 as X
from _factors import dip_depth_last90_level

SMROOT = L.SMROOT
SOUT = SMROOT / "V3.1" / "state" / "out"
ev, wk, px = L.load_events(), L.load_weekly(), L.build_px()
roll = L.load_state_weekly()
order = L.vins_in_order()


def _r(vin):
    return roll[roll["vin_label"] == vin].sort_values("week")


def _cranks(vin):
    p = SOUT / f"V3_1_cranks_{vin}.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame(columns=["ts_start", "soak_h", "cwr", "recrank"])


def _trips(vin):
    p = SOUT / f"V3_1_trips_{vin}.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame(columns=["ts_start", "dur_min", "km", "idle_share"])


rows = []
for v in order:
    r, c, t = _r(v), _cranks(v), _trips(v)
    e = X._evin(ev, v)
    days = max(1.0, float(r["active_days"].sum()))
    run_h = float(r["engine_hours"].sum())
    d = {"vin_label": v,
         "engine_hours_per_day": run_h / days,
         "km_per_day": float(r["km"].sum()) / days,
         "trips_per_day": float(r["n_trips"].sum()) / days,
         "mean_trip_duration_min": float(t["dur_min"].mean()) if len(t) else np.nan,
         "mean_trip_km": float(t["km"].mean()) if len(t) else np.nan,
         "short_trip_share": float(r["n_short_trips"].sum() / r["n_trips"].sum()) if r["n_trips"].sum() else np.nan,
         "idle_share": float(r["idle_hours"].sum() / run_h) if run_h else np.nan,
         "stop_density": float(r["n_trips"].sum() / run_h) if run_h else np.nan,
         "overnight_off_share": float((c["soak_h"] >= 8).mean()) if len(c) else np.nan,
         "soak_before_crank_median": float(c["soak_h"].median()) if len(c) else np.nan,
         "soak_before_crank_p90": float(c["soak_h"].quantile(0.9)) if len(c) else np.nan,
         "overnight_start_share": float(r["n_overnight_starts"].sum() / max(1, r["n_cranks"].sum())),
         "hot_restart_share": float(r["n_hot_restarts"].sum() / max(1, r["n_cranks"].sum())),
         "starts_per_active_day": float(len(e)) / days,
         "starts_per_100km": float(len(e) / (r["km"].sum() / 100.0)) if r["km"].sum() > 0 else np.nan,
         "crank_success_ratio": float(e["success"].mean()) if len(e) else np.nan,
         "crank_dur_p95": float(e["dur_s"].quantile(0.95)) if len(e) else np.nan,
         "cranks_per_trip": float(len(e) / r["n_trips"].sum()) if r["n_trips"].sum() else np.nan,
         "weekly_crank_rate": float(r["n_cranks"].sum() / max(1, len(r))),
         "pre_crank_vsi_median": float(e["baseline_vsi"].median()) if len(e) else np.nan,
         "hard_start_goodv_rate": np.nan, "lowv_crank_share": np.nan,   # filled below
         "dip_resid_last90_median": X.dip_resid_last90_median(ev, wk, px, v),
         "dropout_hours_per_week": float(r["dropout_hours"].mean()) if len(r) else np.nan,
         "heartbeat_coverage_share": float(r["off_dwell_hours"].sum() /
                                           max(1e-9, r["off_dwell_hours"].sum() + r["unknown_gap_hours"].sum() + r["dropout_hours"].sum())),
         "vsi_valid_share": float(np.isfinite(e["baseline_vsi"]).mean()) if len(e) else np.nan,
         "monsoon_start_share": float(e["ts_start"].dt.month.isin([6, 7, 8, 9]).mean()) if len(e) else np.nan,
         "dip_depth_last90_level": dip_depth_last90_level(ev, px, v)}
    # level forms of the attribution ingredients (rubric inputs; also catalog #24/#25)
    if v in px.index and not px.loc[v].isna().any() and len(e):
        t90 = pd.Timestamp(px.loc[v, "t_90_cutoff"])
        last = e[(e["ts_start"] >= t90) & np.isfinite(e["baseline_vsi"])]
        if len(last) >= 3:
            d["hard_start_goodv_rate"] = float(((last["success"] == False) & (last["baseline_vsi"] >= X.GOODV)).mean())  # noqa: E712
            d["lowv_crank_share"] = float((last["baseline_vsi"] < X.LOWV).mean())
        # #27 longest run of consecutive low-voltage cranks (full L40 window)
        bv = e[np.isfinite(e["baseline_vsi"])]["baseline_vsi"].values
        lv = (bv < X.LOWV).astype(int)
        run_max, cur = 0, 0
        for b in lv:
            cur = cur + 1 if b else 0
            run_max = max(run_max, cur)
        d["lowv_consecutive_events_max"] = float(run_max)
        # #21 longest run of consecutive days above own p75 daily crank count, last 90 d
        daily = e[e["ts_start"] >= t90].groupby(e["ts_start"].dt.date).size()
        if len(daily) >= 5:
            thr = float(e.groupby(e["ts_start"].dt.date).size().quantile(0.75))
            days_sorted = daily.sort_index()
            hi = (days_sorted > thr).astype(int).values
            run_max, cur = 0, 0
            for b in hi:
                cur = cur + 1 if b else 0
                run_max = max(run_max, cur)
            d["consecutive_high_crank_days_max90"] = float(run_max)
        else:
            d["consecutive_high_crank_days_max90"] = np.nan
    else:
        d["lowv_consecutive_events_max"] = np.nan
        d["consecutive_high_crank_days_max90"] = np.nan
    # trends
    if len(r) >= 12:
        yv = r["engine_hours"].tail(12).values.astype(float)
        d["weekly_engine_hours_trend"] = float(theilslopes(yv, np.arange(12.0))[0])
    else:
        d["weekly_engine_hours_trend"] = np.nan
    w = wk[(wk["vin_label"] == v) & (wk["active_days"] >= 2)].sort_values("week")
    if len(w) >= 12 and "vsi_rest_median" in w:
        yv = w["vsi_rest_median"].tail(12).values.astype(float)
        m = np.isfinite(yv)
        d["rest_vsi_trend_12w"] = float(theilslopes(yv[m], np.arange(12.0)[m])[0]) if m.sum() >= 6 else np.nan
    else:
        d["rest_vsi_trend_12w"] = np.nan
    rows.append(d)

cat = pd.DataFrame(rows)
# #28 composite: z-sum of (lowv share, dip level, negated rest-floor trend) — Experimental by spec
for c in ("lowv_crank_share", "dip_depth_last90_level", "rest_vsi_trend_12w"):
    mu, sd = cat[c].mean(), cat[c].std()
    cat[f"_z_{c}"] = (cat[c] - mu) / sd if sd and np.isfinite(sd) else np.nan
cat["voltage_stress_index"] = cat["_z_lowv_crank_share"] + cat["_z_dip_depth_last90_level"] - cat["_z_rest_vsi_trend_12w"]
cat = cat.drop(columns=[c for c in cat.columns if c.startswith("_z_")])
cat.to_csv(L.V31_OUT / "V3_1_SM_catalog.csv", index=False)
print(f"catalog: {cat.shape[0]} VINs x {cat.shape[1]-1} features")
# NOT computed by design (plan Refinement 7): post_trip_recovery_delta (#29, graveyard-WEAK),
# rest_vsi_overnight_p05 (#30, predicted-redundant). Documented in the catalog report.
```

- [ ] **Step 2: Run**

```powershell
$env:PYTHONIOENCODING='utf-8'; py -3 "STARTER MOTOR/V3.1/features/build_catalog.py"
```

Expected: `catalog: 34 VINs x ~33 features`.

- [ ] **Step 3: Commit**

```powershell
git add "STARTER MOTOR/V3.1/features"
git commit -m "feat(v3.1-sm): Task 10 - descriptive usage/exposure catalog (values only, label-blind)"
```

---

## Task 11: Validation analytics (BH-FDR, correlations, post-gate exploratory stats)

**Files:**
- Create: `STARTER MOTOR/V3.1/analysis/V3_1_validation.py`
- Output: `analysis/out/V3_1_validation.json`, `analysis/out/correlation_matrix.csv`, `analysis/out/catalog_exploratory_stats.csv`

- [ ] **Step 1: Write the script** (hard-asserts the gate summary exists — catalog discipline §6.3)

```python
# STARTER MOTOR/V3.1/analysis/V3_1_validation.py
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "features"))
import _gate_core as G
import _v31_lib as L

OUT = HERE / "out"; OUT.mkdir(exist_ok=True)
GATE = L.V31_OUT / "V3_1_gate_summary.json"
assert GATE.exists(), "DISCIPLINE VIOLATION: run the gate (Task 9) before any catalog label stats"
S = json.loads(GATE.read_text())

# BH-FDR over the E1 MW p-values
e1 = [e for e in S["E1"] if e["mw_p"] is not None]
p = np.array([e["mw_p"] for e in e1]); order = np.argsort(p); n = len(p)
adj = np.empty(n); prev = 1.0
for rank_i, idx in list(enumerate(order))[::-1]:
    prev = min(prev, p[idx] * n / (rank_i + 1)); adj[idx] = prev
bh = {e1[i]["feature"]: {"p_raw": float(p[i]), "p_bh": round(float(adj[i]), 4)} for i in range(n)}

# correlation matrix: candidates + modal
mat = pd.read_csv(L.SMROOT / "V1.1" / "results" / "V1_1_SM_feature_matrix.csv")
y = mat["failed"].astype(int).values
cols = {m: mat[m].values.astype(float) for m in L.GP["modal_subset"]}
for c in [e["feature"] for e in S["E1"]]:
    cache = pd.read_csv(L.V31_OUT / f"{c}_cache.csv")
    cols[c] = np.array([dict(zip(cache["vin_label"], cache[c])).get(v, np.nan) for v in mat["vin_label"]])
cm = pd.DataFrame(cols).corr(method="pearson")
cm.to_csv(OUT / "correlation_matrix.csv")

# EXPLORATORY catalog stats (post-gate only; never feeds V3.1 gating)
cat = pd.read_csv(L.V31_OUT / "V3_1_SM_catalog.csv")
rows = []
for c in [c for c in cat.columns if c != "vin_label"]:
    arr = cat[c].values.astype(float)
    fv, nfv = arr[y == 1], arr[y == 0]
    fv, nfv = fv[np.isfinite(fv)], nfv[np.isfinite(nfv)]
    if len(fv) >= 3 and len(nfv) >= 3:
        a = G.rank_auroc(np.nan_to_num(arr, nan=np.nanmean(arr)), y)
        rows.append({"feature": c, "n_nonnull": int(np.isfinite(arr).sum()),
                     "mw_p": round(float(G.mw_p(fv, nfv)), 4), "auroc_oriented": round(float(max(a, 1 - a)), 4),
                     "status": "EXPLORATORY_POST_GATE"})
pd.DataFrame(rows).sort_values("mw_p").to_csv(OUT / "catalog_exploratory_stats.csv", index=False)

(OUT / "V3_1_validation.json").write_text(json.dumps({
    "baseline_nonnested": S["modal_nonnested_auroc"], "baseline_nested": L.GP["reconcile_nested"],
    "bh_fdr": bh, "min_bh_p": round(float(adj.min()), 4) if n else None,
    "verdicts": S["verdicts"]}, indent=2))
print(json.dumps({"min_bh_p": round(float(adj.min()), 4) if n else None}, indent=2))
```

- [ ] **Step 2: Run** — expected: `min_bh_p` printed; 3 output files exist.

- [ ] **Step 3: Commit**

```powershell
git add "STARTER MOTOR/V3.1/analysis"
git commit -m "feat(v3.1-sm): Task 11 - BH-FDR, correlation matrix, post-gate exploratory catalog stats"
```

---

## Task 12: Channels T1/T2/T3

**Files:**
- Create: `STARTER MOTOR/V3.1/heuristics/T1_attribution.py`, `T2_windows.py`, `T3_data_health.py`
- Output: `heuristics/out/T1_attribution.csv`, `T1_convergence.json`, `T2_windows.csv`, `T3_data_health.csv`

- [ ] **Step 1: Write T1** (rubric per `V3_1_candidates.json`; convergence vs archetypes)

```python
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
```

- [ ] **Step 2: Write T2**

```python
# STARTER MOTOR/V3.1/heuristics/T2_windows.py
"""A5 graded windows extended with the attribution dimension (spec §8, table logic only)."""
import json
from pathlib import Path
import pandas as pd
HERE = Path(__file__).resolve().parent
import sys; sys.path.insert(0, str(HERE.parent / "features"))
import _v31_lib as L

W = L.CP["t2_windows_days"]
bands = pd.read_csv(L.SMROOT / "V2.1" / "heuristics" / "out" / "A5_per_truck_bands.csv")
t1 = pd.read_csv(HERE / "out" / "T1_attribution.csv")[["vin_label", "attribution"]]
t = bands.merge(t1, on="vin_label", how="left")


def window(row):
    if "GREEN" in str(row["band"]) or row["band"] == "AMBER_only":   # robust to exact GREEN band string
        return None
    a = row["attribution"]
    if a == "BATTERY_FIRST":
        return W["battery_first"]
    if a == "STARTER_FIRST":
        return W["starter_first"]
    if a == "MIXED":
        return W["mixed"]
    return W["starter_first"] if row["band"] == "persistence_AND_RED" else W["battery_first"]


t["window_days"] = t.apply(window, axis=1).astype(str)
t["action"] = t["attribution"].map({"BATTERY_FIRST": "battery service first, then re-evaluate",
                                    "STARTER_FIRST": "starter inspection",
                                    "MIXED": "battery-first triage, starter inspection same visit",
                                    "INSUFFICIENT": "monitor / data-quality follow-up"})
t.to_csv(HERE / "out" / "T2_windows.csv", index=False)
print(t[["vin_label", "band", "attribution", "window_days"]].to_string(index=False))
```

- [ ] **Step 3: Write T3**

```python
# STARTER MOTOR/V3.1/heuristics/T3_data_health.py
"""Per-VIN weekly dropout tracker + escalation flag (would have flagged the 5 silent-gap VINs)."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
HERE = Path(__file__).resolve().parent
import sys; sys.path.insert(0, str(HERE.parent / "features"))
import _v31_lib as L

E = L.CP["t3_escalation"]
roll = L.load_state_weekly()
rows = []
for v, g in roll.groupby("vin_label"):
    g = g.sort_values("week").copy()
    g["dropout_share"] = g["dropout_hours"] / (g["dropout_hours"] + g["observed_hours"]).clip(lower=1e-9)
    g["trail4_h"] = g["dropout_hours"].rolling(E["trailing_weeks"], min_periods=1).mean()
    own_med = float(g["dropout_hours"].median())
    g["escalation"] = (g["trail4_h"] > E["ratio_vs_own_median"] * max(own_med, 1e-9)) & (g["trail4_h"] > E["min_hours"])
    rows.append(g[["vin_label", "week", "dropout_hours", "dropout_share", "trail4_h", "escalation"]])
out = pd.concat(rows, ignore_index=True)
out.to_csv(HERE / "out" / "T3_data_health.csv", index=False)
sil = ["VIN1_F_SM", "VIN4_F_SM", "VIN5_F_SM", "VIN8_F_SM", "VIN9_F_SM"]
summ = {v: bool(out[(out["vin_label"] == v)]["escalation"].any()) for v in sil}
print(json.dumps({"silent_gap_vins_ever_escalated": summ}, indent=2))
```

- [ ] **Step 4: Run all three** (T1 → T2 → T3, in order; T2 depends on T1)

```powershell
$env:PYTHONIOENCODING='utf-8'; py -3 "STARTER MOTOR/V3.1/heuristics/T1_attribution.py"
$env:PYTHONIOENCODING='utf-8'; py -3 "STARTER MOTOR/V3.1/heuristics/T2_windows.py"
$env:PYTHONIOENCODING='utf-8'; py -3 "STARTER MOTOR/V3.1/heuristics/T3_data_health.py"
```

Expected: T1 convergence JSON (n_failed_scored = 11: 5 battery-family + 2 A1 + 4 A4; 3 A3 unscored), T2 table printed, T3 silent-gap escalation dict.

- [ ] **Step 5: Commit**

```powershell
git add "STARTER MOTOR/V3.1/heuristics"
git commit -m "feat(v3.1-sm): Task 12 - T1 attribution triage + convergence, T2 attribution-aware windows, T3 data-health monitor"
```

---

## Task 13: Graphs G1–G8

**Files:**
- Create: `STARTER MOTOR/V3.1/analysis/build_graphs.py`
- Output: `graphs/G1_state_timelines.png` … `G8_dependency_dag.png`

- [ ] **Step 1: Write the graph builder** (4-layer professional style: white bg, no top/right spines, subtle grid, direct labels, no trend connectors)

```python
# STARTER MOTOR/V3.1/analysis/build_graphs.py
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "features"))
import _v31_lib as L

G = L.SMROOT / "V3.1" / "graphs"; G.mkdir(exist_ok=True)
SOUT = L.SMROOT / "V3.1" / "state" / "out"
COLORS = {"CRANK": "#d62728", "ENGINE_OFF": "#bbbbbb", "OFF_DWELL": "#8c8c8c", "IDLE": "#ff7f0e",
          "DRIVE": "#2ca02c", "DROPOUT_RUNNING": "#9467bd", "UNKNOWN_GAP": "#e0e0e0",
          "UNKNOWN_GAP_SHORT": "#eeeeee", "OFF_CONFIRMED": "#aaaaaa", "UNKNOWN": "#f0f0f0"}


def style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(alpha=0.25, linewidth=0.5)


def g1():
    import matplotlib.dates as mdates
    fig, axes = plt.subplots(2, 1, figsize=(14, 5), sharex=False)
    for ax, vin in zip(axes, ["VIN2_F_SM", "VIN2_NF_SM"]):
        ep = pd.read_parquet(SOUT / f"V3_1_state_episodes_{vin}.parquet")
        ep = ep[ep["ts_start"] >= ep["ts_start"].max() - pd.Timedelta(days=14)]
        for _, e in ep.iterrows():
            x0 = mdates.date2num(e["ts_start"])                     # matplotlib date floats (days)
            wdt = (e["ts_end"] - e["ts_start"]).total_seconds() / 86400.0
            ax.barh(0, wdt, left=x0, height=0.6, color=COLORS.get(e["state"], "#000"), linewidth=0)
        ax.xaxis_date(); ax.set_yticks([])
        ax.set_title(f"{vin} — last 14 days of operational states", loc="left", fontsize=10)
        style(ax)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in COLORS.values()]
    fig.legend(handles, COLORS.keys(), ncol=5, loc="lower center", frameon=False, fontsize=8)
    fig.tight_layout(rect=(0, 0.08, 1, 1)); fig.savefig(G / "G1_state_timelines.png", dpi=160); plt.close(fig)


def g2():
    soaks = []
    for v in L.vins_in_order():
        p = SOUT / f"V3_1_cranks_{v}.parquet"
        if p.exists():
            soaks.append(pd.read_parquet(p)["soak_h"].dropna())
    s = pd.concat(soaks)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.hist(np.log10(s[s > 0]), bins=60, color="#4878a8")
    ax.set_xlabel("log10(soak hours before crank)"); ax.set_ylabel("cranks")
    ax.set_title("Fleet soak-duration distribution (bimodality = short stops vs overnight)", loc="left")
    style(ax); fig.tight_layout(); fig.savefig(G / "G2_soak_distribution.png", dpi=160); plt.close(fig)


def g3():
    h = pd.read_csv(SOUT / "P0_gap_hist.csv")
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.bar(h["gap_min_bin_lo"], h["count"], width=1.0, color="#4878a8")
    ax.axvspan(14, 18, color="#d62728", alpha=0.15)
    ax.set_yscale("log"); ax.set_xlabel("gap length (min)"); ax.set_ylabel("count (log)")
    ax.set_title("Telemetry gap lengths with heartbeat band [14,18] min highlighted", loc="left")
    style(ax); fig.tight_layout(); fig.savefig(G / "G3_gap_histogram.png", dpi=160); plt.close(fig)


def g4():
    t1 = pd.read_csv(L.SMROOT / "V3.1" / "heuristics" / "out" / "T1_attribution.csv")
    arch = pd.read_csv(L.SMROOT / "V1.1" / "discovery" / "out" / "E2_failed_vin_archetypes.csv")[["vin_label", "archetype"]]
    t1 = t1.merge(arch, on="vin_label", how="left"); t1["archetype"] = t1["archetype"].fillna("NF")
    fig, ax = plt.subplots(figsize=(8, 6))
    for a, g in t1.groupby("archetype"):
        ax.scatter(g["lowv_crank_share"], g["goodv_hardstart_weeks12"], label=a, s=45, alpha=0.85)
    ax.set_xlabel("battery evidence: low-voltage crank share (last 90 d)")
    ax.set_ylabel("starter evidence: weeks with hard-start @ good V (last 12 wk)")
    ax.set_title("T1 attribution quadrant, archetype-colored", loc="left")
    ax.legend(frameon=False, fontsize=8); style(ax)
    fig.tight_layout(); fig.savefig(G / "G4_attribution_quadrant.png", dpi=160); plt.close(fig)


def g5():
    mat = pd.read_csv(L.SMROOT / "V1.1" / "results" / "V1_1_SM_feature_matrix.csv")
    S = json.loads((L.V31_OUT / "V3_1_gate_summary.json").read_text())
    feats = [e["feature"] for e in S["E1"]]
    fig, axes = plt.subplots(1, len(feats), figsize=(3 * len(feats), 4), sharey=False)
    for ax, c in zip(np.atleast_1d(axes), feats):
        cache = pd.read_csv(L.V31_OUT / f"{c}_cache.csv").merge(mat[["vin_label", "failed"]], on="vin_label")
        for lab, x in [(0, 0), (1, 1)]:
            v = cache.loc[cache["failed"] == bool(lab), c].dropna()
            ax.scatter(np.full(len(v), x) + np.random.default_rng(42).uniform(-0.08, 0.08, len(v)), v, s=18, alpha=0.8,
                       color="#2ca02c" if lab == 0 else "#d62728")
        e1 = next(e for e in S["E1"] if e["feature"] == c)
        ax.set_xticks([0, 1]); ax.set_xticklabels(["NF", "F"])
        ax.set_title(f"{c}\nAUROC={e1['auroc']} p={e1['mw_p']}\n{S['verdicts'][c]['verdict']}", fontsize=7)
        style(ax)
    fig.tight_layout(); fig.savefig(G / "G5_gate_panels.png", dpi=160); plt.close(fig)


def g6():
    r = L.load_state_weekly(); m = r[r["active_days"] >= 2]
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.scatter(m["km"] / m["active_days"], m["engine_hours"] / m["active_days"], s=6, alpha=0.25, color="#4878a8")
    for x in (10, 800):
        ax.axvline(x, color="#d62728", linewidth=0.8, linestyle="--")
    for yv in (0.5, 22):
        ax.axhline(yv, color="#d62728", linewidth=0.8, linestyle="--")
    ax.set_xscale("log"); ax.set_xlabel("km per active day"); ax.set_ylabel("engine-hours per active day")
    ax.set_title("SV-3 plausibility: masked VIN-weeks vs registered bands", loc="left")
    style(ax); fig.tight_layout(); fig.savefig(G / "G6_sv3_plausibility.png", dpi=160); plt.close(fig)


def g7():
    t3 = pd.read_csv(L.SMROOT / "V3.1" / "heuristics" / "out" / "T3_data_health.csv", parse_dates=["week"])
    sil = ["VIN1_F_SM", "VIN4_F_SM", "VIN5_F_SM", "VIN8_F_SM", "VIN9_F_SM"]
    fig, axes = plt.subplots(5, 1, figsize=(11, 9), sharex=False)
    for ax, v in zip(axes, sil):
        g = t3[t3["vin_label"] == v]
        ax.plot(g["week"], g["dropout_share"], linewidth=1.0, color="#4878a8")
        fires = g[g["escalation"]]
        ax.scatter(fires["week"], fires["dropout_share"], color="#d62728", s=14, zorder=3)
        ax.set_title(v, loc="left", fontsize=9); ax.set_ylabel("dropout share", fontsize=7); style(ax)
    fig.suptitle("T3 dropout-share timelines, silent-gap VINs (red = escalation flag)", x=0.01, ha="left")
    fig.tight_layout(); fig.savefig(G / "G7_dropout_timelines.png", dpi=160); plt.close(fig)


def g8():
    nodes = {  # (x, y, label)
        "RAW": (0, 2, "6 signals + ts"), "EVT": (0, 0.8, "crank events\n(frozen)"),
        "SE": (1, 2, "state engine"), "EP": (2, 2, "episodes/trips\nsoak/engine-hrs"),
        "A": (2, 0.8, "A1 A2 A3"), "B": (3, 1.4, "B1 B2"), "C": (3, 2.4, "C1 C2"),
        "GATE": (4, 1.4, "E0-E3 gate"), "T1": (4, 0.4, "T1 triage"), "CAT": (4, 2.6, "catalog")}
    edges = [("RAW", "SE"), ("SE", "EP"), ("EVT", "A"), ("EP", "B"), ("EP", "C"), ("EP", "CAT"),
             ("A", "GATE"), ("B", "GATE"), ("C", "GATE"), ("A", "T1"), ("EVT", "B")]
    fig, ax = plt.subplots(figsize=(10, 5))
    for a, b in edges:
        (x0, y0, _), (x1, y1, _) = nodes[a], nodes[b]
        ax.annotate("", xy=(x1 - 0.18, y1), xytext=(x0 + 0.18, y0),
                    arrowprops=dict(arrowstyle="->", color="#888", lw=1.0))
    for k, (x, y, lab) in nodes.items():
        ax.text(x, y, lab, ha="center", va="center", fontsize=8,
                bbox=dict(boxstyle="round,pad=0.35", fc="#eef3f8", ec="#4878a8"))
    ax.set_xlim(-0.5, 4.7); ax.set_ylim(0, 3.2); ax.axis("off")
    ax.set_title("V3.1 feature dependency DAG", loc="left")
    fig.tight_layout(); fig.savefig(G / "G8_dependency_dag.png", dpi=160); plt.close(fig)


for f in (g1, g2, g3, g4, g5, g6, g7, g8):
    f(); print(f.__name__, "ok")
```

- [ ] **Step 2: Run** — expected `g1 ok` … `g8 ok`, 8 PNGs in `graphs/`.

- [ ] **Step 3: Commit**

```powershell
git add "STARTER MOTOR/V3.1/analysis" "STARTER MOTOR/V3.1/graphs"
git commit -m "feat(v3.1-sm): Task 13 - graphs G1-G8 (state timelines, soak, heartbeat band, attribution quadrant, gate panels, SV-3, dropout, DAG)"
```

---

## Task 14: Reports + appendices

**Files:**
- Create in `STARTER MOTOR/V3.1/reports/`: `V3_1_SM_feature_dictionary.md`, `V3_1_SM_feature_catalog.md`, `V3_1_SM_state_engine_report.md`, `V3_1_SM_data_reality_memo.md`, `V3_1_SM_results.md`, `V3_1_SM_verdict.md`, `V3_1_SM_exec_summary.md`
- Create in `STARTER MOTOR/V3.1/appendix/`: `temperature_closure_and_annex.md`, `instrumentation_v2.md`

These are prose reports written from the produced artifacts. For each, the required structure and data sources (fill every number from the named file — no invented values):

- [ ] **Step 1: `V3_1_SM_data_reality_memo.md`** — P0-1..P0-6 outcomes. Sources: `state/out/P0_*.json`. Sections: heartbeat verdict (quote `confirmed` + fractions); duplicate-timestamp rule adopted; dropout taxonomy fleet table; tz codification (IST assumption); sentinel-reality note (VSI in volts, no 0/255; RPM 65535 absent); SMA undercount per VIN.
- [ ] **Step 2: `V3_1_SM_state_engine_report.md`** — states/thresholds table (from `params/V3_1_state_params.json`), the spec §5.4 Mermaid state diagram (copy verbatim), SV-1..SV-5 adjudication (from `V3_1_sv_gates.json` + gate summary reconciliation for SV-5), per-VIN dwell summary, promotion recommendation (promote to `src/` only if all SV pass).
- [ ] **Step 3: `V3_1_SM_feature_dictionary.md`** — the 7 candidates: math definition (copy spec §7.2 verbatim), params used, n_nonnull, per-candidate E1 row (from `V3_1_gate_summary.json`).
- [ ] **Step 4: `V3_1_SM_feature_catalog.md`** — spec §6.1 table with computed fleet medians per feature (from `features/out/V3_1_SM_catalog.csv`), confidence class, production notes; banned-by-construction registry (lifetime totals + graveyard cross-refs, spec §6.3); the Mermaid dependency DAG; EXPLORATORY post-gate stats table (from `analysis/out/catalog_exploratory_stats.csv`) with the discipline note that nothing promotes within V3.1.
- [ ] **Step 5: `V3_1_SM_results.md`** — §0 reconciliation; §1 E1 table; §2 E2 deltas; §3 E3 (or "not triggered"); §4 BH-FDR (from `analysis/out/V3_1_validation.json`); §5 SV gates; §6 channels (T1 convergence JSON, T2 table, T3 silent-gap flags). Every number from the JSONs/CSVs.
- [ ] **Step 6: `V3_1_SM_verdict.md`** — per-candidate verdict + reason; tiered-success scorecard (Tier 1: gate outcome; Tier 2: T1 convergence n/11; Tier 3: SV gates + artifacts list; Tier 4: annex refreshed); "what would change our mind" (new instrumentation, larger fleet); explicit statement if all-REJECT that this is the pre-registered expected outcome.
- [ ] **Step 7: `V3_1_SM_exec_summary.md`** — 1 page: what was built, gate outcome in one table, the T1 business deliverable, priority-ranked next actions (spec §13 updated with actuals).
- [ ] **Step 8: `appendix/temperature_closure_and_annex.md`** — consolidate spec §9 content + C2's actual gate result as the final temperature-adjacent evidence; forward path (region mapping ask, GPS+Open-Meteo/ERA5, SPN 171 / SPN 110).
- [ ] **Step 9: `appendix/instrumentation_v2.md`** — refreshed 500-truck sensor-gap list: GPS/region, SPN 171 ambient, SPN 110 coolant, battery current sensor, higher-rate VSI sampling around cranks (1 Hz burst), maintenance/parts records (turns archetypes + T1 into supervised labels).
- [ ] **Step 10: Commit**

```powershell
git add "STARTER MOTOR/V3.1/reports" "STARTER MOTOR/V3.1/appendix"
git commit -m "docs(v3.1-sm): Task 14 - reports (data reality, state engine, dictionary, catalog, results, verdict, exec) + appendices"
```

---

## Task 15: Wrap-up — column-dictionary note, final verification

**Files:**
- Modify: `docs/column_dictionary.md` (append a dated correction note)

- [ ] **Step 1: Append to `docs/column_dictionary.md`** (do not alter existing rows):

```markdown
## Correction note (2026-07 V3.1 SM probes)

Verified against the SM parquets (30.9M + 76.3M rows): **VSI is already stored in volts**
(rest median 28.0 V; crank median ~21-22 V) — the "×0.2 if large" rule and the 0/255
sentinels do not occur in these files (missing values are NaN). RPM/CSP 65535 sentinels
also do not occur. Pipelines retain the masking/scaling as a harmless no-op contract.
Timestamps are tz-naive vehicle-local (IST assumption, codified V3.1 P0-4).
```

- [ ] **Step 2: Full test suite + artifact inventory**

```powershell
$env:PYTHONIOENCODING='utf-8'; py -3 -m pytest "STARTER MOTOR/V3.1" -q
Get-ChildItem "STARTER MOTOR/V3.1" -Recurse -File | Group-Object { $_.Directory.Name } | Select-Object Name, Count
```

Expected: `16 passed` (9 state + 6 factors + 1 reconcile); every folder from the spec §10.2 tree is non-empty.

- [ ] **Step 3: Definition-of-done check against spec §14** — walk items 1–8; each must point at an existing artifact. Record the checklist at the bottom of `V3_1_SM_verdict.md`.

- [ ] **Step 4: Final commit**

```powershell
git add "docs/column_dictionary.md" "STARTER MOTOR/V3.1"
git commit -m "docs(v3.1-sm): Task 15 - column-dictionary correction note + definition-of-done checklist"
```

---

## Execution notes

- **Task order is binding**: 0 → 1 → 2 → 3 → 4 → 5 → 6/7 (parallel-safe) → 8 → 9 → 10 → 11 → 12 → 13 → 14 → 15. Task 9 must precede Task 11 (catalog discipline). Task 12 T1 precedes T2.
- **Long-running steps**: Task 2 (~30–60 min fleet probes) and Task 5 (~45–90 min fleet state run) — run in background, verify outputs after.
- **No result-driven edits**: params are frozen at Task 0; the only allowed post-Task-0 changes are the pre-registered SV-3/heartbeat drop rules. If a bug is found in factor code, fix the bug, re-run, and note the fix in the verdict — never adjust thresholds.
