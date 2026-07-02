# V3 Starter Motor — Feature Engineering & Research — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Engineer and honestly adjudicate ~7 new Starter-Motor features (interaction/cross features + two usage probes) against the frozen modal-4 baseline (non-nested LOVO AUROC 0.9357 / nested 0.9321) using the pre-locked V1.1/V2.1 gate, and ship the full deliverable set with accept/reject verdicts.

**Architecture:** Each candidate is computed to a static per-VIN cache CSV (`out/{name}_cache.csv`, 2 cols `vin_label,{name}`) — the exact input contract the existing gate consumes. A verbatim copy of the numeric gate core (`_gate_core.py`) preserves the closed-form Ridge + custom rank-AUROC so reproduction is bit-for-bit; a V3 driver runs reconciliation → E1 (admissibility) → redundancy → E2 (fixed-subset LOVO increment) → E3 (nested, exploratory) and writes `V3_gate_summary.json`. Analysis (correlation/MI/permutation/SHAP/significance), graphs, and reports consume the summary.

**Tech Stack:** `py -3` (system Python — the `.venv` lacks pandas), pandas + numpy + scipy + polars (lazy) + scikit-learn (analysis only) + matplotlib. No pytest dependency — tests are plain `py -3` assert-scripts that exit non-zero on failure.

---

## Refinements vs committed spec (`Plan/V3_SM_spec.md`)

Discovered while extracting the reuse interfaces; all *reduce* scope (no post-hoc additions, so pre-registration integrity holds):

