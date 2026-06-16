---
title: "V2 SM Decision Economics + Evidence-Conditional Failure-Window Product"
status: "complete"
created: "2026-06-12"
program: "V2 Starter Motor"
author: "Economics Analysis Agent"
---

# V2 Starter Motor — Decision Economics and Failure-Window Intake

Fleet: 34 SM trucks (14 failed, 20 NF, suffix _SM). **Total observed truck-years: 48.0
(14.2 failed + 33.7 NF).** All model performance figures are OOF/LOVO-validated from
V1.1. No in-sample numbers are used. Bootstrap seed 42.

**ENRICHMENT WARNING:** This fleet is 41% failed by construction (14/34). The observed
breakdown rate (0.29/truck-yr) must NOT be used as a population rate. All fleet-scale
projections use parameterized population rates of 2%, 4%, 8% per truck-year.

**VIN Independence Rule:** SM VINs are completely independent of ALT VINs. No
cross-dataset analysis is valid.

---

## T1 — Cost Framework

All figures in Indian Rupees (INR), 2026 basis.

### Assumption Transparency Table

| Cost Item | Low | Base | High | Source / Basis |
|---|---|---|---|---|
| Starter motor part | 3,000 | 12,000 | 25,000 | SOURCED: IndiaMart (3k–25k); base = OEM-compatible mid-range ASSUMPTION |
| Planned labour (starter swap, 3–5h) | 1,500 | 2,500 | 4,500 | ASSUMPTION: INR 500–900/h labour rate, tier-2 city to authorised dealer |
| **Planned repair total** | **4,500** | **14,500** | **29,500** | Part + labour |
| Electrical inspection (1–2h, no replacement) | 800 | 1,500 | 3,000 | ASSUMPTION: depot workshop to authorised DICV dealer |
| Battery test (load test, workshop) | 500 | 500 | 500 | ASSUMPTION: standard charge |
| Battery replacement (2 × 12V, 150–200 Ah) | 16,000 | 28,000 | 40,000 | ASSUMPTION: INR 8k–20k per unit × 2; Lucas TVS / Exide range |
| **A2 battery-cascade event total** | **16,500** | **28,500** | **40,500** | Battery test + replacement |
| Breakdown tow (0–50 km flatbed) | 5,000 | 10,000 | 15,000 | ASSUMPTION: India HD flatbed tow rates |
| Emergency labour (after-hours, at-site) | 4,000 | 6,000 | 10,000 | ASSUMPTION: India overtime rates |
| Cargo delay penalty + downtime | 10,000 | 30,000 | 60,000 | ASSUMPTION: 55t tractor, INR 5k–20k/day × 0.5–3 days |
| **Roadside breakdown total** | **19,000** | **46,000** | **85,000** | Tow + emergency labour + cargo delay |

Key ratio: C_breakdown / C_inspect = 19000/800 = 24 (low) to 85000/3000 = 28 (high),
base = 46000/1500 = **31**. This ratio governs all policy economics.

File: `STARTER MOTOR/V2_program/analysis/econ/cost_sensitivity.csv`

---

## T2 — Retrospective Policy Comparison

### Fleet Summary for Policy Accounting

- Observed truck-years: 48.0 total (14.2 F + 33.7 NF)
- Tier distribution (LOVO-validated): RED = 10 F + 2 NF; AMBER = 0 F + 2 NF; GREEN = 4 F + 16 NF
- Youden threshold (per-fold): detects 13/14 F, flags 5/20 NF
- Combined V1.1 channels: 13/14 F detected (persistence: 10 first, A1: 3 first, A2: corroborator)

### Policy Definitions

| Policy | Trigger | Failed detected | Failed missed | NF inspected |
|---|---|---|---|---|
| P0 Run-to-failure | None | 0 | 14 | 0 |
| P1 RED-tier only | tier == RED | 10 | 4 | 2 |
| P2 RED+AMBER | tier in {RED,AMBER} | 10 | 4 | 4 |
| P3 Youden threshold | per-fold score > Youden thr | 13 | 1 | 5 |
| P4 V1.1 recommended | RED->inspect, A2->battery-first, pers/A1=corroborators | 13 | 1 | 10 |
| P5 Quarterly-all | every truck every 3 months | 11* | 3* | 20 |

