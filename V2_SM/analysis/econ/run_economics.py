"""
V2 SM Decision Economics Layer
================================
T1: Cost Framework
T2: Retrospective Policy Comparison (P0–P5)
T3: Evidence-Conditional Failure-Window Matrix
T4: Fleet-Scale Extrapolation (N=500, N=5000)

All numbers use OOF/LOVO-validated results only.
Bootstrap seed 42.
"""

import pandas as pd
import numpy as np
from pathlib import Path
import sys, io

# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

SEED = 42
rng = np.random.default_rng(SEED)

# ──────────────────────────────────────────────────────────────────────
# PATHS
# ──────────────────────────────────────────────────────────────────────
BASE = Path("D:/Daimler-starter_motor_alternator_battery/STARTER MOTOR")
V11R = BASE / "V1.1/results"
V11D = BASE / "V1.1/discovery/out"
V1R  = BASE / "results"
OUT  = BASE / "V2_program/analysis/econ"
OUT.mkdir(parents=True, exist_ok=True)

# ──────────────────────────────────────────────────────────────────────
# LOAD INPUTS
# ──────────────────────────────────────────────────────────────────────
preds   = pd.read_csv(V11R / "V1_1_SM_nested_lovo_predictions.csv")
policy  = pd.read_csv(V11R / "V1_1_SM_alert_policy.csv")
valdat  = pd.read_csv(V11R / "V1_1_SM_alert_validation.csv")
dq      = pd.read_csv(V1R  / "V1_SM_data_quality.csv")
arch    = pd.read_csv(V11D / "E2_failed_vin_archetypes.csv")

print(f"Predictions rows: {len(preds)}, Policy rows: {len(policy)}")

# ──────────────────────────────────────────────────────────────────────
# SECTION 0 — TRUCK-YEARS COMPUTATION
# ──────────────────────────────────────────────────────────────────────
# Use per-VIN active_days_total from data quality file
dq['truck_years'] = dq['active_days_total'] / 365.25

# failed column in dq is string 'true'/'false'; normalise
dq['failed_bool'] = dq['failed'].astype(str).str.lower().str.strip() == 'true'

total_truck_years  = dq['truck_years'].sum()
failed_truck_years = dq.loc[dq['failed_bool'], 'truck_years'].sum()
nf_truck_years     = dq.loc[~dq['failed_bool'],'truck_years'].sum()

print(f"\nFleet truck-years: {total_truck_years:.1f} total "
      f"({failed_truck_years:.1f} F + {nf_truck_years:.1f} NF)")
print(f"Fleet = 34 trucks, 14 failed, 20 NF")
print(f"NOTE: Enriched fleet — 41% failed by construction (14/34). "
      f"Observed failure rate {14/total_truck_years:.3f}/truck-yr "
      f"(DO NOT use as population rate).")

# ──────────────────────────────────────────────────────────────────────
# T1 — COST FRAMEWORK
# ──────────────────────────────────────────────────────────────────────
# Sources:
#   Domain intake §3.2: starter parts INR 3,000–25,000 (IndiaMart cited)
#   BharatBenz 5528T price ~INR 35-45 lakh; DICV 48-hr Rakshana service
#   India HD breakdown costs: assumption-driven; documented below
#   All INR  figures in 2026 Indian Rupees

cost_params = {
    # Part A — Starter motor replacement
    "starter_part_INR_low":   3_000,   # SOURCED: IndiaMart standard aftermarket
    "starter_part_INR_base": 12_000,   # ASSUMPTION: OEM-compatible quality mid-range
    "starter_part_INR_high": 25_000,   # SOURCED upper: IndiaMart premium / OEM Bosch

    # Labour for planned starter swap (2–3 h at DICV workshop)
    "planned_labor_INR_low":   1_500,  # ASSUMPTION: INR 500/h × 3h, tier-2 city
    "planned_labor_INR_base":  2_500,  # ASSUMPTION: INR 700/h × 3.5h
    "planned_labor_INR_high":  4_500,  # ASSUMPTION: authorized dealer, INR 900/h × 5h

    # Part B — Planned inspection (electrical check, no replacement, ~1–2 h)
    # Workshop time only; includes VSI/SMA data pull + battery load test
    "inspection_INR_low":      800,    # ASSUMPTION: at-depot, minimal workshop fee
    "inspection_INR_base":   1_500,    # ASSUMPTION: ~INR 600–800/h × 2h labour + facility
    "inspection_INR_high":   3_000,    # ASSUMPTION: authorized DICV dealer, 2h + admin

    # Part C — Battery test + replacement (if A2 battery-cascade fires)
    # Dual 12V batteries, 150–200 Ah; Indian market HD battery INR 8,000–18,000 each
    "battery_test_INR":        500,    # ASSUMPTION: load test at workshop
    "battery_replace_2x_low": 16_000, # ASSUMPTION: INR 8,000/battery × 2 (budget brand)
    "battery_replace_2x_base":28_000, # ASSUMPTION: INR 14,000/battery × 2 (mid-tier)
    "battery_replace_2x_high":40_000, # ASSUMPTION: INR 20,000/battery × 2 (OEM/premium)
    # Total battery-first inspection event:
    "a2_event_INR_low":  16_500,       # battery_test + battery_replace_2x_low
    "a2_event_INR_base": 28_500,       # battery_test + battery_replace_2x_base
    "a2_event_INR_high": 40_500,       # battery_test + battery_replace_2x_high

    # Part D — Roadside breakdown event (55t tractor, run-to-failure)
    # Components: tow + emergency labor + cargo delay penalty + downtime days
    #   Tow (0–50 km flatbed): INR 5,000–15,000 ASSUMPTION India HD tow rates
    #   Emergency labor (after-hours, at site): INR 4,000–8,000 ASSUMPTION
    #   Cargo delay penalty (contractual, per-day): INR 5,000–20,000/day ASSUMPTION
    #     (55t container moves; delay penalties in India road freight: INR 3,000–25,000/day)
    #   Downtime duration: 0.5–2 days (repair + logistics) ASSUMPTION
    #   Total downtime loss (freight + driver): INR 10,000–60,000 ASSUMPTION
    "breakdown_tow_INR_low":   5_000,
    "breakdown_tow_INR_base": 10_000,
    "breakdown_tow_INR_high": 15_000,
    "breakdown_emerg_labor_INR_low":   4_000,
    "breakdown_emerg_labor_INR_base":  6_000,
    "breakdown_emerg_labor_INR_high": 10_000,
    "breakdown_cargo_delay_INR_low":  10_000,
    "breakdown_cargo_delay_INR_base": 30_000,
    "breakdown_cargo_delay_INR_high": 60_000,
}