1. **Dropped F1a `restart_burst_rate`** — `retry_burst_rate_last90` already exists in `V1_1_SM_feature_matrix.csv` (pooled, non-winning). A burst feature is already-covered.
2. **Reframed F4a** — GED state-2 (disturbance) is absent from failed SM VINs (GED∈{0,3}); screen the tracked `ged3_rows` rate instead and document the state-2 absence as the null.
3. **F4c `vsi_recovery_time` → OPTIONAL** (stretch) — recovery *slope* already WEAK; recovery *time* needs a raw-parquet pass for low expected value.
4. **Interactions use global-z factors** precomputed into the static cache (the gate contract is one scalar/VIN, so true fold-internal z isn't expressible there). Documented SCREEN-GRADE; any E1 survivor is re-verified fold-safe in Task 9.

Final candidate set (7 core + 1 optional): `dose_dip_x_starts` (F3-1), `weakbat_cold_load` (F3-2), `reg_instab_x_usage` (F3-3), `sag_under_load` (F3-4), `cold_start_fraction_delta90` (F1b), `ged3_rate_delta90` (F4a), `night_start_fraction_delta90` (F4b), [`vsi_recovery_time_delta90` (F4c, optional)].

---

## Canonical paths & interfaces (verified)

```
SMROOT   = D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR
V3       = <SMROOT>\V3
MATRIX   = <SMROOT>\V1.1\results\V1_1_SM_feature_matrix.csv          # 34x12; cols vin_label,failed,...
EVENTS   = <SMROOT>\cache\events\V1_SM_crank_events.parquet          # per crank event
WEEKLY   = <SMROOT>\cache\weekly\V1_SM_weekly_*.parquet              # 34 files, per VIN-week
V21_LIB  = <SMROOT>\V2.1\features\_feature_lib.py                    # import for readers (side-effect-free)
V21_GATE = <SMROOT>\V2.1\features\V2_1_feature_gate.py               # SOURCE to copy core from
CONFIG   = <SMROOT>\src\V1_SM_config.py                              # SM_FAILED/SM_NONFAIL parquet paths + sentinels
```

**Modal-4 (verbatim):** `["vsi_withinwk_std_ratio_30d_w","rest_vsi_p05_delta90","vsi_range_trend","dip_depth_last90_delta"]`
**SMA_DEAD (force NaN, verbatim):** `["VIN8_F_SM","VIN9_F_SM","VIN10_NF_SM","VIN11_NF_SM","VIN12_NF_SM","VIN13_NF_SM","VIN20_NF_SM"]`
**Reconcile target:** `plain_lovo(mat[MODAL].values, y)` → `rank_auroc` == **0.9357** (±0.002) else `sys.exit(1)`.
**`_feature_lib` readers:** `vins_in_order()`, `build_px()` → DataFrame indexed by `vin_label`, cols `t_end_approx, t_90_cutoff, win_start_l40`; `load_events_nonartifact()` → events DF (`artifact==False`, `ts_start` datetime).
**Events DF columns:** `vin_label, failed, event_id, ts_start, n_rows, multi_sample, dur_s, artifact, baseline_vsi, min_vsi_crank, dip_depth, rpm_max_15s, success, recovery_slope, retry_within_120s, days_before_t_end`.
**Weekly columns:** `vin_label, failed, week, n_rows, active_days, sma_obs_rows, sma1_rows, vsi_obs_rows, vsi_drive_mean, vsi_drive_std, vsi_drive_p05, vsi_drive_p95, vsi_rest_median, vsi_rest_p05, vsi_below_21_rows, vsi_above_32_rows, rpm_mean, csp_mean, anr_pos_mean, ged3_rows`.
**Gate protocol constants (verbatim):** `ALPHA_MW=0.10, AUROC_MIN=0.60, CORR_MAX=0.85, E2_ADD=+0.01, RIDGE_ALPHA=1.0`; proxy-leak Spearman |r|≤0.5 vs {n_weeks,t_start,span}.

---

## Task 0: Pre-register params & candidate manifest

**Files:**
- Create: `STARTER MOTOR/V3/params/V3_gate_params.json`
- Create: `STARTER MOTOR/V3/params/V3_feature_params.json`
- Create: `STARTER MOTOR/V3/params/V3_candidates.json`

- [ ] **Step 1: Write the three params files (verbatim content)**

`V3_gate_params.json`:
```json
{
  "reconcile_expected_nonnested": 0.9357, "reconcile_nested": 0.9321, "reconcile_tol": 0.002,
  "alpha_mw": 0.10, "auroc_min": 0.60, "corr_max_redundancy": 0.85,
  "proxy_leak_spearman_max": 0.5, "e2_add_threshold": 0.01, "ridge_alpha": 1.0,
  "proxy_targets": ["n_weeks", "t_start", "span"],
  "modal_subset": ["vsi_withinwk_std_ratio_30d_w","rest_vsi_p05_delta90","vsi_range_trend","dip_depth_last90_delta"],
  "sma_dead": ["VIN8_F_SM","VIN9_F_SM","VIN10_NF_SM","VIN11_NF_SM","VIN12_NF_SM","VIN13_NF_SM","VIN20_NF_SM"]
}
```

`V3_feature_params.json`:
```json
{
  "cold_rest_gap_s": 21600, "night_hours": [0,1,2,3,4],
  "min_events_per_vin": 8, "min_events_side": 3, "min_events_base": 6,
  "min_weeks_side": 3, "dip_min_events": 10,
  "anr_pre_crank_window_s": 60, "anr_sentinels": {"high": 65535.0, "neg": -5000.0},
  "recovery_window_s": 45,
  "zscore": "global_across_34_vins_nan_aware",
  "interaction_note": "z(A)*z(B) with global mean/std; SCREEN-GRADE; E1 survivors re-verified fold-safe in Task 9"
}
```

`V3_candidates.json`:
```json
{
  "F3-1": {"name": "dose_dip_x_starts", "kind": "interaction", "factors": ["dip_depth_last90_level","starts_per_active_day_last90"], "exp_power": "M"},
  "F3-2": {"name": "weakbat_cold_load", "kind": "interaction", "factors": ["rest_vsi_p05_last90","cold_start_fraction_last90"], "exp_power": "L-M"},
  "F3-3": {"name": "reg_instab_x_usage", "kind": "interaction", "factors": ["vsi_range_trend","starts_per_active_day_last90"], "exp_power": "L"},
  "F3-4": {"name": "sag_under_load", "kind": "interaction", "factors": ["dip_depth_last90_delta","anr_pre_crank_60s"], "exp_power": "L-M"},
  "F1b": {"name": "cold_start_fraction_delta90", "kind": "usage", "exp_power": "L"},
  "F4a": {"name": "ged3_rate_delta90", "kind": "probe", "exp_power": "VL", "note": "GED state-2 absent in failed SM"},
  "F4b": {"name": "night_start_fraction_delta90", "kind": "probe", "exp_power": "L"},
  "F4c": {"name": "vsi_recovery_time_delta90", "kind": "probe_optional", "exp_power": "L"}
}
```

- [ ] **Step 2: Commit**
```
git add -- "STARTER MOTOR/V3/params/V3_gate_params.json" "STARTER MOTOR/V3/params/V3_feature_params.json" "STARTER MOTOR/V3/params/V3_candidates.json"
git commit -m "feat(v3-sm): pre-register V3 gate params, feature params, candidate manifest"
```

---

## Task 1: Verbatim gate core + reconciliation gate (regression test FIRST)

**Files:**
- Create: `STARTER MOTOR/V3/features/_gate_core.py`
- Create: `STARTER MOTOR/V3/features/tests/test_reconcile.py`

- [ ] **Step 1: Write the failing reconciliation test**

`tests/test_reconcile.py`:
```python
import sys, json
from pathlib import Path
import pandas as pd
HERE = Path(__file__).resolve().parents[1]           # .../V3/features
SMROOT = HERE.parents[1]                              # .../STARTER MOTOR
sys.path.insert(0, str(HERE))
import _gate_core as G

def main():
    mat = pd.read_csv(SMROOT / "V1.1" / "results" / "V1_1_SM_feature_matrix.csv")
    y = mat["failed"].astype(int).values
    assert len(y) == 34 and int(y.sum()) == 14, f"bad matrix {len(y)}/{y.sum()}"
    modal = ["vsi_withinwk_std_ratio_30d_w","rest_vsi_p05_delta90","vsi_range_trend","dip_depth_last90_delta"]
    X = mat[modal].values.astype(float)
    a = G.rank_auroc(G.plain_lovo(X, y), y)
    assert abs(a - 0.9357) <= 0.002, f"RECONCILE FAIL: {a} != 0.9357"
    print(f"PASS reconcile modal-4 non-nested LOVO AUROC = {a:.4f}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it — expect failure (no `_gate_core` yet)**
Run: `py -3 "STARTER MOTOR/V3/features/tests/test_reconcile.py"`
Expected: `ModuleNotFoundError: No module named '_gate_core'`

- [ ] **Step 3: Create `_gate_core.py` by copying the numeric core verbatim**

Open `STARTER MOTOR/V2.1/features/V2_1_feature_gate.py`. Copy **verbatim** ONLY these definitions (and the constant `RIDGE_ALPHA = 1.0`) into `_gate_core.py`, in this order, and **nothing else** (do NOT copy any top-level execution, file I/O, `pd.read_csv`, or print statements — `_gate_core.py` must have zero import-time side effects):
```
RIDGE_ALPHA = 1.0
def ridge_z(Xtr, ytr, Xte, alpha=RIDGE_ALPHA): ...
def sigmoid(z): ...
def lovo_z(X, yy): ...
def rank_auroc(s, l): ...
def mw_p(a, b): ...
def youden_thr(yy, p): ...
def mcc_at(yy, p, thr): ...
def screen_pool(Xdf, yy, feats): ...
def subset_search(Xdf, yy, pool, rank): ...
def nested_lovo(Xdf, yy, feats_all): ...
def plain_lovo(X, yy): ...
```
Add the standard imports the bodies need at the top: `import numpy as np` and `from scipy import stats`. Verify no other module-level names are referenced (if a body references a global constant beyond `RIDGE_ALPHA`, copy that constant too).

- [ ] **Step 4: Run the reconciliation test — expect PASS**
Run: `py -3 "STARTER MOTOR/V3/features/tests/test_reconcile.py"`
Expected: `PASS reconcile modal-4 non-nested LOVO AUROC = 0.9357`
(If it prints any value outside [0.9337, 0.9377], the copy is unfaithful — re-copy the exact function bodies.)

- [ ] **Step 5: Commit**
```
git add -- "STARTER MOTOR/V3/features/_gate_core.py" "STARTER MOTOR/V3/features/tests/test_reconcile.py"
git commit -m "feat(v3-sm): verbatim gate core + reconciliation regression gate (0.9357)"
```

---

## Task 2: V3 feature library (readers, weekly loader, cache writer, z-score)

**Files:**
- Create: `STARTER MOTOR/V3/features/_v3_lib.py`
- Create: `STARTER MOTOR/V3/features/tests/test_v3_lib.py`

- [ ] **Step 1: Write the failing test**

`tests/test_v3_lib.py`:
```python
import sys, math
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import _v3_lib as L

def test_zscore_nan_aware():
    d = {"a": 1.0, "b": 3.0, "c": np.nan, "d": 5.0}
    z = L.zscore_across({k: d[k] for k in ["a","b","c","d"]}, ["a","b","c","d"])
    vals = np.array([z["a"], z["b"], z["d"]])
    assert abs(np.nanmean(vals)) < 1e-9, "z-mean not ~0"
    assert math.isnan(z["c"]), "NaN factor must stay NaN"
    print("PASS zscore_across")

def test_readers_present():
    assert L.vins_in_order() and len(L.vins_in_order()) == 34
    wk = L.load_weekly()
    assert {"vin_label","week","active_days","vsi_rest_p05","ged3_rows"} <= set(wk.columns)
    print("PASS readers")

if __name__ == "__main__":
    test_zscore_nan_aware(); test_readers_present()
```

- [ ] **Step 2: Run — expect failure**
Run: `py -3 "STARTER MOTOR/V3/features/tests/test_v3_lib.py"`
Expected: `ModuleNotFoundError: No module named '_v3_lib'`

- [ ] **Step 3: Implement `_v3_lib.py`**
```python
import sys, glob
from pathlib import Path
import numpy as np
import pandas as pd

SMROOT = Path(__file__).resolve().parents[2]          # .../STARTER MOTOR
V3_OUT = SMROOT / "V3" / "features" / "out"
V3_OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(SMROOT / "V2.1" / "features"))
import _feature_lib as F                              # side-effect-free readers

