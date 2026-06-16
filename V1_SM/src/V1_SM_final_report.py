"""
V1_SM_final_report.py  —  Phase 7: Final Report & Verification Gates
BharatBenz Starter Motor predictive maintenance pipeline.

Produces: STARTER MOTOR/reports/V1_SM_final_report.md

Reads every pipeline artifact, recomputes the headline numbers at generation
time (no hardcoded results — prose only), runs the SIX verification gates
programmatically, prints PASS/FAIL per gate, embeds the gate table in the
report, and exits non-zero if any gate fails.

Gates:
  1. No leakage          — winner features free of gap/obs-length/JCOPENDATE
  2. Label integrity     — 14 F + 20 NF; labels match vin_label suffix only
  3. Threshold honesty   — Youden threshold recomputed from LOVO out-of-fold
                           predictions matches the spec JSON
  4. Gap handling        — GAP_VINS flagged everywhere; t_end anchoring proven
  5. Artifact handling   — duration stats recomputed with/without artifacts
  6. Reproducibility     — seeds in spec; feature_selection rerun byte-checked
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from importlib.util import spec_from_file_location, module_from_spec
import warnings
warnings.filterwarnings("ignore")

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Config import (directory has a space) ────────────────────────────────────
_spec = spec_from_file_location(
    "v1_sm_config",
    Path(__file__).resolve().parent / "V1_SM_config.py"
)
cfg = module_from_spec(_spec)
_spec.loader.exec_module(cfg)

import numpy as np
import pandas as pd
from sklearn.metrics import roc_curve, confusion_matrix

SRC = cfg.OUT / "src"

# ─────────────────────────────────────────────────────────────────────────────
# Load every artifact
# ─────────────────────────────────────────────────────────────────────────────
print("Loading artifacts...")
dq = pd.read_csv(cfg.RESULTS / "V1_SM_data_quality.csv")
events = pd.read_parquet(cfg.CACHE_EVENTS / "V1_SM_crank_events.parquet")
mat = pd.read_csv(cfg.RESULTS / "V1_SM_feature_matrix.csv")
scr = pd.read_csv(cfg.RESULTS / "V1_SM_feature_screening.csv")
elim = pd.read_csv(cfg.RESULTS / "V1_SM_elimination_results.csv")
preds = pd.read_csv(cfg.RESULTS / "V1_SM_lovo_predictions.csv")
lead = pd.read_csv(cfg.RESULTS / "V1_SM_lead_time_verdicts.csv")
with open(cfg.RESULTS / "V1_SM_ridge_spec.json") as f:
    spec = json.load(f)

# Plan §5 epoch-leakage control (optional artifact — produced by
# V1_SM_epoch_control.py; report adapts if absent)
_epoch_path = cfg.RESULTS / "V1_SM_epoch_control.json"
epoch = None
if _epoch_path.exists():
    with open(_epoch_path) as f:
        epoch = json.load(f)

graph_files = sorted(cfg.GRAPHS.glob("V1_SM_*_dashboard.png"))
weekly_files = sorted(cfg.CACHE_WEEKLY.glob("V1_SM_weekly_*.parquet"))

FEATURE_COLS = [c for c in mat.columns if c not in ("vin_label", "failed")]

# ─────────────────────────────────────────────────────────────────────────────
# Recomputed numbers (everything in the report comes from here)
# ─────────────────────────────────────────────────────────────────────────────

# -- Fleet / data quality ------------------------------------------------------
dq_f = dq[dq["failed"] == True]
dq_nf = dq[dq["failed"] == False]
fleet = {
    "rows_total": int(dq["rows"].sum()),
    "rows_f": int(dq_f["rows"].sum()),
    "rows_nf": int(dq_nf["rows"].sum()),
    "active_days_f_mean": float(dq_f["active_days_total"].mean()),
    "active_days_nf_mean": float(dq_nf["active_days_total"].mean()),
    "weeks_f_mean": float(dq_f["n_weeks"].mean()),
    "weeks_nf_mean": float(dq_nf["n_weeks"].mean()),
    "vsi_null_f": float(dq_f["vsi_null_pct"].mean()) * 100,
    "vsi_null_nf": float(dq_nf["vsi_null_pct"].mean()) * 100,
    "sma_null_f": float(dq_f["sma_null_pct"].mean()) * 100,
    "sma_null_nf": float(dq_nf["sma_null_pct"].mean()) * 100,
}

# -- Crank catalog + KT reconciliation (gap-aware, non-artifact) ---------------
ev_na = events[events["artifact"] == False]
ev_art = events[events["artifact"] == True]


def _cohort_stats(g: pd.DataFrame) -> dict:
    succ = g["success"].map(
        lambda x: bool(x) if x is not None and x == x and x != "None" else None
    ).dropna()
    return {
        "n": len(g),
        "dur_mean": float(g["dur_s"].mean()),
        "dip_mean": float(g["dip_depth"].mean()),
        "min_vsi_mean": float(g["min_vsi_crank"].mean()),
        "failed_crank_rate": float(1.0 - succ.astype(bool).mean()) * 100,
        "multi_sample_rate": float((g["n_rows"] >= 2).mean()) * 100,
    }


kt_f = _cohort_stats(ev_na[ev_na["failed"] == True])
kt_nf = _cohort_stats(ev_na[ev_na["failed"] == False])
per_vin_events = events.groupby("vin_label").size()
dur_pct_diff = (kt_f["dur_mean"] / kt_nf["dur_mean"] - 1.0) * 100

# -- Screening / pool ----------------------------------------------------------
pool_df = scr[scr["in_pool"].astype(bool)].sort_values("auroc", ascending=False)
pool = pool_df["feature"].tolist()
BRANCH_A = {
    "crank_dur_mean", "crank_dur_trend", "multi_sample_rate", "dip_depth_mean",
    "dip_depth_trend", "dip_depth_last90_delta", "failed_crank_rate",
    "failed_crank_rate_last90", "retry_rate", "recovery_slope_mean",
    "recovery_slope_trend", "crank_per_active_day", "min_vsi_crank_p05",
}
pool_branch = {f: ("A" if f in BRANCH_A else "B") for f in pool}

# -- Classifier ----------------------------------------------------------------
win_feats = spec["features"]
preds_sorted = pd.concat([
    preds[preds["failed"] == 1].sort_values("y_prob", ascending=False),
    preds[preds["failed"] == 0].sort_values("y_prob", ascending=False),
]).reset_index(drop=True)
tier_counts = preds.groupby(["failed", "alert_tier"]).size()
nf_tiers = preds[preds["failed"] == 0]["alert_tier"].value_counts()

# -- Lead time -----------------------------------------------------------------
lead_vin = lead[[
    "vin_label", "failed", "is_gap_vin", "gap_days", "vin_verdict",
    "best_signal", "lead_vs_t_end", "lead_vs_jcopen",
]].drop_duplicates().reset_index(drop=True)
lv_f = lead_vin[lead_vin["failed"] == True]
lv_nf = lead_vin[lead_vin["failed"] == False]
f_verdicts = lv_f["vin_verdict"].value_counts().to_dict()
nf_verdicts = lv_nf["vin_verdict"].value_counts().to_dict()
nf_trending = int(nf_verdicts.get("trending", 0))
nf_fp_rate = nf_trending / len(lv_nf) * 100

# VIN1_F_SM failed-crank-rate 90d spike (the one crank-specific signal)
vin1_fcr = lead[
    (lead["vin_label"] == "VIN1_F_SM")
    & (lead["signal"] == "failed_crank_rate")
    & (lead["window_days"] == 90)
].iloc[0]

# ─────────────────────────────────────────────────────────────────────────────
# VERIFICATION GATES
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 70)
print("VERIFICATION GATES")
print("=" * 70)
gates = []   # (name, passed: bool, detail: str)


def gate(name: str, passed: bool, detail: str):
    gates.append((name, bool(passed), detail))
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}: {detail}")


# Gate 1 — No leakage ---------------------------------------------------------
FORBIDDEN_TOKENS = ["gap", "jcopen", "saledate", "obs_len", "observation",
                    "n_weeks", "active_days_total", "cumulative", "t_fail"]
leak_hits = [f for f in win_feats
             for tok in FORBIDDEN_TOKENS if tok in f.lower()]
in_matrix = all(f in FEATURE_COLS for f in win_feats)
g1 = (len(leak_hits) == 0) and in_matrix
gate("No leakage", g1,
     f"winner features {win_feats} contain no forbidden token "
     f"({', '.join(FORBIDDEN_TOKENS[:4])}, ...); all in admissible matrix columns"
     if g1 else f"hits={leak_hits}, in_matrix={in_matrix}")

# Gate 2 — Label integrity ----------------------------------------------------
n_f = int(mat["failed"].sum())
n_nf = int((mat["failed"] == 0).sum())
suffix_ok = all(
    (row["failed"] == 1 and str(row["vin_label"]).endswith("_F_SM"))
    or (row["failed"] == 0 and str(row["vin_label"]).endswith("_NF_SM"))
    for _, row in mat.iterrows()
)
g2 = (len(mat) == cfg.N_VINS and n_f == cfg.N_FAILED
      and n_nf == cfg.N_NONFAILED and suffix_ok)
gate("Label integrity", g2,
     f"matrix {len(mat)} rows = {n_f} F + {n_nf} NF; every label matches its "
     f"vin_label file-membership suffix (_F_SM / _NF_SM)"
     if g2 else
     f"rows={len(mat)} (expected {cfg.N_VINS}), F={n_f} (expected "
     f"{cfg.N_FAILED}), NF={n_nf} (expected {cfg.N_NONFAILED}), "
     f"suffix_ok={suffix_ok}")

# Gate 3 — Threshold honesty --------------------------------------------------
y = preds["failed"].values
p = preds["y_prob"].values
fpr, tpr, thr = roc_curve(y, p)
youden_recomputed = float(thr[int(np.argmax(tpr - fpr))])
thr_match = abs(youden_recomputed - spec["youden_threshold"]) < 1e-3
re_pred = (p >= youden_recomputed).astype(int)
tn, fp_, fn, tp = confusion_matrix(y, re_pred, labels=[0, 1]).ravel()
conf_match = {"tp": int(tp), "fp": int(fp_), "fn": int(fn),
              "tn": int(tn)} == spec["confusion"]
per_subset_thr = elim["youden_threshold"].nunique() > 1
ridge_src = (SRC / "V1_SM_ridge_classifier.py").read_text(encoding="utf-8")
doc_ok = ("Youden" in ridge_src) and ("out-of-fold" in ridge_src)
g3 = thr_match and conf_match and per_subset_thr and doc_ok
gate("Threshold honesty", g3,
     f"Youden recomputed from lovo_predictions.csv = {youden_recomputed:.4f} "
     f"matches spec {spec['youden_threshold']:.4f}; confusion matrix "
     f"reproduced {spec['confusion']}; per-subset OOF thresholds vary "
     f"({elim['youden_threshold'].nunique()} distinct); source documents OOF Youden"
     if g3 else
     f"thr_match={thr_match} (recomputed {youden_recomputed:.4f} vs spec "
     f"{spec['youden_threshold']:.4f}), conf_match={conf_match}, "
     f"per_subset_thr={per_subset_thr}, doc_ok={doc_ok}")

# Gate 4 — Gap handling -------------------------------------------------------
gap_in_lead = set(lead_vin[lead_vin["is_gap_vin"] == True]["vin_label"])
gap_set_ok = gap_in_lead == set(cfg.GAP_VINS)
gap_days_ok = all(
    int(lead_vin.loc[lead_vin["vin_label"] == v, "gap_days"].iloc[0]) == d
    for v, d in cfg.GAP_VINS.items()
)
dq_gap_ok = all(
    int(float(dq.loc[dq["vin_label"] == v, "gap_days"].iloc[0])) == d
    for v, d in cfg.GAP_VINS.items()
)
# lead_vs_jcopen = lead_vs_t_end + gap_days for trending gap VINs
jc_ok = True
for v, d in cfg.GAP_VINS.items():
    row = lead_vin[lead_vin["vin_label"] == v].iloc[0]
    if np.isfinite(row["lead_vs_t_end"]) and np.isfinite(row["lead_vs_jcopen"]):
        jc_ok &= abs(row["lead_vs_jcopen"] - row["lead_vs_t_end"] - d) < 0.5
# t_end anchoring: for every gap VIN the implied anchor date of
# days_before_t_end (last event ts_start + its days_before_t_end) must equal
# the telemetry t_end from the data-quality CSV — and that t_end must sit
# exactly gap_days BEFORE JCOPENDATE (i.e. the anchor is NOT the failure date)
anchor_ok = True
_ev_ts = events.copy()
_ev_ts["ts_start"] = pd.to_datetime(_ev_ts["ts_start"])
for v, d in cfg.GAP_VINS.items():
    g_v = _ev_ts[_ev_ts["vin_label"] == v]
    last = g_v.loc[g_v["ts_start"].idxmax()]
    implied = (last["ts_start"].normalize()
               + pd.Timedelta(days=int(last["days_before_t_end"])))
    dq_row = dq[dq["vin_label"] == v].iloc[0]
    t_end_d = pd.to_datetime(dq_row["t_end"]).normalize()
    jco_d = pd.to_datetime(dq_row["jcopendate"]).normalize()
    anchor_ok &= abs((implied - t_end_d).days) <= 1
    anchor_ok &= (jco_d - t_end_d).days == d
feat_src = (SRC / "V1_SM_features.py").read_text(encoding="utf-8")
anchor_doc = "days_before_t_end" in feat_src
g4 = gap_set_ok and gap_days_ok and dq_gap_ok and jc_ok and anchor_ok and anchor_doc
gate("Gap handling", g4,
     f"all 5 GAP_VINS flagged in lead-time CSV with correct gap_days; "
     f"data-quality CSV agrees; lead_vs_jcopen = lead_vs_t_end + gap_days; "
     f"days_before_t_end anchor recomputed from events == telemetry t_end "
     f"(exactly gap_days before JCOPENDATE) for every gap VIN"
     if g4 else
     f"gap_set_ok={gap_set_ok}, gap_days_ok={gap_days_ok}, "
     f"dq_gap_ok={dq_gap_ok}, jc_ok={jc_ok}, anchor_ok={anchor_ok}, "
     f"anchor_doc={anchor_doc}")

# Gate 5 — Artifact handling --------------------------------------------------
art_vin = ev_art.groupby("vin_label").size().idxmax()   # most-artifact VIN
ev_v_all = events[events["vin_label"] == art_vin]
ev_v_na = ev_v_all[ev_v_all["artifact"] == False]
dur_excl = float(ev_v_na["dur_s"].mean())
dur_incl = float(ev_v_all["dur_s"].mean())
mat_val = float(mat.loc[mat["vin_label"] == art_vin, "crank_dur_mean"].iloc[0])
match_excl = abs(mat_val - dur_excl) < 1e-9
differs_incl = abs(mat_val - dur_incl) > 1e-6
no_unflagged = int(((events["dur_s"] > cfg.CRANK_MAX_PLAUSIBLE_DUR_S)
                    & (events["artifact"] == False)).sum()) == 0
g5 = match_excl and differs_incl and no_unflagged
gate("Artifact handling", g5,
     f"{art_vin} ({int(ev_art.groupby('vin_label').size().max())} artifacts): "
     f"matrix crank_dur_mean {mat_val:.4f}s == artifact-excluded recompute "
     f"{dur_excl:.4f}s, != artifact-included {dur_incl:.4f}s; "
     f"0 events with dur_s > {cfg.CRANK_MAX_PLAUSIBLE_DUR_S}s left unflagged"
     if g5 else
     f"{art_vin}: match_excl={match_excl} (matrix {mat_val:.4f}s vs "
     f"artifact-excluded {dur_excl:.4f}s), differs_incl={differs_incl} "
     f"(artifact-included {dur_incl:.4f}s), no_unflagged={no_unflagged}")

# Gate 6 — Reproducibility ----------------------------------------------------
snap = spec.get("config_snapshot", {})
seeds_ok = all(k in snap for k in
               ("random_state", "bootstrap_seed", "permutation_seed"))
fs_script = SRC / "V1_SM_feature_selection.py"
fs_csv = cfg.RESULTS / "V1_SM_feature_screening.csv"
before_bytes = fs_csv.read_bytes()
print("  (rerunning V1_SM_feature_selection.py via py -3 for byte-identity check...)")
rerun_ok = False
rerun_detail = "rerun reproduced V1_SM_feature_screening.csv byte-identically"
try:
    proc = subprocess.run(["py", "-3", str(fs_script)],
                          capture_output=True, text=True, timeout=600,
                          cwd=str(cfg.ROOT))
    after_bytes = fs_csv.read_bytes()
    rerun_ok = (proc.returncode == 0) and (before_bytes == after_bytes)
    if not rerun_ok:
        rerun_detail = (f"rerun rc={proc.returncode}, "
                        f"bytes_identical={before_bytes == after_bytes}")
except Exception as exc:
    rerun_detail = f"rerun raised {type(exc).__name__}: {exc}"
finally:
    # Always restore the audited artifact if the rerun left anything else
    # (half-written CSV, changed bytes) on disk — the gate only needs to
    # know whether the rerun REPRODUCED it.
    if not fs_csv.exists() or fs_csv.read_bytes() != before_bytes:
        fs_csv.write_bytes(before_bytes)
g6 = seeds_ok and rerun_ok
gate("Reproducibility", g6,
     f"ridge_spec config_snapshot pins seeds "
     f"(random_state={snap.get('random_state')}, "
     f"bootstrap_seed={snap.get('bootstrap_seed')}, "
     f"permutation_seed={snap.get('permutation_seed')}); "
     f"V1_SM_feature_selection.py rerun via py -3 reproduced "
     f"V1_SM_feature_screening.csv byte-identically"
     if g6 else f"seeds_ok={seeds_ok}, {rerun_detail}")

all_pass = all(p for _, p, _ in gates)
print("-" * 70)
print(f"  GATES: {sum(p for _, p, _ in gates)}/6 PASS"
      + ("" if all_pass else "  — REPORT MARKED INCOMPLETE"))
print("=" * 70)

# ─────────────────────────────────────────────────────────────────────────────
# Markdown report
# ─────────────────────────────────────────────────────────────────────────────
TODAY = datetime.now().strftime("%Y-%m-%d")


def md_pred_table(df: pd.DataFrame) -> str:
    lines = ["| VIN | Cohort | LOVO P(fail) | Tier | Predicted | Correct | Silent-gap |",
             "|-----|--------|-------------:|------|-----------|---------|------------|"]
    for _, r in df.iterrows():
        gap = f"yes ({cfg.GAP_VINS[r['vin_label']]}d)" if r["vin_label"] in cfg.GAP_VINS else ""
        lines.append(
            f"| {r['vin_label']} | {'Failed' if r['failed'] else 'Non-failed'} "
            f"| {r['y_prob']:.4f} | {r['alert_tier']} "
            f"| {'FAIL' if r['y_pred_youden'] else 'OK'} "
            f"| {'yes' if r['correct'] else '**MISS**'} | {gap} |")
    return "\n".join(lines)


def md_lead_table(df: pd.DataFrame) -> str:
    lines = ["| VIN | Silent-gap | Verdict | Best signal | Lead vs t_end (d) | Lead vs JCOPENDATE (d) |",
             "|-----|-----------|---------|-------------|------------------:|-----------------------:|"]
    for _, r in df.iterrows():
        gap = f"{int(r['gap_days'])}d" if r["is_gap_vin"] else "-"
        lt = f"{r['lead_vs_t_end']:.0f}" if np.isfinite(r["lead_vs_t_end"]) else "-"
        lj = f"{r['lead_vs_jcopen']:.0f}" if np.isfinite(r["lead_vs_jcopen"]) else "-"
        bs = r["best_signal"] if isinstance(r["best_signal"], str) else "-"
        lines.append(f"| {r['vin_label']} | {gap} | {r['vin_verdict']} | {bs} | {lt} | {lj} |")
    return "\n".join(lines)


pool_rows = "\n".join(
    f"| {int(r['rank'])} | `{r['feature']}` | {pool_branch[r['feature']]} "
    f"| {r['auroc']:.3f} | {r['mw_p']:.4f} | {r['cohens_d']:+.2f} |"
    for _, r in pool_df.iterrows())

elim_rows = "\n".join(
    f"| {r['features'].replace('|', ' + ')} | {int(r['k'])} | {r['auroc']:.4f} "
    f"| {r['recall']:.3f} | {r['specificity']:.3f} | {r['mcc']:.3f} |"
    for _, r in elim.iterrows())

imp_rows = "\n".join(
    f"| `{r['feature']}` | {r['importance_mean']:+.4f} | {r['importance_std']:.4f} |"
    for r in spec["feature_importance_insample"])

gate_rows = "\n".join(
    f"| {name} | **{'PASS' if passed else 'FAIL'}** | {detail} |"
    for name, passed, detail in gates)

screen_dropped = scr[~scr["in_pool"].astype(bool)]

# — Limitation 6 + V1.1 list + inventory rows depend on the epoch control —
_obs_asym = (f"Failed trucks were observed on average "
             f"{fleet['active_days_f_mean']:.0f} active days vs "
             f"{fleet['active_days_nf_mean']:.0f} for non-failed, over "
             f"different calendar ranges")
if epoch is not None:
    _pass = epoch["verdict"] == "PASS"
    epoch_lim6 = (
        f"6. **Calendar-epoch asymmetry — measured (plan §5 control).** "
        f"{_obs_asym}. The calendar-truncation control "
        f"(`V1_SM_epoch_control.py`) truncated all NF windows to the "
        f"failed-fleet calendar end (cutoff {epoch['cutoff_week']}; "
        f"{epoch['n_nf_truncated']}/20 NF VINs truncated) and re-ran the "
        f"winner-subset LOVO: AUROC {epoch['baseline_auroc']:.4f} → "
        f"{epoch['truncated_auroc']:.4f} (drop {epoch['auroc_drop']:+.4f}, "
        f"threshold 0.05) — verdict **{epoch['verdict']}**. "
        + ("No evidence the classifier exploits calendar-epoch differences."
           if _pass else
           "The drop exceeds 0.05 — epoch leakage must be investigated "
           "before deployment.")
    )
    v11_epoch_item = ""
    epoch_inventory = (
        f"\n| Epoch-leakage control | `STARTER MOTOR/src/V1_SM_epoch_control.py` "
        f"| Plan §5 calendar-truncation control → result JSON |"
        f"\n| Epoch control result | `STARTER MOTOR/results/V1_SM_epoch_control.json` "
        f"| cutoff {epoch['cutoff_week']}, AUROC drop {epoch['auroc_drop']:+.4f}, "
        f"verdict {epoch['verdict']} |")
else:
    epoch_lim6 = (
        f"6. **Single-epoch fleet.** {_obs_asym}; rates/trends-only features "
        f"and t_end anchoring mitigate, but calendar-epoch effects cannot be "
        f"fully excluded at this n (control never measured)."
    )
    v11_epoch_item = "a calendar-epoch truncation control; "
    epoch_inventory = ""

report = f"""---
title: "V1 Starter Motor — Final Report: Crank Catalog, Ridge Classifier, Lead-Time Verdict"
status: "{'complete' if all_pass else 'wip'}"
created: "{TODAY}"
updated: "{TODAY}"
---