# Composite breakdown cost (tow + emergency labor + cargo delay)
for level, tow_k, lab_k, cargo_k in [
    ("low",  "breakdown_tow_INR_low",  "breakdown_emerg_labor_INR_low",  "breakdown_cargo_delay_INR_low"),
    ("base", "breakdown_tow_INR_base", "breakdown_emerg_labor_INR_base", "breakdown_cargo_delay_INR_base"),
    ("high", "breakdown_tow_INR_high", "breakdown_emerg_labor_INR_high", "breakdown_cargo_delay_INR_high"),
]:
    cost_params[f"breakdown_total_INR_{level}"] = (
        cost_params[tow_k] + cost_params[lab_k] + cost_params[cargo_k]
    )

# Planned repair (inspection found issue → planned starter swap)
for level in ["low","base","high"]:
    part_k  = f"starter_part_INR_{level}"
    labor_k = f"planned_labor_INR_{level}"
    cost_params[f"planned_repair_total_INR_{level}"] = (
        cost_params[part_k] + cost_params[labor_k]
    )

print("\nT1 Cost Framework:")
for k, v in cost_params.items():
    print(f"  {k}: INR {v:,}")

# Save T1 as a tidy CSV
cost_rows = []
for scenario in ["low","base","high"]:
    cost_rows.append({
        "scenario": scenario,
        "starter_part_INR":          cost_params[f"starter_part_INR_{scenario}"],
        "planned_labor_INR":         cost_params[f"planned_labor_INR_{scenario}"],
        "planned_inspection_INR":    cost_params[f"inspection_INR_{scenario}"],
        "battery_replace_2x_INR":    cost_params[f"battery_replace_2x_{scenario}"],
        "a2_event_total_INR":        cost_params[f"a2_event_INR_{scenario}"],
        "breakdown_tow_INR":         cost_params[f"breakdown_tow_INR_{scenario}"],
        "breakdown_emerg_labor_INR": cost_params[f"breakdown_emerg_labor_INR_{scenario}"],
        "breakdown_cargo_delay_INR": cost_params[f"breakdown_cargo_delay_INR_{scenario}"],
        "breakdown_total_INR":       cost_params[f"breakdown_total_INR_{scenario}"],
        "planned_repair_total_INR":  cost_params[f"planned_repair_total_INR_{scenario}"],
        "source_notes": (
            "starter_part SOURCED IndiaMart INR 3k-25k; "
            "labor ASSUMPTION INR 500-900/h; "
            "inspection ASSUMPTION 1-2h workshop; "
            "battery_replace ASSUMPTION INR 8k-20k/unit×2; "
            "breakdown ASSUMPTION India HD tow+emergency+cargo"
        ),
    })
cost_df = pd.DataFrame(cost_rows)
cost_df.to_csv(OUT / "cost_sensitivity.csv", index=False)
print("\ncost_sensitivity.csv written.")

# ──────────────────────────────────────────────────────────────────────
# T2 — RETROSPECTIVE POLICY COMPARISON
# ──────────────────────────────────────────────────────────────────────
# Per-VIN OOF-validated outcomes (from alert_policy.csv + preds.csv)
# Merge predictions (tier) into policy table
merged = policy.merge(
    preds[['vin_label','tier']].rename(columns={'tier':'tier_pred'}),
    on='vin_label', how='left'
)

# Resolve tier from preds (the definitive LOVO output)
merged['tier'] = merged['tier_pred'].fillna(merged['tier'])

# ─── Identify NF false-alarm counts per policy per VIN ───
# For NF trucks we need to know what each policy would trigger
# RED tier: fire if tier == RED
# AMBER tier: fire if tier in {RED, AMBER}
# Persistence end-state: pers_end_fire == True
# A2: a2_fire == True
# A1 (as corroborator only in P4): handled separately

# per-VIN outcomes
failed_vins = merged[merged['failed']==1]['vin_label'].tolist()
nf_vins     = merged[merged['failed']==0]['vin_label'].tolist()

print(f"\nFailed VINs: {len(failed_vins)}, NF VINs: {len(nf_vins)}")

# Build lookup
def get_field(vin, col):
    rows = merged[merged['vin_label']==vin]
    if len(rows)==0:
        return None
    return rows.iloc[0][col]

# Youden threshold: recall 13/14 (specificity 15/20)
# Youden-passing NF: those NOT flagged under Youden threshold
# From context packet: Youden = recall 13/14, specificity 15/20 → 5 NF flag
# Those 5 NF are the RED + AMBER NF (2 AMBER + RED NF flags = 2+2 = 4 flagged by tier,
# plus Youden catches 5): RED NF = {VIN5_NF, VIN20_NF}, AMBER = {VIN10_NF, VIN2_NF}
# = 4 NF tier-flagged.  Youden at per-fold threshold gets 5/20 NF flagged.

# From context: Youden recall 13/14, spec 15/20 means 5 NF trigger
# Identify those 5 NF (vs 4 from RED+AMBER):
# RED NF: VIN5_NF, VIN20_NF (from preds)
# AMBER NF: VIN2_NF, VIN10_NF
# The 5th Youden NF: from context packet 13/14 recall / 15/20 spec = 5 NF FP
# Looking at preds: the 5th might be a borderline GREEN NF with high prob
# From preds: VIN15_NF (prob=0.399, tier=GREEN, pred_foldthr=1 — wait, GREEN despite pred_foldthr=1?)
# pred_foldthr is the fold-specific Youden threshold outcome (1=above).
# VIN15_NF: pred_foldthr=1 → triggers under Youden. That's the 5th.
youden_nf_fp = ['VIN2_NF_SM','VIN5_NF_SM','VIN10_NF_SM','VIN15_NF_SM','VIN20_NF_SM']

