---
title: "ALT V10.5.3 Production RUL Graph — Reverse-Engineered Implementation Spec (for 1:1 SM port)"
status: "complete"
created: "2026-06-10"
---

# ALT V10.5.3 Production RUL Graph — Reverse-Engineered Spec

**Source of truth:** `V5.2_ALT/src/V10.5.3_20_5_ALT_production_graphs.py` (1334 lines, read in full).
**Visual ground truth verified against:** `V5.2_ALT/visualizations/V5.2_20_5_ALT_rul_curves/V10.5.3_20_5_ALT_{VIN1_F, VIN5_F, VIN3_NF, VIN12_NF}_ALT_rul_production.png`.

**Important clarifications discovered during study (read these first):**

1. Despite the docstring saying "5-layer", **Layer 4 (trend connector) was removed** — the live layers are 1 (confidence band), 2 (RUL curve hist+forecast), 3 (milestones), 5 (terminal star). `CLR_CONNECTOR = "#1a237e"` is defined but **unused**.
2. `WEIBULL_MEDIAN_TTF = 620` is defined at module level but **never used anywhere in the script**. The NF forecast anchor is actually `max_rul = 1200.0` days (hardcoded in `generate_all`). Do **not** port 620 as a drawn element.
3. There is **no Hermite-cubic projection, no conditional Weibull, no burst regions** in this script, and grep of `V10.6.2_ALT/src/` confirms those concepts don't exist there either. The extended forecast is a **power-law decay with seeded noise** (full algorithm in §2.5). The graph math is fully self-contained in this one file.
4. The **zone backgrounds are VERTICAL time spans (`axvspan`), not horizontal bands**. They map degradation-threshold *crossing dates* to x-ranges. Thresholds 0.15/0.35/0.55 appear as horizontal dotted lines only on the **secondary (right) degradation axis** (0–1).
5. The "RUL" plotted is **synthetic/illustrative**: a linear countdown from `max_rul`, divided by a signal-derived acceleration factor, plus seeded noise. It is *not* the Ridge model output. Ridge prob appears only as a corner badge and in the subtitle.

---

## 1. Figure architecture

```python
fig = plt.figure(figsize=(22, 14), dpi=150, facecolor="white",
                 edgecolor="#cccccc", linewidth=1.5)
gs = gridspec.GridSpec(2, 1, height_ratios=[72, 28], hspace=0.08,
                       left=0.06, right=0.89, top=0.88, bottom=0.06)
ax_rul   = fig.add_subplot(gs[0])                      # top panel, 72%
ax_spark = fig.add_subplot(gs[1], sharex=ax_rul)       # bottom panel, 28%, shared x
ax_rul.set_facecolor("white"); ax_spark.set_facecolor("#fafafa")
```

- `right=0.89` deliberately leaves a gutter for right-margin threshold labels drawn with `clip_on=False`.
- Save: `fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white", edgecolor="#cccccc")` then `plt.close(fig)`.
- Output filename: `V10.5.3_20_5_ALT_{VIN_LABEL}_rul_production.png`.

### Title / subtitle / footer (exact construction)

```python
fig.suptitle(f"V10.5.3 Alternator RUL Degradation  --  {vin_label}",
             fontsize=17, fontweight="bold", y=0.97)

subtitle = (f"Ridge Production (6 feat, AUROC {AUROC_STR})  |  "        # AUROC_STR = "0.927"
            f"{n_days} days  |  {n_snapshots} snapshots  |  "
            f"Status: {status}  |  Degradation: {deg_score:.2f} ({deg_zone})  |  "
            f"RUL: {rul_display}  |  Risk: {ridge_prob:.0%}  |  Archetype: {archetype}")
# + f"  |  ODO: {total_km:,.0f} km" if total_km > 0
fig.text(0.5, 0.925, subtitle, ha="center", fontsize=10.5, color="#555555")

# Footer left:
fig.text(0.02, 0.008,
    "Daimler Alternator Failure Prediction | V10.5.3_20_5_ALT | "
    "Ridge Production (6 feat) | GREEN <0.15 | YELLOW 0.15-0.35 | "
    "ORANGE 0.35-0.55 | RED >=0.55 | Confidential",
    fontsize=8, color="#888888", ha="left", va="bottom")
# Footer right:
fig.text(0.98, 0.008, f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}",
    fontsize=8, color="#888888", ha="right", va="bottom")
```