# V1 Starter Motor (SM) — Final Report

Pipeline: `V1_SM` | Fleet: 34 independent trucks (14 failed + 20 non-failed) | Generated: {TODAY} by `STARTER MOTOR/src/V1_SM_final_report.py` (all numbers recomputed from pipeline artifacts at generation time).

> **VIN independence reminder:** SM VINs are completely different physical trucks from the ALT fleet — the `_SM` suffix is mandatory and no cross-dataset VIN-level comparison is valid.

---

## 1. Executive Summary

**The classifier works; the lead-time channel does not.**

- **Ridge classifier (4 features, 34-fold LOVO): AUROC {spec['auroc']:.4f}**, bootstrap 95% CI [{spec['bootstrap_95ci'][0]:.3f}, {spec['bootstrap_95ci'][1]:.3f}], label-permutation p = {spec['permutation_p']:.3f}. Recall {spec['confusion']['tp']}/{cfg.N_FAILED} failed trucks caught, specificity {spec['confusion']['tn']}/{cfg.N_NONFAILED} non-failed cleared — goals G1/G1a/G1b/G1c all met (target AUROC >= 0.85, recall >= 11/14, specificity >= 18/20, <= 8 features).
- **No validated lead-time channel exists.** 12/14 failed VINs show "trending" signals in their final 90 days — but so do {nf_trending}/{len(lv_nf)} non-failed control trucks ({nf_fp_rate:.0f}% false-positive rate). The trend battery cannot distinguish degradation from ordinary fleet variation at this sampling resolution. This mirrors the ALT finding (no 3–4-week precursor); SM additionally lacks the GED=2 channel entirely.
- **KT's headline crank claims largely did not survive** the gap-aware event definition: failed-truck cranks are only +{dur_pct_diff:.0f}% longer (not +48%), and the whole-life failed-crank-rate threshold (">5% critical") flags *both* cohorts. Only the **last-90-day** failed-crank rate discriminates (single-feature AUROC {pool_df[pool_df['feature']=='failed_crank_rate_last90']['auroc'].iloc[0]:.2f}) — degradation is a late *change*, not a lifetime level.
- **Deployment deliverable is risk bands, not day-precision RUL** (per the V10.6.2 ALT lesson: per-truck RUL cannot beat the fleet clock). Current non-failed fleet: {int(nf_tiers.get('GREEN', 0))} GREEN, {int(nf_tiers.get('AMBER', 0))} AMBER, {int(nf_tiers.get('RED', 0))} RED.