*P5: quarterly catches trucks with leads >91d (11/14); VIN4_F (28d), VIN2_F (77d), VIN9_F (blind) missed.

### Primary Results (base cost, p_convert = 0.70)

p_convert = probability an inspection-within-lead converts roadside breakdown to planned repair.

| Policy | Expected breakdowns | Inspections | FP NF inspections | Total cost (INR) | Savings vs P0 | Savings % |
|---|---|---|---|---|---|---|
| P0 run-to-failure | 14.0 | 0 | 0 | 6,44,000 | — | — |
| P1 RED-tier only | 7.0 | 12 | 2 | 4,26,500 | 2,17,500 | 33.8% |
| P2 RED+AMBER | 7.0 | 14 | 4 | 4,29,500 | 2,14,500 | 33.3% |
| P3 Youden | 4.9 | 18 | 5 | 3,64,850 | 2,79,150 | **43.3%** |
| P4 V1.1 recommended | 4.9 | 23 | 10 | 4,11,550 | 2,32,450 | 36.1% |
| P5 quarterly-all | 6.3 | 191 | 20 | 6,87,950 | -43,950 | **-6.8%** |

P5 costs MORE than run-to-failure because inspection overhead (191 visits × INR 1,500)
exceeds breakdown savings at this fleet size. Quarterly is not economical for 34 trucks.

### Sensitivity: p_convert sweep (base cost)

Qualitative pattern is stable: P3/P4 dominate P0 at all p_convert >= 0.5.

| p_convert | P0 | P1 | P3 | P4 | Best |
|---|---|---|---|---|---|
| 0.5 | 6,44,000 | 4,62,500 | 3,99,350 | 4,59,550 | P3 |
| 0.7 | 6,44,000 | 4,26,500 | 3,64,850 | 4,11,550 | P3 |
| 0.9 | 6,44,000 | 3,90,500 | 3,30,350 | 3,63,550 | P3 |

### Cost-Ratio Sweep: Where Does Each Policy Dominate?

R = C_breakdown / C_inspect (all else held equal, p_convert=0.7)

| R | Best Policy | Notes |
|---|---|---|
| 1–10 | P0 (run-to-fail) | Inspection more expensive than breakdown — economically absurd but possible at very cheap breakdowns |
| 11–19 | P0 barely | P3 approaches P0 |
| 20–29 | P3 Youden | P3 dominates; P4 close behind |
| 30–49 | P3 | Youden optimal — higher recall worth the 5 FP inspections |
| 50–100+ | P4 | P4 eventually dominates as A2 battery savings compound at very high breakdown cost |

**Youden (P3) vs RED-only (P1) flip point:** P3 < P1 when R > 11.5.
At base costs R = 31 — far above the flip. **P3 dominates P1 at all realistic India HD breakdown costs.**

**Key finding:** The recommended policy P4 (tier-gated V1.1 channels) costs more in
inspections than Youden (P3) because its 10 NF false alarms (vs 5 for P3) create
additional inspection load. However, P4 provides qualitatively richer routing information
(battery-first for A2 trucks) and reduces the risk of unnecessary starter swaps on
battery-only failures. At R >= 50, P4 dominates due to A2's precise 0/20 NF specificity
enabling confident battery replacement without additional diagnostics.

**Operating point recommendation:** At base costs and p_convert = 0.7:
**P3 (Youden threshold) minimises total cost (INR 3,64,850 vs P0 INR 6,44,000 = 43% saving)**.
P4 is preferred operationally when battery-cascade routing matters or R >= 50.

File: `STARTER MOTOR/V2_program/analysis/econ/policy_comparison.csv`

---

## T3 — Evidence-Conditional Failure-Window Matrix

**CRITICAL DISCLAIMER:** This is NOT a countdown clock. All leads are measured
retrospectively to t_end (last data timestamp) or JCOPENDATE (fault log open date).
Sample sizes are tiny (n=2 to n=10). Bootstrap CIs on median with seed 42, 10,000
resamples. These windows are a planning aid for operations scheduling, not a
deterministic RUL estimate.

### State 1 — A2 Battery-Cascade Fired