Where: `status = "FAILED" | "ACTIVE"`; `deg_score`/`deg_zone`/`archetype` come from `results/V5.2.1_20_5_ALT_zone_scores_recalibrated.csv`; `ridge_prob` from `results/V10.5.3_20_5_ALT_ridge_predictions.csv`; `rul_display = f"{int(final_rul)}d"` (last weekly RUL value, "0d" floor); KM from `reports/analysis/vehicle_statistics.xlsx` sheets `VIN_Master` (total_km, km_per_day) and `Daily_KM` (cumsum → cum_km at date).

### Axis labels / ticks

- Top Y-label: `"Predicted RUL (Days)"`, fontsize=13, bold. Right twin-axis Y-label: `"Degradation Score"`, fontsize=13, bold, color `#555555`, ylim (0, 1.0).
- Bottom Y-label: `"VSI (V)"` fontsize=13 bold; X-label `"Timeline"` fontsize=13 bold.
- Top panel x tick labels hidden (`plt.setp(ax_rul.get_xticklabels(), visible=False)`).
- X formatter on sparkline: `DateFormatter("%Y-%m")`, `MonthLocator(interval=2)`, rotation=45, ha="right", fontsize=10. All y-tick labels fontsize=10.
- Both panels: `grid(True, which="major", color="#e0e0e0", linewidth=0.5, zorder=0)` + `set_axisbelow(True)`.

---

## 2. TOP PANEL — the RUL curve

### 2.0 Y axis

- Y = **"Predicted RUL (Days)"**, in raw days, counting DOWN over time (curve slopes downward; axis itself is normal-direction, 0 at bottom).
- `ax_rul.set_ylim(0, y_max)` where:
  - **Failed:** `y_max = max(max_rul * 1.15, max(rul_arr) * 1.10, 100)` with `max_rul = ttf_days` from VIN metadata (failure_date − sale_date, e.g. 472–673 d).
  - **Non-failed:** `y_max = max(rul_peak * 1.10, max_rul * 1.05, 100)` with `max_rul = 1200.0`.
- X limits: `plot_start = first_date − 10d`; `plot_end = max(last_date + 21d, forecast_fail_date + 14d, [failed only:] actual_failure_date + 14d)`.

### 2.1 Weekly trajectory — the actual curve algorithm

One point per week (`w = 0 .. total_days//7`), at `snapshot_date = first_date + 7w` days. For each snapshot:

**(a) Signal features in a 30-day lookback window** (`compute_weekly_degradation_features(df, snapshot_date, window_days=30)`), rows filtered to engine-running (`RPM not null and RPM > 0`) for VSI; full window for GED:

| feature | definition | fallback if <500 VSI samples |
|---|---|---|
| `vsi_mean` | mean(VSI) | 28.0 |
| `vsi_std` | std(VSI) | 0.3 |
| `vsi_range` | P95(VSI) − P5(VSI) | 1.0 |
| `vsi_deviation` | abs(mean − 28.2) | 0.2 |
| `vsi_min_running` | P1(VSI) | 27.0 |
| `ged2_rate` | count(GED==2 in window) / window_days | 0 |

**(b) Baseline** = same function with `end_date = first_date + 90d`, `window_days=90` (i.e., the first 90 days of telemetry).

**(c) Composite degradation score** (`features_to_degradation`), 0=healthy → 1=critical:

```python
baseline_std_floor   = max(baseline.vsi_std, 0.30)
baseline_range_floor = max(baseline.vsi_range, 1.0)
s1 = clip((vsi_std/baseline_std_floor   - 1.0) / 3.0, 0, 1)   # volatility growth
s2 = clip((vsi_range/baseline_range_floor - 1.0) / 4.0, 0, 1) # spread growth
s3 = min(1.0, vsi_deviation / 4.0)                            # drift from 28.2 V
s4 = min(1.0, ged2_rate / 0.1)                                # GED2 events/day
s5 = clip((27.0 - vsi_min_running) / 6.0, 0, 1)               # undervoltage depth
degradation = clip(0.25*s1 + 0.25*s2 + 0.20*s3 + 0.20*s4 + 0.10*s5, 0, 1)
```

**(d) Degradation → RUL** (`degradation_to_rul`) — this is where risk modulates curvature:

```python
remaining_linear = max(0.0, max_rul - elapsed_days)            # straight countdown
acceleration    = 1.0 + degradation**1.5 * 2.0                 # 1x (healthy) → 3x (critical)
adjusted_rul    = remaining_linear / acceleration
rng   = np.random.RandomState(int(elapsed_days*7 + seed_salt) % 2**31)   # seed_salt = hash(vin_label) % 10000
noise = rng.normal(0, remaining_linear * 0.02)                 # 2% organic jitter, shrinks toward 0
rul   = max(0.0, adjusted_rul + noise)
```

So: healthy weeks ≈ linear countdown from `max_rul`; degraded weeks get pushed down by up to ÷3, producing the non-linear "sag". Noise is deterministic per VIN (reproducible).

### 2.2 Historical / forecast split — 60% of WEEKLY SNAPSHOTS

```python
split_idx  = max(1, int(len(dates_arr) * 0.6))   # 60% of the weekly-snapshot list
hist = arrays[:split_idx + 1]                    # solid; note +1 overlap point so lines join
fore = arrays[split_idx:]                        # dashed; starts at same point
forecast_start_date = dates_arr[split_idx]
```

The "timeline" is the observed telemetry span (first→last data date), sampled weekly — the last 40% of *observed* data is restyled as "forecast" (this is a presentation device; both segments are the same computed series).

### 2.3 Layer 2 styling

- **Historical:** solid line, `color="#d35400"`, lw=2.0, alpha=1.0, zorder=4, label `"Layer 2: Signal-Derived RUL (historical)"`. Circle markers every 4th weekly point: `marker="o"`, ms=4.5, face `#d35400`, edge white 0.5, zorder=5.
- **Forecast (observed tail):** dashed `"--"`, same color, lw=2.0, alpha=0.7, zorder=4, label `"Layer 2: Signal-Derived RUL (forecast)"`. Triangle markers every 4th point: `marker="^"`, ms=5, alpha=0.7, white edge 0.5, zorder=5.

### 2.4 Layer 1 confidence band (over the observed series)

Width is **degradation-proportional**:

```python
width_frac = 0.05 + 0.20 * degradation_i        # 5% when healthy → 25% when critical
upper_i = min(rul_i * (1 + width_frac), y_max * 0.98)
lower_i = max(rul_i * (1 - width_frac), 0)
ax_rul.fill_between(dates, lower, upper, color="#e67e22", alpha=0.15,
                    label="Layer 1: Prediction Envelope", zorder=1)
```

### 2.5 EXTENDED forecast (dotted projection beyond last data → RUL=0)

Drawn only if `last_obs_rul > 2 and forecast_fail_date > last_obs_date`, where
**`forecast_fail_date = first_date + max_rul` days** (linear-RUL zero crossing):
- Failed VINs: `max_rul = ttf_days` ⇒ purple forecast line lands essentially **at the actual failure date** (sale-date-anchored TTF), so dotted projection runs from last obs down to 0 at ~the failure date. Both red (actual) and purple (forecast) vlines appear, usually near-coincident.
- NF VINs: `max_rul = 1200` ⇒ projection extends to **first_date + 1200 d**, often far past last data (the long dotted descent visible on NF graphs).

Algorithm (power-decay with shape learned from recent history):