SMA_DEAD = ["VIN8_F_SM","VIN9_F_SM","VIN10_NF_SM","VIN11_NF_SM","VIN12_NF_SM","VIN13_NF_SM","VIN20_NF_SM"]

def vins_in_order():         return F.vins_in_order()
def build_px():              return F.build_px()
def load_events():           return F.load_events_nonartifact()

def load_weekly():
    files = sorted(glob.glob(str(SMROOT / "cache" / "weekly" / "V1_SM_weekly_*.parquet")))
    wk = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    wk["week"] = pd.to_datetime(wk["week"])
    return wk

def zscore_across(value_by_vin, order):
    vals = np.array([value_by_vin.get(v, np.nan) for v in order], dtype=float)
    mu, sd = np.nanmean(vals), np.nanstd(vals)
    if not np.isfinite(sd) or sd == 0:
        return {v: np.nan for v in order}
    return {v: (value_by_vin.get(v, np.nan) - mu) / sd for v in order}

def write_cache(name, value_by_vin):
    order = vins_in_order()
    rows = []
    for v in order:
        val = np.nan if v in SMA_DEAD else value_by_vin.get(v, np.nan)
        rows.append({"vin_label": v, name: val})
    df = pd.DataFrame(rows)
    path = V3_OUT / f"{name}_cache.csv"
    df.to_csv(path, index=False)
    print(f"wrote {path.name} ({len(df)} rows, {df[name].notna().sum()} non-null)")
    return path
```
Note: `write_cache` intentionally forces SMA_DEAD → NaN for SMA/crank-derived features (matches the gate). For non-SMA features (e.g. `ged3_rate`, weekly-VSI) call `write_cache` with `force_dead=False` variant — add that param:
```python
def write_cache(name, value_by_vin, force_dead=True):
    order = vins_in_order(); rows = []
    for v in order:
        val = np.nan if (force_dead and v in SMA_DEAD) else value_by_vin.get(v, np.nan)
        rows.append({"vin_label": v, name: val})
    df = pd.DataFrame(rows); path = V3_OUT / f"{name}_cache.csv"; df.to_csv(path, index=False)
    print(f"wrote {path.name} ({len(df)} rows, {df[name].notna().sum()} non-null)"); return path
```

- [ ] **Step 4: Run the test — expect PASS**
Run: `py -3 "STARTER MOTOR/V3/features/tests/test_v3_lib.py"`
Expected: `PASS zscore_across` then `PASS readers`

- [ ] **Step 5: Commit**
```
git add -- "STARTER MOTOR/V3/features/_v3_lib.py" "STARTER MOTOR/V3/features/tests/test_v3_lib.py"
git commit -m "feat(v3-sm): V3 feature lib (readers, weekly loader, nan-aware z-score, cache writer)"
```

---

## Task 3: Factor builders (shared per-VIN scalars) + unit test on synthetic events

**Files:**
- Create: `STARTER MOTOR/V3/features/_factors.py`
- Create: `STARTER MOTOR/V3/features/tests/test_factors.py`

These are the reusable per-VIN scalar factors consumed by F1b and the F3 interactions.

- [ ] **Step 1: Write the failing test (synthetic events, known answers)**

`tests/test_factors.py`:
```python
import sys
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(HERE))
import _factors as FA

def _synth():
    # 10 events for VINX: t90 cutoff at day 20; 6 before (base), 4 after (last90)
    base = pd.Timestamp("2025-01-01")
    ts = [base + pd.Timedelta(days=d) for d in [0, 2, 4, 6, 8, 10,   22, 22.3, 25, 40]]
    ev = pd.DataFrame({"vin_label": "VINX", "ts_start": ts,
                       "dip_depth": [1.0]*6 + [2.0,2.0,2.0,2.0]})
    px = pd.DataFrame({"t_90_cutoff": [pd.Timestamp("2025-01-21")],
                       "win_start_l40": [pd.Timestamp("2024-06-01")],
                       "t_end_approx": [pd.Timestamp("2025-03-01")]}, index=["VINX"])
    return ev, px

def test_dip_level_last90():
    ev, px = _synth()
    v = FA.dip_depth_last90_level(ev, px, "VINX", min_events=1)
    assert abs(v - 2.0) < 1e-9, v
    print("PASS dip_depth_last90_level")

def test_cold_fraction_delta():
    ev, px = _synth()
    # gaps: first=cold; day22 after 12d gap=cold; 22.3 (0.3d) not cold; 25 (2.7d) cold; 40 cold
    v = FA.cold_start_fraction_delta90(ev, px, "VINX", rest_gap_s=6*3600, min_side=1, min_base=1)
    assert v is not None and np.isfinite(v), v
    print(f"PASS cold_start_fraction_delta90 = {v:.3f}")

if __name__ == "__main__":
    test_dip_level_last90(); test_cold_fraction_delta()
```

- [ ] **Step 2: Run — expect failure**
Run: `py -3 "STARTER MOTOR/V3/features/tests/test_factors.py"` → `ModuleNotFoundError: _factors`

- [ ] **Step 3: Implement `_factors.py`**
```python
import numpy as np, pandas as pd

def _evin(ev, vin):
    return ev[ev["vin_label"] == vin].sort_values("ts_start").reset_index(drop=True)

