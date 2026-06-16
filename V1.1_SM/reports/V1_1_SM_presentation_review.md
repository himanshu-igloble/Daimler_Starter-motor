---
title: "V1.1 SM Presentation Review — Adversarial Fact-Check of Technical & Business Decks"
status: "complete"
created: "2026-06-10"
---

# V1.1 SM Presentation Review (Data Correctness + Honesty)

Reviewer protocol: every number, count, VIN reference, and definitive statement in both decks was
extracted programmatically (python-pptx, all shapes/tables) and checked against ground truth in
priority order: `V1.1/results/*.csv|json` > `V1.1/discovery/out/*` > reports. Chart-input constants
were audited in the two build scripts (`build_sm_technical_presentation.py`,
`build_sm_business_presentation.py`). Decks were NOT modified.

## Verdict

| Deck | Numbers accuracy | Framing honesty | Overall |
|---|---|---|---|
| **SM_Predictive_Maintenance_V1.1.pptx** (technical, 23 slides) | **1 WRONG (chart), ~5 MINOR** — every quoted number traced to source | **High** — restatement story, VIN9_F blind spot, suppressor, A4 ceiling, both operating points all disclosed | **PASS with one mandatory chart fix** |
| **SM_Business_Summary_V1.1.pptx** (business, 5 slides) | **0 WRONG, ~4 MINOR** | **Medium-high** — one operating-point pairing issue (13/14 recall juxtaposed with 2/20 RED-tier FP) | **PASS with one framing fix** |

AUROC reconciliation note: recomputing AUROC from `V1_1_SM_nested_lovo_predictions.csv` `prob`
column gives 0.9339, not 0.9321 — this is a CSV rounding artifact: VIN9_F (0.4008) ties VIN18_NF
(0.4008) at 4 d.p.; resolving the tie in the NF's favour yields exactly 0.9321 (0.9339 − 0.5/280).
The deck's 0.9321 matches the canonical `model_spec.json`/`gates.json` value. Not a finding.

---

## 1. WRONG findings

### W1 — Confusion-matrix chart, technical slide 10: off-diagonal cells transposed vs axis labels

`chart_confusion()` builds `matrix = [[TP, FP], [FN, TN]]` with y-labels (Actual Failed, Actual
Healthy) and x-labels (Predicted Failed, Predicted Healthy). Verified in the rendered PNG embedded
in the deck: the cell **(Actual Failed, Predicted Healthy) shows "FP 5"** and **(Actual Healthy,
Predicted Failed) shows "FN 1"**. By definition those cells are FN and FP respectively. As drawn,
the chart says 5 failed trucks were predicted healthy — i.e. recall 9/14 — contradicting the
deck's own 13/14 and the ground truth (predictions CSV: TP 13, FN 1 = VIN9_F_SM; FP 5 = VIN5/20/2/10/15_NF;
TN 15). The four numbers and their TP/FP/FN/TN acronyms are individually correct; their
**placement against the axes is wrong**. Fix: `matrix = [[TP, FN], [FP, TN]]` with labels
`[['TP 13','FN 1'],['FP 5','TN 15']]`.

No other WRONG finding in either deck.

---

## 2. Claims table — technical deck (every materially checkable claim)

