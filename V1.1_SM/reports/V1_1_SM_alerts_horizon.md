---
title: "V1.1 SM — X3 Validated Alert Rules + X4 Prequential Horizon (Frozen Model)"
status: complete
created: "2026-06-10"
---

# V1.1 Starter Motor — Alerts (X3) and Horizon (X4)

Fleet: 34 SM trucks (14 failed + 20 NF). Layer-1 model context: nested-LOVO AUROC
0.9321 (X2, `V1_1_SM_experiment_results.md`), frozen 4-feature modal winner
`vsi_withinwk_std_ratio_30d_w`, `rest_vsi_p05_delta90`, `vsi_range_trend`,
`dip_depth_last90_delta`. Seed 42 throughout. SMA-dead cohort (VIN8_F, VIN9_F +
VIN10/11/12/13/20_NF) masked on all crank channels.

Scripts / outputs:

| Item | Path |
|---|---|
| X3 script | `STARTER MOTOR/V1.1/src/V1_1_SM_alerts.py` |
| X3 per-VIN validation | `STARTER MOTOR/V1.1/results/V1_1_SM_alert_validation.csv` |
| X3 sensitivity sweep | `STARTER MOTOR/V1.1/results/V1_1_SM_alert_sensitivity.csv` |
| X3 combined policy | `STARTER MOTOR/V1.1/results/V1_1_SM_alert_policy.csv` |
| X4 script | `STARTER MOTOR/V1.1/src/V1_1_SM_horizon.py` |
| X4 horizon curve | `STARTER MOTOR/V1.1/results/V1_1_SM_horizon_curve.csv` |

---

## 1. X3 — Persistence rule, LOVO-validated

Rule (frozen from E3, never retuned): causal within-week VSI-std ratio
(trailing-4-wk mean of weekly `vsi_drive_std` / expanding mean) above the
**training-fold-only** NF p90 envelope (end-aligned week-of-life positions
−12..−1) in **≥4 of the last 12 weeks**. 34-fold LOVO: the held-out truck never
contributes to its own envelope.

### Headline — out-of-fold vs in-sample

| Metric | In-sample screen (E3) | LOVO-validated | Degradation |
|---|---|---|---|
| Recall (end-of-history) | 13/14 | **13/14** | none |
| NF false positives | 2/20 | **4/20** | FP rate doubled (0.10 → 0.20) |

Honest read: recall holds perfectly out-of-fold (the only miss is VIN9_F, an A4
silent / SMA-dead truck with 3/12 weeks above — one short of firing). The
specificity claim was optimistic: removing each NF truck from its own envelope
adds **VIN5_NF and VIN8_NF** (5/12 and 4/12 weeks above) to the in-sample
false-firers VIN2_NF (12/12) and VIN15_NF (4/12). 4/20 NF fire at end of history.