def _ok_px(px, vin):
    return (vin in px.index) and (not px.loc[vin].isna().any())

def dip_depth_last90_level(ev, px, vin, min_events=10):
    if not _ok_px(px, vin): return np.nan
    e = _evin(ev, vin); t90 = pd.Timestamp(px.loc[vin, "t_90_cutoff"])
    d = e.loc[e["ts_start"] >= t90, "dip_depth"].astype(float).values
    d = d[np.isfinite(d)]
    return float(d.mean()) if len(d) >= min_events else np.nan

def starts_per_active_day_last90(ev, wk, px, vin):
    if not _ok_px(px, vin): return np.nan
    e = _evin(ev, vin); t90 = pd.Timestamp(px.loc[vin, "t_90_cutoff"])
    n_starts = int((e["ts_start"] >= t90).sum())
    w = wk[wk["vin_label"] == vin]; active = float(w.loc[w["week"] >= t90, "active_days"].sum())
    return (n_starts / active) if active > 0 else np.nan

def cold_start_fraction_last90(ev, px, vin, rest_gap_s=6*3600, min_events=3):
    if not _ok_px(px, vin): return np.nan
    e = _evin(ev, vin)
    if len(e) < 2: return np.nan
    gaps = np.diff(e["ts_start"].values).astype("timedelta64[s]").astype(float)
    e["is_cold"] = np.concatenate([[True], gaps >= rest_gap_s])
    t90 = pd.Timestamp(px.loc[vin, "t_90_cutoff"])
    last = e[e["ts_start"] >= t90]
    return float(last["is_cold"].mean()) if len(last) >= min_events else np.nan

def cold_start_fraction_delta90(ev, px, vin, rest_gap_s=6*3600, min_side=3, min_base=6):
    if not _ok_px(px, vin): return np.nan
    e = _evin(ev, vin)
    if len(e) < 2: return np.nan
    gaps = np.diff(e["ts_start"].values).astype("timedelta64[s]").astype(float)
    e["is_cold"] = np.concatenate([[True], gaps >= rest_gap_s])
    win = pd.Timestamp(px.loc[vin, "win_start_l40"]); t90 = pd.Timestamp(px.loc[vin, "t_90_cutoff"])
    e = e[e["ts_start"] >= win]
    last = e[e["ts_start"] >= t90]; base = e[e["ts_start"] < t90]
    if len(last) < min_side or len(base) < min_base: return np.nan
    return float(last["is_cold"].mean() - base["is_cold"].mean())

def rest_vsi_p05_last90(wk, px, vin, min_weeks=3):
    if not _ok_px(px, vin): return np.nan
    w = wk[wk["vin_label"] == vin]; t90 = pd.Timestamp(px.loc[vin, "t_90_cutoff"])
    v = w.loc[w["week"] >= t90, "vsi_rest_p05"].astype(float).values; v = v[np.isfinite(v)]
    return float(v.mean()) if len(v) >= min_weeks else np.nan
```

- [ ] **Step 4: Run — expect PASS**
Run: `py -3 "STARTER MOTOR/V3/features/tests/test_factors.py"`
Expected: `PASS dip_depth_last90_level` then `PASS cold_start_fraction_delta90 = ...`

- [ ] **Step 5: Commit**
```
git add -- "STARTER MOTOR/V3/features/_factors.py" "STARTER MOTOR/V3/features/tests/test_factors.py"
git commit -m "feat(v3-sm): per-VIN factor builders (dip level, starts/day, cold-start fraction, rest-VSI) + tests"
```

---

## Task 4: F1b cold-start-fraction candidate + the three cache-based interactions (F3-1/2/3)

**Files:**
- Create: `STARTER MOTOR/V3/features/build_cache_features.py`

- [ ] **Step 1: Implement the builder (writes 4 candidate caches)**
```python
import sys
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
import _v3_lib as L
import _factors as FA

def main():
    order = L.vins_in_order(); px = L.build_px(); ev = L.load_events(); wk = L.load_weekly()
    mat = pd.read_csv(L.SMROOT / "V1.1" / "results" / "V1_1_SM_feature_matrix.csv").set_index("vin_label")

    dip_level   = {v: FA.dip_depth_last90_level(ev, px, v) for v in order}
    starts_day  = {v: FA.starts_per_active_day_last90(ev, wk, px, v) for v in order}
    cold_frac   = {v: FA.cold_start_fraction_last90(ev, px, v) for v in order}
    rest_p05    = {v: FA.rest_vsi_p05_last90(wk, px, v) for v in order}
    cold_delta  = {v: FA.cold_start_fraction_delta90(ev, px, v) for v in order}
    range_trend = {v: float(mat.loc[v, "vsi_range_trend"]) if v in mat.index else np.nan for v in order}

    # F1b standalone usage feature
    L.write_cache("cold_start_fraction_delta90", cold_delta, force_dead=True)

    # F3 interactions: z(A)*z(B) with global nan-aware z
    def interact(a, b):
        za, zb = L.zscore_across(a, order), L.zscore_across(b, order)
        return {v: za[v] * zb[v] for v in order}

    L.write_cache("dose_dip_x_starts",   interact(dip_level, starts_day),   force_dead=True)
    L.write_cache("weakbat_cold_load",   interact(rest_p05, cold_frac),     force_dead=True)
    L.write_cache("reg_instab_x_usage",  interact(range_trend, starts_day), force_dead=True)

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**
Run: `py -3 "STARTER MOTOR/V3/features/build_cache_features.py"`
Expected: four `wrote ..._cache.csv (34 rows, N non-null)` lines (N typically 18–27 given SMA_DEAD + NaN factors).

- [ ] **Step 3: Sanity-check the caches exist & are well-formed**
Run: `py -3 -c "import pandas as pd,glob;[print(f.split('out')[-1], pd.read_csv(f).shape) for f in glob.glob(r'STARTER MOTOR/V3/features/out/*_cache.csv')]"`
Expected: each `(34, 2)`.

- [ ] **Step 4: Commit**
```
git add -- "STARTER MOTOR/V3/features/build_cache_features.py" "STARTER MOTOR/V3/features/out/"
git commit -m "feat(v3-sm): build F1b + F3-1/2/3 candidate caches (cold-start rate + 3 interactions)"
```

---

## Task 5: F3-4 `sag_under_load` (raw-parquet ANR pre-crank) + F4 probes

**Files:**
- Create: `STARTER MOTOR/V3/features/build_raw_and_probes.py`