| # | Claim | Slide | Source | Verdict |
|---|---|---|---|---|
| 1 | Fleet 34 VINs (14F + 20NF) | 1,2,3 | predictions CSV (34 rows, 14 failed) | VERIFIED |
| 2 | Nested-LOVO AUROC 0.9321 / 93.2% | 2,6,8,10,22 | model_spec `headline.nested_auroc` | VERIFIED |
| 3 | 95% CI [0.811, 0.986] | 2,8,10,20,22 | model_spec `[0.8107, 0.9861]` | VERIFIED |
| 4 | Permutation p = 0.005, N=200 floor, 0/200 shuffles reach 0.9321 | 2,6,10 | model_spec, experiment report (p = 1/201) | VERIFIED |
| 5 | Recall 13/14 @ Youden, spec 15/20; TP 13 FP 5 FN 1 TN 15 | 2,10 | model_spec per_fold_threshold_metrics; recomputed from CSV `pred_foldthr` | VERIFIED |
| 6 | RED tier 10/14 @ 18/20 | 2,10,20 | model_spec tier_counts; recomputed from CSV `tier` | VERIFIED |
| 7 | Calibration slope 0.86, Brier 0.124, CITL −0.062, in [0.5, 2] | 2,10,22 | gates G3 (0.86 / 0.124 / −0.0619) | VERIFIED |
| 8 | F1 0.812 / MCC 0.669 | 10 | model_spec (0.8125 / 0.6691) | VERIFIED |
| 9 | Selection optimism +0.0036 (non-nested 0.9357); V1 hid +0.0285 | 2,6,10 | model_spec comparisons; 0.9214−0.8929 | VERIFIED |
| 10 | V1 reported 0.9214 → restated 0.8929 (recall 12/14 @ 18/20) | 2,6,10,22 | model_spec `v1_restated_baseline`; B/C audits | VERIFIED |
| 11 | Ablation: nested on V1-era features 0.8429; gain +0.089 | 6 | model_spec `ablation_nested_v1era_22feats` | VERIFIED |
| 12 | Jackknife 0.927–0.951, range 0.024, std 0.007 | 10 | gates G5 (0.9269/0.9511/0.0242/0.007) | VERIFIED |
| 13 | Leak ceilings: n_weeks AUROC 0.952, t_start 0.893 | 6,22 | A_data_quality_audit.md lines 105, 109 | VERIFIED |
| 14 | vsi_dominant_freq collapses 0.748 → 0.525 under fixed-window control | 6 | experiment report §3 | VERIFIED |
| 15 | G1 L40 control drop 0.0000, matrices bit-identical | 6,9 | gates G1 | VERIFIED |
| 16 | G6: 0 banned tokens | 6 | gates G6 | VERIFIED |
| 17 | "AUROC holds to k=10, collapses to chance at k=11" | 6 | discovery G3 curve (0.857 at k=10, 0.536 at k=11) | VERIFIED but see M1 — this is the **screening-feature** curve; the frozen-model curve (slide 16) is 0.704 at k=11 |
| 18 | Coefs +0.886 / −0.270 / −0.414 / +0.141; suppressor r=+0.82 | 9 | explanations.json coefficients (0.8862/−0.2704/−0.4139/0.1409; r=0.821) | VERIFIED |
| 19 | withinwk univariate AUROC 0.921; 10-candidate pool; core pair 34/34; 3 distinct subsets; retry-burst + crank-tail rejected 34/34 | 9 | admissibility CSV, gates G4, fold-winners CSV | VERIFIED (but see M4: G4 strict FAIL not disclosed) |
| 20 | Battery-step re-baseline: VIN8_F + 5 NF | 9 | experiment report §1 (VIN3/5/12/17/18_NF) | VERIFIED |
| 21 | Per-VIN table: all 14 OOF P, Recal P, tier, archetype, first channel, leads | 12 | predictions CSV + alert_policy CSV + E2 archetypes CSV — all 14×7 cells match (incl. VIN9_F recal 0.224, the corrected value) | VERIFIED |
| 22 | VIN9_F miss: prob 0.401 vs thr 0.406, A4, SMA-dead, 142-d gap | 10,12 | CSV (0.4008 vs inner_youden 0.4055), E2 (silent_gap 142, sma_dead True) | VERIFIED |
| 23 | VIN8_F: V1 0.303 → OOF 0.521, recal 0.716, RED; pers +98 d; 37-d gap | 2,12,14 | B audit (0.3031), CSV, alert CSVs, E2 | VERIFIED |
| 24 | NF fleet 16 GREEN / 2 AMBER / 2 RED; RED = VIN5_NF 0.96, VIN20_NF 0.62; AMBER = VIN2_NF 0.45, VIN10_NF 0.43 | 2,13,22 | CSV (0.9575/0.6228/0.4517/0.4349) | VERIFIED |
| 25 | Persistence: 13/14, 4/20 NF (VIN2/5/8/15_NF), walking alarm visits 20/20 NF, 31% of weeks | 8,13,15,20 | alert_validation CSV; report 31.4% (recomputed 31.4%) | VERIFIED |
| 26 | A2: 4/5 archetype, 0/20 NF, median lead 66.5 d; battery replacements don't fire | 8,15 | alert_validation (fires VIN13/14/3/6_F, miss VIN2_F; median of 63/28/91/70 = 66.5) | VERIFIED |
| 27 | A1: 4/12 applicable fire; 1.52 FP eps/truck-yr; rescued VIN1_F | 8,15 | alert_validation (recomputed 22 eps / 14.5 yr = 1.517) | VERIFIED |
| 28 | Combined: 13/14 fire ≥1 channel; persistence first ×10, A1 first ×3; median lead 168 d (min 28, VIN4_F); 10/20 NF fully clean; 6/2/2 channel counts | 15 | alert_policy CSV (recomputed median of 13 leads = 168) | VERIFIED |
| 29 | Horizon: k=0 0.9357 (reconciles to X2), k=10 0.768, k=11 0.704, tail k=23–26 mean 0.592, CIs span 0.5; k\*=10 | 16 | horizon_curve CSV (0.9357/0.7679/0.7036/mean 0.5917) | VERIFIED |
| 30 | k=13–16 hover 0.63–0.77 | 16 | CSV: 0.625–0.773 | MINOR (0.625 rounds to 0.63 only generously) |
| 31 | Survival closed: ranking 0.586 vs 0.893; RUL MAE 576 d vs constant 44 d; hazard ~0.005/wk | 8,19,22 | F_survival_analysis.md (0.586/0.893; 576.1/44.4; 0.0053) | VERIFIED |
| 32 | Deep closed: 235×–6,275× over budget; 43-param LSTM seed-unstable | 19 | G_sequence_representation.md | VERIFIED |
| 33 | Probes saturate ~0.89–0.93 | 19 | G report says ≈0.89–0.92 (comparison report says 0.89–0.93) | MINOR (upper bound +0.01 vs root source) |
| 34 | GED: zero GED2 in all 14 failed SM trucks | 5,19 | V1 final report / memory | VERIFIED |
| 35 | Data: 106,445,161 rows; 2,636 truck-weeks; 20,471 events; 5 s / ~0.2 V | 5,19 | V1_SM_final_report.md; C audit | VERIFIED |
| 36 | KT: durations +3% not +48%; >5% lifetime threshold refuted; last-90-d AUROC 0.74 | 5 | V1_SM_final_report.md §KT | VERIFIED |
| 37 | Archetypes: A1 3 / A2 4(+VIN14) / A3 3 / A4 4; 5/14 silent 32–142 d; 7/34 SMA-dead | 4 | E2 CSV (gaps 32/37/72/97/142; SMA-dead 2 F + 5 NF) | VERIFIED |
| 38 | VIN6_F card: 2.07×, −3.15 V, +4.12 V, +0.200 V/wk; contributions +1.202/+0.957/+0.579/−1.084; counterfactual 2.07→1.01; A2 fired 70 d | 14,18 | explanations.json VIN6_F card; alert_validation | VERIFIED |
| 39 | V1 had no alert channel (trend battery fired on 90% of healthy trucks) | 2,15 | comparison report / V1 final (NF FP 90%) | VERIFIED |
| 40 | VSI setpoints 27.6–28.2 V; persistence ≥4-of-12 vs NF p90; A2 triple definition; SMA-dead <1% coverage | 23 | A audit; alerts report | VERIFIED |