A second, larger honest negative: as a **deployed weekly walking alarm** (each
week scored "as if today were end-of-life"), **all 20/20 NF trucks enter the
fire state at least once** in their history, spending on average **31.4%** of
evaluable weeks in-fire (range 0.10–0.75; worst VIN15_NF 0.75, VIN2_NF 0.73).
The rule is only useful as a *terminal-state* check ("is the alarm active now,
and has it persisted?"), not as a first-crossing pager. Leads below therefore
use the **terminal episode** (the contiguous fire run still active at t_end) —
the deployable failure lead — with first-ever fire shown for transparency.

### Per-VIN persistence leads (failed trucks, terminal episode)

| VIN | wks above /12 | fires | terminal start | lead vs t_end (d) | lead vs JCOPENDATE (d) | first-ever fire | first lead (d) | episodes |
|---|---|---|---|---|---|---|---|---|
| VIN10_F | 12 | yes | 2025-08-04 | 147 | 147 | 2025-02-10 | 322 | 4 |
| VIN11_F | 12 | yes | 2025-02-24 | 266 | 266 | 2025-02-24 | 266 | 1 |
| VIN12_F | 12 | yes | 2025-07-28 | 126 | 126 | 2025-07-28 | 126 | 1 |
| VIN13_F | 12 | yes | 2025-01-06 | 301 | 301 | 2025-01-06 | 301 | 1 |
| VIN14_F | 12 | yes | 2025-03-17 | 245 | 245 | 2024-09-16 | 427 | 2 |
| VIN1_F | 4 | yes | 2025-06-23 | 84 | 156 | 2024-12-16 | 273 | 2 |
| VIN2_F | 5 | yes | 2025-09-22 | 77 | 77 | 2025-09-22 | 77 | 1 |
| VIN3_F | 12 | yes | 2025-06-30 | 168 | 168 | 2025-06-30 | 168 | 1 |
| VIN4_F | 6 | yes | 2025-06-30 | 28 | 125 | 2025-06-30 | 28 | 1 |
| VIN5_F | 12 | yes | 2024-09-30 | 392 | 424 | 2024-09-30 | 392 | 1 |
| VIN6_F | 12 | yes | 2025-05-19 | 168 | 168 | 2025-02-03 | 273 | 2 |
| VIN7_F | 12 | yes | 2025-02-10 | 266 | 266 | 2025-02-10 | 266 | 1 |
| VIN8_F | 12 | yes | 2025-07-14 | 98 | 135 | 2025-07-14 | 98 | 1 |
| VIN9_F | 3 | **no** | — | — | — | (2024-05-13, sub-threshold history fire) | — | 1 |

Median lead among the 13 firers: **168 d vs t_end and 168 d vs JCOPENDATE**
(JCOPENDATE adds the silent-gap days for VIN1/4/5/8/9_F only). Minimum lead 28 d
(VIN4_F vs t_end; 125 d vs JCOPENDATE). These long leads mean the rule is a
*condition flag*, not a failure-imminent timer — consistent with V1's finding of
no short-fuse lead-time channel.

### Parameter sensitivity (m-of-12, evaluated inside training folds only)

| m | mean train recall | mean train NF FP rate |
|---|---|---|
| 3 | 0.966 | 0.206 |
| 4 (frozen) | 0.901 | 0.109 |
| 5 | 0.861 | 0.105 |

The frozen m=4 sits at the knee; m=3 buys ~1 extra recall fold for ~2× the FP
rate, m=5 saves almost nothing. The rule is not perched on a cliff — verdict:
parameter-stable.

## 2. X3 — A1 crank-burst alarm (physics prior, cohort-masked)

Daily failed-cranks + retries-within-120 s, 7-d rolling sum S7; alarm = S7 >
own-first-half mean + 3 sd (absolute floor S7 ≥ 3) for ≥2 consecutive days;
evaluated on the second half only. SMA-dead trucks excluded (VIN8_F, VIN9_F + 5 NF).

Failed VINs fired (4/12 applicable):

| VIN | archetype | first alarm | lead vs t_end (d) | lead vs JCOPENDATE (d) | episodes |
|---|---|---|---|---|---|
| VIN10_F | A1 solenoid | 2025-07-22 | 160 | 160 | 4 |
| VIN11_F | A3 volatility | 2025-05-22 | 179 | 179 | 1 |
| VIN12_F | A3 volatility | 2025-07-26 | 128 | 128 | 1 |
| VIN1_F | A1 solenoid | 2025-04-08 | 160 | 232 | 2 |

Catches 2/3 of the A1 solenoid archetype (VIN14_F's bursts predate its second
half / stay under the floor) plus 2/3 of A3. False-alarm burden: **8/15
applicable NF trucks fire; 22 episodes over 14.5 truck-years = 1.52
episodes/truck-year** — roughly one shop-visit-grade alarm per truck per 8
months. That is too noisy as a standalone pager; usable only as a corroborating
channel on trucks already AMBER/RED.

## 3. X3 — A2 battery-cascade triple detector (causal)

Fire requires all three, causally at the scoring week: rest-VSI step ≤ −0.5 V
(SNR ≥ 2) **and** drive-VSI step ≥ +0.3 V (SNR ≥ 2) within ±8 weeks of each
other, **and** dip-depth widening > +1 V (last 60 d vs earlier, ≥10 events each).

| VIN | archetype | fire week | lead vs t_end (d) | rest step (V) | drive step (V) | dip widen (V) |
|---|---|---|---|---|---|---|
| VIN13_F | A2 battery | 2025-09-01 | 63 | −1.80 | +0.63 | +1.16 |
| VIN14_F | A2 battery | 2025-10-20 | 28 | −2.51 | +0.61 | +1.23 |
| VIN3_F | A2 battery | 2025-09-15 | 91 | −1.80 | +0.45 | +1.11 |
| VIN6_F | A2 battery | 2025-08-25 | 70 | −3.00 | +0.42 | +2.08 |

- Catches **4/5 of the A2 battery archetype** (miss: VIN2_F — its cascade never
  produces a qualifying paired drive-step before t_end). Median lead 66.5 d.
- **NF false alarms: 0/20.** Perfectly clean on this fleet.
- **Battery-replacement confirmation: PASS.** All five NF trucks with E5
  rest-VSI steps UP (VIN3/5/12/17/18_NF) do **not** fire — the detector's
  sign requirements correctly separate replacement (rest up) from cascade
  (rest down + drive up + dips widening).

## 4. X3 — Combined alert policy (Layer-1 tier + persistence + A1 + A2)

Failed trucks — first-firing channel:

| VIN | tier | first channel | first fire | lead vs t_end (d) | lead vs JCOPENDATE (d) |
|---|---|---|---|---|---|
| VIN10_F | RED | A1 crank burst | 2025-07-22 | 160 | 160 |
| VIN11_F | RED | persistence | 2025-02-24 | 266 | 266 |
| VIN12_F | RED | A1 crank burst | 2025-07-26 | 128 | 128 |
| VIN13_F | RED | persistence | 2025-01-06 | 301 | 301 |
| VIN14_F | RED | persistence | 2025-03-17 | 245 | 245 |
| VIN1_F | GREEN | A1 crank burst | 2025-04-08 | 160 | 232 |
| VIN2_F | RED | persistence | 2025-09-22 | 77 | 77 |
| VIN3_F | GREEN | persistence | 2025-06-30 | 168 | 168 |
| VIN4_F | GREEN | persistence | 2025-06-30 | 28 | 125 |
| VIN5_F | RED | persistence | 2024-09-30 | 392 | 424 |
| VIN6_F | RED | persistence | 2025-05-19 | 168 | 168 |
| VIN7_F | RED | persistence | 2025-02-10 | 266 | 266 |
| VIN8_F | RED | persistence | 2025-07-14 | 98 | 135 |
| VIN9_F | GREEN | **NONE** | — | — | — |

**13/14 failed trucks fire at least one channel** (persistence first on 10, A1
first on 3; A2 never first but corroborates 4 and is the only short-fuse
(~1–3 month) signal). Median combined first-fire lead **168 d** vs both anchors.
The one full miss, VIN9_F, is the A4-silent + SMA-dead + GREEN-tier truck —
invisible on every layer; that is the irreducible blind spot of this dataset.
Note the three GREEN-tier saves (VIN1/3/4_F): alert channels recover 3 of the 4
Layer-1 tier misses.

NF false-alarm burden (channels counted = end-state persistence + A1-any + A2 +
AMBER/RED tier): **10/20 NF trucks are completely clean (zero channels)**;
6 trucks show 1 channel, 2 show 2, and 2 (VIN2_NF, VIN5_NF) show 3. The
repeat offenders VIN2_NF / VIN5_NF / VIN8_NF / VIN15_NF dominate both the
persistence FPs and the A1 episode count — plausibly genuinely degrading
electrical systems that had not failed by end of observation (right-censoring),
but counted as false alarms here, honestly.

## 5. X4 — Prequential horizon of the frozen 4-feature model

Method: per VIN, weekly cache + events truncated at its own cut = t_end − 7k
days (t_end = max raw timestamp, the `days_before_t_end` anchor;
`V1_SM_data_quality.csv`); the 4 frozen features recomputed causally on
truncated data (90-d / 13-wk / L40 windows re-anchored at the cut;
battery-step re-baseline applied only when the E5 step week precedes the cut;
SMA-dead cohort masking preserved); then LOVO with train-median impute →
StandardScaler → RidgeClassifier(alpha=1.0), **no re-screening**. Feature code
replicated verbatim from `V1_1_SM_features.py` (it cannot be imported — no
main-guard) and verified by an exact k=0 reconciliation: max|diff| ≤ 4.4e-16 on
all 4 features, zero NaN-pattern mismatches; k=0 AUROC 0.9357 = X2's non-nested
modal-subset figure exactly. Spec range k=0..16; walk-back extended to k=26
(G3's range) solely to adjudicate decay-to-chance.

| k (wks) | AUROC | 95% CI | recall @ spec 18/20 | n usable (F) |
|---|---|---|---|---|
| 0 | 0.936 | [0.840, 0.989] | 10/14 (0.714) | 34 (14) |
| 1 | 0.929 | [0.823, 0.991] | 0.714 | 34 (14) |
| 2 | 0.921 | [0.823, 0.992] | 0.714 | 34 (14) |
| 3 | 0.921 | [0.800, 0.996] | 0.786 | 34 (14) |
| 4 | 0.893 | [0.779, 0.979] | 0.643 | 34 (14) |
| 5 | 0.904 | [0.787, 0.986] | 0.643 | 34 (14) |
| 6 | 0.843 | [0.702, 0.970] | 0.643 | 34 (14) |
| 7 | 0.850 | [0.696, 0.973] | 0.714 | 34 (14) |
| 8 | 0.857 | [0.695, 0.966] | 0.714 | 34 (14) |
| 9 | 0.818 | [0.616, 0.958] | 0.571 | 34 (14) |
| **10** | **0.768** | [0.586, 0.921] | 0.357 | 34 (14) |
| 11 | 0.704 | [0.517, 0.868] | 0.286 | 34 (14) |
| 12 | 0.732 | [0.556, 0.887] | 0.286 | 34 (14) |
| 13 | 0.657 | [0.453, 0.833] | 0.429 | 34 (14) |
| 14 | 0.625 | [0.428, 0.827] | 0.429 | 34 (14) |
| 15 | 0.773 | [0.580, 0.913] | 0.538 | 33 (13) |
| 16 | 0.735 | [0.533, 0.905] | 0.538 | 33 (13) |
| 17–26 (extended) | 0.52–0.71 | all CIs include 0.5 | 0.17–0.50 | 32–33 |

- **k\* = 10 weeks** (largest k with AUROC ≥ 0.75 sustained from k=0; the
  isolated k=15 blip at 0.773 coincides with the shortest-history failed truck
  dropping out and is not counted). Identical to G3's k\*=10 on the screening
  features — the frozen model neither gained nor lost horizon.
- **Decay verdict: CONFIRMED, no leak signature.** Head (k≤2) mean 0.929 →
  far-tail (k=23..26) mean 0.592, every tail bootstrap CI includes 0.5, recall
  at the operating point collapses from 10/14 to 2–6/14. The score is
  time-locked to failure. Note honestly: at k=13–16 the curve still hovers at
  0.63–0.77 (CIs spanning 0.5) — decay is gradual, reaching chance only past
  ~k=20, exactly as G3's curve did; this reflects slow-burn degradation
  signal plus small-n noise, not leakage.
- Operating-point caveat: even at k=0, the rigid 18/20-specificity threshold
  yields only 10/14 recall on raw LOVO decision values (X2's headline 13/14 at
  75% specificity used per-fold Youden thresholds). The 18/20 point is the
  apples-to-apples V1-restated comparison, and it degrades smoothly with k.

## 6. Ship / don't-ship per channel

| Channel | Verdict | Basis |
|---|---|---|
| Persistence (≥4-of-12 vs NF p90) | **SHIP — as terminal-state condition flag only** | 13/14 recall LOVO-validated, but NF FP doubled to 4/20 and every NF truck visits the fire state (31% of weeks). Gate it behind AMBER/RED tier; never page on first crossing. |
| A1 crank burst | **DON'T SHIP standalone; ship as corroborator** | Only 4/12 applicable failed fired; 1.52 FP episodes/truck-year is pager-fatigue territory. As a tier-gated corroborator it recovered GREEN-tier VIN1_F. |
| A2 battery cascade | **SHIP** | 4/5 of the battery archetype, 0/20 NF, battery replacements provably don't fire, and it is the only ~1–3-month-fuse signal in the system. |
| Layer-1 frozen model + horizon | **SHIP with 10-week claim** | AUROC ≥ 0.75 sustained to k\*=10 weeks, clean decay to chance (no leak), k=0 reconciliation exact. Claim "risk score valid ~2.5 months out", not more. |

Known blind spot to state in any deployment doc: A4-silent/SMA-dead trucks
(VIN9_F pattern) fire nothing on any layer.
