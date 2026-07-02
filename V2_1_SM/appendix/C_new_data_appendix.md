---
title: "V2.1 SM — New-Data Acquisition Appendix (what actually breaks the data ceiling)"
status: "complete"
created: "2026-06-22"
audience: "DICV"
---

# New-Data Acquisition Appendix

The supervised classifier is at a **data ceiling** (0.9321 nested AUROC, 10-wk
horizon, n=14 failed). No feature engineered from the current 6 signals at 5 s
sampling has beaten it. The only way to materially improve detection is new data.

## C1 — Intelligent Battery Sensor / current clamp
- **Signal unlocked:** crank in-rush current waveform → brush wear, solenoid
  contact resistance, mechanical drag. These are the actual SM failure modes;
  voltage at 5 s only sees the secondary battery-cascade effect.
- **Why current data can't reach it:** 5 s VSI cannot resolve the sub-second
  crank current transient; SMA is a binary flag, not a load measurement.
- **Cost:** ₹2–15k/truck. **Effort:** hardware fit + CAN integration.
- **Expected payoff:** direct brush/solenoid degradation channel; plausibly the
  missing 60–120 d lead-time signal for the abrupt-failure archetypes (A4).

## C2 — High-rate VSI firmware trigger during SMA=1
- **Signal unlocked:** crank voltage waveform sampled > 0.2 Hz only while
  SMA=1 → dip shape, recovery transient, brush-wear micro-structure.
- **Why current data can't reach it:** the 5 s grid quantizes 93% of cranks to a
  single sample (the KT "+48% duration" finding collapsed for this reason).
- **Cost:** firmware-only (no hardware). **Effort:** telematics firmware change.
- **Expected payoff:** revives the 60–120 d brush-wear channel shelved in V1.1.

## C3 — Full true-CWR scan + SALEDATE/odometer/maintenance ingest
- **Signal unlocked:** age/mileage normalization; completes the partial B5 true
  crank-while-running scan (only 9/15 active NF processed in V2).
- **Why current data can't reach it:** SALEDATE present only on failed files;
  no odometer in telemetry; maintenance events unlabeled.
- **Cost:** data request (specs already drafted in v2_system/specs/).
- **Expected payoff:** removes the n_weeks/t_start recruitment-epoch confounders
  that cap honest AUROC; enables per-age hazard normalization.

## Priority
C2 (firmware-only, cheapest) → C1 (direct failure-mode channel) → C3 (removes
confounders). C1+C2 together are the realistic path to beating 0.932.
