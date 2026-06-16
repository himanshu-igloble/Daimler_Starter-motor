---
title: "SM V2 Program — DICV Instrumentation Proposal (Roadmap C2)"
status: "complete"
created: "2026-06-12"
program: "V2 Starter Motor"
author: "Technical Product Lead"
---

# DICV Instrumentation Proposal — Starter Motor V2 Program

## §1 Executive Ask

The V1.1 starter-motor PdM system achieved nested AUROC 0.932 with a validated 10-week
alert horizon — the honest ceiling of the current six telematics signals. That ceiling
is not a modeling limit; it is an instrumentation limit. We request a pilot to add up to
two additional measurement channels on 20–50 BharatBenz 5528T trucks over two operating
quarters. Three options are costed below; **our recommendation is Option C on 25 trucks**,
with Option A on 50 trucks as the no-hardware fallback.

| Option | Description | Hardware required | Approx. cost/truck | Recommended pilot size | Pilot total cost |
|--------|-------------|-------------------|--------------------|------------------------|-----------------|
| A | Trigger-based high-rate VSI only (firmware: sample at 50–100 Hz during SMA=1 events ±10 s) | None — telematics firmware config only | ~₹0 hardware; integration labour TBD | 50 trucks | ~₹0–1.5 lakh (labour/integration) |
| B | Option A + battery-post temperature sensor (NTC thermistor, ±0.5 °C) | ₹500–1,500/truck | ~₹0.5–1.5 k | 30 trucks | ~₹1.5–4.5 lakh |
| C **(recommended)** | Option B + IBS current sensor on battery negative terminal (or split-core Hall clamp on main starter cable) | ₹5,000–15,000/truck | ~₹5–15 k | 25 trucks | ~₹1.25–3.75 lakh hardware; ~₹0.5–1 lakh integration |

**Recommended: Option C on 25 trucks (mixed selection — see §4). Fallback: Option A on
50 trucks at near-zero cost if the IBS integration timeline is prohibitive.**

---

## §2 Why Now: The Validated Ceiling Is Instrument-Limited

The current alert horizon of 10 weeks is not a model artifact. Two independent physics
arguments close it at that value:

**Brush-wear lead destroyed by 5-second sampling.** Brush wear is a gradual failure mode
with a 60–120 day physical precursor window (carbon erosion, rising commutator resistance,
deepening cranking-voltage dip over hundreds of events). That precursor is expressed in
the shape and depth of the cranking-voltage dip during each start. At 5-second telemetry
sampling a 1–3 second crank produces zero or one VSI samples — the dip shape, minimum
voltage, and inrush transient are all aliased away. Trigger-based sampling at 50 Hz during
SMA=1 windows converts "sometimes catches a dip" into "captures every crank profile" and
reopens this 60–120 day channel.

**VSI-without-current conflates three separate fault sources.** At present, every VSI dip
trend observed in the data reflects a superposition of battery state-of-health decline +
battery-cable resistance rise + starter motor internal resistance rise (brushes, solenoid
contacts, winding). These three sources are physically separate failure modes with
different remediation paths (battery replacement vs. cable cleaning/replacement vs. starter
overhaul), but they are mathematically identical in a voltage-only measurement. Adding a
current channel (V + I → R = V/I per crank) separates them: a rising R from starter
components while battery impedance is stable is a direct brush/contact degradation signal.

The validated 4/5 battery-cascade archetype (A2 channel, 0/20 NF false alarms, 66.5-day
median lead) illustrates the precision already possible when one physical mode separates
cleanly. Current sensing extends that precision to the remaining 65% of failure modes.

---

## §3 What Each Option Unlocks

**Option A — Trigger-VSI only (firmware config, no hardware cost)**

Revives the dip-shape physics by capturing every crank event's full voltage trajectory.
New capabilities enabled:
- Per-event minimum cranking voltage (V_min) — currently often missed entirely at 5 s
- Dip duration and recovery profile — discriminates solenoid-contact erosion (slow
  recovery) from battery stress (sharp drop, fast recovery)
- V_min trend over 50–100+ events — the core brush-wear / cable-corrosion indicator
- First-failed-start / retry-sequence voltage cascade — direct solenoid intermittency
  signature
- Overrunning clutch slip confirmation: SMA=1 + zero RPM rise + shallow dip (unloaded
  motor draws less current → shallower dip) becomes reliably measurable, not hit-or-miss
Failure modes newly addressable: Mode 4 (brush wear), Mode 1 (solenoid contact erosion),
Mode 14 (cable/terminal corrosion), Mode 10 (clutch slip), Mode 2 (contact welding).

**Option B — Option A + battery temperature**