# Confirmed from context packet: Youden recall 13/14, specificity 15/20 (5 NF FP)
# Cross-check preds: pred_foldthr==1 for NF trucks
youden_fp_check = preds[(preds['failed']==0) & (preds['pred_foldthr']==1)]['vin_label'].tolist()
print(f"Youden NF FP from pred_foldthr==1: {sorted(youden_fp_check)}")
print(f"Manual list: {sorted(youden_nf_fp)}")
# Use the pred_foldthr list as authoritative
youden_nf_fp = youden_fp_check

# Quarterly inspection (P5): every truck gets 4 inspections per truck-year
def annual_inspections_quarterly(ty):
    return 4.0 * ty

# ─── Policy definitions ───
# p_convert: probability an inspection-within-lead averts a roadside breakdown
# Using base cost scenario for primary table; sensitivity sweeps separately

def policy_analysis(p_convert, cost_level, inspection_cost_per_event=None):
    """
    Returns a DataFrame with one row per policy.
    """
    C_breakdown = cost_params[f"breakdown_total_INR_{cost_level}"]
    C_inspect   = inspection_cost_per_event if inspection_cost_per_event is not None \
                  else cost_params[f"inspection_INR_{cost_level}"]
    C_planned   = cost_params[f"planned_repair_total_INR_{cost_level}"]
    C_a2        = cost_params[f"a2_event_INR_{cost_level}"]

    # ── P0: run-to-failure baseline ──
    # All 14 failures → breakdown events; no inspections
    # NF: 0 inspections
    p0_breakdowns   = 14
    p0_inspections  = 0
    p0_cost         = p0_breakdowns * C_breakdown

    # ── P1: RED-tier only inspection ──
    # RED failed: VIN2/5/6/7/8/10/11/12/13/14_F = 10 RED failed
    red_failed = preds[(preds['failed']==1) & (preds['tier']=='RED')]['vin_label'].tolist()
    red_nf     = preds[(preds['failed']==0) & (preds['tier']=='RED')]['vin_label'].tolist()
    amber_failed = preds[(preds['failed']==1) & (preds['tier']=='AMBER')]['vin_label'].tolist()
    amber_nf     = preds[(preds['failed']==0) & (preds['tier']=='AMBER')]['vin_label'].tolist()

    # P1 detects 10/14 failed; 4 missed → breakdown
    p1_detected_f   = len(red_failed)   # 10
    p1_missed_f     = 14 - p1_detected_f  # 4 missed
    p1_fp_nf        = len(red_nf)         # 2 NF inspected unnecessarily
    p1_breakdowns   = p1_missed_f + p1_detected_f * (1 - p_convert)
    # inspections = detected_failed + NF FP + 1 for each NF FP
    p1_inspections  = p1_detected_f + p1_fp_nf
    p1_cost = (p1_breakdowns * C_breakdown
               + p1_detected_f * p_convert * C_planned
               + p1_fp_nf * C_inspect)

    # ── P2: RED+AMBER inspection ──
    p2_detected_f   = len(red_failed) + len(amber_failed)  # 10+0=10
    p2_missed_f     = 14 - p2_detected_f
    p2_fp_nf        = len(red_nf) + len(amber_nf)  # 2+2=4
    p2_breakdowns   = p2_missed_f + p2_detected_f * (1 - p_convert)
    p2_inspections  = p2_detected_f + p2_fp_nf
    p2_cost = (p2_breakdowns * C_breakdown
               + p2_detected_f * p_convert * C_planned
               + p2_fp_nf * C_inspect)

    # ── P3: Youden-threshold inspection ──
    youden_failed = preds[(preds['failed']==1) & (preds['pred_foldthr']==1)]['vin_label'].tolist()
    youden_nf_fp2 = preds[(preds['failed']==0) & (preds['pred_foldthr']==1)]['vin_label'].tolist()
    p3_detected_f   = len(youden_failed)  # 13
    p3_missed_f     = 14 - p3_detected_f  # 1
    p3_fp_nf        = len(youden_nf_fp2)  # 5
    p3_breakdowns   = p3_missed_f + p3_detected_f * (1 - p_convert)
    p3_inspections  = p3_detected_f + p3_fp_nf
    p3_cost = (p3_breakdowns * C_breakdown
               + p3_detected_f * p_convert * C_planned
               + p3_fp_nf * C_inspect)

    # ── P4: V1.1 recommended tier-gated channels ──
    # Logic: RED → inspect at 2-4 wk; A2 → battery-first immediately; persistence/A1 = corroborators
    # Combined first-fire: 13/14 detected (any channel); NF fire burden:
    #   10/20 clean; 10/20 have ≥1 channel
    # Inspection count: each detected failed = 1 inspection (conservative: 1 planned visit)
    #                   each NF with ≥1 channel = 1 inspection
    # A2 fires in 4 detected failed: route to battery-first (cost = C_a2 instead of C_planned)
    #   VIN13_F, VIN14_F, VIN3_F, VIN6_F (A2 battery-cascade)
    # Other 9 detected failed: C_planned
    # NF with ≥1 channel (10 NF): C_inspect each
    #   But A2 NF false alarms = 0, so no A2 cost on NF

    p4_a2_vins = ['VIN13_F_SM','VIN14_F_SM','VIN3_F_SM','VIN6_F_SM']
    p4_detected_f      = 13
    p4_missed_f        = 1   # VIN9_F
    p4_a2_detected     = 4   # those routed to battery-first
    p4_other_detected  = p4_detected_f - p4_a2_detected  # 9
    p4_fp_nf           = 10  # NF with ≥1 channel (from context packet)
    p4_a2_nf_fp        = 0   # A2 has 0 NF false alarms
    p4_breakdowns      = p4_missed_f + p4_detected_f * (1 - p_convert)
    p4_inspections     = p4_detected_f + p4_fp_nf

    p4_cost = (
        p4_breakdowns * C_breakdown
        + p4_a2_detected * p_convert * C_a2         # battery-first events (includes battery swap)
        + p4_other_detected * p_convert * C_planned  # standard starter swap
        + p4_fp_nf * C_inspect                       # NF false alarms (inspection only)
    )

    # ── P5: Inspect everything quarterly ──
    # 4 inspections per truck per year × total truck years
    p5_breakdowns  = 14  # no early detection — quarterly not targeted enough
    # Actually quarterly inspection would catch anything within the last 3 months...
    # But without a detection model, quarterly = fixed-interval
    # Generous: assume quarterly catches the ~14 failures if lead > 90d (most have lead >90d)
    # From context: median lead 168d, min 28d → quarterly catches 12/14 (those with lead>90d)
    # VIN4_F (28d lead) and VIN2_F (77d lead) would be missed
    p5_leads_d = [160,266,128,301,245,160,77,168,28,392,168,266,98,0]
    # VIN9_F lead=0 (blind spot, never detected regardless)
    quarterly_interval_d = 91
    p5_detected_f = sum(1 for l in p5_leads_d if l > quarterly_interval_d)  # lead > 91d
    # VIN9_F (0d lead), VIN4_F (28d), VIN2_F (77d) missed → 3 missed
    p5_missed_f   = 14 - p5_detected_f
    p5_fp_nf      = 20  # all NF trucks also get quarterly inspection
    # Total inspections = 34 trucks × 4 per year × truck-years (use observed span)
    # Approximate: avg observation span for NF ~1.5 years, F ~0.75 year
    avg_nf_years = nf_truck_years / 20
    avg_f_years  = failed_truck_years / 14
    p5_inspections = int(20 * 4 * avg_nf_years + 14 * 4 * avg_f_years)
    p5_cost = (
        p5_missed_f * C_breakdown
        + p5_detected_f * (1-p_convert) * C_breakdown
        + p5_detected_f * p_convert * C_planned
        + p5_inspections * C_inspect
    )

    records = []
    for name, bd, insp, cost_val, det_f, miss_f, fp_nf in [
        ("P0_run_to_failure",   p0_breakdowns, p0_inspections, p0_cost,   0,  14, 0),
        ("P1_RED_tier_only",    p1_breakdowns, p1_inspections, p1_cost,   p1_detected_f, p1_missed_f, p1_fp_nf),
        ("P2_RED_AMBER",        p2_breakdowns, p2_inspections, p2_cost,   p2_detected_f, p2_missed_f, p2_fp_nf),
        ("P3_Youden",           p3_breakdowns, p3_inspections, p3_cost,   p3_detected_f, p3_missed_f, p3_fp_nf),
        ("P4_V11_recommended",  p4_breakdowns, p4_inspections, p4_cost,   p4_detected_f, p4_missed_f, p4_fp_nf),
        ("P5_quarterly_all",    p5_missed_f + p5_detected_f*(1-p_convert),
                                p5_inspections, p5_cost, p5_detected_f, p5_missed_f, p5_fp_nf),
    ]:
        records.append({
            "policy": name,
            "p_convert": p_convert,
            "cost_level": cost_level,
            "expected_breakdowns": round(bd,2),
            "inspections": int(insp),
            "fp_nf_inspections": int(fp_nf),
            "failed_detected": int(det_f),
            "failed_missed": int(miss_f),
            "total_cost_INR": int(cost_val),
            "savings_vs_P0_INR": int(p0_cost - cost_val),
            "savings_pct": round((p0_cost - cost_val)/p0_cost*100, 1),
            "C_breakdown_used": C_breakdown,
            "C_inspect_used": C_inspect,
            "C_planned_used": C_planned,
        })
    return pd.DataFrame(records)