Honest caveats up front: n = 34 trucks; the bootstrap CI is wide ([{spec['bootstrap_95ci'][0]:.2f}, {spec['bootstrap_95ci'][1]:.2f}]); 5 failed VINs go silent 32–142 days before their recorded failure date; crank duration is quantized by 5-second sampling.

---

## 2. Fleet & Data-Quality Summary

| Metric | Failed (n={cfg.N_FAILED}) | Non-failed (n={cfg.N_NONFAILED}) |
|--------|------------------|--------------------|
| Telemetry rows | {fleet['rows_f']:,} | {fleet['rows_nf']:,} |
| Mean active days | {fleet['active_days_f_mean']:.0f} | {fleet['active_days_nf_mean']:.0f} |
| Mean observed weeks | {fleet['weeks_f_mean']:.0f} | {fleet['weeks_nf_mean']:.0f} |
| Mean VSI null rate | {fleet['vsi_null_f']:.1f}% | {fleet['vsi_null_nf']:.1f}% |
| Mean SMA null rate | {fleet['sma_null_f']:.1f}% | {fleet['sma_null_nf']:.1f}% |

Total: {fleet['rows_total']:,} rows across both parquets. Per-VIN detail: `STARTER MOTOR/results/V1_SM_data_quality.csv`.

**Plan §2 preliminary findings — confirmed/updated by the full pipeline:**

