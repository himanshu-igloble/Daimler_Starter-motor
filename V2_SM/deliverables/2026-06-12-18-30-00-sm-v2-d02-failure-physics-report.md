---
title: "SM V2 Program — D2: Starter Motor Failure Physics Research Report"
status: "complete"
created: "2026-06-12"
---

# Deliverable 2 — Failure Physics Research Report (BharatBenz 5528T Starter System)

> Sources: web-sourced domain research (`STARTER MOTOR/V2_program/intake/02_domain_research_intake.md`,
> 28 cited sources) + the V1.1 physics audit (`V1.1/audit/D_failure_physics.md`) + data-derived
> archetypes (`V1.1/discovery/E_pattern_discovery.md §2`). Claims labeled SOURCED vs DOMAIN-INFERRED
> in the intake; this report keeps that discipline.

## 1. The machine

- **Vehicle**: BharatBenz 5528T (DICV), OM926LA 7.2L I6 diesel, ~280 hp / 1,100 Nm, 24V electrical
  system (2×12V series) [SOURCED].
- **Starter**: 24V / ~5.4 kW co-axial gear-reduction class (Bosch 0001416009-family cross-references
  for OM-series; Bosch = most probable OEM, Lucas TVS = most probable India aftermarket source;
  definitive supplier requires DICV parts book) [SOURCED/UNKNOWN].
- **Sub-assemblies in failure order of relevance**: solenoid (pull-in/hold-in windings + contact
  bridge — arc erosion at every start), brushes/commutator (frictional + arc wear), overrunning
  clutch (freewheel protection), planetary reduction stage, bushings, pinion/ring-gear interface.
- **Duty environment (India)**: 35–48 °C ambient, dust, monsoon ingress, high idle/gate time,
  documented driver tendency to extended cranking — all accelerate the electrical-wear and
  thermal-stress modes.

## 2. The instrument reality (read before the table)

Six signals only: CSP, RPM, ANR, GED, VSI (0.2 V resolution, ~5 s sampling, 16–24% null), SMA
(binary). **No starter current, no battery current, no temperature.** At 5 s sampling a 1–3 s crank
can produce zero VSI samples. Per `D_failure_physics.md §2`: the sampling destroys inrush
transients, true dip shape, sub-5s duration deltas, solenoid chatter, and commutator ripple; it
preserves event existence/count, retry clustering, failed starts, pre-crank rest VSI, and post-start
recovery. Without a current channel, every VSI-dip trend conflates battery SoH + cable resistance +
motor internal resistance.

## 3. Failure physics table (17 modes)

