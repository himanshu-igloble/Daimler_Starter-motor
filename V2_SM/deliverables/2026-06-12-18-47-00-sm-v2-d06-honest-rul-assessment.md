---
title: "SM V2 Program — D6: Honest RUL Assessment & Failure-Window Framework"
status: "complete"
created: "2026-06-12"
---

# Deliverable 6 — Honest RUL Assessment (and what ships instead)

> Basis: `V1.1/discovery/F_survival_analysis.md` (F1–F4, read in full and verified),
> `V1_1_SM_alerts_horizon.md` (X4 horizon), and the V2 evidence-window build
> (`V2_program/analysis/econ/failure_window_matrix.csv`, `V2_program/intake/04_economics_windows_intake.md`).

## 1. The four audit questions, answered per candidate RUL framing

| Framing | VIN-specific? | Truly predictive? | Fleet average in disguise? | Uncertainty honest? | Verdict |
|---|---|---|---|---|---|
| KM fleet clock | No | No — median undefined (S(t) never crosses 0.5 at 14/34 events) | Yes | n/a | Unusable |
| Weibull fleet clock, conditional median (LOVO) | Age-conditional only | No — MAE **461.9 d** on trucks dying ≤182 d | Yes (λ=133.3 wk, ρ=2.03) | CI computable but irrelevant at this error | Closed |
| Discrete-time hazard, 3 lagged covariates (LOVO) | Nominally | No — median-RUL MAE **576.1 d**; truck ranking AUROC 0.586 vs static 0.893 | Effectively (hazard 0.0053/wk dominates) | Calibrated-in-the-large (1.06) — which is exactly why precision is impossible | Closed |
| Cox PH / Weibull AFT | — | vsi_std_ratio HR 1.74 (only signal); early-life covariate NS | — | Naive SEs anti-conservative | Sanity checks only |
| Deep survival (DeepSurv/DeepHit/DSM/RSF) | — | Unfittable: EPV < 0.5–1 at 14 events | — | — | Closed by parameter arithmetic |
| **Constant 91 d** (no model) | No | No | By construction | n/a | **MAE 44.4 d — the floor every model loses to** |
| Static risk + validated horizon (V1.1) | **Yes (tier)** | **Yes — 10-wk validity, decay-to-chance verified** | No | CI on AUROC + calibration shipped | **Shipped** |
| **Evidence-conditional failure windows (V2)** | **Yes (state)** | Empirical, channel-conditioned | No — leads come from the truck's own evidence state | **Bootstrap CIs + n stated per state** | **The V2 product** |

## 2. Why day-precision RUL is mathematically closed here

At 14 events / 2,636 truck-weeks the calibrated weekly hazard is 0.0053. A *correctly calibrated*
model must therefore put median survival ~700 d even on trucks that die within 182 d — calibration
and day-precision are incompatible at this event rate (`F_survival_analysis.md §5`). Per-VIN hazard
MAE ranged 76 d (VIN14_F, strong crank signal) to 1,012 d (VIN9_F, masked covariates). This
replicates and exceeds the ALT finding (fleet clock unbeatable, MAE 142 vs 50 d). **No modeling
effort changes this; only ≥30–50 failures and richer signals do.**

## 3. What V2 ships instead — the failure-window lookup card

Per-truck, per-week: tier (calibrated prob) + active channels → evidence state → scheduling window.
(Full CSV: `V2_program/analysis/econ/failure_window_matrix.csv`. Leads vs t_end/JCOPENDATE;
bootstrap 95% CI on the median; **retrospective; NOT a countdown clock**.)

| Evidence state | n | Median lead | Range | CI (median) | Action / scheduling window |
|---|---|---|---|---|---|
| **A2 cascade fired** | 4 | **66.5 d** | 28–91 | [28, 91] | Battery-first inspection in **14–30 d** (min lead 28 d — tight; prioritize) |
| **Persistence-terminal ∧ RED** | 10 | 206.5 d | 77–392 | [126, 284] | Planned electrical inspection in 14–28 d; month-priority if A1 corroborates |
| **RED, no channel yet** | 10* | 206.5 d* | 77–392 | [128, 273] | Monitor ↑ cadence; inspect within 4–8 wk or next service. *Retrospectively identical truck set to the row above (all RED-failed eventually fired persistence); in deployment this state precedes channel fire and the true horizon may be longer |
| AMBER, no channel | 0 | no data | — | — | Next service ≤90 d; promote on H1+H5 co-fire. (0 failed scored AMBER OOF — empirically empty state) |
| GREEN, channel later fires | 3 | 160 d | 28–168 | [28, 168] | Routine schedule until a channel fires (3 of 4 GREEN-failed were recovered this way) |
| Silent >30 d while RED/AMBER | 2 | — | — | — | **Ops check within 72 h** — transmission health is itself the signal (VIN8/9_F class; note 5 NF are also SMA-dead — silence ≠ failure) |

With the V2 heuristic layer (D4), **H2 persistent-RED dwell** (10/14 recall, median 116 d lead,
0.19 NF ep/truck-yr) becomes the walking trigger that moves a truck from "RED, monitoring" to
"inspect in 2–4 wk" — the state machine D7 formalizes.

## 4. Compliance with the V2 requirements (and the one substitution)

| Requirement | V2 delivery |
|---|---|
| Predicted RUL | **Substituted** — scheduling window per evidence state (above). A day-count RUL would be fabricated precision; the program proves it loses to a constant by 10–13× |
| Confidence interval | Bootstrap 95% CI on each state's median lead, with n displayed |
| Prediction uncertainty | Tier probabilities calibrated (slope 0.86, Brier 0.124); horizon validity bounded at 10 wk; per-state n of 2–10 stated plainly |
| Risk category | GREEN/AMBER/RED (pre-registered thresholds 0.35/0.55) |
| Supporting evidence | Per-alert card: archetype, active channels, feature drivers, fleet-relative percentiles (Layer 4) |
| No fixed fleet averages | Windows are conditioned on the truck's own evidence state, not population age |
| No deterministic outputs | Every output carries CI + n + retrospective caveat |
| No overstated confidence | The blind spot (VIN9_F class) and the empty AMBER state are documented, not hidden |

## 5. Governance that keeps it honest

- Weekly re-scoring; any window statement expires after 4 weeks without re-evaluation.
- The 4 chronic NF firers (VIN2/5/8/15_NF) are the **prospective watchlist**: each is either a
  future save (validates the system) or a measured FP cost (calibrates it). Either outcome is data.
- Refit triggers: ≥5 new failure labels, or calibration drift (slope outside [0.5, 2]), or PSI > 0.2
  on any modal feature — always under the full nested + admissibility protocol.
- Upgrade path to true VIN-specific RUL: n_failed ≥ 30–50 **and** a current channel (or triggered
  high-rate VSI) **and** one prospective validation quarter. Until all three exist, any RUL number
  finer than these windows is theater.