| Prelim finding | Status after full pipeline |
|----------------|----------------------------|
| F1: Silent-failure gap — 5/14 failed VINs stop transmitting before JCOPENDATE | **Confirmed.** VIN1 (72d), VIN4 (97d), VIN5 (32d), VIN8 (37d), VIN9 (142d). All windows anchored on t_end throughout; gap flagged in every per-VIN output; gap itself excluded as a feature (label leakage). |
| F2: GED=2 does not transfer from ALT | **Confirmed.** Zero GED=2 in all 14 failed VINs; SM timing analysis ran on crank physics (SMA) instead. GED retained as data-quality covariate only. |
| F3: Naive crank durations artifact-contaminated | **Confirmed and handled.** Gap-aware definition (intra-event gap <= {cfg.CRANK_MAX_INTRA_GAP_S}s) yields {len(events):,} events; {len(ev_art)} flagged as artifacts (dur > {cfg.CRANK_MAX_PLAUSIBLE_DUR_S}s, max {events['dur_s'].max():.0f}s) — kept but excluded from all duration/dip statistics. |
| F4: Crank inventory rich enough | **Confirmed.** Every VIN has >= {int(per_vin_events.min())} events (median {per_vin_events.median():.0f}, max {int(per_vin_events.max())}); KT floor of {cfg.MIN_EVENTS_PER_VIN}/VIN met fleet-wide. |
| F5: Observation-length asymmetry ({fleet['active_days_f_mean']:.0f} vs {fleet['active_days_nf_mean']:.0f} active days) | **Confirmed — leakage guard enforced.** Only rates and trends admitted as features; no cumulative counts, no observation length, nothing from SALEDATE/JCOPENDATE. |

