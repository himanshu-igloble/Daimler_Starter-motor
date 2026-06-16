---
title: "V1.1 Starter Motor — Final Executive Recommendation"
status: "complete"
created: "2026-06-10"
---

# Final Executive Recommendation — Starter Motor Failure Prediction (V1.1)

## The realistic path

**Ship V1.1 as a three-channel fleet-monitoring program, not a countdown.** The data supports — and only supports — the following:

1. **Layer 1 — Calibrated risk tiers (ship now).** RidgeClassifier, 4 audited features, nested-LOVO AUROC 0.9321 (CI [0.811, 0.986], p = 0.005), calibrated probabilities (slope 0.86). Score weekly (features need 30–90-day windows; weekly scoring is what the 10-week horizon is built on), review monthly. RED → starter + battery circuit inspection within 2–4 weeks; AMBER → bundle into next scheduled service; GREEN → normal operation.
2. **Layer 2 — Early-warning alerts (ship, tier-gated).**
   - **A2 battery-cascade detector** (rest-VSI step-down + drive-VSI step-up + dip widening): zero NF false alarms, ~9-week median lead, immune to battery replacements. Routes to **battery-first inspection** (DICV A6) — the cheapest intervention with the highest expected save.
   - **Persistence flag** (volatility above fleet envelope ≥4 of last 12 weeks): condition flag on AMBER/RED trucks only — never a standalone pager.
   - **A1 crank-burst corroborator**: tier-gated only; it rescued a GREEN-tier failure (VIN1_F) but is too noisy alone (1.5 FP episodes/truck-year).
3. **Layer 3 — Validity-horizon statement instead of RUL.** Tell operations: *a flagged truck is typically within ~10 weeks of failure; a clean score is valid for ~2.5 months.* Do not quote dates. This is not a modeling gap to be closed later — discrete-time hazard, Cox, Weibull, and every deep survival variant were built or sized and all lose to a constant (RUL MAE 576 d vs 44 d). At 14 events, calibration and day-precision are mathematically incompatible.
4. **Layer 4 — Explanations with every alert.** Per-truck driver attributions, archetype, and a raw-unit counterfactual ("returns to GREEN if rest-floor recovers 0.4 V") — these make the alert actionable and auditable.

## What to stop doing

- **Stop chasing longer lead times in this data.** The physics says the dominant failure modes (solenoid contacts, engagement hardware) telegraph days-to-weeks at best; the one genuine 60–120-day channel (brush wear) is destroyed by 5-second sampling. The 10-week horizon is the ceiling, and ~4 of 14 failures (silent/abrupt A4) are invisible at any horizon.
- **Stop evaluating deep/sequence/survival models at this fleet size.** Every requested architecture is 200×–6,000× over the parameter budget for 14 failure events. Revisit only at n_failed ≥ 30–50.

## What to buy/instrument next (ranked by value per rupee)

1. **High-frequency crank logging** (≥1 Hz during SMA=1, post-2026 vehicle architecture): revives brush-wear prognosis and true dip physics — the single biggest unlock.
2. **Cranking current or battery SoC/SoH signal**: ends the battery-vs-starter ambiguity that caps alert precision today.
3. **Maintenance/parts-replacement records**: converts data-derived archetypes into supervised failure-mode labels.
4. **Keep collecting failures**: at ~30–50 failed trucks, self-supervised crank-encoder pretraining on the 106M raw rows and proper survival modeling become defensible.

## Governance

- Refit only when new failure labels arrive, always under the full nested protocol + admissibility gates (the banned-feature registry in the model card is binding — V1's headline feature turned out to be an observation-length artifact; the gates exist because the leak ceilings in this data, AUROC 0.95 from data volume alone, exceed any honest model).
- Track the 4 persistence-flag NF trucks (VIN2/5/8/15_NF) — they are either future failures or the first evidence of rule drift; either outcome is informative.
- VIN9_F_SM-class failures (SMA-dead + silent gap) are a telemetry-architecture problem, not a modeling problem: the actionable fix is transmission-health monitoring (a truck going quiet is itself a maintenance trigger), not a better classifier.

**Bottom line:** V1.1 is the honest ceiling of this dataset — a well-calibrated risk ranking with a validated ~10-week warning window and physics-grounded triage, delivered with its limits measured and stated. Reliable improvement beyond it requires new signals, not new models.