# Run over all combinations
p_converts = [0.5, 0.7, 0.9]
cost_levels = ["low","base","high"]

all_rows = []
for p in p_converts:
    for cl in cost_levels:
        df = policy_analysis(p_convert=p, cost_level=cl)
        all_rows.append(df)

policy_df = pd.concat(all_rows, ignore_index=True)
policy_df.to_csv(OUT / "policy_comparison.csv", index=False)
print(f"\npolicy_comparison.csv written ({len(policy_df)} rows).")

# Print key table: base cost, p_convert=0.7
print("\n=== T2: Policy Comparison (base cost, p_convert=0.7) ===")
base_tbl = policy_df[(policy_df['cost_level']=='base') & (policy_df['p_convert']==0.7)]
print(base_tbl[['policy','expected_breakdowns','inspections','fp_nf_inspections',
                 'total_cost_INR','savings_vs_P0_INR','savings_pct']].to_string(index=False))

# ─── Cost-ratio sweep: at what ratio does each policy dominate? ───
# Ratio R = C_breakdown / C_inspect
# Policy dominates P0 when its cost < P0 cost → solve for R
# For simplicity, sweep R from 1 to 100 at base p_convert=0.7

ratio_rows = []
for R in [1, 2, 5, 10, 15, 20, 30, 50, 75, 100]:
    C_inspect_sweep = 1_000   # base inspection cost INR 1,000
    C_breakdown_sweep = R * C_inspect_sweep
    C_planned_sweep = C_inspect_sweep * 15  # ~INR 15,000 planned repair
    C_a2_sweep = C_inspect_sweep * 28       # ~INR 28,000 battery event

    p_c = 0.7
    def policy_cost_at_ratio(policy_id, det_f, miss_f, fp_nf, a2_det=0):
        bd = miss_f + (det_f - a2_det) * (1-p_c)
        non_a2 = det_f - a2_det
        if policy_id == "P0":
            return 14 * C_breakdown_sweep
        c = (bd * C_breakdown_sweep
             + (det_f - a2_det) * p_c * C_planned_sweep
             + a2_det * p_c * C_a2_sweep
             + fp_nf * C_inspect_sweep)
        return c

    costs = {
        "P0": 14 * C_breakdown_sweep,
        "P1": policy_cost_at_ratio("P1", 10, 4, 2),
        "P2": policy_cost_at_ratio("P2", 10, 4, 4),
        "P3": policy_cost_at_ratio("P3", 13, 1, 5),
        "P4": policy_cost_at_ratio("P4", 13, 1, 10, a2_det=4),
        "P5": (3 * C_breakdown_sweep
               + 11 * 0.3 * C_breakdown_sweep
               + 11 * 0.7 * C_planned_sweep
               + 300 * C_inspect_sweep),
    }
    best = min(costs, key=costs.get)
    row = {"ratio_R": R, "best_policy": best}
    row.update(costs)
    ratio_rows.append(row)

