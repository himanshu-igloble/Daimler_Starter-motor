---
title: "V3.1 Starter Motor — Instrumentation Roadmap v2 (500-Truck Program)"
status: "complete"
created: "2026-07-02"
program: "SM V3.1"
sources: "V3.1 findings (P0-1 heartbeat, 5s-cadence limits, T1 convergence caveat), spec §9"
---

# Instrumentation Roadmap v2 — Sensor-Gap List for the 500-Truck Program

V3.1 confirmed, for a fourth iteration, that the ceiling (0.9357 non-nested / 0.9321 nested)
is a **data ceiling**, not a method or feature-engineering ceiling. Feature engineering on the
existing 6-signal / 5-second frame is closed. The only lever left is new data. This annex
lists the concrete sensor / data asks for the 500-truck program, each tied to the specific
V3.1 finding that motivates it and ranked by ROI (physics value × feasibility).

The binding constraints V3.1 exposed:
- **5-second cadence** destroys sub-second crank physics — a crank is ~1 telemetry row, so the
  inrush waveform, dip shape, and solenoid-chatter signature are unrecoverable.
- **Voltage-only** electrical frame — no current channel, so brush / solenoid / battery
  internal-resistance health cannot be measured directly.
- **No geo / thermal channel** — ambient temperature is unjoinable (Theme 1 closed with
  evidence; see `temperature_closure_and_annex.md`).
- **Heartbeat refuted (P0-1)** — telemetry chains do not mark engine wake, so soak / off-ground
  truth is inferred, biased short, and incomplete.
- **No supervised labels** — `Failure_type` is a constant; T1 attribution can only be a
  *convergence check*, not an accuracy claim.

---

## Priority list

### 1. Battery current sensor (IBS / current clamp) — highest ROI

**Why.** The frame is voltage-only. A direct crank-current measurement yields the **true
starter I²t dose per engagement** — the physical wear driver for brushes, commutator, and
solenoid contacts — and battery internal-resistance estimates. This is the one channel that
converts every voltage-dip *proxy* (the champion `dip_depth_last90_delta`, the REJECTed
`dose_dip_x_intensity`) into a *measured* energy quantity.
**Unlocks.** Brush-wear dose, solenoid-contact erosion, battery IR trend — the mechanisms the
5 s voltage frame can only shadow.
**Ties to V3.1.** Explains why interaction/dose candidates (B2) reject: the dose is being
proxied through voltage dip, not measured.

### 2. High-rate (1 Hz+) VSI burst sampling around SMA events — highest ROI

**Why.** The 5-second cadence is the single most destructive constraint. A firmware trigger
that captures VSI at ≥ 1 Hz for a few seconds around each SMA = 1 event restores the
**sub-second dip waveform** — depth, recovery slope, and shape — within the existing data
pipeline and with no new sensor.
**Unlocks.** Crank-voltage recovery slope (currently ≥ 5 s quantized and graveyard), dip-shape
features, retry-burst micro-structure.
**Ties to V3.1.** Directly addresses the §2.1 constraint "no sub-crank waveform physics exists
at this cadence"; A2 (`dip_resid_trend_12w`) was the closest we could get to a starter-side dip
signature and it was redundant precisely because the dip is under-sampled.

### 3. SPN 110 Engine Coolant Temperature (J1939 CAN) — high ROI

**Why.** **Coolant-at-key-on is the best available crank thermal proxy** — it captures the
actual thermal state the starter must crank against (a cold engine means higher oil-drag torque
and higher inrush current). Cheaper and more directly relevant than ambient air temperature.
**Unlocks.** A genuine thermal-stress feature to pre-register for V3.2, replacing the null
temperature proxies (month seasonality, night-start, cold-dip — all rejected).
**Ties to V3.1.** Theme 1 closed for lack of any thermal channel; SPN 110 is the highest-value
re-opener.

### 4. Per-VIN operating-region mapping — high ROI, lowest cost

**Why.** A single fleet-registry field (operating region) lets regional climatology (IMD
normals / Open-Meteo) be joined **without per-truck GPS**, turning monsoon/winter/summer
exposure from a duty proxy into a real covariate.
**Unlocks.** Legitimizes `monsoon_start_share` (the strongest raw exploratory separator, AUROC
0.7357, currently a leak-adjacent duty proxy).
**Ties to V3.1.** The user decision (2026-07-02) that no region data exists is exactly the gap
this closes.

### 5. Maintenance / parts / warranty records — high ROI (labels)

**Why.** `Failure_type` is a constant string, so V3.1's T1 attribution could only report
**convergence (9/11) with telemetry-derived archetypes, not ground-truth accuracy**, and the
STARTER / solenoid arm stayed unvalidated (n = 2). Real repair records (what part was replaced,
when) turn archetypes and the attribution channel into **supervised labels**.
**Unlocks.** True attribution accuracy; a validated starter-vs-battery classifier; failure-mode
taxonomy the current data cannot provide.
**Ties to V3.1.** Removes the single largest disclosed caveat on the T1 business deliverable.

### 6. SPN 171 Ambient Air Temperature (J1939 CAN) — medium ROI

**Why.** Direct ambient temperature at the vehicle, no external join needed. Complements SPN
110 (coolant) and region mapping for full thermal context.
**Unlocks.** Temp-normalized cranking-load features; thermal-fatigue indices.
**Ties to V3.1.** Second thermal channel after coolant; closes the temperature theme properly.

### 7. TCU deep-sleep beacon / ignition-state signal — medium ROI

**Why.** P0-1 refuted the heartbeat hypothesis: chains of 15–16-min gaps begin right after
shutdown (start_ok 0.9832) but **do not mark wake** (end_ok 0.1587) — the TCU drops to deeper
sleep. As a result V3.1 emits no OFF_DWELL, measures soak only via in-band adjacency (0.7102 of
cranks), and the soak distribution is biased short (unknown-gap hours 288,936.8 vs off-hours
12,976.0). A single ignition-state bit or a deep-sleep wake beacon provides **soak / OFF ground
truth**.
**Unlocks.** Un-biased soak, hot-restart, and overnight features (currently Experimental);
clean off-dwell episodes; the C1 dropout/UNKNOWN_GAP disambiguation (would have caught the
VIN4_F 97-day blackout T3 missed).
**Ties to V3.1.** Directly repairs the heartbeat-refutation consequence documented in the
state-engine report and the T3 unknown-gap gap.

---

## Summary — what to ask for, in order

1–2. **Battery current sensor + 1 Hz VSI burst around SMA** — the physics the voltage-only 5 s
frame cannot reach (crank-current dose + sub-second dip waveform).
3–4. **SPN 110 coolant + per-VIN region mapping** — the cheapest route to a real thermal /
exposure covariate (re-opens Theme 1).
5. **Maintenance records** — supervised labels; ends the convergence-vs-accuracy caveat on T1.
6–7. **SPN 171 ambient + ignition-state / deep-sleep beacon** — full thermal context and soak
ground truth (repairs the heartbeat-refutation consequence).

Everything above is additive to the frozen 6-signal feed; none of it disturbs the shipped
modal-4 champion. Combined with a larger failure cohort (n = 14 failed is SCREEN-GRADE; ~10
more failed VINs cut LOVO variance by ~√(n/(n+10))), these asks are what move the ceiling.

*Motivated by V3.1 findings (P0-1 heartbeat refutation, 5 s-cadence limits, T1
convergence-not-accuracy caveat, T3 unknown-gap miss) and spec §9. Fleet: SM, n = 34.*