## 3. Claims table — business deck

| # | Claim | Slide | Source | Verdict |
|---|---|---|---|---|
| 1 | "13 of 14 failures caught — flagged by risk score or alert" | 1,2,3 | Youden 13/14 AND combined alerts 13/14 | VERIFIED as stated; see H1 pairing issue |
| 2 | "~10 weeks early-warning window / typically within ~2.5 months of failure" | 1,2,3,5 | horizon k\*=10 wk | VERIFIED number; MINOR framing (M6) — horizon = detection validity, not guaranteed advance notice; 10 wk = 2.3 months |
| 3 | "False alarms (RED tier): 2 of 20 — both show real electrical stress" | 1,3 | tier counts (2/20 RED: VIN5_NF, VIN20_NF) | VERIFIED count, operating point labeled; "both show real electrical stress" is over-firm for VIN20_NF (M7) |
| 4 | "13 of 14 past failures ranked high before they failed" | 2 | Youden 13/14 | MINOR — "ranked high" unlabeled; at the tier level only 10/14 are RED (M5) |
| 5 | Battery-cascade: ~9-week median lead, zero false alarms, ignores battery replacements | 2,3 | 66.5 d (=9.5 wk), 0/20, E5-step trucks don't fire | VERIFIED (lead rounds down) |
| 6 | Fleet today 16 LOW / 2 WATCH / 2 HIGH; RED = VIN5_NF + VIN20_NF; AMBER = VIN2_NF + VIN10_NF | 3,5 | predictions CSV | VERIFIED |
| 7 | "One more failure caught (incl. its worst miss) vs first-generation system" | 3 | 13/14 vs V1 restated 12/14; VIN8_F | VERIFIED (vs restated baseline; technical deck explains the restatement) |
| 8 | ~4 of 14 invisible; no failure dates; every timing model lost to a constant; 7 of 34 no crank data; only 14 failure examples; 5-s sampling kills brush-wear (2–4 month) channel | 4 | E2, F survival, A audit, D physics (60–120 d) | VERIFIED |
| 9 | "No new sensors needed — runs on existing CAN bus data" | 2 | data inventory | VERIFIED |