ratio_df = pd.DataFrame(ratio_rows)
print("\n=== Cost-Ratio Sweep (p_convert=0.7) ===")
print(ratio_df[['ratio_R','best_policy','P0','P1','P3','P4','P5']].to_string(index=False))


# ──────────────────────────────────────────────────────────────────────
# T3 — EVIDENCE-CONDITIONAL FAILURE-WINDOW MATRIX
# ──────────────────────────────────────────────────────────────────────
# Bootstrap 95% CI on median, seed 42, n_resamples=10000

def bootstrap_median_ci(values, n_resamples=10000, ci=0.95):
    """Return (median, ci_lo, ci_hi) using percentile bootstrap."""
    arr = np.array(values, dtype=float)
    if len(arr) == 0:
        return np.nan, np.nan, np.nan
    medians = np.array([
        np.median(rng.choice(arr, size=len(arr), replace=True))
        for _ in range(n_resamples)
    ])
    alpha = (1 - ci) / 2
    return (float(np.median(arr)),
            float(np.percentile(medians, alpha*100)),
            float(np.percentile(medians, (1-alpha)*100)))

# ── State 1: A2 fired ──
# n=4; leads vs t_end: 63, 28, 91, 70 (VIN13, VIN14, VIN3, VIN6)
a2_leads = [63, 28, 91, 70]  # days

# ── State 2: Persistence terminal + RED tier ──
# Persistence fires (terminal) AND tier==RED
# From policy CSV: failed with pers_end_fire=True AND tier=RED
pers_red_failed = policy[
    (policy['failed']==1) &
    (policy['pers_end_fire']==True) &
    (policy['tier']=='RED')
]
# Get terminal persistence leads from validation csv
pers_red_leads = []
for vin in pers_red_failed['vin_label']:
    row = valdat[valdat['vin_label']==vin]
    if len(row) > 0 and pd.notna(row.iloc[0]['pers_lead_vs_t_end_d']):
        pers_red_leads.append(float(row.iloc[0]['pers_lead_vs_t_end_d']))
print(f"\nPersistence+RED terminal leads: {pers_red_leads}")

# ── State 3: RED tier, no channel ──
# RED failed trucks with first_channel == NONE → none in data (all RED failed triggered something)
# VIN2_F: RED, persistence first.
# Let's check for RED failed where only tier triggers (no persistence terminal at end-state)
# This state is effectively "RED score, monitoring phase, no channel yet fired"
# For the window card: use the full set of RED-tier failed leads
# (these are the trucks that would be in RED without having fired yet in deployment)
# Use the 10 RED failed VINs' combined first-fire leads as the detection horizon
red_failed_vins_leads = []
for vin in policy[(policy['failed']==1) & (policy['tier']=='RED')]['vin_label']:
    row = policy[policy['vin_label']==vin]
    l = float(row.iloc[0]['lead_vs_t_end_d']) if pd.notna(row.iloc[0]['lead_vs_t_end_d']) else None
    if l is not None:
        red_failed_vins_leads.append(l)
print(f"RED-failed first-fire leads: {red_failed_vins_leads}")

# ── State 4: AMBER tier ──
# 0 failed in AMBER tier; AMBER = uncertain zone, inspection recommended
# No failure-window data — specify monitoring only

# ── State 5: GREEN + clean ──
# 4 failed GREEN; 3 of those still fired a channel (VIN1/3/4_F), 1 did not (VIN9_F)
# For clean GREEN failed (those who fired eventually): leads from combined policy
green_failed_leads = []
for vin in policy[(policy['failed']==1) & (policy['tier']=='GREEN')]['vin_label']:
    row = policy[policy['vin_label']==vin]
    l = float(row.iloc[0]['lead_vs_t_end_d']) if pd.notna(row.iloc[0]['lead_vs_t_end_d']) else None
    if l is not None:
        green_failed_leads.append(l)
print(f"GREEN-failed leads (those with any channel): {green_failed_leads}")
# VIN9_F has no lead (blind spot)

# ── State 6: Silent >30d while RED/AMBER (transmission health trigger) ──
# This is a data-gap / SMA-dead condition
# From data quality: SMA-dead trucks = VIN8_F, VIN9_F + 5 NF
# VIN8_F was still RED with persistence (98d lead via VSI)
# The "silent" condition here means: RED/AMBER tier but SMA shows no crank events for >30d
# This is a concern flag — may indicate data loss or vehicle off-road
# No lead data for this state; recommend immediate manual check

window_records = []

# State 1: A2 battery-cascade fired
med1, lo1, hi1 = bootstrap_median_ci(a2_leads)
window_records.append({
    "evidence_state": "A2_battery_cascade_fired",
    "n": len(a2_leads),
    "lead_values_d": str(a2_leads),
    "median_lead_d": round(med1,1),
    "range_min_d": min(a2_leads),
    "range_max_d": max(a2_leads),
    "bootstrap_95ci_lo_d": round(lo1,1),
    "bootstrap_95ci_hi_d": round(hi1,1),
    "recommended_action": "Battery-first inspection IMMEDIATELY (within 1-2 weeks)",
    "scheduling_window_d": "14-30 days from alert",
    "honest_caveat": (
        "Retrospective n=4 only (4/5 A2 archetype). "
        "Leads measured to JCOPENDATE/t_end. "
        "Min lead 28d so 2-week scheduling is tight — prioritize. "
        "NF false alarms: 0/20 on this fleet (very clean channel). "
        "NOT a countdown clock."
    ),
})