Battery voltage has a 0.3–0.5 V dependence on temperature across India's seasonal range
(~20 °C in cool-season mornings to ~45 °C in summer afternoons). Without temperature
correction, the VSI_min trend has a strong seasonal confound that smears across the
battery-degradation signal. A single NTC thermistor at the battery post eliminates the
dominant noise source in all VSI-based features, estimated to reduce feature variance by
30–50%. Directly benefits: all gradual-mode trend detectors (A2 battery cascade, brush-wear
trend, cable-corrosion trend). Required before deploying trigger-VSI features in high-
temperature fleets beyond this pilot.

**Option C — Option B + starter/battery current (recommended)**

A shunt-type Intelligent Battery Sensor (IBS) on the battery negative terminal, or a
non-invasive split-core Hall-effect clamp on the main starter cable, adds the current
channel. With both V and I available:
- R_per_crank = V_min / I_peak: separates starter internal resistance from battery
  impedance for the first time — mode-specific prognosis becomes possible
- Brush wear (rising R_motor at constant battery SoH) → actionable "starter overhaul"
  recommendation with weeks-to-months lead
- Battery degradation (rising R_battery at stable R_motor) → actionable "battery
  replacement" routing, distinct from starter work
- A2-archetype trucks get a precision confirmation: the current evidence today is a
  battery-only inference; adding current proves battery vs. cable vs. starter causality
- Thermal-overload quantification: cumulative I²t per event (energy deposited in windings)
  gives a direct thermal-stress accumulator — the physically correct predictor for
  thermal modes
Failure modes newly prognosis-capable: Modes 1, 4, 5, 6, 14, 15 (previously conflated);
Modes 3, 7, 10 confirmable at event time.

---

## §4 Pilot Design

**Truck selection — 25 trucks (Option C) or 50 (Option A fallback):**

| Stratum | Count (25-truck) | Count (50-truck) | Rationale |
|---------|-----------------|-----------------|-----------|
| Current watchlist (V1.1 RED: VIN2_NF, VIN5_NF, VIN8_NF, VIN15_NF + VIN20_NF RED) | 5 | 10 | Highest prospective failure risk; most likely to yield positive examples early |
| High-duty cycle trucks (verified by high starts/day or high total crank-time from weekly caches) | 5 | 10 | Faster degradation physics; quicker signal accumulation |
| SMA-dead-config trucks (null SMA rate >90% in their history; >=5 trucks in this category per fleet audit) | 5 | 10 | Critical cohort fix: fixes the blind spot responsible for VIN9_F-class silence |
| Random from GREEN tier, diverse route/region | 10 | 20 | Controls for selection bias; needed for production envelope building |

**Data specification — per crank event (SMA=1 trigger ±10 s window):**

| Field | Rate | Notes |
|-------|------|-------|
| VSI | 50–100 Hz triggered | During SMA=1 and 10 s pre/post |
| Current (Option C) | 50–100 Hz triggered | Synchronous with VSI trigger |
| Battery temperature (Option B+) | 1 Hz continuous | Low-rate OK; thermal time constant is minutes |
| SMA | Event-edge triggered | Timestamp of rising/falling edge at ms precision |
| RPM | 1 Hz continuous | Engine state context |
| Existing 6 channels | Unchanged 5 s background | Baseline continuity |

**Volume estimate:** Average 5–10 crank events/day × 10 s window × 100 Hz × 2 channels
= ~10,000–20,000 samples/day/truck. At 4 bytes/sample: ~40–80 kB/day/truck — negligible
on any modern telematics uplink.

**Duration:** 2 quarters (approximately 26 weeks). Quarter 1 gate (see §7) at week 13.

**Pre-registered success criteria (evaluated blind, before outcome unblinding):**
1. Capture rate: >=90% of crank events (SMA=1 episodes) must yield a complete dip profile
   with >=5 high-rate VSI samples spanning the dip minimum.
2. R computability (Option C only): per-event internal resistance R_per_crank must be
   computable on >=80% of cranks where both V and I are available.
3. Physics signal: demonstrate a statistically significant monotonic trend in dip-depth
   OR R_per_crank on >=1 truck that subsequently degrades or fails during or within 30 days
   after the pilot window. If no truck degrades, the null must be reported with confidence
   intervals and documented formally.
4. Zero interference: no event in which the added instrumentation caused a vehicle
   operational issue, CAN-bus fault, or telematics dropout exceeding the pre-pilot rate.

---

## §5 Economics

**Current system economics (validated retrospectively):**

At base costs (breakdown ₹46,000 vs. inspection ₹1,500, ratio 30.7×) and 70% inspection
conversion rate, P3 Youden-queue policy saves 43% vs. run-to-failure. At N=5,000 trucks
with 4% annual failure rate: modelled saving ₹23.4 lakh/year. Break-even ratio is 30.7×;
actual ratio at base costs ≈ 31 — the system is economically marginal at N=5,000/4%;
the case strengthens above 4% or with higher fleet counts.