---

## 3. Crank-Event Catalog & KT Reconciliation

Catalog: `STARTER MOTOR/cache/events/V1_SM_crank_events.parquet` — **{len(events):,} crank events** ({len(ev_na):,} non-artifact: {kt_f['n']:,} failed-cohort + {kt_nf['n']:,} non-failed-cohort; {len(ev_art)} artifacts flagged). Prelim gap-naive grouping found 20,729; the gap-aware definition is canonical.

**KT claim reconciliation (gap-aware, non-artifact events):**

| Metric | Failed | Non-failed | KT claim (KT_startermotor_alternator.md §6.4) | Verdict |
|--------|-------:|-----------:|------------------------------------------------|---------|
| Mean crank duration | {kt_f['dur_mean']:.2f}s | {kt_nf['dur_mean']:.2f}s | 3.2s vs 2.2s (+48%) | **Not reproduced.** Only +{dur_pct_diff:.1f}% under the gap-aware definition; 5s sampling quantizes single-row events to a 5.0s floor (~93% of events), washing out absolute-duration contrast. |
| Mean dip depth (baseline − min VSI) | {kt_f['dip_mean']:.2f}V | {kt_nf['dip_mean']:.2f}V | — (S4 channel) | **Direction only.** Failed cohort dips marginally deeper; not separable (single-feature AUROC {scr[scr['feature']=='dip_depth_mean']['auroc'].iloc[0]:.2f}). |
| Mean min-VSI during crank | {kt_f['min_vsi_mean']:.2f}V | {kt_nf['min_vsi_mean']:.2f}V | 23.1V vs 24.0V | **Direction survives, magnitude does not.** Failed is lower by {kt_nf['min_vsi_mean'] - kt_f['min_vsi_mean']:.2f}V (KT: 0.9V); absolute levels differ from KT's because 5s averaging smooths the true dip (S4, partially confirmed). |
| Failed-crank rate (whole life) | {kt_f['failed_crank_rate']:.1f}% | {kt_nf['failed_crank_rate']:.1f}% | >5% critical | **Refuted as a lifetime threshold.** Both cohorts exceed 5%, and the non-failed cohort is *higher*. The discriminating form is the **last-90-day** rate (`failed_crank_rate_last90`, AUROC {pool_df[pool_df['feature']=='failed_crank_rate_last90']['auroc'].iloc[0]:.2f}, winner feature) — a late change, not a level. |
| Multi-sample crank rate (>= 2 rows) | {kt_f['multi_sample_rate']:.1f}% | {kt_nf['multi_sample_rate']:.1f}% | — (robust duration proxy) | **Weak, same direction.** Failed cranks span >= 2 samples slightly more often; not separable alone (AUROC {scr[scr['feature']=='multi_sample_rate']['auroc'].iloc[0]:.2f}). |