# State 2: Persistence terminal + RED tier
if len(pers_red_leads) > 0:
    med2, lo2, hi2 = bootstrap_median_ci(pers_red_leads)
    window_records.append({
        "evidence_state": "persistence_terminal_AND_RED_tier",
        "n": len(pers_red_leads),
        "lead_values_d": str(pers_red_leads),
        "median_lead_d": round(med2,1),
        "range_min_d": min(pers_red_leads),
        "range_max_d": max(pers_red_leads),
        "bootstrap_95ci_lo_d": round(lo2,1),
        "bootstrap_95ci_hi_d": round(hi2,1),
        "recommended_action": "Schedule planned electrical inspection within 2-4 weeks; "
                              "if A1 also fires, elevate to this-month priority",
        "scheduling_window_d": "14-28 days",
        "honest_caveat": (
            "Terminal persistence = contiguous fire run still active at t_end. "
            "Leads are vs t_end (or JCOPENDATE where gap data). "
            f"n={len(pers_red_leads)} RED-failed. Long median lead (~months) means condition flag, "
            "NOT failure-imminent alarm. "
            "4/20 NF also end in persistence fire state (false alarm risk). "
            "NOT a countdown clock."
        ),
    })

# State 3: RED tier, no channel fired yet (monitoring)
if len(red_failed_vins_leads) > 0:
    med3, lo3, hi3 = bootstrap_median_ci(red_failed_vins_leads)
    window_records.append({
        "evidence_state": "RED_tier_no_channel_yet",
        "n": len(red_failed_vins_leads),
        "lead_values_d": str([round(x) for x in red_failed_vins_leads]),
        "median_lead_d": round(med3,1),
        "range_min_d": round(min(red_failed_vins_leads)),
        "range_max_d": round(max(red_failed_vins_leads)),
        "bootstrap_95ci_lo_d": round(lo3,1),
        "bootstrap_95ci_hi_d": round(hi3,1),
        "recommended_action": "Increase monitoring cadence; schedule inspection at next planned "
                              "service or within 4-8 weeks; do not treat as urgent without channel",
        "scheduling_window_d": "30-60 days or next scheduled service",
        "honest_caveat": (
            "These are first-fire combined-channel leads for RED-tier failed trucks. "
            "In deployment, a truck is in this state *before* any channel fires — "
            "the actual horizon to failure may be longer. "
            "2 RED NF trucks are false positives (VIN5_NF, VIN20_NF). "
            "Monitoring only; act on channel fire. NOT a countdown clock."
        ),
    })

# State 4: AMBER tier
window_records.append({
    "evidence_state": "AMBER_tier_no_channel",
    "n": 0,
    "lead_values_d": "No failed trucks in AMBER tier (OOF validated)",
    "median_lead_d": None,
    "range_min_d": None,
    "range_max_d": None,
    "bootstrap_95ci_lo_d": None,
    "bootstrap_95ci_hi_d": None,
    "recommended_action": "Monitor; schedule inspection at next routine service (≤3 months); "
                          "watch for persistence or A2 channel promotion",
    "scheduling_window_d": "At next scheduled service (≤90 days)",
    "honest_caveat": (
        "0 failed trucks scored AMBER in OOF validation — no empirical lead-time data. "
        "AMBER = borderline risk; 2/20 NF scored AMBER (VIN2_NF, VIN10_NF). "
        "Treat as uncertain risk zone requiring monitoring. "
        "No action threshold without a channel fire."
    ),
})

# State 5: GREEN + clean (no channels)
if len(green_failed_leads) > 0:
    med5, lo5, hi5 = bootstrap_median_ci(green_failed_leads)
    window_records.append({
        "evidence_state": "GREEN_tier_channel_fires_eventually",
        "n": len(green_failed_leads),
        "lead_values_d": str([round(x) for x in green_failed_leads]),
        "median_lead_d": round(med5,1),
        "range_min_d": round(min(green_failed_leads)),
        "range_max_d": round(max(green_failed_leads)),
        "bootstrap_95ci_lo_d": round(lo5,1),
        "bootstrap_95ci_hi_d": round(hi5,1),
        "recommended_action": "Routine maintenance schedule only; no proactive intervention "
                              "until a channel fires",
        "scheduling_window_d": "Next scheduled service (50,000 km or 6 months)",
        "honest_caveat": (
            "3 of 4 GREEN-failed trucks eventually fired a channel (VIN1/3/4_F). "
            "1 GREEN-failed (VIN9_F) fired nothing — the irreducible blind spot. "
            "Leads shown are when the channel fired, not from GREEN score issuance. "
            "Majority of NF trucks (16/20) score GREEN — correct classification. "
            "NOT a countdown clock."
        ),
    })

# State 6: Silent >30d while RED/AMBER
window_records.append({
    "evidence_state": "SILENT_SMA_30d_while_RED_or_AMBER",
    "n": 2,
    "lead_values_d": "VIN8_F (SMA-dead, 98d lead via VSI persistence), VIN9_F (SMA-dead, blind spot)",
    "median_lead_d": None,
    "range_min_d": None,
    "range_max_d": None,
    "bootstrap_95ci_lo_d": None,
    "bootstrap_95ci_hi_d": None,
    "recommended_action": "IMMEDIATE manual inspection to confirm vehicle operational and "
                          "telematics connected; if vehicle active, escalate to shop visit",
    "scheduling_window_d": "Within 72 hours",
    "honest_caveat": (
        "SMA-dead trucks can still be detected via VSI persistence (VIN8_F, 98d lead). "
        "VIN9_F was fully blind on all channels. "
        "Transmission health trigger = data gap, not failure signal per se. "
        "Applicable to VIN8/9_F class trucks only (2/14 failed in this fleet). "
        "5 NF were also SMA-dead — not all silent trucks are failing. "
        "n=2 observed cases; very limited evidence base."
    ),
})