| Item | Value |
|---|---|
| Evidence | A2 detector fires (rest-VSI step <= -0.5V AND drive-VSI step >= +0.3V AND dip-depth widens > +1V) |
| n | 4 (VIN13_F, VIN14_F, VIN3_F, VIN6_F) |
| Lead values (days to t_end) | 63, 28, 91, 70 |
| Median lead | 66.5 d |
| Range | 28 – 91 d |
| Bootstrap 95% CI on median | [28.0, 91.0] |
| NF false alarm rate | 0 / 20 (perfectly clean on this fleet) |
| Recommended action | Battery-first inspection IMMEDIATELY — schedule within 14–30 days |
| Scheduling window | 14–30 days from alert date |
| Honest caveat | Retrospective n=4 only (4/5 A2 archetype). Min lead 28d means 2-week scheduling is tight — prioritise. The 5th A2 archetype (VIN2_F) missed because its cascade never produced a qualifying drive-step before t_end. Boot CI spans full range due to small n. |

### State 2 — Persistence Terminal + RED Tier

| Item | Value |
|---|---|
| Evidence | Persistence flag fires (>=4 of last 12 weeks above NF p90 envelope) AND tier = RED |
| n | 10 RED-tier failed trucks with terminal persistence |
| Lead values (days to t_end) | 147, 266, 126, 301, 245, 77, 392, 168, 266, 98 |
| Median lead | 206.5 d |
| Range | 77 – 392 d |
| Bootstrap 95% CI on median | [126.0, 283.5] |
| NF end-state false alarms | 4/20 NF end in persistence fire (deployable walking alarm: all 20 NF visit at ~31% of weeks) |
| Recommended action | Schedule planned electrical inspection within 2–4 weeks; if A1 also fires, elevate to this-month priority |
| Scheduling window | 14–28 days |
| Honest caveat | These are terminal-episode leads — the contiguous fire run still active at t_end. The very long median (207d) means this is a condition flag, not failure-imminent alarm. Persistence is only reliable as a terminal-state check, not a first-crossing pager. |

### State 3 — RED Tier, No Channel Fired Yet (Monitoring Phase)

| Item | Value |
|---|---|
| Evidence | Risk score places truck in RED tier but persistence/A2/A1 have not yet fired |
| n | 10 RED-tier failed trucks (first-fire leads once any channel fires) |
| Lead values (days, combined first-fire) | 160, 266, 128, 301, 245, 77, 392, 168, 266, 98 |
| Median lead | 206.5 d |
| Range | 77 – 392 d |
| Bootstrap 95% CI on median | [128.0, 273.0] |
| NF false positives | 2 RED NF trucks (VIN5_NF, VIN20_NF) — monitoring burden |
| Recommended action | Increase monitoring cadence; schedule inspection at next planned service or within 4–8 weeks; do NOT treat as urgent without channel fire |
| Scheduling window | 30–60 days or next scheduled service |
| Honest caveat | In deployment, this state precedes any channel fire — actual horizon to failure is *longer* than shown leads. Model horizon is valid to ~10 weeks (k*=10). 2/20 NF score RED. Do not act on tier alone. |

### State 4 — AMBER Tier, No Channel

| Item | Value |
|---|---|
| Evidence | Risk score in AMBER (borderline zone) |
| n | 0 failed trucks in AMBER (OOF validated) |
| Lead values | No empirical data |
| Median lead | N/A |
| NF false positives | 2/20 NF score AMBER (VIN2_NF, VIN10_NF) |
| Recommended action | Monitor; schedule inspection at next routine service (<=3 months); watch for persistence or A2 channel promotion |
| Scheduling window | At next scheduled service (<=90 days) |
| Honest caveat | Zero empirical failure-window data for AMBER tier (0 F trucks here OOF). AMBER = uncertain risk zone. Both AMBER NF trucks (VIN2_NF, VIN10_NF) may be genuinely degrading (right-censored). No action threshold without a channel fire. |

### State 5 — GREEN Tier, Channel Eventually Fires

| Item | Value |
|---|---|
| Evidence | Risk score GREEN but persistence or A1 fires (late detection) |
| n | 3 (VIN1_F A1 crank burst, VIN3_F persistence, VIN4_F persistence) |
| Lead values (days to t_end) | 160, 168, 28 |
| Median lead | 160.0 d |
| Range | 28 – 168 d |
| Bootstrap 95% CI on median | [28.0, 168.0] |
| NF false positives | 16/20 NF score GREEN — correct classification |
| Recommended action | Routine maintenance schedule only; no proactive intervention until channel fires |
| Scheduling window | Next scheduled service (50,000 km or 6 months) |
| Honest caveat | VIN9_F is a GREEN truck that fired nothing — the irreducible blind spot. Of 4 GREEN-failed trucks, 3 were saved by channel recovery. The 28d lead (VIN4_F) was tight. GREEN tier alone gives no meaningful lead-time product. |