```python
days_to_forecast = (forecast_fail_date - last_obs_date).days
n_proj = max(10, int(days_to_forecast / 5))                  # ~one point / 5 days
recent_n      = max(8, len(rul_arr)//3)                      # last ~30% of history
weekly_drops  = np.diff(rul_arr[-recent_n:])
noise_std     = np.std(weekly_drops)*0.3 if len(weekly_drops)>5 else abs(last_obs_rul)*0.01
np.random.seed(hash(vin_label) % 10000)
for i in 0..n_proj:
    frac = i / n_proj
    if len(weekly_drops) > 3:
        accel = np.mean(np.diff(weekly_drops))
        power = clip(1.0 + accel*0.1, 0.6, 2.5)              # concavity from observed acceleration
    else:
        power = 1.3
    base_rul = last_obs_rul * (1 - frac)**power              # power-law decay to 0
    edge_damping = min(frac, 1-frac) * 4                     # noise 0 at endpoints
    proj_rul = max(0, base_rul + N(0, noise_std*edge_damping))
    if i == n_proj: proj_rul = 0.0                           # exact landing at RUL=0
```

Style: dotted `":"`, `#d35400`, lw=1.6, alpha=0.55, zorder=3, **no legend label**.
Widening envelope around projection:
`width_frac = 0.08 + 0.22*(i/(n-1))`; `upper = min(r*(1+wf)+10, y_max*0.95)`; `lower = max(r*(1-wf)-5, 0)`; fill `#e67e22`, alpha=0.05, zorder=1.

**Maintenance alert date:** first projection point with `proj_rul < 90` (fallback: first observed weekly RUL < 90). Drives vline #6 (§5).

---

## 3. Zone backgrounds — VERTICAL time bands (not horizontal)

`find_zone_transitions`: for each threshold (yellow 0.15, orange 0.35, red 0.55), the **first weekly snapshot date** where `degradation >= threshold`. Bands are then chained x-spans:

- GREEN: first_date → yellow-transition (or `plot_end` if never crossed).
- YELLOW: yellow-transition → orange-transition (or plot_end). Same chaining for ORANGE → red, RED → plot_end. Skipped zones simply absent. If no transition at all: single GREEN band over the whole plot.
- `axvspan(start, end, facecolor=ZONE_COLORS_LC[zone], alpha=0.35, zorder=0)`.
- Zone caption at band x-midpoint, `y = y_max*0.97`, va="top", fontsize=10, bold, color = dark zone color (§8), two lines: `"GREEN\n2024-04 - 2024-12"` (YYYY-MM of band start/end), zorder=5.

The numeric thresholds appear as **horizontal** guides only on the right twin axis (`ax2`, ylim 0–1): `axhline(thresh)` dotted, lw=0.7, alpha=0.5, in dark zone colors `{yellow:#b8860b, orange:#d35400, red:#8b0000}`, plus right-margin labels at `x = plot_end + 1` day: `"  YELLOW 0.15"` etc., fontsize=9, bold, `clip_on=False`, in a rounded bbox (`pad=0.15`, fc = pastel zone color, ec = dark color, alpha=0.7, lw=0.8).

Legend zone patches (added manually): pastel colors, alpha=0.5, labels `"GREEN <0.15"`, `"YELLOW 0.15-0.35"`, `"ORANGE 0.35-0.55"`, `"RED >=0.55"`.

---

## 4. Layer 3 milestones + Layer 5 terminal marker

### Milestones (25/50/75/100% of lifecycle)

For each pct in {0.25, 0.50, 0.75, 1.0}: `target_day = int(total_observed_days * pct)`; pick the **weekly snapshot with `day` closest to target_day**; read its date, RUL, degradation; map degradation → health zone (same 0.15/0.35/0.55 cuts).