window_df = pd.DataFrame(window_records)
window_df.to_csv(OUT / "failure_window_matrix.csv", index=False)
print(f"\nfailure_window_matrix.csv written ({len(window_df)} states).")

print("\n=== T3: Evidence-Conditional Failure-Window Matrix ===")
for _, row in window_df.iterrows():
    print(f"\n  {row['evidence_state']}")
    print(f"    n={row['n']}, leads={row['lead_values_d']}")
    print(f"    median={row['median_lead_d']}d, range=[{row['range_min_d']},{row['range_max_d']}], "
          f"95%CI=[{row['bootstrap_95ci_lo_d']},{row['bootstrap_95ci_hi_d']}]")
    print(f"    Action: {row['recommended_action']}")
    print(f"    Scheduling: {row['scheduling_window_d']}")


# ──────────────────────────────────────────────────────────────────────
# T4 — FLEET-SCALE EXTRAPOLATION
# ──────────────────────────────────────────────────────────────────────
# Key rates from THIS fleet (per truck-year, adjusted for enrichment bias)

# Observed rates in THIS fleet (41% failed by construction — enriched)
# Per-truck-year channel rates (must be estimated from observed truck-years in NF + F)

# A2 channel rate among failed trucks: 4 fires / failed_truck_years
a2_rate_failed_observed = 4 / failed_truck_years

# A1 channel rate among applicable: 4 fires / ~10 truck-years applicable failed
# (12 applicable failed × avg ~0.6yr eval window from valdat)
a1_applicable_ty = valdat[valdat['failed']==1]['a1_eval_years'].sum()
a1_fires_f = valdat[valdat['failed']==1]['a1_fire'].apply(lambda x: 1 if x==True else 0).sum()
a1_rate_failed = a1_fires_f / a1_applicable_ty if a1_applicable_ty > 0 else 0

# RED tier: 10/14 failed in RED
red_rate_per_failure = 10/14

# NF false alarm rates per truck-year (from NF cohort)
# Recompute red_nf and amber_nf at module scope (were inside policy_analysis())
red_nf_global   = preds[(preds['failed']==0) & (preds['tier']=='RED')]['vin_label'].tolist()
amber_nf_global = preds[(preds['failed']==0) & (preds['tier']=='AMBER')]['vin_label'].tolist()
# RED NF: 2/20 = 0.10 per truck observed, but per-year:
red_nf_per_ty    = len(red_nf_global)   / nf_truck_years  # VINs per truck-year
amber_nf_per_ty  = len(amber_nf_global) / nf_truck_years
youden_nf_per_ty = len(youden_fp_check) / nf_truck_years

# A1 NF: 8 fires / 15 applicable NF trucks → FP episodes
a1_nf_episodes_per_ty = 22 / nf_truck_years  # 22 episodes over ~14.5 truck-years cited

# A2 NF: 0/20 → 0 per truck-year

# Persistence NF walking alarm: 10/20 fire end-state → 0.5 per truck (binary at end)
pers_nf_end_rate = 10/20  # end-state fraction

print(f"\nFleet observed rates:")
print(f"  A2 fires / failed truck-year: {a2_rate_failed_observed:.3f}")
print(f"  A1 fires / applicable failed truck-year: {a1_rate_failed:.3f}")
print(f"  RED NF per truck-year (in NF cohort): {red_nf_per_ty:.3f}")
print(f"  A1 NF FP episodes per truck-year: {a1_nf_episodes_per_ty:.3f}")
print(f"  Total fleet truck-years: F={failed_truck_years:.1f}, NF={nf_truck_years:.1f}")
print(f"  ENRICHMENT BIAS: This fleet is {14/34*100:.0f}% failed by construction.")
print(f"  DO NOT use observed failure rate ({14/total_truck_years:.3f}/ty) as population rate.")

fleet_rows = []