- [ ] **Step 1: Implement (ANR pre-crank interaction + ged3 rate + night-start fraction)**
```python
import sys
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
import _v3_lib as L
import _factors as FA
sys.path.insert(0, str(L.SMROOT / "src"))
import V1_SM_config as cfg      # SM_FAILED / SM_NONFAIL paths + sentinels

ANR_HI, ANR_NEG, WIN_S = 65535.0, -5000.0, 60

def anr_pre_crank_last90(ev, px, vin):
    if (vin not in px.index) or px.loc[vin].isna().any(): return np.nan
    failed = vin.endswith("_F_SM")
    base_vin = vin.replace("_F_SM", "").replace("_NF_SM", "")
    src = cfg.SM_FAILED if failed else cfg.SM_NONFAIL
    raw = pd.read_parquet(src, filters=[("VIN", "==", base_vin)], columns=["VIN", "timestamp", "ANR"])
    if raw.empty: return np.nan
    raw["timestamp"] = pd.to_datetime(raw["timestamp"]); raw = raw.sort_values("timestamp")
    raw.loc[(raw["ANR"] >= ANR_HI) | (raw["ANR"] <= ANR_NEG), "ANR"] = np.nan
    tarr = raw["timestamp"].values.astype("datetime64[ns]"); anr = raw["ANR"].values.astype(float)
    e = ev[ev["vin_label"] == vin]; t90 = pd.Timestamp(px.loc[vin, "t_90_cutoff"])
    starts = e.loc[e["ts_start"] >= t90, "ts_start"].values.astype("datetime64[ns]")
    means = []
    for s in starts:
        lo = np.searchsorted(tarr, s - np.timedelta64(WIN_S, "s")); hi = np.searchsorted(tarr, s)
        if hi > lo:
            w = anr[lo:hi]; w = w[np.isfinite(w)]
            if len(w): means.append(w.mean())
    return float(np.mean(means)) if len(means) >= 5 else np.nan

def ged3_rate_delta90(wk, px, vin):
    if (vin not in px.index) or px.loc[vin].isna().any(): return np.nan
    w = wk[wk["vin_label"] == vin].copy()
    w["rate"] = w["ged3_rows"] / w["n_rows"].replace(0, np.nan)
    t90 = pd.Timestamp(px.loc[vin, "t_90_cutoff"]); win = pd.Timestamp(px.loc[vin, "win_start_l40"])
    w = w[w["week"] >= win]; last = w.loc[w["week"] >= t90, "rate"]; base = w.loc[w["week"] < t90, "rate"]
    if last.notna().sum() < 3 or base.notna().sum() < 3: return np.nan
    return float(last.mean() - base.mean())

def night_start_fraction_delta90(ev, px, vin, night=(0,1,2,3,4), min_side=3, min_base=6):
    if (vin not in px.index) or px.loc[vin].isna().any(): return np.nan
    e = ev[ev["vin_label"] == vin].copy()
    e["hr"] = pd.to_datetime(e["ts_start"]).dt.hour; e["is_night"] = e["hr"].isin(night)
    win = pd.Timestamp(px.loc[vin, "win_start_l40"]); t90 = pd.Timestamp(px.loc[vin, "t_90_cutoff"])
    e = e[e["ts_start"] >= win]; last = e[e["ts_start"] >= t90]; base = e[e["ts_start"] < t90]
    if len(last) < min_side or len(base) < min_base: return np.nan
    return float(last["is_night"].mean() - base["is_night"].mean())

def main():
    order = L.vins_in_order(); px = L.build_px(); ev = L.load_events(); wk = L.load_weekly()
    mat = pd.read_csv(L.SMROOT / "V1.1" / "results" / "V1_1_SM_feature_matrix.csv").set_index("vin_label")

    anr = {v: anr_pre_crank_last90(ev, px, v) for v in order}
    dip_delta = {v: float(mat.loc[v, "dip_depth_last90_delta"]) if v in mat.index else np.nan for v in order}
    za, zb = L.zscore_across(dip_delta, order), L.zscore_across(anr, order)
    L.write_cache("sag_under_load", {v: za[v]*zb[v] for v in order}, force_dead=True)

    L.write_cache("ged3_rate_delta90", {v: ged3_rate_delta90(wk, px, v) for v in order}, force_dead=False)
    L.write_cache("night_start_fraction_delta90", {v: night_start_fraction_delta90(ev, px, v) for v in order}, force_dead=True)

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**
Run: `py -3 "STARTER MOTOR/V3/features/build_raw_and_probes.py"`
Expected: three `wrote ..._cache.csv` lines. (The ANR pass reads the raw parquets with predicate pushdown — allow ~1–3 min.)
If `V1_SM_config` lacks `SM_FAILED`/`SM_NONFAIL`, open `STARTER MOTOR/src/V1_SM_config.py`, confirm the attribute names, and adjust the import (GAP #1: real dir is `Data/processed/starter_motor_complete/`).

- [ ] **Step 3: Commit**
```
git add -- "STARTER MOTOR/V3/features/build_raw_and_probes.py" "STARTER MOTOR/V3/features/out/"
git commit -m "feat(v3-sm): build F3-4 (ANR-pre-crank interaction) + F4a/F4b probe caches"
```

---

## Task 6: V3 gate driver (reconcile → E1 → redundancy → E2 → E3)

**Files:**
- Create: `STARTER MOTOR/V3/features/V3_feature_gate.py`

- [ ] **Step 1: Implement the driver**
```python
import sys, json
from pathlib import Path
import numpy as np, pandas as pd
from scipy import stats
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
import _gate_core as G
import _v3_lib as L

SMROOT = L.SMROOT
OUT = SMROOT / "V3" / "features" / "out"
P = json.loads((SMROOT / "V3" / "params" / "V3_gate_params.json").read_text())
MODAL = P["modal_subset"]; SMA_DEAD = set(P["sma_dead"])
CANDS = ["dose_dip_x_starts","weakbat_cold_load","reg_instab_x_usage","sag_under_load",
         "cold_start_fraction_delta90","ged3_rate_delta90","night_start_fraction_delta90"]

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
    return float(stats.spearmanr(a[m], b[m]).correlation)