| Failure Mode | Physical Cause | Expected Sensor Signature (our 6 signals) | Lead Time Potential | Detectability |
|---|---|---|---|---|
| Solenoid contact erosion/pitting | 400–1,000 A arcing ablates contact bridge; resistance rises | Deepening VSI dip per crank; longer SMA episodes; retry bursts | Weeks–months (gradual) | MEDIUM |
| Solenoid contact welding (stick-on) | Arc fusion under low-voltage/high-current; heat | SMA=1 persists while RPM at idle; VSI recovers during SMA=1 | Low (sudden; chronic undervoltage precedes) | MEDIUM (if sampled) |
| Solenoid hold-in failure (chatter) | Coil wire break/corrosion; plunger cycles 5–20 Hz | Fragmented/short SMA episodes, no RPM rise — sub-second, invisible at 5 s | Very low | LOW |
| Brush wear-out | Carbon erosion; spring pressure loss below ~40% length | Deepening dip + lengthening crank, trending over 50–100+ events | **60–120 d in physics — destroyed by 5 s sampling** | MEDIUM (trend only) |
| Commutator wear/glazing | Scoring, oxide glaze, proud mica | Same channel as brush wear — telemetry-indistinguishable | Medium | MEDIUM (not separable) |
| Armature winding short/open | Insulation breakdown / wire fatigue | Short: deeper dip; open: shallow dip + failed crank — below 0.2 V resolution early | Low | LOW |
| Field winding fault | Coil break (rare in HD series-wound) | As armature fault | Very low | LOW |
| Bearing/bushing wear | Egg-shaped bronze bushings → shaft drag, misalignment | Slightly deeper dip, longer crank; the grinding is acoustic — no channel | Medium (slow) | LOW–MEDIUM |
| Planetary gear wear | Tooth wear/pitting; grease degradation | Near-zero until seizure (SMA=1, RPM=0) | Low | LOW |
| Overrunning clutch slip (free-spin) | Sprag/roller wear; spring weakening | **Distinctive triad: SMA=1 + zero RPM rise + shallower-than-normal dip** (unloaded motor) | Low (often sudden) | MEDIUM |
| Pinion/ring-gear tooth damage | Engagement misalignment, kickback, crank-while-running | Delayed/erratic RPM rise; complete strip mimics clutch slip | Very low | LOW |
| Thermal overload (extended cranking) | >15 s cranks / rapid retries; windings reach 200–300 °C | **Directly observable: long SMA episodes, retry sequences without RPM rise** | Medium-high (stress events observable; tipping point not) | **HIGH (event) / MEDIUM (prognosis)** |
| Oil/dust/water ingress | Seal weep; monsoon flooding; wash ingress | None directly; outcome = sudden dip deepening / failed starts; seasonal clustering | Low | LOW |
| Cable/terminal corrosion | Electrochemical resistance growth (10 mΩ ≈ 5 V at 500 A) | Deepening dip + longer crank — identical to brush wear & battery aging | Medium (gradual) | MEDIUM signal, LOW specificity |
| Battery-induced starter stress | Aging battery → lower V, series motor draws more current → accelerates all electrical wear | Chronic VSI_min decline across events over months; rest-VSI sag; dip widening | **Months** | **MEDIUM-HIGH — the best observable group** |
| Driver abuse: long cranking | Key held >10–15 s on hard-start engine | SMA duration directly observable; >15 s = thermal risk event | Medium-high (events countable) | **HIGH** |
| Driver abuse: crank-while-running | Starter engaged at running engine; single-event clutch/ring-gear kill | **SMA=1 with RPM>400 in same sample — unambiguous two-signal pattern** | Low (instantaneous) | **HIGH (detection), LOW (prevention)** |

## 4. What the fleet data says the failures actually were

Data-derived archetypes (`E_pattern_discovery.md §2`) map onto the physics table:

| Archetype | n | Physics correspondence | Channel that catches it | Validated catch |
|---|---|---|---|---|
| A1 solenoid intermittency | 3 (VIN1/10/14_F; 14 mixed) | Solenoid contact erosion → retry/failed-start bursts | A1 crank-burst + persistence | 2/3 by A1; all 3 by combined policy |
| A2 battery cascade | 5 (VIN2/3/6/13/14_F) | Battery-induced stress (rest-VSI down, drive-VSI pushed up, dips widening) | **A2 triple detector** | 4/5, 0/20 NF, median 66.5 d lead |
| A3 VSI volatility | 3 (VIN7/11/12_F) | Regulation instability / early A2 without crank signature | Persistence + Layer-1 | 3/3 (RED tier) |
| A4 silent/abrupt | 4 (VIN4/5/8/9_F) | Abrupt modes (clutch, gear, welded contact) + telemetry silence | Layer-1 partially; VIN9_F nothing | 3/4 partial; 1 invisible |

**Premature-failure finding**: HD starter design life is ~30,000–100,000 starts (Delco Remy 39MT
carries 3-yr/unlimited-mile warranty) [SOURCED]; this fleet fails at 1–3 years ≈ 1,800–16,500
starts — severely premature. That points away from normal brush wear-out and toward **battery-induced
stress, thermal overload, and contamination** as dominant causes — consistent with the archetype
split (5/14 battery-cascade, 3/14 solenoid-intermittency). Critically, these dominant groups are
exactly the modes our signal set CAN observe — the model has a physical basis precisely where this
fleet's failures concentrate.