for N_fleet in [500, 5000]:
    for r_failure in [0.02, 0.04, 0.08]:  # population failure rate /truck-year
        # Expected failures per year in this fleet
        expected_failures_yr = N_fleet * r_failure
        # Expected NF trucks = N_fleet - those who fail this year
        n_nf_trucks = N_fleet * (1 - r_failure)

        # Weekly alert volumes per channel:
        # RED tier: alerts on ~71% of eventual-to-fail trucks in RED
        # In practice: RED fires on trucks approaching failure, not necessarily all at once
        # Use: RED alerts per week = (expected_failures_yr × 0.714 RED-detection rate) / 52
        #      + NF RED false alarms per week = (N_fleet × red_nf_per_ty) / 52
        red_fp_wkly    = (N_fleet * red_nf_per_ty) / 52
        red_tp_wkly    = (expected_failures_yr * 10/14) / 52
        a2_tp_wkly     = (expected_failures_yr * 4/14) / 52  # A2 fires on 4/14 failed
        a2_fp_wkly     = 0.0  # 0 NF false alarms
        a1_fp_wkly     = (N_fleet * a1_nf_episodes_per_ty) / 52
        a1_tp_wkly     = (expected_failures_yr * 4/14) / 52  # 4/12 applicable
        pers_end_wkly  = (expected_failures_yr * 13/14) / 52  # 13/14 terminal
        pers_fp_wkly   = (N_fleet * pers_nf_end_rate) / 52

        total_alerts_wkly = red_tp_wkly + red_fp_wkly + a2_tp_wkly + a1_fp_wkly + pers_end_wkly

        # Inspector workload (2h per inspection)
        # Each RED-tier truck: 1 inspection / 10 weeks (monitoring frequency)
        # Each A2 fire: 1 inspection immediate
        # Each A1 corroboration: count as fraction (not standalone)
        inspections_per_wk = red_tp_wkly + red_fp_wkly + a2_tp_wkly + a2_fp_wkly
        inspector_hours_wk = inspections_per_wk * 2.0

        # Annual savings (base cost, p_convert=0.7)
        C_bd   = cost_params["breakdown_total_INR_base"]
        C_insp = cost_params["inspection_INR_base"]
        C_plan = cost_params["planned_repair_total_INR_base"]
        C_a2v  = cost_params["a2_event_INR_base"]

        # P0 cost (run-to-failure baseline for this fleet)
        p0_annual = expected_failures_yr * C_bd

        # P4 cost for fleet
        p4_a2_det   = expected_failures_yr * 4/14
        p4_other_det = expected_failures_yr * 9/14
        p4_missed   = expected_failures_yr * 1/14
        p4_fp_insp  = N_fleet * (10/20) * r_failure * 2  # rough: 50% NF truck-years get inspected

        p4_annual = (
            p4_missed * C_bd
            + (p4_a2_det + p4_other_det) * 0.3 * C_bd  # 30% still break down (1-p_convert=0.7)
            + p4_a2_det * 0.7 * C_a2v
            + p4_other_det * 0.7 * C_plan
            + (N_fleet * red_nf_per_ty + N_fleet * 0.1) * C_insp  # NF inspections
        )

        savings_annual_INR = p0_annual - p4_annual
        breakeven_ratio = C_insp / C_bd if C_bd > 0 else 0

        fleet_rows.append({
            "N_fleet": N_fleet,
            "population_failure_rate_pct_per_yr": r_failure*100,
            "expected_failures_per_yr": round(expected_failures_yr,1),
            "RED_tp_alerts_per_wk": round(red_tp_wkly,2),
            "RED_fp_alerts_per_wk": round(red_fp_wkly,2),
            "A2_tp_alerts_per_wk": round(a2_tp_wkly,3),
            "A2_fp_alerts_per_wk": 0.0,
            "A1_fp_episodes_per_wk": round(a1_fp_wkly,2),
            "persistence_end_tp_per_wk": round(pers_end_wkly,2),
            "total_actionable_alerts_per_wk": round(total_alerts_wkly,2),
            "inspections_per_wk": round(inspections_per_wk,2),
            "inspector_hours_per_wk": round(inspector_hours_wk,1),
            "P0_annual_cost_INR_lakhs": round(p0_annual/1e5,1),
            "P4_annual_cost_INR_lakhs": round(p4_annual/1e5,1),
            "P4_savings_vs_P0_INR_lakhs": round(savings_annual_INR/1e5,1),
            "breakeven_R": round(C_bd / C_insp, 1),
            "enrichment_bias_note": (
                "This fleet 41% failed by construction. "
                f"Population rate {r_failure*100:.0f}% used (parameterized). "
                "All channel rates derived from observed fleet truck-years: "
                f"F={failed_truck_years:.1f}ty, NF={nf_truck_years:.1f}ty."
            ),
        })

fleet_df = pd.DataFrame(fleet_rows)
fleet_df.to_csv(OUT / "fleet_scale_projection.csv", index=False)
print(f"\nfleet_scale_projection.csv written ({len(fleet_df)} scenarios).")

print("\n=== T4: Fleet-Scale Projections (N=500) ===")
print(fleet_df[fleet_df['N_fleet']==500][[
    'population_failure_rate_pct_per_yr',
    'expected_failures_per_yr',
    'total_actionable_alerts_per_wk',
    'inspector_hours_per_wk',
    'P0_annual_cost_INR_lakhs',
    'P4_savings_vs_P0_INR_lakhs',
    'breakeven_R',
]].to_string(index=False))

print("\n=== T4: Fleet-Scale Projections (N=5000) ===")
print(fleet_df[fleet_df['N_fleet']==5000][[
    'population_failure_rate_pct_per_yr',
    'expected_failures_per_yr',
    'total_actionable_alerts_per_wk',
    'inspector_hours_per_wk',
    'P0_annual_cost_INR_lakhs',
    'P4_savings_vs_P0_INR_lakhs',
    'breakeven_R',
]].to_string(index=False))

# ──────────────────────────────────────────────────────────────────────
# COST-RATIO FLIP POINT: where does Youden (P3) vs RED-only (P1) flip?
# ──────────────────────────────────────────────────────────────────────
# At p_convert=0.7:
# P1 cost = 4*R + 10*0.7*15 + 2*1 = 4R + 105 + 2 = 4R + 107  (×C_inspect units)
# P3 cost = 1*R + 13*0.7*15 + 5*1 = R + 136.5 + 5 = R + 141.5
# P3 < P1 when: R + 141.5 < 4R + 107  → 34.5 < 3R  → R > 11.5
# So Youden dominates RED-only when breakdown:inspection ratio > ~11.5
print("\n=== Youden vs RED-only flip point ===")
# Solve analytically: P3 < P1
# P1: 4*C_bd + 10*0.7*C_plan + 2*C_insp
# P3: 1*C_bd + 13*0.7*C_plan + 5*C_insp
# P3 < P1: 1*C_bd + 9.1*C_plan + 5*C_insp < 4*C_bd + 7*C_plan + 2*C_insp
# (9.1-7)*C_plan + 3*C_insp < 3*C_bd
# Assume C_plan = 15*C_insp:
# 2.1*15 + 3 < 3*R  →  31.5 + 3 < 3R  →  R > 34.5/3 = 11.5
flip_R = (2.1*15 + 3) / 3
print(f"Youden (P3) dominates RED-only (P1) when R = C_breakdown/C_inspect > {flip_R:.1f}")
print(f"At base costs: C_breakdown=INR {cost_params['breakdown_total_INR_base']:,}, "
      f"C_inspect=INR {cost_params['inspection_INR_base']:,}, "
      f"R={cost_params['breakdown_total_INR_base']/cost_params['inspection_INR_base']:.0f}")
actual_R = cost_params['breakdown_total_INR_base'] / cost_params['inspection_INR_base']
print(f"Actual R at base costs = {actual_R:.0f} >> {flip_R:.1f}: Youden dominates at base costs.")

print("\n=== DONE — all 4 CSVs written to:", OUT, "===")