### State 6 — SMA-Dead / Silent > 30d While RED or AMBER

| Item | Value |
|---|---|
| Evidence | SMA shows no crank events for >30d while risk tier is RED or AMBER |
| n observed | 2 (VIN8_F SMA-dead but RED/VSI-detectable; VIN9_F SMA-dead and blind) |
| Lead via VSI channel (VIN8_F) | 98d (persistence via VSI) |
| VIN9_F | Blind spot — no lead on any channel |
| NF SMA-dead count | 5 NF trucks also SMA-dead — not all silent trucks are failing |
| Recommended action | IMMEDIATE manual inspection to confirm vehicle is operational and telematics is connected; if vehicle is active, escalate to shop visit within 72h |
| Scheduling window | Within 72 hours |
| Honest caveat | This trigger is primarily a data-health / telematics-gap flag. Only 2/14 failed trucks were in this state. VSI-based persistence remained viable for VIN8_F. VIN9_F represents the blind spot that cannot be resolved without SMA signal restoration. |

### Summary Lookup Card (Operations Use)

| Evidence State | Scheduling Target | Priority | n basis |
|---|---|---|---|
| A2 battery-cascade fired | 14–30 days | HIGH | n=4, 0 NF FP |
| Persistence terminal + RED | 14–28 days | HIGH | n=10 RED-F |
| RED tier (monitoring, no channel) | 30–60 days | MEDIUM | n=10 RED-F |
| AMBER, no channel | Next service (<= 90d) | LOW-MEDIUM | n=0 F (no data) |
| GREEN + clean | Next routine service | ROUTINE | 1 blind spot known |
| SMA-dead while RED/AMBER | 72 hours | URGENT (data/ops) | n=2 |

File: `STARTER MOTOR/V2_program/analysis/econ/failure_window_matrix.csv`

---

## T4 — Fleet-Scale Extrapolation

### Key Rate Parameters (derived from THIS fleet; enrichment bias corrected)

| Parameter | Observed in fleet | Per truck-year | Notes |
|---|---|---|---|
| A2 channel fires / failed truck | 4 fires | 0.281/F-ty | 4 fires / 14.2 F truck-years |
| A1 fires / applicable failed truck | 4/12 applicable | 0.659/applicable-F-ty | 4 fires / 6.07 eval years |
| RED NF per NF truck-year | 2/20 NF at end | 0.059/NF-ty | 2 VINs / 33.7 NF truck-years |
| A1 NF FP episodes/truck-year | 22 episodes / ~14.5 A1-ty | 0.652/NF-ty | per V1.1 report cited rate |
| Persistence NF end-state | 4/20 NF end-fire | 0.50 per NF (binary) | Walking alarm: 31% of weeks |
| A2 NF false alarm rate | 0/20 | 0.0 | Zero FP on this fleet |

**Enrichment correction:** All projections replace the observed 0.29/ty rate with
parameterized r in {2%, 4%, 8%}/truck-yr.

### N=500 Fleet Projection

| Pop failure rate (%/yr) | Expected failures/yr | Alerts/wk (total) | Inspector hrs/wk | P0 cost (INR lakhs/yr) | P4 savings (INR lakhs/yr) |
|---|---|---|---|---|---|
| 2% | 10 | 7.2 | 1.5 | 4.6 | 0.6 |
| 4% | 20 | 7.6 | 1.9 | 9.2 | 2.3 |
| 8% | 40 | 8.3 | 2.7 | 18.4 | 5.9 |

Break-even ratio R = 30.7 (i.e., breakdown must cost at least 31x inspection cost for
P4 to dominate P0). At base costs R = 31 — system is at break-even for N=500 at 2%
failure rate; economic case strengthens with fleet growth or higher failure rates.

### N=5000 Fleet Projection