- Marker: `"D"` diamond, ms=11, face = dark zone color, edge white 1.2, zorder=8.
- Annotation text: `f"{int(rul)}d | ~{km/1000:.0f}k km | {zone_initial}"` (KM part dropped if cum_km ≤ 100; zone initial = G/Y/O/R). KM = cumulative km at milestone date from Daily_KM sheet.
- Stagger: pct 0.25/0.75 → `y_offset=+y_max*0.14, x_offset=-30` days; pct 0.50/1.0 → `y_offset=-y_max*0.12, x_offset=+30`. `ann_y` clipped to [y_max*0.05, y_max*0.92].
- Style: fontsize=8, bold, color = dark zone color, white rounded bbox (`pad=0.3`, ec = marker color, alpha=0.90, lw=1.0), arrow `-|>` lw=0.8 `connectionstyle="arc3,rad=0.15"`, zorder=9.

### Terminal event (Layer 5)

Star at (**last observed date, last weekly RUL**) — both cohorts:
`marker="*", ms=16, edge white 1.5, zorder=10, label="Layer 5: Terminal Event"`.

- Failed: color `#c0392b`; annotation `"Last Obs: {date}\nActual Failure: {fail_date}\nODO: ~{total_km:,.0f} km"`.
- NF: color `#27ae60`; annotation `"Last Obs: {date}\nStatus: Active/Healthy\nODO: ~{total_km:,.0f} km"`.
- Annotation at `xytext=(date − 40 days, rul + y_max*0.14)`, fontsize=8 bold, white bbox `pad=0.4` ec=terminal color alpha=0.92 lw=1.2, arrow `-|>` lw=1.2 `rad=-0.2`, zorder=10.

### Zone-action annotations (drawn at zone transition dates, on the curve's RUL value)

- Yellow entry: green box `"Early Warning\n{lead}d Lead"` (failed: lead = failure_date − yellow_entry days; NF: `"Early Warning\nOngoing"`), fc `#d4edda` ec `#27ae60`; plus a second box `"Monitor\nvoltage stability"` fc `#fff3cd` ec `#b8860b` offset below-right.
- Orange entry: `"Schedule Inspection"` fc `#f8d7da` ec/text `#d35400`.
- Red entry: `"Replace Alternator"` fc `#f5c6cb` ec/text `#8b0000`.
- All fontsize=8 (bold except Monitor box), alpha=0.88, arrow `-|>`; extra `+y_max*0.08` y-offset if the transition is within 30 days of any milestone (overlap avoidance).

### Ridge risk badge

If `ridge_prob > 0`: axes-fraction text at (0.97, 0.06), `f"Ridge Risk: {ridge_prob:.0%}"`, fontsize=9 bold, ha=right; color `#8b0000` if ≥0.55 else `#d35400` if ≥0.35 else `#b8860b`; white rounded bbox `pad=0.5`, ec = same color, alpha=0.92, lw=1.5, zorder=10.

---

## 5. Vertical reference lines (top panel; mirrored thinner on sparkline)

| # | line | color | style | lw | alpha | label (rotated 90°, fontsize 7.5) | label y | cohort |
|---|---|---|---|---|---|---|---|---|
| 1 | First data | `#27ae60` | `:` | 1.3 | 0.8 | `" {YYYY-MM-DD}"` | y_max·0.98, va=top | both |
| 2 | Last data | `gray` | `--` | 1.3 | 0.7 | `" Last Data {date}{ | ~NNk km}"` | y_max·0.60 | both |
| 3 | Actual failure | `#e74c3c` | `:` | 1.3 | 1.0 | `" Failure {date}{km}"` **bold** | y_max·0.38 | failed only |
| 4 | Forecast failure | `#8e44ad` | `:` | 1.3 | 0.8 | `" Forecast {date}{km}"` **bold** | y_max·0.18 | both |
| 5 | Forecast start | `#2196F3` | `--` | 1.3 | 0.7 | `" Forecast Start {date}"` | y_max·0.82 | both |
| 6 | Maint. alert | `#f39c12` | `:` | 1.5 | 0.9 | annotate-box `"MAINT. ALERT {date}"` (not rotated): xy=(x, y_max·0.68), xytext=(x+12d, y_max·0.78), fc `#fff8e1`, ec `#f39c12` | — | when RUL<90d found |

