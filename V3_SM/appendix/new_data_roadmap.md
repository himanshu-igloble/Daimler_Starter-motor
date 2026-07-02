---
title: "V3 Starter Motor — New Data Roadmap"
status: "complete"
created: "2026-07-01"
program: "SM V3"
---

# New Data Roadmap

## Context

The starter motor failure-risk classifier is feature-complete at the current dataset.
The 6-signal / 5-second frame (CSP, RPM, ANR, GED, VSI, SMA + timestamp) has been
exhaustively explored across four iterations (V1, V1.1, V2/V2.1, V3). The data ceiling
at AUROC 0.9321 nested / 0.9357 non-nested is the data ceiling, not a feature-engineering
gap. This roadmap specifies three concrete instrumentation or data-collection paths that
would break it.

Each path is described with: signal unlocked, why the current frame cannot reach it,
rough cost/effort, and expected payoff.

---

## Path A — IBS / Current-Clamp: Crank-Current Waveform

### Signal Unlocked

A battery current sensor (Intelligent Battery Sensor, IBS, or an external current clamp
on the starter motor lead) records the per-crank current draw at sub-second resolution.
This yields:

- **Peak inrush current:** proportional to solenoid contact integrity and battery
  internal resistance.
- **Inrush decay shape:** the rate of current rise and fall encodes starter winding
  impedance and rotor dynamics.
- **Crank-duration-resolved current profile:** the full engagement waveform — not just
  the 5-second average — exposes brush/commutator degradation as waveform distortion,
  increased RMS at low RPM, and asymmetric current peaks.
- **Per-crank internal resistance estimate:** R_int ≈ ΔV / ΔI during inrush, computed
  per event without needing a rest period.

These are the signals used in automotive starter durability test benches and are the
most direct observable of the failure modes (brush wear, solenoid contact erosion,
winding impedance drift).

### Why the Current Frame Cannot Reach It

The existing frame contains only VSI (system voltage). Voltage and current are related
by Ohm's law, but without simultaneous current measurement, R_int cannot be computed
per-event — only fleet-averaged proxies can be derived. The 5-second cadence further
means that the inrush peak (which lasts < 1 second) is never sampled directly; only the
tail of the crank event appears in the VSI record. All VSI-based features are therefore
indirect, attenuated proxies of the underlying electrical health.

### Cost / Effort

- **Hardware:** IBS or Hall-effect current clamp per vehicle (~₹1,500–3,000/vehicle at
  volume). Fitted to the starter lead at the battery terminal.
- **Firmware:** CAN logging of the current channel at ≥ 10 Hz during SMA = 1 events
  (event-triggered, not continuous — minimal storage overhead).
- **Deployment:** Feasible as a fleet-wide upgrade at next scheduled service interval.
  A 50-vehicle pilot (to reach AUROC-stabilising n) requires ~12–18 months of collection.

### Expected Payoff

Direct crank-current waveform is the standard signal for starter health assessment in
the academic and OEM literature. At n = 50+ with a current channel, the expected AUROC
improvement is substantial and the confidence intervals narrow to the point where
SCREEN-GRADE caveats relax. This is the highest-ROI instrumentation path.

---

## Path B — High-Rate VSI Firmware Trigger

### Signal Unlocked

The existing firmware logs VSI at a fixed 5-second cadence. A firmware change to add an
event-triggered high-rate VSI window during SMA = 1 events would log VSI at ≥ 1 Hz (or
ideally ≥ 10 Hz) for the duration of each crank session. This would yield:

- **Sub-second voltage dip shape:** the true dip profile, including the inrush minimum
  and the recovery trajectory, rather than the attenuated 5-second average.
- **Per-crank minimum VSI:** the actual voltage floor at inrush, not the 5-second
  minimum.
- **Post-crank recovery time to baseline:** the elapsed time for VSI to return to
  pre-crank level (the `vsi_recovery_time_delta90` feature was pre-registered in V3 as
  F4c but assessed as too quantized at 5-second cadence to be reliable; high-rate
  logging resolves this directly).
- **Crank duration in seconds:** the true duration of the SMA = 1 event at sub-second
  resolution, as opposed to the 5-second-quantized duration currently available.

### Why the Current Frame Cannot Reach It

At 5-second cadence, a typical crank event lasting 2–4 seconds may occupy a single
timestep, and the inrush minimum is averaged with the subsequent recovery period within
that same window. The per-crank dip depth available at 5-second resolution is a
heavily-smoothed approximation. Sub-second features (true inrush minimum, recovery rate,
crank duration < 5 s) are structurally unavailable at the current cadence.

### Cost / Effort