## 5. Detectable vs fundamentally invisible (with current telemetry)

- **Predictable in principle**: brush/commutator + solenoid-contact electrical wear (trend),
  battery-induced stress (months), cable corrosion (trend, unspecific), thermal-stress events
  (direct), driver abuse (direct), clutch slip (distinctive triad at event time).
- **Marginal**: contact welding (post-event), bearing wear (weak, slow).
- **Invisible**: early winding faults, planetary gear wear, hold-in chatter, ingress, early
  pinion/ring-gear damage, anything inside the 5-second sampling floor, and any truck that stops
  transmitting (A4-silent pattern — 5/14 of this fleet's failures had 32–142 d terminal silence).
- Hence the validated honest ceiling: **~10–11/14 recall for lead-time-observable archetypes**
  (`D_failure_physics.md §6`), achieved by V1.1's combined policy (13/14 fire ≥1 channel, but the
  A4 leads are partly post-hoc; VIN9_F catches nothing).

## 6. Industry benchmarks and practice

- PdM for starters in industry = cranking-voltage analysis (VSI_min trending, crank-time trending,
  SOH parameter estimation — US patents 8234036, 10937257, 11182987) and full current-signature
  analysis where instrumented [SOURCED]. Fleets with crank-voltage-trend alerts report ~60%
  reduction in battery/starter service calls [SOURCED, single-vendor claim — treat as upper bound].
- Standard fleet practice is replace-on-fail (₹3,000–25,000 part cost India aftermarket); preventive
  replacement exists only in high-start-frequency niches [SOURCED/DOMAIN-INFERRED].
- BharatBenz: 50,000 km service intervals; 6-yr powertrain warranty (starter coverage unconfirmed);
  no public starter TSBs on the 5528 family [SOURCED/UNKNOWN].

## 7. Sensor gap — what unlocks the next level (ranked)

1. **Battery/starter current channel** (split-core Hall clamp ₹2–8k/truck or IBS ₹5–15k/truck):
   V+I separates battery vs cable vs motor resistance — the single ambiguity that caps today's
   precision. Unlocks brush/winding prognosis, clutch-slip confirmation, thermal-history integration.
2. **Trigger-based high-rate VSI** (100–500 ms while SMA=1): near-zero hardware cost, firmware
   config only; converts "sometimes catches a dip" into "captures every crank profile"; revives the
   60–120 d brush-wear channel that 5 s sampling destroys.
3. **Battery-post temperature** (₹0.5–1.5k/truck): removes the dominant seasonal confound in VSI
   interpretation (~0.3–0.5 V across India's range).
4. **Vibration/acoustic on starter body** (₹15–50k/truck): unlocks bearings/gears/ring-gear — the
   currently-invisible mechanical modes; highest integration cost.
Also operational, not a sensor: **transmission-health monitoring** — a truck going telemetry-silent
is itself a maintenance trigger (the A4/VIN9_F lesson), and **maintenance/parts records** would
convert archetypes into supervised failure-mode labels.

## 8. Implications carried into V2

- Model where the physics is observable: battery-stress (A2) and thermal/abuse events are the
  high-yield channels; keep VSI-trend features as the workhorse (they are, at 4/4 of the modal subset).
- Do not promise earlier warning from this data: the 10-week horizon is physics-consistent, not a
  modeling shortfall (brush-wear's longer channel is instrumentally destroyed).
- Add the two never-built direct event detectors as operational telltales: crank-while-running flag
  and long-crank/retry thermal-stress counter (both HIGH detectability, zero ambiguity).
- Put the current-clamp + trigger-sampling proposal in front of DICV with the economics from D6 —
  it is the only path that changes the physics of what is predictable.