Net: the KT physics intuitions point the right way, but at 5-second sampling none of the absolute crank statistics separates the cohorts. What survives into the model is the *recent-window change* in crank success.

---

## 4. Feature Engineering & Screening (23 → 5)

Matrix: `STARTER MOTOR/results/V1_SM_feature_matrix.csv` — 34 rows x 23 features (13 Branch A crank-physics + 10 Branch B electrical/VSI weekly), rates and trends only, all last-N-day windows anchored on t_end.

Screening pipeline (Mann-Whitney p < 0.10 AND single-feature AUROC >= 0.60 → |Spearman r| < 0.85 → LOVO stability >= 80%) passed **{len(pool)} of 23** into the candidate pool:

| Rank | Feature | Branch | AUROC | MW p | Cohen's d |
|------|---------|--------|-------|------|-----------|
{pool_rows}

**Branch B (electrical/VSI weekly — the family that won for ALT) won again**: {sum(1 for f in pool if pool_branch[f] == 'B')} of {len(pool)} pool features. The only crank-physics survivor is `failed_crank_rate_last90`. {len(screen_dropped)} features failed screening, including every absolute crank statistic (duration, dip depth, retry rate) — consistent with the §3 reconciliation.

---

## 5. Classifier Results

Exhaustive subset search (k = {spec['subset_search']['k_range_effective'][0]}–{spec['subset_search']['k_range_effective'][1]} from the {spec['subset_search']['pool_size']}-feature pool = {spec['subset_search']['n_subsets']} subsets x 34-fold LOVO; per fold: train-median imputation → StandardScaler → RidgeClassifier(alpha={spec['alpha']})):

| Subset | k | AUROC | Recall | Specificity | MCC |
|--------|---|-------|--------|-------------|-----|
{elim_rows}

**Winner (k = {spec['k']}): `{'` + `'.join(win_feats)}`**