## 4. Chart-constant audit (build scripts)

| Chart | Script constants | Ground truth | Verdict |
|---|---|---|---|
| AUROC progression (tech S6) | 0.9214 / 0.8929 / 0.8429 / 0.9321 | model_spec comparisons | VERIFIED |
| Ridge metrics bars (tech S10) | 93.21 / 13/14 / 15/20 / 0.812 / 0.86 | model_spec | VERIFIED |
| **Confusion matrix (tech S10)** | TP 13, FP 5, FN 1, TN 15 | values correct; **layout WRONG (W1)** | **WRONG** |
| Feature coefficients (tech S9) | +0.8862 / −0.4139 / −0.2704 / +0.1409 | explanations.json | VERIFIED |
| Archetype split (tech S4) | [3, 5, 3, 4]; VIN14_F counted in A1 and A2, disclosed in chart title; VIN lists correct | E2 CSV | VERIFIED (sum 15 > 14 explicitly explained) |
| Horizon curve (tech S16) | read live from `V1_1_SM_horizon_curve.csv`; K_STAR 10, k0 0.9357, tail 0.592 | CSV | VERIFIED |
| Alert leads (tech S15) | 14 hardcoded (vin, lead, channel) tuples; VIN9_F = 0/"NONE" | alert_policy CSV — all 14 match | VERIFIED |
| NF tiers (tech S13) | 16/2/2 + VIN annotations | predictions CSV | VERIFIED |
| Fleet risk (biz S3) | [16, 2, 2] | predictions CSV | VERIFIED |
| Before/after (biz S3) | bar heights 0.93/1.0/0.86/1.0 (symbolic), labels 13/14, ~10-wk, calibrated, battery-first | sources above | VERIFIED (heights decorative) |
| What-works (biz S4) | scores [93, 93, 100, 0, 0]; labels 13/14 ranked high, 13/14 fire alert ~10-wk window, 0 FA cascade | sources above | VERIFIED numbers; "13/14 fire an alert, ~10-wk window" conflates alert coverage (median lead 168 d) with the horizon (M8) |
| KPI tiles (biz S1) | 13 of 14 / ~10 weeks / 2 of 20 (RED tier) / 34 trucks | sources above | VERIFIED individually; see H1 |