**Pilot cost vs. prevented breakdowns:**

| Option | Pilot trucks | Hardware cost | Integration (est.) | Total pilot cost | Breakdowns prevented to cover pilot cost (base ₹46k) |
|--------|--------------|---------------|-------------------|-----------------|------------------------------------------------------|
| A | 50 | ~₹0 | ₹0.5–1.5 lakh | ₹0.5–1.5 lakh | 1.1–3.3 breakdowns |
| B | 30 | ₹1.5–4.5 lakh | ₹0.5–1 lakh | ₹2–5.5 lakh | 4.3–11.9 breakdowns |
| C | 25 | ₹1.25–3.75 lakh | ₹0.75–1.25 lakh | ₹2–5 lakh | 4.3–10.9 breakdowns |

**Pilot C at base cost needs ~4–11 breakdowns prevented over its lifetime to pay for
itself.** The 34-truck training fleet had 14 breakdowns in approximately 2 years → ~7/yr
at 34 trucks; at 25 pilot trucks that is ~5 per year expected. With a 43% policy saving,
approximately 2.1 breakdowns/yr avoided — meaning C pays back in roughly 2 years at
deployment scale, with the evidence value (prospective validation of the physics claims)
being the primary near-term return.

**Assumption-flagged cells** (treat as order-of-magnitude): tow cost ₹10k, cargo delay
₹30k, and p_convert=0.70 are all assumptions — see `04_economics_windows_intake.md` T1
for the full sensitivity table. If the operator can provide actual breakdown cost records,
the break-even calculation will tighten substantially.

---

## §6 Asks of DICV Beyond Hardware

The following data items are prerequisite for the V2 program independent of the
instrumentation pilot:

1. **SALEDATE / in-service date for the 20 NF trucks:** The current model uses
   extraction-window start as t_start for NF trucks, which understates their true age
   and biases the fleet Weibull and all time-since-purchase features. SALEDATE enables
   a corrected truck-week table and fleet-clock refit (no model retrain needed — features
   are age-free at week-level). See `specs/data_request_saledate.md` for exact schema.

2. **Maintenance and parts records for all 34 trucks:** Starter/battery/electrical work
   orders with dates and part numbers enable supervised failure-mode labels (battery
   replacement = ground truth for A2 archetype; starter overhaul = confirms brush/solenoid
   modes). Required for V3 supervised-by-mode modelling. See
   `specs/data_request_maintenance_records.md` for schema.

3. **Starter warranty coverage clarification:** Whether starter motors fall under the
   6-year powertrain warranty or a shorter electrical-components warranty directly affects
   cost accounting (warranty repair vs. fleet-cost repair) and the break-even calculation.

4. **Telematics firmware trigger-sampling capability confirmation:** Option A requires
   the existing telematics ECU to support conditional high-rate logging. Please confirm
   manufacturer/model and whether firmware supports trigger-based rate switching. If not
   natively supported, an aftermarket edge logger (e.g., Calamp LMU-4000 class) is the
   fallback.

---

## §7 Risks and Exit Criteria

**Risks:**

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Capture rate <90% at Q1 gate (firmware cannot reliably trigger) | MEDIUM | HIGH — invalidates Option A/B; must step up to edge logger | Q1 gate + explicit fallback path to external logger |
| CAN-bus integration issues with IBS or current clamp | MEDIUM | MEDIUM — delays Option C; Option A/B unaffected | Pre-pilot bench test on one truck before fleet rollout |
| No truck degrades in pilot window | MEDIUM (15% fail/yr at this fleet's observed rate, so ~3–4 of 25 expected) | LOW — null is publishable; does not invalidate method | Pre-registered null report protocol |
| DICV declines data sharing (SALEDATE, maintenance records) | MEDIUM | MEDIUM — NF age-axis bias persists; modelling limitation documented | Proceed with V2 shadow quarter regardless; document the bias |
| SMA-dead-config trucks provide no crank-event data even post-fix | LOW-MEDIUM | MEDIUM — cohort remains blind | Ops check protocol for SMA-silent trucks activated at deployment |

**Exit criteria (kill the pilot if any of the following hold at the Quarter 1 gate, week 13):**

- Capture rate criterion (§4 criterion i) is below 90% AND the fallback edge-logger path
  cannot be activated within 4 weeks.
- Any vehicle operational interference event attributable to the pilot instrumentation
  (§4 criterion iv violated).
- DICV withdraws telematics access for pilot trucks.

If the pilot is killed at Q1 gate, all data collected to that point is retained and
analysed; the V2 system continues in production on the original six signals.

---

*This document is part of V2 Starter Motor Program Roadmap C2. See also:
`specs/data_request_saledate.md`, `specs/data_request_maintenance_records.md`,
`deployment_kit/DEPLOYMENT_RUNBOOK.md`.*