| Pop failure rate (%/yr) | Expected failures/yr | Alerts/wk (total) | Inspector hrs/wk | P0 cost (INR lakhs/yr) | P4 savings (INR lakhs/yr) |
|---|---|---|---|---|---|
| 2% | 100 | 72 | 15 | 46.0 | 5.7 |
| 4% | 200 | 76 | 19 | 92.0 | 23.4 |
| 8% | 400 | 83 | 27 | 184.0 | 58.8 |

At 4% failure rate and N=5000, P4 saves ~INR 23 lakhs/year vs run-to-failure.

### Extrapolation Assumption Table

| Assumption | Value | Basis |
|---|---|---|
| Inspector time per inspection | 2 hours | ASSUMPTION: electrical check + report |
| A2 rate applied to all failures | 4/14 per observed F-truck | OOF-validated on this fleet |
| A1 FP rate | 22 episodes / 14.5 A1-eligible truck-years | OOF-validated |
| NF RED false alarm rate | 0.059/NF-ty | Observed 2/33.7 NF-ty |
| Persistence NF end-state fraction | 0.50 per NF truck | OOF-validated (4/20) |
| Channel rates assumed constant across fleets | N/A | Strong assumption; duty cycle, climate, and maintenance quality vary |
| Population failure rate | Parameterized {2%, 4%, 8%} | Enrichment-corrected; actual rate is unknown |
| A2 NF false alarm rate | 0.0 | Observed 0/20 on this fleet; may be non-zero at scale |
| Inspection cost | INR 1,500 (base) | See T1 |
| Breakdown cost | INR 46,000 (base) | See T1 |

File: `STARTER MOTOR/V2_program/analysis/econ/fleet_scale_projection.csv`

---

## Recommended Policy + Dominance Conditions

### Primary Recommendation: P3 Youden Threshold (cost-minimising)

**When P3 is optimal:**
- Breakdown:inspection cost ratio R > 12 (effectively always in India HD trucking context)
- Inspection capacity is not a bottleneck (18 inspections for this 34-truck fleet)
- Battery-routing information is not needed (if A2 routing is important, use P4)

**When P4 (V1.1 recommended tier-gated) is preferred:**
- R >= 50 (high cargo-delay scenario: e.g., refrigerated cargo, time-critical contracts)
- Battery-cascade archetype trucks (VIN13/14/3/6 type) need precise routing to avoid
  unnecessary starter swaps (P4's A2 channel routes to battery-first, saving INR 28.5k
  on a starter replacement that would not have fixed the root cause)
- Operational teams can handle 23 inspections vs 18 (5 more FP inspections per fleet cycle)

### Policy Dominance Map

```
R < 12:   P0 run-to-failure dominates (inspection overhead exceeds breakdown savings)
12 < R < 20:  P3 Youden marginal advantage
20 < R < 50:  P3 Youden clearly best
R > 50:   P4 V1.1 recommended (A2 battery-cascade routing adds INR 14k/event savings
              vs unnecessary starter swap)
Always:   P5 quarterly-all is never economical — 191 inspections vs 18–23 targeted
Always:   P2 RED+AMBER dominated by P3 (P3 catches 13 vs 10 failed, 1 extra NF FP)
```

### Known Limitations and Gaps

1. **n=34 fleet, n=14 failed:** All policy economics are derived from 34 OOF-validated
   outcomes. Confidence intervals on savings estimates are wide; treat the numbers as
   order-of-magnitude guidance, not precise forecasts.

2. **VIN9_F blind spot:** 1/14 (7%) of failures is undetectable on any channel. Any
   policy accepting this blind spot must be communicated to operations.

3. **Cost assumptions are largely ASSUMPTION-driven** for breakdown components (tow,
   cargo delay). If the operator has actual breakdown cost data, the T1 table should
   be updated and the policy comparison rerun.

4. **p_convert assumption:** The probability that an inspection within the lead time
   averts a breakdown (p_convert = 0.5–0.9) is assumption-driven. Validation would
   require tracking actual intervention outcomes.

5. **A2's 0/20 NF false alarm rate** may not hold at scale. This fleet had 20 NF
   trucks; at N=5000 NF trucks, even a 1% false alarm rate would generate 50 FP
   battery-cascade events/year at INR 28.5k each = INR 14.25 lakh/yr.

6. **Extrapolation validity:** Channel rates are derived from a BharatBenz-specific,
   telematics-instrumented fleet in specific duty conditions. Do not apply to fleets
   with different VSI null rates, duty cycles, or climates without validation.