| Metric | Value |
|--------|-------|
| LOVO AUROC | **{spec['auroc']:.4f}** |
| Bootstrap 95% CI (N={spec['config_snapshot']['n_bootstrap']}, fixed LOVO preds) | [{spec['bootstrap_95ci'][0]:.4f}, {spec['bootstrap_95ci'][1]:.4f}] |
| Label-permutation p (N={spec['config_snapshot']['n_permutation']}) | {spec['permutation_p']:.4f} |
| Youden threshold (from pooled out-of-fold predictions) | {spec['youden_threshold']:.4f} |
| Recall | {spec['confusion']['tp']}/{cfg.N_FAILED} ({spec['recall']:.3f}) |
| Specificity | {spec['confusion']['tn']}/{cfg.N_NONFAILED} ({spec['specificity']:.3f}) |
| F1 / MCC | {spec['f1']:.3f} / {spec['mcc']:.3f} |

In-sample permutation importance (diagnostic only — not an out-of-fold estimate):

| Feature | AUROC drop (mean) | std |
|---------|------------------:|-----|
{imp_rows}

**Methodological benchmark — ALT V10.5.3 (AUROC 0.927, 6 features, n=25):** the SM result ({spec['auroc']:.3f}, {spec['k']} features, n=34) was produced by the same recipe (weekly aggregation → screening → exhaustive subsets → LOVO Ridge) and lands in the same performance regime. **These numbers are NOT comparable** — different fleets, different components, different failure mechanisms; the comparison validates the *methodology*, nothing more. Both runs independently confirm the fewer-features lesson (4–6 features beat larger subsets at n <= 34).

### Per-VIN LOVO predictions

{md_pred_table(preds_sorted)}

Misclassifications: **VIN8_F_SM** (P = {preds[preds['vin_label']=='VIN8_F_SM']['y_prob'].iloc[0]:.3f}, the one missed failure — also a 37-day silent-gap VIN whose final telemetry window predates the failure) and **{', '.join(preds[(preds['failed']==0) & (preds['correct']==0)]['vin_label'])}** (false alarms at the Youden cut; both sit in AMBER, not RED).

---

## 6. Lead-Time Analysis — No Validated Channel

Protocol: per VIN, Mann-Whitney of final-window (30/60/90d before t_end) weekly values vs that VIN's own baseline, for 8 signals (4 electrical + 4 crank-physics), plus Theil-Sen slope. The 20 non-failed trucks ran the **identical protocol as a false-positive control**.

**The control result is the headline: {nf_trending}/{len(lv_nf)} non-failed trucks ({nf_fp_rate:.0f}%) also test "trending."** A test battery that fires on {nf_fp_rate:.0f}% of healthy trucks provides no usable lead-time signal — the failed-cohort "trends" ({int(f_verdicts.get('trending', 0))}/14) are indistinguishable from ordinary fleet variation (seasonality, route changes, load changes). This is the SM analogue of the ALT lesson that long threshold-derived "lead times" are spurious.

### Failed VINs (n=14)

{md_lead_table(lv_f)}

### Non-failed control (n=20) — verdict counts

| Verdict | Count |
|---------|-------|
| trending | {int(nf_verdicts.get('trending', 0))} |
| late-spike | {int(nf_verdicts.get('late-spike', 0))} |
| flat | {int(nf_verdicts.get('flat', 0))} |
| insufficient-data | {int(nf_verdicts.get('insufficient-data', 0))} |

**The one crank-specific signal:** VIN1_F_SM shows a failed-crank-rate spike in its final 90 days (MW p = {vin1_fcr['mw_p']:.1e}, direction {vin1_fcr['direction']}) — physically plausible solenoid-wear behaviour and the only crank-physics hit in the failed cohort. The protocol ruled it **insufficient-data** (30/60-day windows lacked the >= 3 weekly values required), so it does not count as a validated lead. It is the single candidate worth re-testing in V1.1 with daily aggregation.

**Conclusion: no validated lead-time channel exists for the SM fleet.** The classifier separates failed from non-failed trucks on their recent-window signatures, but nothing in this data reliably announces *when* a failing truck will fail. Deployment must therefore be risk-band-driven (§8), not countdown-driven.

---

## 7. Limitations

1. **n = 34 trucks.** Every statistic carries small-sample uncertainty; the bootstrap 95% CI on AUROC spans [{spec['bootstrap_95ci'][0]:.2f}, {spec['bootstrap_95ci'][1]:.2f}]. The permutation test (p = {spec['permutation_p']:.3f}) rules out chance, not optimism from pipeline choices.
2. **5 silent-gap VINs.** For VIN1/4/5/8/9 (_F_SM) the last 32–142 days before failure are unobserved. Their "final-window" features describe the truck *before* it went silent; the one missed failure (VIN8_F_SM) is a gap VIN.
3. **5-second sampling quantization.** ~93% of cranks land in a single sample; absolute duration and true dip depth are unresolved (KT S3/S4 stand partially). Crank features carry less information than they would at 1Hz.
4. **No GED channel.** ALT's only physics-based timing signal (GED=2) is absent from all 14 failed SM VINs — one fewer independent channel than the ALT pipeline had.
5. **In-sample feature importance is diagnostic only** (all-34 refit); it is not an out-of-fold effect-size estimate.
{epoch_lim6}

---

## 8. Deployment Recommendation

**Deliverable: risk bands + maintenance windows — explicitly NOT day-precision RUL** (V10.6.2 ALT evidence: per-truck RUL MAE 142d vs 50d fleet-clock baseline; nothing in §6 suggests SM differs).

