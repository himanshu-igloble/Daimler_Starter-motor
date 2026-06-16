---
title: "V1 Starter Motor — Complete Failure-Prediction Pipeline Plan"
status: "wip"
created: "2026-06-09"
updated: "2026-06-09"
execution: "subagent-driven (started 2026-06-09)"
---

# V1 Starter Motor (SM) — Complete Project Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete starter motor failure-prediction pipeline for the 34-truck SM fleet (14 failed + 20 non-failed): a crank-event physics catalog, a Ridge classifier targeting LOVO AUROC ≥ 0.85, an honest lead-time assessment, and production fleet deliverables (risk bands, graphs, reports).

**Architecture:** Port the proven V10.5.3 alternator methodology (weekly aggregation → feature matrix → exhaustive-subset Ridge → LOVO validation) with the physics layer **replaced** by SM-specific crank-event analysis built on the SMA signal. Two feature branches: Branch A (crank physics: duration, dip depth, failed-crank rate, recovery) and Branch B (electrical/VSI weekly statistics — the family that won for ALT). All outputs use the `V1_SM_` prefix under `STARTER MOTOR/`.

**Tech Stack:** Python 3.11 (`py -3` — .venv lacks pandas), Polars streaming (parquet I/O over 107M rows), pandas + scikit-learn (RidgeClassifier, StandardScaler), scipy (Mann-Whitney, Theil–Sen), matplotlib (production graphs).

---

## 1. Context & Scope

### 1.1 Fleet Definition (VIN Independence Rule — CRITICAL)