def main():
    mat = pd.read_csv(SMROOT / "V1.1" / "results" / "V1_1_SM_feature_matrix.csv")
    order = mat["vin_label"].tolist(); y = mat["failed"].astype(int).values

    a_modal = G.rank_auroc(G.plain_lovo(mat[MODAL].values.astype(float), y), y)
    recon = {"computed": round(float(a_modal), 4), "expected": P["reconcile_expected_nonnested"],
             "pass": bool(abs(a_modal - P["reconcile_expected_nonnested"]) <= P["reconcile_tol"])}
    if not recon["pass"]:
        print("RECONCILE FAIL", recon); sys.exit(1)

    prox = proxy_frame(order)
    mat_ext = mat.copy(); E1 = []
    for c in CANDS:
        cache = pd.read_csv(OUT / f"{c}_cache.csv")
        cmap = dict(zip(cache["vin_label"], cache[c]))
        arr = np.array([np.nan if v in SMA_DEAD and c != "ged3_rate_delta90" else cmap.get(v, np.nan)
                        for v in order], dtype=float)
        mat_ext[c] = arr
        f_vals, nf_vals = arr[y == 1], arr[y == 0]
        f_vals, nf_vals = f_vals[np.isfinite(f_vals)], nf_vals[np.isfinite(nf_vals)]
        mw = float(stats.mannwhitneyu(f_vals, nf_vals, alternative="two-sided").pvalue) if len(f_vals) and len(nf_vals) else np.nan
        a_raw = G.rank_auroc(np.nan_to_num(arr, nan=np.nanmean(arr)), y)
        auroc = max(a_raw, 1 - a_raw)
        rprx = {t: spearman(arr, prox[t].values.astype(float)) for t in ["n_weeks","t_start","span"]}
        rmod = {m: float(pd.Series(arr).corr(mat[m])) for m in MODAL}
        proxy_flag = any(abs(v) > P["proxy_leak_spearman_max"] for v in rprx.values() if np.isfinite(v))
        redun_flag = any(abs(v) >= P["corr_max_redundancy"] for v in rmod.values() if np.isfinite(v))
        e1_pass = (np.isfinite(mw) and mw <= P["alpha_mw"]) and (auroc >= P["auroc_min"]) and not proxy_flag and not redun_flag
        E1.append({"feature": c, "n_nonnull": int(np.isfinite(arr).sum()), "mw_p": round(mw,4) if np.isfinite(mw) else None,
                   "auroc": round(float(auroc),4), "r_proxy": {k: (round(v,3) if np.isfinite(v) else None) for k,v in rprx.items()},
                   "r_vs_modal": {k: (round(v,3) if np.isfinite(v) else None) for k,v in rmod.items()},
                   "proxy_flag": bool(proxy_flag), "redundancy_flag": bool(redun_flag), "e1_pass": bool(e1_pass)})

    # E2 fixed-subset LOVO increment
    def make_X(cols): return mat_ext[MODAL + cols].values.astype(float)
    E2 = {}
    for c in CANDS:
        a_c = G.rank_auroc(G.plain_lovo(make_X([c]), y), y)
        E2[c] = {"auroc": round(float(a_c),4), "delta": round(float(a_c - a_modal),4)}

    # E3 nested (exploratory) only for E1 survivors that also gained in E2
    survivors = [c for c in CANDS if next(e for e in E1 if e["feature"]==c)["e1_pass"] and E2[c]["delta"] >= P["e2_add_threshold"]]
    E3 = None
    if survivors:
        E3 = {"survivors": survivors,
              "nested_auroc": round(float(G.nested_lovo(mat_ext, y, MODAL + survivors)), 4)}

    verdicts = {}
    for c in CANDS:
        e1 = next(e for e in E1 if e["feature"]==c); d = E2[c]["delta"]
        if e1["proxy_flag"] or e1["redundancy_flag"]:
            verdicts[c] = {"verdict":"REJECT","reason":"E1 proxy/redundancy flag"}
        elif not e1["e1_pass"]:
            verdicts[c] = {"verdict":"REJECT","reason":f"E1 fail (mw_p={e1['mw_p']}, auroc={e1['auroc']})"}
        elif d >= P["e2_add_threshold"]:
            verdicts[c] = {"verdict":"ADD","reason":f"E2 delta=+{d}"}
        elif d > 0:
            verdicts[c] = {"verdict":"SOFT_SIGNAL","reason":f"E1-pass, E2 delta=+{d} < +0.01"}
        else:
            verdicts[c] = {"verdict":"REJECT","reason":f"E2 delta={d} <= 0"}

    summary = {"reconciliation": recon, "modal_nonnested_auroc": round(float(a_modal),4),
               "E1": E1, "E2": E2, "E3": E3, "verdicts": verdicts}
    (OUT / "V3_gate_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({"reconcile": recon["pass"], "verdicts": {c: verdicts[c]["verdict"] for c in CANDS}}, indent=2))

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the gate**
Run: `py -3 "STARTER MOTOR/V3/features/V3_feature_gate.py"`
Expected: JSON to stdout with `"reconcile": true` and a verdict per candidate; `out/V3_gate_summary.json` written. Most-likely verdicts: SOFT_SIGNAL/REJECT across the board (ceiling holds); `dose_dip_x_starts` is the one to watch.

- [ ] **Step 3: Assert reconciliation passed inside the summary**
Run: `py -3 -c "import json;d=json.load(open(r'STARTER MOTOR/V3/features/out/V3_gate_summary.json'));assert d['reconciliation']['pass'];print('gate OK', {c:v['verdict'] for c,v in d['verdicts'].items()})"`
Expected: `gate OK {...}`

- [ ] **Step 4: Commit**
```
git add -- "STARTER MOTOR/V3/features/V3_feature_gate.py" "STARTER MOTOR/V3/features/out/V3_gate_summary.json"
git commit -m "feat(v3-sm): V3 feature gate driver + gate summary (reconcile + E1/E2/E3 + verdicts)"
```

---

## Task 7: Validation analytics (correlation, MI, permutation, SHAP, significance) + secondary GBM probe

**Files:**
- Create: `STARTER MOTOR/V3/analysis/V3_validation.py`

- [ ] **Step 1: Implement analytics over the modal-4 + candidates matrix**
```python
import sys, json
from pathlib import Path
import numpy as np, pandas as pd
from scipy import stats
from sklearn.feature_selection import mutual_info_classif
from sklearn.inspection import permutation_importance
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import LeaveOneGroupOut
HERE = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(HERE / "features"))
import _v3_lib as L
SMROOT = L.SMROOT; OUT = SMROOT / "V3" / "analysis" / "out"; OUT.mkdir(parents=True, exist_ok=True)
CANDS = ["dose_dip_x_starts","weakbat_cold_load","reg_instab_x_usage","sag_under_load",
         "cold_start_fraction_delta90","ged3_rate_delta90","night_start_fraction_delta90"]
MODAL = ["vsi_withinwk_std_ratio_30d_w","rest_vsi_p05_delta90","vsi_range_trend","dip_depth_last90_delta"]

def main():
    mat = pd.read_csv(SMROOT / "V1.1" / "results" / "V1_1_SM_feature_matrix.csv")
    order = mat["vin_label"].tolist(); y = mat["failed"].astype(int).values
    for c in CANDS:
        cache = pd.read_csv(SMROOT / "V3" / "features" / "out" / f"{c}_cache.csv")
        mat[c] = mat["vin_label"].map(dict(zip(cache["vin_label"], cache[c])))
    feats = MODAL + CANDS
    X = mat[feats].copy()
    Ximp = X.fillna(X.median(numeric_only=True)).values

    # 1. correlation matrix + BH-FDR on candidate MW p-values
    corr = pd.DataFrame(np.corrcoef(np.nan_to_num(X.T.values, nan=0.0)), index=feats, columns=feats)
    corr.to_csv(OUT / "correlation_matrix.csv")
    pvals = {}
    for c in CANDS:
        a = X[c].values; fa, na = a[y==1], a[y==0]; fa, na = fa[np.isfinite(fa)], na[np.isfinite(na)]
        pvals[c] = float(stats.mannwhitneyu(fa, na, alternative="two-sided").pvalue) if len(fa) and len(na) else np.nan
    ps = pd.Series(pvals).dropna().sort_values(); m = len(ps)
    bh = {k: float(min(1.0, p * m / (i+1))) for i,(k,p) in enumerate(ps.items())}

    # 2. mutual information + permutation importance (GBM, LOVO groups)
    mi = dict(zip(feats, mutual_info_classif(Ximp, y, discrete_features=False, random_state=0).round(4).tolist()))
    gbm = HistGradientBoostingClassifier(max_depth=2, max_iter=120, l2_regularization=1.0, random_state=0)
    logo = LeaveOneGroupOut(); groups = np.arange(len(y))
    # LOVO CV AUROC for GBM (secondary model-class probe)
    from sklearn.metrics import roc_auc_score
    preds = np.zeros(len(y))
    for tr, te in logo.split(Ximp, y, groups):
        gbm.fit(Ximp[tr], y[tr]); preds[te] = gbm.predict_proba(Ximp[te])[:,1]
    gbm_auroc = float(roc_auc_score(y, preds))
    gbm.fit(Ximp, y)
    perm = permutation_importance(gbm, Ximp, y, n_repeats=30, random_state=0)
    pi = dict(zip(feats, perm.importances_mean.round(4).tolist()))

    # 3. SHAP (optional; degrade gracefully if not installed)
    shap_summary = None
    try:
        import shap
        expl = shap.TreeExplainer(gbm); sv = expl.shap_values(Ximp)
        arr = sv[1] if isinstance(sv, list) else sv
        shap_summary = dict(zip(feats, np.abs(arr).mean(axis=0).round(4).tolist()))
    except Exception as e:
        shap_summary = {"error": str(e)}

    out = {"mw_p": {k: (round(v,4) if np.isfinite(v) else None) for k,v in pvals.items()},
           "bh_fdr": {k: round(v,4) for k,v in bh.items()},
           "mutual_info": mi, "permutation_importance": pi, "shap_mean_abs": shap_summary,
           "gbm_lovo_auroc": round(gbm_auroc,4),
           "note": "GBM AUROC is a SCREEN-GRADE model-class probe (n=34, high variance); not a shipped model."}
    (OUT / "V3_validation.json").write_text(json.dumps(out, indent=2))
    print(json.dumps({"gbm_lovo_auroc": out["gbm_lovo_auroc"], "bh_fdr": out["bh_fdr"]}, indent=2))

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**
Run: `py -3 "STARTER MOTOR/V3/analysis/V3_validation.py"`
Expected: prints `gbm_lovo_auroc` (compare to 0.9321 — likely ≤, with wide variance) and BH-FDR-adjusted p-values; writes `analysis/out/V3_validation.json` + `correlation_matrix.csv`. If `shap` import fails, the `shap_mean_abs.error` field is recorded (acceptable — permutation importance is the primary attribution).

- [ ] **Step 3: Fold-safe re-verification of any E1 survivor** (only if Task 6 produced survivors)
If `V3_gate_summary.json` lists survivors, add a function to recompute each survivor interaction with **per-fold** z-scores (fit z on the 33 training VINs, apply to the held-out VIN) and re-run `G.plain_lovo`; append `{survivor: {global_z_delta, fold_safe_delta}}` to `V3_validation.json`. If no survivors, write `"fold_safe_reverify": "n/a — no E1 survivors"` and skip. (This closes the SCREEN-GRADE global-z caveat honestly.)

- [ ] **Step 4: Commit**
```
git add -- "STARTER MOTOR/V3/analysis/"
git commit -m "feat(v3-sm): validation analytics (corr/MI/permutation/SHAP/BH-FDR) + GBM model-class probe"
```

---

## Task 8: Visualizations

**Files:**
- Create: `STARTER MOTOR/V3/graphs/V3_graphs.py`

- [ ] **Step 1: Implement plots (matplotlib; save PNGs to `graphs/`)**
Produce, from the merged matrix + `V3_gate_summary.json` + `V3_validation.json`:
1. `feature_ranking.png` — horizontal bar of E1 oriented AUROC per candidate, colored by verdict (ADD/SOFT_SIGNAL/REJECT), with the 0.60 admit line and modal-4 0.9357 reference.
2. `dist_failed_vs_nonfailed.png` — small-multiples strip/box of each candidate, failed vs non-failed.
3. `correlation_heatmap.png` — heatmap of `correlation_matrix.csv` (modal-4 + candidates), annotating |r|≥0.85 redundancy cells.
4. `e2_delta.png` — bar of E2 ΔAUROC per candidate with the +0.01 accept line at 0.
5. `degradation_trend_dose.png` — for the top candidate (`dose_dip_x_starts` unless another wins), per-VIN last-12-week trajectory of its two factors, failed (red) vs non-failed (grey).
Use `matplotlib` only; 150 dpi; titles state "SCREEN-GRADE, n=34".

- [ ] **Step 2: Run & eyeball**
Run: `py -3 "STARTER MOTOR/V3/graphs/V3_graphs.py"`
Expected: 5 PNGs in `STARTER MOTOR/V3/graphs/`. Open `feature_ranking.png` to confirm axis labels and the verdict coloring render.

- [ ] **Step 3: Commit**
```
git add -- "STARTER MOTOR/V3/graphs/"
git commit -m "feat(v3-sm): V3 exploratory + ranking visualizations"
```

---

## Task 9: Reports, feature dictionary, appendix

**Files:**
- Create: `STARTER MOTOR/V3/reports/V3_SM_feature_dictionary.md`
- Create: `STARTER MOTOR/V3/reports/V3_SM_results.md`
- Create: `STARTER MOTOR/V3/reports/V3_SM_feasibility_report.md`
- Create: `STARTER MOTOR/V3/reports/V3_SM_verdict.md`
- Create: `STARTER MOTOR/V3/reports/V3_SM_exec_summary.md`
- Create: `STARTER MOTOR/V3/appendix/temperature_infeasibility.md`
- Create: `STARTER MOTOR/V3/appendix/new_data_roadmap.md`

- [ ] **Step 1: Write `V3_SM_feature_dictionary.md`** — one entry per candidate with the brief's exact schema: **physical justification · mathematical definition · required raw signals · data availability (computable? nulls?) · expected predictive power (L/M/H + reasoning) · risks (noise/leakage/overfit)**. Pull the actual E1/E2 numbers from `V3_gate_summary.json` into a final "screened verdict" line per feature. (Seed content already in `Plan/V3_SM_spec.md §4` — expand with realized numbers.)

- [ ] **Step 2: Write `V3_SM_results.md`** — per-candidate E1 table (n_nonnull, MW p, oriented AUROC, proxy r, redundancy r vs each modal, flags), E2 ΔAUROC, E3 (if any), BH-FDR column, and the GBM model-class probe result. Every number cited from the JSON artifacts (no hand-typed values).

- [ ] **Step 3: Write `V3_SM_feasibility_report.md`** — automotive-engineering justification per feature family (cranking-wear physics, battery-under-load, duty-cycle), literature-style references (starter brush/solenoid/contact wear; cold-crank current), the data-availability verdict per proposed signal, and the honest feasibility conclusion (what the 6-signal/5-s frame can and cannot support).

- [ ] **Step 4: Write `V3_SM_verdict.md`** (synthesis) — comparison table vs the frozen 0.9321 baseline; accept/reject/soft-signal per candidate; whether the ceiling held; recommendations; limitations (n=34, SCREEN-GRADE, multiplicity, global-z caveat + fold-safe result); future work → points to `appendix/new_data_roadmap.md`. Explicitly permit and state the "NO IMPROVEMENT / all HOLD" outcome if that is what happened.

- [ ] **Step 5: Write `V3_SM_exec_summary.md`** — 1 page: what was tested, what passed/failed, the one-line bottom line, and the single most valuable next step.

- [ ] **Step 6: Write `appendix/temperature_infeasibility.md`** — no-location-channel proof (column dictionary + repo grep), the two already-null proxies (seasonality KW p=0.90; cold-dip redundant r≈0.92), and the data that would unlock it (per-vehicle GPS+timestamp → historical daily temp; or onboard ambient/coolant temp channel).

- [ ] **Step 7: Write `appendix/new_data_roadmap.md`** — reuse/refresh V2.1 Appendix C: IBS/current-clamp (crank-current waveform), hi-rate VSI firmware trigger during SMA=1, warranty+odometer+SALEDATE ingest — each with signal unlocked, why the current frame can't reach it, cost, and expected payoff.

- [ ] **Step 8: Commit**
```
git add -- "STARTER MOTOR/V3/reports/" "STARTER MOTOR/V3/appendix/"
git commit -m "docs(v3-sm): feature dictionary, results, feasibility, verdict, exec summary, appendix"
```

---

## Task 10: Final sweep — spec sync, graph update, verification

- [ ] **Step 1: Sync the spec candidate list** — edit `Plan/V3_SM_spec.md §4.1` to match the executed 7+1 set (note the F1a drop / F4a reframe / F4c-optional as "refined pre-execution after interface verification"). Commit: `docs(v3-sm): sync spec candidate table with executed set`.
- [ ] **Step 2: Re-run the two gates end-to-end** to confirm reproducibility from clean caches:
  Run: `py -3 "STARTER MOTOR/V3/features/tests/test_reconcile.py"` (PASS 0.9357), then `py -3 "STARTER MOTOR/V3/features/V3_feature_gate.py"` (reconcile true).
- [ ] **Step 3: Update the knowledge graph** (per project CLAUDE.md): `graphify update .` (AST-only, no API cost) so V3 code is indexed.
- [ ] **Step 4: Verify no unrelated files were swept into any commit** — `git log --oneline -12` and `git show --stat` on each V3 commit should touch only `STARTER MOTOR/V3/**`.

---

## Self-Review (author checklist — completed)

**Spec coverage:** ✅ Objective/target → Tasks 1,6. Binding constraints/§2.1 → refinements note + reused gate. §4 candidates → Tasks 3–5 (all 7 core + optional F4c). §5 gate (reconcile→E1→redundancy→E2→E3) → Tasks 1,6. §6 guardrails (pre-registration→Task 0; SCREEN-GRADE/BH-FDR→Task 7; leak gates→Task 6 `proxy_frame`; VIN independence→SMA_DEAD handling; determinism→fixed seeds). §7 secondary probe → Task 7 GBM. §8 temperature → Task 9 Step 6. §9 deliverables → Tasks 7–9. §11 definition-of-done → Task 10.

**Placeholder scan:** ✅ No TBD/TODO in code steps; every code step contains runnable content. Task 1 Step 3 is a precise verbatim-copy instruction (named functions from a named source) verified by the reconciliation gate — not a placeholder. Task 8/9 steps specify exact figures/sections (content authored at execution against real JSON, standard for report/plot tasks).

**Type/name consistency:** ✅ `_gate_core` exposes `plain_lovo/rank_auroc/nested_lovo`; used consistently in Tasks 1,6. `_v3_lib` exposes `vins_in_order/build_px/load_events/load_weekly/zscore_across/write_cache/SMROOT`; used consistently in Tasks 2–7. `_factors` names match between definition (Task 3) and callers (Tasks 4,5). Candidate cache names match across `V3_candidates.json`, builders, gate `CANDS`, analytics, graphs. `px` columns (`t_90_cutoff/win_start_l40/t_end_approx`) used consistently.

**Known risks flagged in-plan:** global-z interaction caveat (Task 5/7 fold-safe re-verify); `V1_SM_config` attribute-name check (Task 5 Step 2); SHAP optional-dependency graceful degrade (Task 7); `starts_per_active_day` denominator from weekly `active_days`.