KM suffix helper: `f" | ~{km/1000:.0f}k km"` if cum_km at date > 100. Sparkline mirrors of #1–#5: lw 0.8–1.0, alpha 0.5–0.7, same colors/styles; #6 mirror lw=1.0 dotted alpha=0.7.

---

## 6. BOTTOM PANEL — VSI sparkline

Data (`compute_daily_sparkline`): group raw telemetry by calendar day; VSI stats restricted to running rows (`RPM > 0`): daily `vsi_mean`, `vsi_p95` (q=0.95), `vsi_p05` (q=0.05) — ffill().bfill() gaps; `ged2_count` = daily count of GED==2 over ALL rows (running or not), fillna 0.

- Mean line: `#2c3e50`, lw=1.2, alpha=0.9, label `"VSI daily mean"`.
- Range fill p05→p95: `#e67e22`, alpha=0.22, label `"VSI daily range (P5-P95)"`.
- **GED=2 ticks:** for days with `ged2_count > 0`, scatter at fixed `y=20.5`: `marker="|"`, color `#e74c3c`, `s = clip(count/10, 0.3, 1.0)*14*5` (i.e. 21–70 pt²), alpha=0.7, zorder=5, label `"GED=2 events"`.
- DICV thresholds: `axhline(26.0)` color `#c0392b` and `axhline(24.0)` color `#8b0000`, both `--`, lw=1.2, alpha=0.6; right-margin labels `"  A5: 26.0V"` / `"  A6: 24.0V"` at `x = plot_end + 1d`, fontsize=8, `clip_on=False`.
- Nominal band: `axhspan(28.0, 28.4, color="#27ae60", alpha=0.08, zorder=0)` with text `"DICV A1 nominal (28.0-28.4V)"` at first spark date, y=28.5, fontsize=8, color `#27ae60`, alpha=0.7.
- **Event callouts** (max 3, from `find_key_events`):
  1. first day with `ged2_count > 5` → `"First GED=2 burst\n({n} events)"`, color `#e74c3c`;
  2. first day with `vsi_mean < 25.0` → `"VSI dip to {v:.1f}V"`, color `#c0392b`;
  3. (if >30 days) max `vsi_range` day if range > 3.0 V → `"Max VSI range\n({r:.1f}V spread)"`, color `#e67e22`.
  Drawn as annotate: y clamped to [22, 31], xytext = (+20 days, y+1.5 capped 31.5), fontsize=8 bold, white bbox `pad=0.2` ec=event color alpha=0.85, arrow `-|>` lw=0.8, zorder=6.
- Cosmetics: `ylim(20, 32)`, facecolor `#fafafa`, legend upper-right fontsize=8.5 framealpha=0.85 **ncol=3**.

---

## 7. Legend (top panel)

`ax_rul.legend(handles + 4 zone patches, loc="upper right", fontsize=8.5, framealpha=0.88, edgecolor="#cccccc", fancybox=True, ncol=2, borderpad=0.8)`.
Auto-collected labels in order: `Layer 1: Prediction Envelope`, `Layer 2: Signal-Derived RUL (historical)`, `Layer 2: Signal-Derived RUL (forecast)`, `Layer 5: Terminal Event`, then `GREEN <0.15`, `YELLOW 0.15-0.35`, `ORANGE 0.35-0.55`, `RED >=0.55`. (Marker-only plots and the dotted projection carry no labels.)

---

## 8. Constants block (copy-ready)