- **Hardware:** none — the voltage channel (VSI) already exists.
- **Firmware:** event-triggered high-rate logging mode activated on SMA rising edge,
  deactivated on SMA falling edge + ~2 s buffer. Log window ~5–10 s per event.
- **Storage:** a fleet of 34 trucks averages roughly 20–50 crank events per operating day.
  At 1 Hz for 10 s per event, this is ~200–500 additional bytes per truck per day —
  negligible relative to the existing 5-second continuous log.
- **Pipeline:** the V1_SM_crank_events.py extraction script reads SMA-defined sessions;
  high-rate windows slot directly into the existing crank-session framework.

### Expected Payoff

High-rate VSI during cranks revives the crank-voltage-waveform physics that the 5-second
cadence destroys, specifically the brush-wear channel (gradual increase in inrush
minimum and recovery time). The 60–120 day brush-wear precursor window (which the
current-frame analysis could not recover) may become accessible. At the same n = 34,
this would likely add 1–2 new features; at n = 50+, a meaningful AUROC improvement is
plausible. Cost: a firmware ticket. This is the lowest-cost path with moderate payoff.

---

## Path C — Full Warranty + Odometer + SALEDATE Ingest

### Signal Unlocked

The current dataset contains observation timestamps but no absolute vehicle age, no
odometer reading, and no sale date. Ingesting these fields from DICV's warranty and
Truckonnect records would unlock:

- **Vehicle age at censor point:** in days and months from SALEDATE to last observed
  timestep. Currently approximated by `n_weeks` (observation span), which is the
  data-ceiling proxy leak flagged in all prior iterations (r(failed, n_weeks) = −0.771).
  True age decoupled from observation span eliminates this leak ceiling.
- **Cumulative odometer at censor:** total distance driven. Enables mileage-normalized
  features (cranks per 10,000 km; dip-depth per 100 hours engine-on) that are robust to
  varying usage intensity across trucks.
- **More failed examples.** The binding constraint on AUROC stability at n = 34 is the
  number of failed VINs (14). Every 10 additional failed examples reduces LOVO variance
  by roughly √(14/(14+10)) ≈ 0.77×, narrowing bootstrap CIs by ~23%. At n = 50 failed
  VINs, the SCREEN-GRADE caveat relaxes materially and a meaningful signal from the
  current feature set may be re-testable without the data-ceiling dominating.

### Why the Current Frame Cannot Reach It

The SM dataset was extracted from a specific time window. Age and mileage are not logged
in the 5-second telemetry; they reside in the warranty / workshop system (JCOPENDATE,
service intervals) and the Truckonnect odometer feed. The JCOPENDATE (job card open date,
used as failure proxy) is already clipped to the observation window in some VINs, as
noted in the V11.2 ALT dossier for the ALT dataset. Full SALEDATE + odometer requires a
cross-system join that was out of scope for the current extraction.

### Cost / Effort

- **Engineering:** a one-time SQL join between the telemetry extract and DICV warranty +
  odometer tables, keyed on anonymized VIN.
- **Data governance:** requires DICV permission to link telemetry and warranty records;
  standard for a production predictive-maintenance system.
- **Timeline:** 1–2 weeks engineering + approval cycle. Does not require new hardware.

### Expected Payoff

Age and mileage normalization are the most important missing confound corrections.
The n_weeks proxy leak (r = −0.771) means the current model is partially exploiting
observation-length as a failure proxy; true age would break this conflation and may
reveal whether the remaining signal is genuinely degradation-driven. Additional failed
examples (from a larger fleet or longer collection window) is the single most direct
intervention to lift the n = 34 ceiling. This path has the highest strategic payoff
and the lowest hardware cost — it requires data pipeline work, not new sensors.

---

## Summary

| Path | Signal Unlocked | Current Frame Gap | Effort | Expected Payoff |
|---|---|---|---|---|
| A — IBS / current-clamp | Crank-current waveform; brush/solenoid health | No current channel; VSI only | Hardware per vehicle; ~12–18 mo pilot | High — unlocks the core failure-mode physics |
| B — High-rate VSI trigger | Sub-second dip shape; recovery time; crank duration | 5-second cadence averages inrush | Firmware ticket; no hardware | Moderate — revives waveform features at low cost |
| C — Warranty + odometer ingest | True vehicle age; mileage; more failed examples | No SALEDATE/odometer in telemetry extract | Data pipeline join; approval needed | High — removes n_weeks leak ceiling; scales n |

Recommended prioritization: Path C first (no hardware, immediate data value), then Path B
(firmware change, low cost), then Path A (highest payoff but requires hardware rollout).