- SM fleet = **34 independent trucks**: 14 failed (`VIN1_F_SM`–`VIN14_F_SM`) + 20 non-failed (`VIN1_NF_SM`–`VIN20_NF_SM`).
- Raw VIN labels inside the parquet files are `VIN1`–`VIN14` / `VIN1`–`VIN20`. **They reuse the alternator fleet's numbering but are different physical trucks.** Every script must relabel to `_F_SM` / `_NF_SM` at load time. No cross-dataset (ALT↔SM) VIN-level analysis is valid.
- Class balance: 14/34 = 41.2% failed (comparable to ALT's 10/25 = 40%), so LOVO metrics transfer conceptually.

### 1.2 Data Files (canonical inputs)

| Key | Path | Rows | VINs | Size |
|-----|------|------|------|------|
| `sm_failed` | `Data/processed/starter_motor_complete/2026-03-06-12-38-23-starter_motor_failed.parquet` | 30,925,573 | 14 | 275 MB |
| `sm_nonfail` | `Data/processed/starter_motor_complete/2026-03-06-12-39-14-starter_motor_non_failed.parquet` | 76,250,496 | 20 | 681 MB |
| (raw CSV) | `Data/csv_data/5528T_failed_vins_data_only_Startermotor_data_1.csv` | — | 14 | 2.8 GB |
| (raw CSV) | `Data/csv_data/5528t_non_failed_vins_startermotor_data_1.csv` | — | 20 | 4.4 GB |

Columns (failed file): `VIN, CSP, RPM, ANR, GED, VSI, SMA, timestamp, SALEDATE, JCOPENDATE, Failure_type` (11 cols).
Columns (non-failed file): `VIN, CSP, RPM, ANR, GED, VSI, SMA, timestamp` (8 cols).
**Column order differs between files — always reference by name.** Canonical signal reference: `docs/column_dictionary.md`.

### 1.3 Inherited Knowledge (what we already know)

**DICV starter motor rules (from `KT_daimler/KT_startermotor_alternator.md`):**

| Rule | Statement | Data verdict |
|------|-----------|--------------|
| S1 | Crank detected via RPM 0→550–600 transition (no direct crank signal) | **Superseded** — SMA gives direct crank detection |
| S2 | Duty cycle = count of RPM transitions | **Superseded** — count SMA events directly |
| S3 | 5s sampling too slow for crank duration | **Partially refuted** — relative differences measurable (KT: failed +48% duration) |
| S4 | Crank voltage dip to 16–18V may be missed | **Partially confirmed** — 5s averaging smooths the dip; relative depth still discriminates |
| S5 | Part-quality failure dominates long-haul; duty cycle in short-haul | All 14 failed VINs are long-haul → target electrical-degradation features |
| S6 | Failed start = ignition ON + RPM stays 0 | **Superseded** — SMA=1 without RPM rise detects failed cranks directly |

**SM failure modes and signatures (KT §6):** solenoid wear / part quality (dominant; longer cranks, deeper dips, repeat attempts), brush/armature degradation (declining crank VSI over 60–120d), bearing seizure (sudden, weeks of lead at best), battery–starter cascade (A6 linkage: resting VSI near the 24V crank-minimum edge → deeper dips → solenoid stress).

**ALT pipeline lessons that bind this plan (exhaustively proven at n=25):**
1. **Fewer features win.** 6 features (AUROC 0.927) beat 11 (0.887) and 17 (0.907). → Exhaustive subset search, target 4–8 features.
2. **Simple linear models win at small n.** Ridge beat every tree/boosting model. → RidgeClassifier(alpha=1.0) is the primary model.
3. **Unsupervised anomaly detection fails at this n** (80–100% FP). → No standalone anomaly-detection track; anomaly-style features only as classifier inputs.
4. **Per-truck day-precision RUL cannot beat the fleet clock** (MAE 142d vs 50d). → Deliverable is risk bands + maintenance windows, not day-precision RUL. One honest fleet-clock baseline check only.
5. **Rates/trends > absolutes; duration > magnitude; never cap outliers** (flag them instead).
6. **Long "lead times" (120–460d) from threshold methods are spurious** — they fire on early-life noise, not degradation. Lead-time claims require the trend-vs-final-window test (Phase 5).

### 1.4 Explicit Non-Goals

- ❌ Per-truck day-precision RUL regression (shelved after V10.6.2 ALT evidence).
- ❌ Standalone unsupervised anomaly detection track.
- ❌ Any ALT↔SM cross-VIN analysis.
- ❌ GED=2 monitoring channel (see §2.3 — signal absent in failed SM cohort).

---

## 2. Preliminary Data Analysis — Findings That Shape This Plan

Full auto-generated results: `STARTER MOTOR/Plan/prelim_sm_analysis_results.md` (script: `STARTER MOTOR/Plan/prelim_sm_analysis.py`). Run on 2026-06-09 against both parquets. Key findings:

### 2.1 Per-VIN inventory — FAILED fleet (n=14)

| VIN | Rows | First ts | Last ts | Active days | SMA=1 rows | Crank events | SALEDATE | JCOPENDATE | **Obs→fail gap** |
|-----|------|----------|---------|-------------|-----------|--------------|----------|------------|------------------|
| VIN1_F_SM | 1,303,473 | 2024-09-30 | 2025-09-15 | 305 | 596 | 553 | 2024-09-30 | 2025-11-26 | **72d** |
| VIN2_F_SM | 843,430 | 2025-06-27 | 2025-12-13 | 163 | 148 | 136 | 2025-06-25 | 2025-12-13 | 0d |
| VIN3_F_SM | 1,165,335 | 2025-04-08 | 2025-12-16 | 248 | 266 | 262 | 2025-04-08 | 2025-12-16 | 0d |
| VIN4_F_SM | 1,227,142 | 2025-03-05 | 2025-08-02 | 151 | 258 | 246 | 2025-03-05 | 2025-11-07 | **97d** |
| VIN5_F_SM | 1,275,868 | 2024-04-30 | 2025-10-27 | 219 | 135 | 80 | 2024-04-30 | 2025-11-28 | **32d** |
| VIN6_F_SM | 2,219,533 | 2024-10-03 | 2025-11-04 | 396 | 208 | 193 | 2024-09-30 | 2025-11-04 | 0d |
| VIN7_F_SM | 2,733,480 | 2024-04-30 | 2025-11-08 | 543 | 924 | 777 | 2024-04-30 | 2025-11-08 | 0d |
| VIN8_F_SM | 4,802,641 | 2024-01-31 | 2025-10-26 | 547 | 1,985 | 1,933 | 2024-01-31 | 2025-12-02 | **37d** |
| VIN9_F_SM | 3,810,537 | 2024-01-31 | 2025-06-29 | 501 | 705 | 680 | 2024-01-31 | 2025-11-18 | **142d** |
| VIN10_F_SM | 1,837,988 | 2024-07-01 | 2025-12-29 | 416 | 160 | 142 | 2024-06-30 | 2025-12-29 | 0d |
| VIN11_F_SM | 2,702,394 | 2024-03-27 | 2025-11-22 | 445 | 206 | 192 | 2024-03-27 | 2025-11-22 | 0d |
| VIN12_F_SM | 2,490,690 | 2024-12-27 | 2025-12-07 | 344 | 373 | 350 | 2024-12-13 | 2025-12-07 | 0d |
| VIN13_F_SM | 1,629,920 | 2024-07-31 | 2025-11-06 | 460 | 176 | 160 | 2024-07-31 | 2025-11-06 | 0d |
| VIN14_F_SM | 2,883,142 | 2024-07-03 | 2025-11-17 | 457 | 1,063 | 695 | 2024-06-30 | 2025-11-17 | 0d |

### 2.1b Per-VIN inventory — NON-FAILED fleet (n=20, condensed)

| VIN | Rows | First ts | Last ts | Active days | Crank events | GED2 | GED3 |
|-----|------|----------|---------|-------------|--------------|------|------|
| VIN1_NF_SM | 4,504,567 | 2024-02-02 | 2026-02-18 | 643 | 291 | 0 | 0 |
| VIN2_NF_SM | 3,344,219 | 2024-01-22 | 2026-02-18 | 688 | 282 | 0 | 0 |
| VIN3_NF_SM | 3,272,661 | 2024-03-18 | 2026-02-18 | 694 | 244 | 0 | 0 |
| VIN4_NF_SM | 3,771,217 | 2024-03-22 | 2026-02-13 | 589 | 1,046 | 0 | 0 |
| VIN5_NF_SM | 4,255,968 | 2024-04-03 | 2026-02-17 | 623 | 782 | 142 | 0 |
| VIN6_NF_SM | 3,573,730 | 2024-02-28 | 2026-02-18 | 603 | 698 | 0 | 0 |
| VIN7_NF_SM | 3,996,381 | 2024-02-22 | 2026-02-18 | 707 | 586 | 0 | 0 |
| VIN8_NF_SM | 3,350,069 | 2024-03-01 | 2026-02-18 | 693 | 527 | 0 | 0 |
| VIN9_NF_SM | 3,335,531 | 2024-02-27 | 2026-02-10 | 641 | 129 | 16 | 0 |
| VIN10_NF_SM | 3,169,970 | 2024-01-01 | 2025-02-26 | 422 | 451 | 0 | 6,622 |
| VIN11_NF_SM | 4,682,465 | 2023-12-31 | 2025-05-27 | 491 | 4,147 | 1 | 3,030 |
| VIN12_NF_SM | 3,192,824 | 2024-01-01 | 2026-02-18 | 724 | 483 | 0 | 2 |
| VIN13_NF_SM | 3,869,661 | 2024-01-01 | 2025-07-28 | 525 | 426 | 1 | 782 |
| VIN14_NF_SM | 3,424,679 | 2024-01-19 | 2026-02-18 | 720 | 207 | 0 | 0 |
| VIN15_NF_SM | 3,195,196 | 2024-01-30 | 2026-02-18 | 722 | 953 | 0 | 0 |
| VIN16_NF_SM | 5,317,190 | 2024-01-12 | 2026-02-16 | 576 | 258 | 318 | 0 |
| VIN17_NF_SM | 3,374,666 | 2024-07-17 | 2026-02-18 | 459 | 598 | 0 | 0 |
| VIN18_NF_SM | 4,643,257 | 2024-03-22 | 2026-02-11 | 597 | 488 | 0 | 0 |
| VIN19_NF_SM | 3,602,136 | 2024-05-03 | 2026-02-18 | 603 | 203 | 0 | 0 |
| VIN20_NF_SM | 4,374,109 | 2024-01-01 | 2025-09-26 | 627 | 1,531 | 28 | 8,393 |

Note: 4 NF VINs also end observation well before 2026-02 (VIN10: 2025-02, VIN11: 2025-05, VIN13: 2025-07, VIN20: 2025-09) — t_end anchoring applies to NF trucks too (see §5 epoch-leakage control).

Event-count reconciliation: prelim gap-naive grouping finds 20,729 events vs KT's catalogued 20,052 — a 3.3% difference attributable to event-definition differences; Task 3's gap-aware definition is the canonical one going forward.

### 2.2 Finding 1 — Silent-failure gap (5/14 failed VINs)

**VIN1, VIN4, VIN5, VIN8, VIN9 (_F_SM) stop transmitting 32–142 days before JCOPENDATE.** Same "silent failure" phenomenon as the ALT fleet. Consequences baked into this plan:
- Define `t_end = last telemetry timestamp` and `t_fail = JCOPENDATE`; **all degradation features must be computed relative to `t_end`**, never `t_fail`, otherwise the "final 30 days" window is empty for 5 VINs.
- Lead-time analysis (Phase 5) reports both `lead_vs_t_end` and `lead_vs_jcopen` and flags the 5 gap VINs explicitly.
- The gap itself is a candidate signal (truck pulled from service before the failure was recorded) — but it is **label leakage if used as a feature**. Excluded from the classifier; reported descriptively only.

### 2.3 Finding 2 — GED=2 channel does NOT transfer from ALT

GED=2 (alternator excitation disturbance) was ALT's only physics-based timing signal. In the SM fleet it is **absent from all 14 failed VINs** (failed file contains only GED∈{0,3}) and appears only in 5 non-failed VINs (VIN16: 318, VIN5: 142, VIN20: 28, VIN9: 16, VIN11/13: 1). GED=3 ("signal not available") is heavy in a few VINs (VIN20_NF: 8,393; VIN10_NF: 6,622; VIN9_F: 358; VIN8_F: 270) and is a data-availability artifact, not a health signal. **The SM timing/lead-time channel must come from crank physics (SMA), not GED.** GED columns are retained only as data-quality covariates.

### 2.4 Finding 3 — Naive crank-event durations are artifact-contaminated

Grouping consecutive SMA=1 rows (no gap constraint) yields impossible "cranks": 25,234s (VIN9_F), 71,656s (VIN10_NF), 65,022s (VIN11_NF). These are SMA=1 readings spanning telemetry gaps or stuck flags. Meanwhile ~85% of events are single-row (a healthy 1–5s crank usually lands inside one 5s sample). Hard requirements for Phase 1:
- **Event definition:** consecutive SMA=1 rows with intra-event Δt ≤ 10s; a larger gap splits the event.
- **Plausibility flag:** event duration > 60s ⇒ `artifact=True` (kept, flagged, excluded from duration stats — never silently dropped, per the ALT "never cap outliers" lesson, but these are sensor artifacts, not physical extremes).
- Duration at 5s sampling is **quantized**: a single-row event has unknown duration in (0, 5s]. Use `n_rows_per_event` and multi-sample-crank rate (`share of events with ≥2 rows`) as the robust duration proxies. KT's "+48% duration (3.2s vs 2.2s)" must be re-derived under this gap-aware definition before being trusted (Phase 1 reconciliation step).

### 2.5 Finding 4 — Crank inventory is rich enough

20,729 raw crank events total (6,399 failed + 14,330 non-failed); every VIN has ≥ 80 events (median ~330), comfortably above the KT minimum of 50/VIN for reliable statistics. Average min-VSI during crank ≈ 20–22V in **both** cohorts at this crude resolution — cohort separation (KT claims 23.1V vs 24.0V) requires the proper pre-crank-baseline dip computation, not raw minima. Per-day crank frequency does **not** trivially separate cohorts (max-events VIN is non-failed VIN11_NF at 4,147), consistent with DICV S5 (part quality, not duty cycle, dominates long-haul).

### 2.6 Finding 5 — Data quality profile

- Sampling: median Δt = 5.0s in both files; p99 ≈ 391–619s. Gaps >1d: 60 (failed) / 232 (non-failed) — weekly aggregation must carry an `active_days_in_week` denominator.
- Nulls after sentinel cleaning: CSP/RPM 2–3%, ANR 5–7%, VSI 19–24%, SMA 27–30%, GED 34–44%. SMA nulls mean crank-rate features must normalize by **non-null-SMA observation time**, not calendar time.
- VSI ×0.2 scaling subpopulation is negligible in SM files (2 rows failed / 7 rows non-failed above 36V; max 51V). Keep the scaling guard for safety; it will be a no-op.
- Sentinels confirmed present: CSP/RPM/ANR = 65535; ANR = -5000; VSI ∈ {0, 255} treated as null.
- Observation-length asymmetry: failed VINs average ~370 active days vs non-failed ~620. **Any cumulative-count feature leaks the label via observation length** — only rates and trends are admissible.

---

## 3. Defined Goals & Success Criteria

| ID | Goal | Metric | Target | Stretch |
|----|------|--------|--------|---------|
| G1 | Failed-vs-non-failed classifier | 34-fold LOVO AUROC | **≥ 0.85** | ≥ 0.90 |
| G1a | — recall | failed VINs caught | ≥ 11/14 (0.79) | 12/14 |
| G1b | — specificity | NF false alarms | ≥ 18/20 (0.90) | 19/20 |
| G1c | — parsimony | feature count | ≤ 8 | 6 |
| G2 | Crank-event catalog | events extracted, quality-flagged | 100% of SMA=1 runs | — |
| G3 | Honest lead-time verdict | per-failed-VIN trend test (last 30/60/90d vs baseline) | verdict for all 14 | ≥ 3 VINs with actionable signal |
| G4 | Production deliverables | 34 per-VIN graphs + fleet report + risk bands | all delivered | — |
| G5 | Statistical honesty | bootstrap 95% CI + label-permutation p | CI reported, p < 0.05 | — |

Quality gates (all phases): no leakage features (gap-to-JCOPENDATE, observation length, cumulative counts), LOVO threshold chosen inside folds, every claim traceable to a results CSV.

---

## 4. Output Structure & Naming

```
STARTER MOTOR/
├── Plan/
│   ├── V1_SM_plan.md                        # this file
│   ├── prelim_sm_analysis.py                # preliminary analysis (done)
│   └── prelim_sm_analysis_results.md        # preliminary results (done)
├── src/
│   ├── V1_SM_config.py                      # Task 1
│   ├── V1_SM_build_weekly_cache.py          # Task 2
│   ├── V1_SM_crank_events.py                # Task 3
│   ├── V1_SM_features.py                    # Task 4
│   ├── V1_SM_feature_selection.py           # Task 5
│   ├── V1_SM_ridge_classifier.py            # Task 6
│   ├── V1_SM_lead_time.py                   # Task 7
│   ├── V1_SM_production_graphs.py           # Task 8
│   └── V1_SM_final_report.py                # Task 9
├── cache/
│   ├── weekly/V1_SM_weekly_{VIN_LABEL}.parquet      # 34 files
│   └── events/V1_SM_crank_events.parquet            # ~20k rows
├── results/
│   ├── V1_SM_data_quality.csv
│   ├── V1_SM_feature_matrix.csv             # 34 rows × ~50 features
│   ├── V1_SM_feature_screening.csv
│   ├── V1_SM_elimination_results.csv
│   ├── V1_SM_lovo_predictions.csv
│   ├── V1_SM_lead_time_verdicts.csv
│   └── V1_SM_ridge_spec.json
├── graphs/                                  # 34 production per-VIN dashboards
└── reports/
    └── V1_SM_final_report.md
```

Prefix: `V1_SM_`. VIN labels everywhere: `VIN{n}_F_SM` / `VIN{n}_NF_SM`.

---

## Task 1: Config & Constants

**Files:**
- Create: `STARTER MOTOR/src/V1_SM_config.py`

- [ ] **Step 1: Write config**

```python
"""V1_SM config — starter motor pipeline constants. Single source of truth."""
from pathlib import Path

ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery")
SM_FAILED = ROOT / "Data/processed/starter_motor_complete/2026-03-06-12-38-23-starter_motor_failed.parquet"
SM_NONFAIL = ROOT / "Data/processed/starter_motor_complete/2026-03-06-12-39-14-starter_motor_non_failed.parquet"

OUT = ROOT / "STARTER MOTOR"
CACHE_WEEKLY = OUT / "cache/weekly"
CACHE_EVENTS = OUT / "cache/events"
RESULTS = OUT / "results"
GRAPHS = OUT / "graphs"
REPORTS = OUT / "reports"

VERSION = "V1_SM"
FILE_PREFIX = "V1_SM_"

# Fleet
N_FAILED, N_NONFAILED = 14, 20
N_VINS = 34

# Sentinels (docs/column_dictionary.md)
SENT_U16 = 65535.0          # CSP, RPM, ANR
SENT_ANR_NEG = -5000.0      # ANR
VSI_NULL = (0.0, 255.0)     # VSI: exclusive bounds — keep (0, 255) open interval
VSI_SCALE_TRIGGER = 36.0    # raw > 36V -> multiply by 0.2 (near no-op in SM files)

# Crank event extraction (Finding 3, prelim analysis)
CRANK_MAX_INTRA_GAP_S = 10      # split event if gap between SMA=1 rows exceeds
CRANK_MAX_PLAUSIBLE_DUR_S = 60  # longer => artifact=True (flag, never drop)
CRANK_BASELINE_WINDOW_S = (-90, -10)   # pre-crank VSI baseline window
CRANK_RECOVERY_WINDOW_S = 45    # post-crank recovery observation
CRANK_SUCCESS_RPM = 550         # DICV S1/S6: RPM >= 550 within event+15s = success
MIN_EVENTS_PER_VIN = 50         # KT reliability floor

# Silent-failure gap VINs (prelim analysis 2026-06-09): telemetry ends before JCOPENDATE
GAP_VINS = {"VIN1_F_SM": 72, "VIN4_F_SM": 97, "VIN5_F_SM": 32,
            "VIN8_F_SM": 37, "VIN9_F_SM": 142}   # gap in days

# Modelling
LOVO_FOLDS = 34
RIDGE_ALPHA = 1.0
RANDOM_STATE = 42
SUBSET_MIN, SUBSET_MAX = 4, 8   # exhaustive search range (fewer-features lesson)
N_BOOTSTRAP = 200
N_PERMUTATION = 1000

def vin_label(raw_vin: str, failed: bool) -> str:
    """VIN3 + failed=True -> 'VIN3_F_SM'. NEVER use raw labels downstream."""
    return f"{raw_vin}_{'F' if failed else 'NF'}_SM"
```

- [ ] **Step 2: Verify**

```powershell
py -3 -c "import importlib.util as u; s=u.spec_from_file_location('c', r'STARTER MOTOR/src/V1_SM_config.py'); c=u.module_from_spec(s); s.loader.exec_module(c); print(c.VERSION, c.N_VINS, c.vin_label('VIN3', True), len(c.GAP_VINS))"
```

Expected: `V1_SM 34 VIN3_F_SM 5`

- [ ] **Step 3: Commit** — `git add "STARTER MOTOR/src/V1_SM_config.py" && git commit -m "feat(v1-sm): pipeline config with crank-event and gap-VIN constants"`

---

## Task 2: Phase 0 — Sentinel Cleaning + Weekly Cache `[ADAPT from ALT]`

**Files:**
- Create: `STARTER MOTOR/src/V1_SM_build_weekly_cache.py`
- Write: `STARTER MOTOR/cache/weekly/V1_SM_weekly_{VIN_LABEL}.parquet` (34 files)
- Write: `STARTER MOTOR/results/V1_SM_data_quality.csv`

Build the per-VIN weekly aggregate cache that Phases 2–6 consume, so the 107M-row parquets are only streamed once.

- [ ] **Step 1: Write the cache builder**

Cleaning (apply lazily, per `docs/column_dictionary.md`):

```python
def clean(lf: pl.LazyFrame) -> pl.LazyFrame:
    return lf.with_columns([
        pl.when(pl.col("CSP") >= cfg.SENT_U16).then(None).otherwise(pl.col("CSP")).alias("CSP"),
        pl.when(pl.col("RPM") >= cfg.SENT_U16).then(None).otherwise(pl.col("RPM")).alias("RPM"),
        pl.when((pl.col("ANR") >= cfg.SENT_U16) | (pl.col("ANR") <= cfg.SENT_ANR_NEG))
          .then(None).otherwise(pl.col("ANR")).alias("ANR"),
        pl.when((pl.col("VSI") <= 0.0) | (pl.col("VSI") >= 255.0))
          .then(None).otherwise(pl.col("VSI")).alias("VSI"),
    ]).with_columns(
        # scaling guard (near no-op in SM: 2+7 rows; see prelim Finding 5)
        pl.when(pl.col("VSI") > cfg.VSI_SCALE_TRIGGER).then(pl.col("VSI") * 0.2)
          .otherwise(pl.col("VSI")).alias("VSI")
    )
```

Weekly aggregation per VIN (`group_by_dynamic` on `timestamp`, every="1w"), regime-conditioned as in ALT:

```python
# regimes: parked (RPM null or 0), idle (0<RPM<=700), driving (RPM>700)
agg = [
    pl.len().alias("n_rows"),
    pl.col("timestamp").dt.date().n_unique().alias("active_days"),
    pl.col("SMA").is_not_null().sum().alias("sma_obs_rows"),       # crank-rate denominator
    (pl.col("SMA") == 1).sum().alias("sma1_rows"),
    # VSI stats conditioned on driving regime (alternator charging — stable baseline)
    pl.col("VSI").filter(pl.col("RPM") > 700).mean().alias("vsi_drive_mean"),
    pl.col("VSI").filter(pl.col("RPM") > 700).std().alias("vsi_drive_std"),
    pl.col("VSI").filter(pl.col("RPM") > 700).quantile(0.05).alias("vsi_drive_p05"),
    pl.col("VSI").filter(pl.col("RPM") > 700).quantile(0.95).alias("vsi_drive_p95"),
    # resting VSI (engine off — battery state; DICV A6: ~24V floor to crank)
    pl.col("VSI").filter(pl.col("RPM").is_null() | (pl.col("RPM") == 0)).median().alias("vsi_rest_median"),
    pl.col("VSI").filter(pl.col("RPM").is_null() | (pl.col("RPM") == 0)).quantile(0.05).alias("vsi_rest_p05"),
    (pl.col("VSI") < 21.0).sum().alias("vsi_below_21_rows"),       # DICV A5 severe-low
    (pl.col("VSI") > 32.0).sum().alias("vsi_above_32_rows"),       # DICV A4 battery rejection
    pl.col("RPM").mean().alias("rpm_mean"),
    pl.col("CSP").mean().alias("csp_mean"),
    pl.col("ANR").filter(pl.col("ANR") > 0).mean().alias("anr_pos_mean"),
    (pl.col("GED") == 3).sum().alias("ged3_rows"),                 # data-quality covariate only
]
```

Per VIN also store metadata: `vin_label, failed, t_start, t_end, saledate, jcopendate, gap_days`.
Data-quality CSV: one row per VIN with row counts, null %, active days, weeks with <2 active days (to be masked in trend features).

- [ ] **Step 2: Run** — `py -3 "STARTER MOTOR/src/V1_SM_build_weekly_cache.py"` (streaming; expect ~3–6 min). Expected: 34 weekly parquets, each 22–104 weekly rows; data-quality CSV with 34 rows; console prints per-VIN week counts.

- [ ] **Step 3: Spot-verify** — `py -3 -c "import polars as pl; d=pl.read_parquet(r'STARTER MOTOR/cache/weekly/V1_SM_weekly_VIN8_F_SM.parquet'); print(d.shape); print(d.select(['week','vsi_drive_mean','sma1_rows']).tail(5))"` — VIN8_F_SM should span 2024-01→2025-10 (~91 weeks) and last week must be ≤ 2025-10-26 (t_end), not JCOPENDATE.

- [ ] **Step 4: Commit**

---

## Task 3: Phase 1 — Crank-Event Catalog `[REPLACE — SM-specific core]`

**Files:**
- Create: `STARTER MOTOR/src/V1_SM_crank_events.py`
- Write: `STARTER MOTOR/cache/events/V1_SM_crank_events.parquet`

The heart of the SM pipeline. One row per crank event (~20k rows expected), gap-aware per Finding 3 (§2.4).

- [ ] **Step 1: Write the event extractor**

Per VIN (streamed, sorted by timestamp):

```python
# 1. Event segmentation: SMA==1 rows; new event when Δt to previous SMA==1 row > CRANK_MAX_INTRA_GAP_S
# 2. Per event, from the surrounding cleaned rows (window join on timestamp):
#    baseline_vsi   = mean(VSI) in [start-90s, start-10s], require >= 3 valid rows else null
#    min_vsi_crank  = min(VSI) during event rows
#    dip_depth      = baseline_vsi - min_vsi_crank          # DICV S4 channel
#    n_rows         = rows in event;  multi_sample = n_rows >= 2
#    dur_s          = (last_ts - first_ts) + 5.0            # +1 sample width; quantized
#    artifact       = dur_s > CRANK_MAX_PLAUSIBLE_DUR_S
#    rpm_max_15s    = max(RPM) in [start, end+15s]
#    success        = rpm_max_15s >= CRANK_SUCCESS_RPM      # DICV S1/S6
#    recovery_slope = (VSI@end+45s − min_vsi_crank) / Δt    # V/s, null if no post rows
#    retry_within_120s = next event starts within 120s      # repeat-attempt signature
# 3. Columns: vin_label, failed, event_id, ts_start, n_rows, dur_s, artifact,
#    baseline_vsi, min_vsi_crank, dip_depth, rpm_max_15s, success,
#    recovery_slope, retry_within_120s, days_before_t_end
```

- [ ] **Step 2: Run and reconcile with KT claims**

`py -3 "STARTER MOTOR/src/V1_SM_crank_events.py"`

Console must print the reconciliation table:

```
RECONCILIATION vs KT_startermotor_alternator.md §6.4 (gap-aware definition):
  events total:              ~20,700 (raw prelim: 20,729)   artifacts flagged: N (expect ~50-200)
  mean dur (non-artifact):   failed X.Xs vs NF X.Xs         KT claim: 3.2s vs 2.2s (+48%)
  mean dip_depth:            failed X.XV vs NF X.XV         KT claim: min-VSI 23.1V vs 24.0V
  failed_crank_rate:         failed X.X% vs NF X.X%         KT threshold: >5% critical
  multi_sample_rate:         failed X.X% vs NF X.X%
```

If the KT +48% duration claim does not survive the gap-aware definition, record that in the final report — the feature catalog (Task 4) does not depend on it being true.

- [ ] **Step 3: Sanity assertions** — every VIN ≥ 50 non-artifact events (`MIN_EVENTS_PER_VIN`); no event with `dur_s > 60` and `artifact == False`; `dip_depth` null rate < 40% (baseline window availability).

- [ ] **Step 4: Commit**

---

## Task 4: Phase 2 — Feature Matrix `[ADAPT]`

**Files:**
- Create: `STARTER MOTOR/src/V1_SM_features.py`
- Write: `STARTER MOTOR/results/V1_SM_feature_matrix.csv` (34 rows × ~50 features)

One row per VIN. **Admissibility rules (leakage guards, §2.6):** rates and trends only — no cumulative counts, no observation-length, no gap-days, nothing derived from JCOPENDATE. All "last-30d/last-90d" windows anchor on `t_end`.

- [ ] **Step 1: Implement Branch A — crank physics (from events parquet, non-artifact events)**

| Feature | Definition | Hypothesis source |
|---------|-----------|-------------------|
| `crank_dur_mean` | mean dur_s | KT §6.4 (+48%) |
| `crank_dur_trend` | Theil–Sen slope of monthly mean dur_s vs month index | mode 1 (solenoid wear) |
| `multi_sample_rate` | share of events with n_rows ≥ 2 | robust duration proxy (§2.4) |
| `dip_depth_mean` | mean dip_depth | DICV S4 |
| `dip_depth_trend` | Theil–Sen slope of monthly mean dip_depth | battery–starter cascade (A6) |
| `dip_depth_last90_delta` | mean(last 90d) − mean(rest) | late-stage degradation |
| `failed_crank_rate` | 1 − mean(success) | DICV S6; >5% critical |
| `failed_crank_rate_last90` | same, last 90d before t_end | late-stage |
| `retry_rate` | mean(retry_within_120s) | repeat-attempt signature |
| `recovery_slope_mean` | mean recovery_slope | brush/armature mode |
| `recovery_slope_trend` | monthly Theil–Sen | brush/armature mode |
| `crank_per_active_day` | events / active days | DICV S2/S5 (expect weak — §2.5) |
| `min_vsi_crank_p05` | 5th pct of min_vsi_crank | worst-case crank stress |

- [ ] **Step 2: Implement Branch B — electrical/VSI weekly (from weekly cache; ALT-proven family)**

Port the ALT V10.5.3 winners, computed on `vsi_drive_*` weekly series: `vsi_std_ratio_30d` (last-30d std / overall std), `vsi_dominant_freq`, `vsi_spectral_entropy` (Welch on weekly mean series), `vsi_range_trend_last30d`, `progressive_drift` (CUSUM vs first-8-week baseline), `bat_charge_delta_trend` (weekly `vsi_drive_mean − vsi_rest_median` trend). Plus battery-state features: `vsi_rest_median_trend`, `vsi_rest_p05_last90`, `rate_vsi_below_21` (per active day), `rate_vsi_above_32`.

- [ ] **Step 3: Run, verify matrix** — 34 rows, no feature with >25% nulls, no |r| = 1.0 duplicate pairs; print per-feature failed-vs-NF means as a first look.

- [ ] **Step 4: Commit**

---

## Task 5: Phase 3 — Feature Screening `[COPY from ALT]`

**Files:**
- Create: `STARTER MOTOR/src/V1_SM_feature_selection.py`
- Write: `STARTER MOTOR/results/V1_SM_feature_screening.csv`

- [ ] **Step 1: Screen** — for each feature: Mann–Whitney U p-value (α=0.10), single-feature AUROC (keep ≥ 0.60), Cohen's d; then correlation filter |r| < 0.85 (keep higher-AUROC member); then LOVO stability (feature significant in ≥ 80% of 34 leave-one-out re-screens). Output a ranked pool of **≤ 12 candidates** for the subset search.

- [ ] **Step 2: Run + commit.** Expected output: screening CSV ranked by AUROC with pass/fail flags per criterion, and a printed candidate pool.

---

## Task 6: Phase 4 — Ridge Classifier + Exhaustive Subset Search `[COPY]`

**Files:**
- Create: `STARTER MOTOR/src/V1_SM_ridge_classifier.py`
- Write: `STARTER MOTOR/results/V1_SM_elimination_results.csv`, `V1_SM_lovo_predictions.csv`, `V1_SM_ridge_spec.json`

- [ ] **Step 1: Implement** — exactly the V10.5.3 recipe at n=34:

```python
# 34-fold LOVO; inside each fold: median imputation (train medians) -> StandardScaler
# -> RidgeClassifier(alpha=1.0, random_state=42); sigmoid of decision_function as prob.
# Exhaustive subsets: all combinations of k=4..8 from the <=12-candidate pool
#   C(12,4..8) = 495+792+924+792+495 = 3,498 subsets x 34 folds ≈ 119k fits (~1-2 min)
# Per subset record: features, k, AUROC, recall, specificity, F1, MCC @ Youden threshold
# Winner = highest AUROC, ties -> smaller k, then higher MCC.
# For the winner: bootstrap 95% CI (N=200, resample fixed LOVO preds),
#   label-permutation test (N=1000, p-value), permutation feature importance,
#   per-VIN prediction table with alert tier (GREEN < 0.35 <= AMBER < 0.55 <= RED).
```

- [ ] **Step 2: Run.** Expected console:

```
V1_SM RIDGE — exhaustive subset search (3,498 subsets, 34-fold LOVO)
  best per k:  k=4 AUROC=0.8XX | k=5 ... | k=8 ...
  WINNER: k=X, AUROC=0.8XX [features...]
  Recall: XX/14   Specificity: XX/20   F1: 0.8XX   MCC: 0.XXX
  Bootstrap 95% CI: [0.XX, 0.XX]   Permutation p: 0.00X
```

Gate: AUROC ≥ 0.85 → G1 met. If 0.80–0.85, ship with honest framing + a V1.1 improvement plan; if < 0.80, stop and diagnose per-VIN misses before adding features (do not feature-mine past the screening pool — that's how leakage happens at n=34).

- [ ] **Step 3: Commit.**

---

## Task 7: Phase 5 — Honest Lead-Time Analysis `[ADAPT]`

**Files:**
- Create: `STARTER MOTOR/src/V1_SM_lead_time.py`
- Write: `STARTER MOTOR/results/V1_SM_lead_time_verdicts.csv`

The ALT lesson: most "lead times" from threshold methods were spurious. The SM question is narrower and testable per failed VIN: **does any Branch-A/B signal change measurably in the final 30/60/90 days before `t_end`, relative to that VIN's own baseline?**

- [ ] **Step 1: Implement per-VIN trend test** — for each of the 14 failed VINs and each of ~8 top signals (winner features + `failed_crank_rate`, `dip_depth`): Mann–Whitney of final-window weekly values vs baseline weeks (excluding final window), plus Theil–Sen slope sign; verdict per VIN ∈ {`trending` (p<0.05, consistent direction in ≥2 windows), `late-spike`, `flat`, `insufficient-data`}. Run the identical test on the 20 NF VINs (final 90d before their t_end) as the false-positive control. Report `lead_vs_t_end` and `lead_vs_jcopen` separately; flag the 5 GAP_VINS.

- [ ] **Step 2: Run + commit.** Deliverable mirrors the ALT failure-mode split: an honest per-VIN verdict table — even if the answer is "0–3 of 14 have actionable lead," that is the deliverable.

---

## Task 8: Phase 6 — Production Graphs `[COPY ALT 4-layer design]`

**Files:**
- Create: `STARTER MOTOR/src/V1_SM_production_graphs.py`
- Write: `STARTER MOTOR/graphs/V1_SM_{VIN_LABEL}_dashboard.png` (34 files)

- [ ] **Step 1: Implement** the established 4-panel professional layout per VIN (no trend connector; forecast/reference lines on all VINs per graph-design conventions): Panel 1 — weekly `vsi_drive_mean` ± std band with 24V/21V/32V reference lines; Panel 2 — monthly crank physics (dur mean, dip depth, failed-crank rate as bars); Panel 3 — risk gauge (ridge prob + tier); Panel 4 — event strip (cranks/week, artifacts greyed, silent-gap region hatched with annotation for the 5 GAP_VINS, JCOPENDATE marker on failed VINs).

- [ ] **Step 2: Run (34 graphs) + visual spot-check 3 VINs (VIN8_F_SM, VIN9_F_SM with 142d gap, one NF) + commit.**

---

## Task 9: Phase 7 — Final Report & Verification Gates `[COPY]`

**Files:**
- Create: `STARTER MOTOR/src/V1_SM_final_report.py`
- Write: `STARTER MOTOR/reports/V1_SM_final_report.md`

- [ ] **Step 1: Generate report** with: fleet summary; data-quality findings (§2 of this plan, confirmed/updated); crank catalog statistics + KT reconciliation outcome; classifier results (per-VIN table, CI, permutation p, version context vs ALT V10.5.3 0.927 as methodological benchmark — **not** a comparable number, different fleet); lead-time verdict table; honest limitations (n=34, 5 silent-gap VINs, 5s quantization, no GED channel); deployment recommendation (risk bands + maintenance windows).

- [ ] **Step 2: Verification gates (all must pass before "complete"):**

| Gate | Check |
|------|-------|
| No leakage | feature list contains no gap/observation-length/JCOPENDATE-derived features |
| Label integrity | 14 F + 20 NF rows in matrix; labels from file membership only |
| Threshold honesty | Youden threshold computed within LOVO, not on full predictions |
| Gap handling | all last-N-day features anchored on t_end; GAP_VINS flagged in every output |
| Artifact handling | no artifact event in any duration/dip statistic |
| Reproducibility | every script runs end-to-end via `py -3`, fixed seeds |

- [ ] **Step 3: Final commit + tag `v1-sm`.**

---

## 5. Cross-Validation & Anti-Leakage Protocol

- **LOVO, 34 folds** (one per truck). No stratification possible at truck level. All preprocessing (imputation medians, scaler) fit inside the training fold only.
- **Forbidden features:** observation length, active-day count, telemetry gap to JCOPENDATE, anything touching SALEDATE/JCOPENDATE, raw cumulative counts (§2.6 — failed VINs average ~370 active days vs ~620 NF; cumulative anything = label proxy).
- **Threshold selection** (Youden) is computed per-fold-out predictions, reported with the full confusion matrix; bootstrap CI on fixed LOVO predictions (no retraining); permutation test shuffles labels against fixed predictions.
- **Temporal honesty:** NF trucks' final-window features use their own t_end (2025-02→2026-02) — the classifier must not exploit calendar-epoch differences. Add one control: re-run winner subset with NF windows truncated to match failed-fleet calendar range; AUROC drop > 0.05 ⇒ investigate epoch leakage.

## 6. Risk Analysis

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Crank features too quantized at 5s sampling to separate cohorts | Medium | Branch B (VSI weekly family — won for ALT) carries the classifier; crank features are additive |
| KT duration/dip claims don't reproduce under gap-aware definition | Medium | Task 3 reconciliation step; plan doesn't depend on them |
| 5 silent-gap VINs distort late-window features | High (known) | t_end anchoring everywhere; GAP_VINS flagged; lead-time dual reporting |
| No timing signal found (ALT analogue: GED=2 covered only 2/10) | Medium | G3 is an honest-verdict goal, not a detection-rate promise |
| Epoch/seasonality leakage (failed fleet observed earlier than NF tail) | Medium | §5 calendar-truncation control |
| n=34 overfitting via feature mining | Medium | Screening pool ≤ 12, subsets ≤ 8 features, permutation p required |

## 7. Dependency Graph & Effort

```
Task 1 (Config) ─→ Task 2 (Weekly cache) ─→ Task 4 (Features) ─→ Task 5 (Screening) ─→ Task 6 (Ridge)
        └────────→ Task 3 (Crank events) ──↗                                              │
                                            Task 7 (Lead time) ←──────────────────────────┤
                                            Task 8 (Graphs)    ←──────────────────────────┤
                                            Task 9 (Report)    ←── Tasks 6+7+8
```

Parallelizable: Tasks 2 ∥ 3 (both read raw parquets independently); Tasks 7 ∥ 8 after Task 6.

| Task | Effort (write + run) |
|------|---------------------|
| 1 Config | 15 min |
| 2 Weekly cache | 1 h + ~5 min run |
| 3 Crank events | 1.5 h + ~5 min run |
| 4 Features | 1.5 h + 1 min |
| 5 Screening | 45 min + <1 min |
| 6 Ridge + subsets | 1 h + ~2 min (119k fits) |
| 7 Lead time | 1 h + <1 min |
| 8 Graphs | 1.5 h + 5 min |
| 9 Report + gates | 1 h |
| **Total** | **~10 h** (~8 h with parallelism) |