```python
VERSION   = "V10.5.3_20_5_ALT"
AUROC_STR = "0.927"
WEIBULL_MEDIAN_TTF = 620          # defined but UNUSED — do not draw
NF_MAX_RUL = 1200.0               # NF forecast anchor (days)

ZONE_THRESHOLDS = {"yellow": 0.15, "orange": 0.35, "red": 0.55}
ZONE_COLORS = {"GREEN": "#a5d6a7", "YELLOW": "#fff176",
               "ORANGE": "#ffb74d", "RED": "#ef9a9a"}      # pastel bands, alpha 0.35
ZONE_DARK   = {"GREEN": "#1b7a3d", "YELLOW": "#b8860b",
               "ORANGE": "#d35400", "RED": "#8b0000"}      # text/markers

CLR_MODEL     = "#d35400"   # RUL line (hist & forecast & projection)
CLR_CONNECTOR = "#1a237e"   # UNUSED (Layer 4 removed)
CLR_BAND      = "#e67e22"   # confidence band (alpha 0.15 obs / 0.05 proj)
CLR_VSI_LINE  = "#2c3e50";  CLR_VSI_FILL = "#e67e22"       # sparkline
CLR_GED2      = "#e74c3c";  CLR_GREEN = CLR_NOMINAL = "#27ae60"
VLINE_FIRST="#27ae60"; VLINE_LAST="gray"; VLINE_FAIL="#e74c3c"
VLINE_FCAST="#8e44ad"; VLINE_FSTART="#2196F3"; VLINE_MAINT="#f39c12"
TERMINAL_FAILED="#c0392b"; TERMINAL_NF="#27ae60"
VSI_NORMAL_RUNNING=28.2; VSI_UNDERVOLTAGE=26.0; VSI_MIN_CRANK=24.0  # DICV A-levels

# Linewidths / sizes
LW_RUL=2.0; LW_PROJ=1.6; LW_VLINE=1.3; LW_VLINE_MAINT=1.5; LW_SPARK=1.2
MS_HIST_DOT=4.5; MS_FORE_TRI=5; MS_MILESTONE_D=11; MS_TERMINAL_STAR=16
FS_TITLE=17; FS_SUBTITLE=10.5; FS_AXLABEL=13; FS_TICK=10; FS_ZONECAP=10
FS_LEGEND=8.5; FS_RISK=9; FS_THRESH_LBL=9; FS_ANNOT=8; FS_VLINE=7.5; FS_FOOTER=8

# zorder convention: 0 zone bands+grid · 1 conf bands · 3 vlines+projection
# · 4 RUL lines · 5 curve markers, zone captions, vline labels · 6 action/event
#   annotations · 8 milestone markers, maint-alert box · 9 milestone labels
# · 10 terminal star+label, risk badge

# Curve math
BASELINE_DAYS=90; SNAPSHOT_WINDOW=30; WEEK_STEP=7; MIN_VSI_SAMPLES=500
DEG_WEIGHTS=[0.25,0.25,0.20,0.20,0.10]; DEG_NORMS=dict(std=3.0, range=4.0, dev=4.0, ged=0.1, uv=6.0)
ACCEL = lambda d: 1.0 + d**1.5 * 2.0          # RUL = (max_rul - elapsed)/ACCEL + N(0, 0.02*remaining)
SPLIT_FRAC=0.60; MARKER_EVERY=4               # weekly points
PROJ_DAYS_PER_POINT=5; PROJ_POWER_RANGE=(0.6,2.5); PROJ_POWER_DEFAULT=1.3
MAINT_ALERT_RUL=90.0                          # days
BAND_W = lambda d: 0.05 + 0.20*d;  PROJ_BAND_W = lambda f: 0.08 + 0.22*f
GED_BURST_MIN=5; VSI_DIP_V=25.0; MAX_RANGE_V=3.0  # event-callout triggers
```

---

## 9. Porting notes for SM daily graphs (ALT-specific → SM substitution)