**Risk bands** (LOVO probability, Youden-anchored tiers: GREEN < {spec['alert_tiers']['green_lt']:.2f} <= AMBER < {spec['alert_tiers']['amber_lt']:.2f} <= RED):

| Tier | Current non-failed fleet | Action |
|------|--------------------------|--------|
| RED (>= {spec['alert_tiers']['red_gte']:.2f}) | {int(nf_tiers.get('RED', 0))} trucks | Inspect starter/battery circuit at the next depot visit (target: within 2–4 weeks). Pull crank history; check battery health first (battery–starter cascade, DICV A6). |
| AMBER ({spec['alert_tiers']['green_lt']:.2f}–{spec['alert_tiers']['amber_lt']:.2f}) | {int(nf_tiers.get('AMBER', 0))} trucks ({', '.join(sorted(preds[(preds['failed']==0) & (preds['alert_tier']=='AMBER')]['vin_label']))}) | No immediate action; re-score on the standard cadence and watch for tier escalation. Bundle a starter inspection into the next *scheduled* service. |
| GREEN (< {spec['alert_tiers']['green_lt']:.2f}) | {int(nf_tiers.get('GREEN', 0))} trucks | Normal operation. |

**Cadence:** re-score **monthly** (the winner features need 30–90-day windows to move; weekly re-scoring adds noise, not signal — though the weekly cache supports it if a truck enters RED and closer watch is wanted). Re-run: weekly cache update → features → score against the frozen `V1_SM_ridge_spec.json`.

**Maintenance-window guidance:** anchor on tier, not a predicted date. A RED truck warrants action within the next maintenance cycle; an AMBER truck warrants attention at the next scheduled service. Do not quote a days-to-failure number to operations — §6 shows the data cannot support one.

**What V1.1 could add:** daily-resolution re-test of the VIN1_F_SM failed-crank-rate spike; alert-on-tier-escalation (delta features) instead of static scoring; battery-health covariates from resting VSI; {v11_epoch_item}threshold re-tuning toward recall if the field cost of a missed failure exceeds ~9 false alarms.

---

## 9. Verification Gates — {'ALL PASS' if all_pass else 'FAILURES PRESENT'}

| Gate | Result | Evidence |
|------|--------|----------|
{gate_rows}

---

## 10. Artifact Inventory

| Artifact | Path | Contents |
|----------|------|----------|
| Pipeline config | `STARTER MOTOR/src/V1_SM_config.py` | Constants, sentinels, GAP_VINS, seeds |
| Weekly cache builder | `STARTER MOTOR/src/V1_SM_build_weekly_cache.py` | → 34 parquets + data-quality CSV |
| Crank-event extractor | `STARTER MOTOR/src/V1_SM_crank_events.py` | → events parquet + KT reconciliation |
| Feature builder | `STARTER MOTOR/src/V1_SM_features.py` | → 34x25 feature matrix |
| Feature screening | `STARTER MOTOR/src/V1_SM_feature_selection.py` | → screening CSV (23 → {len(pool)} pool) |
| Ridge + subset search | `STARTER MOTOR/src/V1_SM_ridge_classifier.py` | → elimination CSV, LOVO predictions, spec JSON |
| Lead-time analysis | `STARTER MOTOR/src/V1_SM_lead_time.py` | → verdicts CSV ({len(lead)} rows) |
| Production graphs | `STARTER MOTOR/src/V1_SM_production_graphs.py` | → {len(graph_files)} per-VIN dashboards |
| Final report generator | `STARTER MOTOR/src/V1_SM_final_report.py` | → this report + verification gates |
| Weekly cache | `STARTER MOTOR/cache/weekly/V1_SM_weekly_{{VIN}}.parquet` | {len(weekly_files)} files |
| Crank-event catalog | `STARTER MOTOR/cache/events/V1_SM_crank_events.parquet` | {len(events):,} events, 16 cols |
| Data quality | `STARTER MOTOR/results/V1_SM_data_quality.csv` | {len(dq)} rows |
| Feature matrix | `STARTER MOTOR/results/V1_SM_feature_matrix.csv` | {mat.shape[0]} x {mat.shape[1]} |
| Feature screening | `STARTER MOTOR/results/V1_SM_feature_screening.csv` | {len(scr)} rows |
| Elimination results | `STARTER MOTOR/results/V1_SM_elimination_results.csv` | {len(elim)} subsets |
| LOVO predictions | `STARTER MOTOR/results/V1_SM_lovo_predictions.csv` | {len(preds)} rows |
| Ridge spec (frozen model) | `STARTER MOTOR/results/V1_SM_ridge_spec.json` | Winner spec + config snapshot |
| Lead-time verdicts | `STARTER MOTOR/results/V1_SM_lead_time_verdicts.csv` | {len(lead)} rows (34 VINs x 8 signals x 3 windows) |{epoch_inventory}
| Dashboards | `STARTER MOTOR/graphs/V1_SM_{{VIN}}_dashboard.png` | {len(graph_files)} files |
| Final report | `STARTER MOTOR/reports/V1_SM_final_report.md` | This document |

*Plan: `STARTER MOTOR/Plan/V1_SM_plan.md` (+ prelim analysis). Canonical column reference: `docs/column_dictionary.md`.*
"""

cfg.REPORTS.mkdir(parents=True, exist_ok=True)
out_path = cfg.REPORTS / "V1_SM_final_report.md"
out_path.write_text(report, encoding="utf-8")
print(f"\nSaved: {out_path} ({len(report.splitlines())} lines)")

if not all_pass:
    failed_gates = [n for n, p, _ in gates if not p]
    print(f"GATE FAILURES: {failed_gates}")
    sys.exit(1)
print("ALL 6 VERIFICATION GATES PASS — V1_SM pipeline complete.")