## 5. Operating-point-mixing assessment

- **Technical deck: CLEAN.** Both pre-registered operating points are stated side by side with
  their full trade (S2 tiles, S10 scorecard row "choose per maintenance economics", S20 limitation
  row "no operating point dominates V1 everywhere"). Youden (13/14 @ 15/20) and RED tier
  (10/14 @ 18/20) are never cross-paired.
- **Business deck: ONE PAIRING ISSUE (H1).** Slide 1 KPIs and the slide-3 "headline results" table
  juxtapose "13 of 14 caught" (Youden / combined-alert operating point) with "2 of 20 false alarms
  (RED tier)". Each number is individually correct and the FP tile is labeled "(RED TIER)", but
  the juxtaposition implies a single system achieving 13/14 recall at 2/20 FP. The honest pairs
  are: Youden 13/14 @ **5/20** FP; RED tier **10/14** @ 2/20; combined alert policy 13/14 with
  **10/20** NF trucks showing ≥1 channel/tier alarm. No single sentence in the business deck
  states this trade-off.

## 6. Honesty assessment

**Technical deck — honest (9/10).** Discloses: the V1 restatement before claiming the win (S6,
with optimism deltas and the ablation isolating feature-vs-protocol gain); the VIN9_F/A4 blind
spot on four separate slides; the suppressor coefficient as non-physics; the persistence rule's
FP doubling and walking-alarm pathology; A1 as corroborator-only; no RUL ships (with the
576-vs-44 proof); leak-axis correlations above tripwire (S20) with the defense stated; CI width
and n=34 limits. Two omissions worth fixing: (a) **G4 winner-stability gate strictly FAILS**
(modal subset 14/34 < 17/34 criterion; gates.json `"pass": false`) — S6/S9 present only the
favorable substance ("core pair 34/34, 3 subsets") without noting the strict-criterion FAIL;
(b) the comparison report's disclosure that **V1 nominally caught VIN9_F (P=0.4825)** which V1.1
now misses is absent — "+1 recall vs restated V1" is true, but the swap (gained VIN8_F, lost
VIN9_F vs V1-as-reported) is not visible in the deck. Also M1: slide 6 quotes the discovery
screening curve ("chance at k=11" = 0.536) while slide 16 shows the frozen-model curve (0.704 at
k=11, chance past ~k=20) — both sourced, but the unlabeled switch reads as a contradiction.

**Business deck — honest with one structural caveat (7/10).** Strong "what it cannot do" slide
(no failure dates, ~4/14 invisible, data gaps with causes); never promises per-truck failure
dates; communication rule "quote tiers and the ~10-week window — never a failure date" is exactly
right. The H1 recall/FP pairing is the one material framing problem. Secondary wording: "ranked
high" (M5), "EARLY-WARNING WINDOW" header for a detection-validity horizon (M6), "both show real
electrical stress" where VIN20_NF's corroborating evidence is tier-only (SMA-dead, zero alert
channels) (M7).

## 7. Prioritized fix list

1. **(MUST) W1 — fix the confusion-matrix chart** in `chart_confusion()`: use
   `[[TP, FN], [FP, TN]]` so FN=1 sits under (Actual Failed, Predicted Healthy) and FP=5 under
   (Actual Healthy, Predicted Failed); rebuild the technical deck. As shipped, the chart visually
   claims 5 missed failures.
2. **(SHOULD) H1 — un-mix the business operating points**: on business slides 1 and 3 add one
   line, e.g. "13/14 caught at the recall-greedy point (5/20 healthy flagged); the RED-tier
   policy catches 10/14 at 2/20" — or quote a single consistent pair.
3. **(SHOULD) M1 — label the two horizon curves**: on technical S6, mark "chance at k=11" as the
   discovery-phase screening curve (G3, 0.536) and cross-reference S16's frozen-model curve
   (0.704 at k=11, chance past ~k=20) so the slides don't appear to contradict each other.