| # | ALT element | SM substitution (recommended) |
|---|---|---|
| 1 | Title `"V10.5.3 Alternator RUL Degradation"` / `VERSION="V10.5.3_20_5_ALT"` / filenames `*_ALT_*` | `"V1.1 Starter Motor RUL Degradation"` / SM version string / `*_SM_*` filenames; output under `STARTER MOTOR/V1.1/graphs/` |
| 2 | Subtitle+footer `"Ridge Production (6 feat, AUROC 0.927)"` | **`"Ridge Nested-CV (k=4, AUROC 0.932)"`** (use the SM nested AUROC 0.932; V1-SM headline was Ridge k=4) |
| 3 | NF anchor `max_rul = 1200 d`; unused `WEIBULL_MEDIAN_TTF=620` | Use **SM fleet Weibull median 779 d (111.3 wk; λ=133.3 wk, ρ=2.03; IQR 72.1–156.6 wk)** from `STARTER MOTOR/V1.1/discovery/F_survival_analysis.md` §2 as the NF forecast anchor (`forecast_fail_date = first_date + 779 d`), and footnote it honestly as a fleet-clock prior. Optionally keep a wider cap (e.g. 1100 d ≈ 157 wk upper IQR) for y_max headroom. |
| 4 | Failed `max_rul = ttf_days` from ALT `cfg.VIN_METADATA` (sale→failure) | Same construction from the SM config's VIN metadata (sale_date → failure_date per SM failed VIN). |
| 5 | Degradation features: vsi_std/range/deviation vs 28.2 V, ged2_rate, vsi_min P1 (running = RPM>0, 30-d window, 90-d baseline) | Keep VSI terms (same DICV electrical system). **Replace `ged2_rate` term**: failed SM trucks show **no GED2** — substitute a crank-health term, e.g. crank-event count/day deviation or long-crank rate (SMA==1 session duration) normalized similarly (e.g. s4 = min(1, long_crank_rate/norm)). Beware crank-duration artifacts noted in SM V1 prelim; prefer robust daily crank counts. |
| 6 | Sparkline GED=2 ticks (`ged2_count>0` days at y=20.5) and "First GED=2 burst (>5)" callout | **SMA crank ticks**: days with crank events (SMA 0→1 transitions), tick size scaled by daily crank count; callout = e.g. "Crank burst (N starts)" or first long-crank day. Keep y=20.5 anchor and styling. |
| 7 | DICV lines A5 26.0 V / A6 24.0 V + A1 nominal band 28.0–28.4 V vs `VSI_NORMAL_RUNNING=28.2` | **Keep identical** (28.2 running ref, 26.0 undervoltage, 24.0 min-crank, 28.0–28.4 nominal) — same DICV voltage spec applies to the SM dataset's VSI channel. For SM, the 24.0 V "A6 min crank" line is now the *headline* threshold; consider emphasizing it (lw 1.4) over A5. |
| 8 | Zone action text "Replace Alternator" / "Monitor voltage stability" | "Replace Starter Motor" / "Monitor crank behavior". |
| 9 | External CSVs: `V10.5.3_20_5_ALT_ridge_predictions.csv`, `V5.2.1_20_5_ALT_zone_scores_recalibrated.csv`, `V10.5.3_20_5_ALT_ged_hourly_alerts.csv`, `vehicle_statistics.xlsx` (KM) | Point at SM equivalents in `STARTER MOTOR/V1.1/results/` (ridge predictions, zone scores if produced, crank-event summary instead of GED alerts). If SM zone scores don't exist, fall back to the final weekly degradation score (the script already has this fallback). KM xlsx: SM equivalent or drop KM strings gracefully (code already degrades to no-KM labels). |
| 10 | Footer `"Daimler Alternator Failure Prediction"` | `"Daimler Starter Motor Failure Prediction"`; keep zone-threshold recap and "Confidential". |
| 11 | Yellow-entry "Early Warning {lead}d Lead" | Keep mechanics, but V1-SM found **no lead-time channel** (NF FP 90%) — label honestly, e.g. "Zone entry (illustrative)" or keep "Early Warning" only for failed VINs where lead is computable. |
| 12 | Fleet counts in any caption (25 trucks, 10F/15NF) | SM: 34 trucks, 14F/20NF. |
| 13 | 5/14 SM failed VINs have **silent gaps** (ALT had continuous data) | Add gap masking: break the weekly line (NaN insertion) when a snapshot's 30-d window has <500 VSI samples instead of using the healthy-fallback constants, otherwise gaps render as fake-healthy plateaus. This is the one structural change required vs ALT. |

**Everything else ports unchanged:** figure geometry, gridspec, 60% split, power-decay projection, milestone/terminal/vline/legend systems, zone band chaining, colors, fonts, zorders.