4. **(SHOULD) G4 disclosure**: add "G4 winner-stability: strict criterion FAIL (modal 14/34 due
   to a 14/14 k=3/k=4 tie); substantive stability strong (core pair 34/34, 3 subsets total)" to
   the S6 gates table — the deck currently omits the only failed gate.
5. **(NICE) wording precision**: A2 median lead is 66.5 d = **9.5 weeks** (write "~9–10 wk");
   10 weeks = **2.3 months** (keep "~2.5 months" only with the tilde); business "ranked high" →
   "flagged"; soften "both show real electrical stress" for VIN20_NF; note V1 nominally caught
   VIN9_F in the technical comparison takeaway; k=13–16 hover is 0.62–0.77.

---

## 8. Post-review fixes applied (2026-06-10)

All five items above were applied to the build scripts and both decks rebuilt
(`py -3 build_sm_*.py`); python-pptx read-back verified each change.

1. **W1 (MUST) fixed** — `chart_confusion()` now builds `[[TP, FN], [FP, TN]]`
   (TP 13 / FN 1 / FP 5 / TN 15); the regenerated PNG was extracted from the rebuilt deck and
   visually confirmed: (Actual Failed, Predicted Healthy) = FN 1, (Actual Healthy,
   Predicted Failed) = FP 5.
2. **H1 fixed** — business slide-1 tiles now self-label the operating points ("Catch-most
   setting — also flags 5 of 20 healthy trucks" / "Stricter RED-tier setting — catches 10 of 14
   failures"); slide-3 table pairs each number with its own setting and a key-takeaway line states
   the full trade explicitly (13/14 @ 5/20 vs 10/14 @ 2/20).
3. **M1 fixed** — tech slide 6 G3 row now says "Screening-feature curve … chance at k=11 (0.536)"
   with a cross-reference to the frozen final-model curve (0.704 at k=11); slide 16 carries a
   matching "curve identity" note.
4. **G4 disclosed** — a G4 row was added to the slide-6 gates table: strict modal criterion FAIL
   (14/34 < 17/34, k=3/k=4 tie) with the mitigation (core pair 34/34 folds, 3 subsets total);
   slide 9 selection text repeats the strict-FAIL disclosure.
5. **Wording** — "~9.5 wk (66.5 d)" replaces "~9 wk" everywhere (both decks); "~2.3 months (70 d)"
   replaces "~2.5 months"; business "ranked high" → "flagged"; VIN20_NF softened to "tier-only
   evidence (SMA-dead, no alert channel fired)" (tech S13) and "flagged on its risk score alone"
   (biz S4); the VIN9_F/VIN8_F recall swap vs V1-as-reported is now stated on tech slides 6 and 14;
   k=13–16 hover corrected to 0.62–0.77.

**Daily-risk dashboards embedded** (verified by the 2026-06-10 data audit; forecast-endpoint
graphs re-rendered): technical deck gains three "Daily-Risk RUL Views" slides (now S17–S19,
deck 23 → 26 slides) — VIN1_F_SM (how-to-read: curve breaks = no telemetry, 34-d real gap
2025-07-31 → 2025-09-02, 72-d hatched terminal silent gap, failure 2025-11-26, dotted
fleet-Weibull-anchored projection), VIN6_F_SM (full GREEN→RED cascade, A2 fired 70 d early) and
VIN1_NF_SM (healthy contrast, risk 0.07). Each carries the honest note that the daily RUL curve is
a fleet-Weibull-anchored illustration — the validated deliverable remains tier + ≤10-week horizon.
Tech S14 now mentions both views (weekly trajectory + daily view). Business deck stays at
5 slides: the decorative before/after chart on S3 was replaced by the VIN6_F daily-risk view with
a plain-language caption. All embeds are width-only (aspect 1.549 preserved, no stretching) and
existence-checked. Placeholder scan: clean on both decks.
