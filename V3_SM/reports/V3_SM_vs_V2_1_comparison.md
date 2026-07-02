---
title: "Starter Motor — V3 vs V2.1 Iteration Comparison & Honest Analysis"
status: "complete"
created: "2026-07-02"
program: "SM V3"
scope: "Compares the two most recent Starter Motor feature-hunt iterations (V2.1, V3) on the same 34-truck fleet, same frozen baseline, same locked gate. Includes a calibrated critical analysis."
sources: "STARTER MOTOR/V2.1/features/out/V2_1_gate_summary.json; STARTER MOTOR/V3/features/out/V3_gate_summary.json; STARTER MOTOR/V3/analysis/out/V3_validation.json"
---

# Starter Motor — V3 vs V2.1: Comparison & Honest Analysis

## 1. Purpose & scope

Both V2.1 (2026-06-22) and V3 (2026-07-01) are feature-hunt iterations on the **same 34-truck
SM fleet** (14 failed / 20 non-failed), against the **same frozen baseline** (modal-4:
non-nested LOVO AUROC **0.9357** / nested **0.9321**), scored by the **same locked gate**
(reconcile → E1 → E2 → E3). Both **rejected every candidate**. This document compares *what*
each tested, *why* things failed, and gives a deliberately skeptical read of *what was actually
established vs. what is merely plausible.* All numbers are drawn from the two `gate_summary.json`
files and `V3_validation.json`.

---

## 2. Headline comparison

| | **V2.1** (2026-06-22) | **V3** (2026-07-01) |
|---|---|---|
| Primary aim | Specificity / pager hunt (features a *secondary* screen, "expect HOLD") | **Pure feature-value investigation** |
| Baseline / reconcile | 0.9357 non-nested / 0.9321 nested ✓ | **Identical** 0.9357 / 0.9321 ✓ |
| Candidates | **3** (marginal refinements of known channels) | **7** (incl. the never-tested interaction class) |
| Gate | E1 (MW p≤0.10 ∧ AUROC≥0.60, |r|<0.85, proxy) → E2 (+0.01) → E3 nested | **Same gate, verbatim core** |
| Verdicts | **3 / 3 REJECT** | **7 / 7 REJECT** |
| E3 nested | null (no survivors) | null (no survivors) |
| Also shipped | Heuristic wins: A3 terminal-fix recall lever, A5 graded-RUL, H2 pager | Nothing deployable — closed feature space + new-data roadmap |
| Outcome | NO IMPROVEMENT; ceiling re-confirmed | NO IMPROVEMENT; ceiling re-confirmed |

---

## 3. Feature-level results

### V2.1 — marginal refinements of already-explored channels
| Feature | Type | E1 AUROC | MW p | E2 Δ | Failed on |
|---|---|---|---|---|---|
| z_cold_dip_delta90 | cold-start voltage dip (per-VIN z) | **0.728** | **0.048** ✓ | −0.0036 | **redundancy** (r=0.94 vs dip_depth) |
| intercrank_cv_delta90 | crank interval-timing CV | 0.589 | 0.449 | +0.000 | no signal |
| anr_pos_mean_delta90 | engine-torque / load marginal | 0.506 | 0.981 | −0.043 | chance; displaces winners |

### V3 — interaction/cross + usage + probe (novel surface)
| Feature | Type | E1 AUROC | MW p | E2 Δ | Failed on |
|---|---|---|---|---|---|
| reg_instab_x_usage | interaction (range-trend × starts) | **0.654** | 0.164 | +0.0036 | significance (exposure-tinged) |
| dose_dip_x_starts | interaction (dip × starts) | 0.614 | 0.252 | −0.0036 | significance |
| sag_under_load | interaction (dip × ANR pre-crank) | 0.595 | 0.350 | 0.000 | significance |
| weakbat_cold_load | interaction (rest-VSI × cold-frac) | 0.550 | 0.421 | **+0.0071** | significance (best Δ, still noise) |
| cold_start_fraction_delta90 | usage rate | 0.511 | 1.000 | −0.0071 | no signal |
| night_start_fraction_delta90 | usage / circadian | 0.500 | 0.903 | +0.0036 | no signal |
| ged3_rate_delta90 | GED cross-system probe | 0.500 | 1.000 | 0.000 | **zero-variance null** |

Supporting V3 analytics: BH-FDR smallest adjusted p = **0.7363** (nothing significant even before
multiplicity); mutual information dominated by incumbents (vsi_withinwk 0.366, vsi_range_trend
0.209) with all candidates ≤0.045; GBM model-class probe LOVO AUROC **0.8429**.

---

## 4. Features compared — the key insight

- **V2.1 tested single-signal marginals; V3 tested interactions/cross features** — the one class a
  linear model is *structurally blind to*. V3 also re-tried V2.1's **rejected ingredients as
  interactions**: `sag_under_load` = dip × **ANR** (V2.1's rejected marginal), `weakbat_cold_load`
  uses **cold-start** (V2.1's z_cold_dip theme). They still reject. The ingredients that failed as
  marginals also fail as interactions.
- **The dataset has essentially one latent signal** — battery/crank-voltage degradation, already
  captured by `dip_depth_last90_delta` + `rest_vsi_p05_delta90`. V2.1's strongest candidate
  (z_cold_dip, AUROC 0.728, p=0.048) *looked* significant and only died because the redundancy
  audit caught that it **re-measures dip_depth** (r=0.94). Both iterations keep **rediscovering the
  same one factor**; everything else is a proxy for it (redundant) or noise.
- **The failure mode flipped.** V2.1's best candidate died on **redundancy** (strong but a
  re-measurement); V3's candidates are all **novel** (zero redundancy/proxy flags fired) but **too
  weak** (max AUROC 0.654, none significant). V2.1 exhausted *strong-but-redundant*; V3 exhausted
  *novel-but-weak*.

---

## 5. Methods compared

| Dimension | V2.1 | V3 |
|---|---|---|
| **Shared core** | Pre-registered params · reconcile-to-0.9357 · E1 (MW p, oriented AUROC, proxy-leak, redundancy) → E2 (+0.01 LOVO) → E3 nested · hand-rolled ridge + rank-AUROC (no sklearn) · SMA-dead masking · VIN independence | **Identical** (V3 copied the numeric core verbatim; reconciliation is the proof it is faithful) |
| **Unique methods** | Heuristic layer: CUSUM/EWMA change-point (A1), conjunction pagers (A2), terminal-state H4 (A3), graded-RUL (A5); **specificity/economics accept-bar** (NF ep/truck-yr) | Interaction construction (global z-score); **GBM model-class probe**; **BH-FDR multiplicity**; SHAP/permutation/MI attribution; raw-parquet ANR windowing; formal temperature-infeasibility closure |
| **Rigor axis** | Deeper on **deployment** (pager economics, recall/specificity) | Deeper on **feature-value inference** (multiplicity, model-class, attribution) |
| **Feature-screen intent** | Secondary, pre-declared "expect HOLD" | Primary, deliberate test of a new class |

---

## 6. Most honest analysis (calibrated / skeptical)

### 6.1 Detection, not proof
At **n = 14 failed trucks**, the +0.01 AUROC gate is roughly **one truck's worth of ranking**. "All
reject" substantially means *nothing cleared a one-truck detection threshold at n = 34* — **not**
that the features are intrinsically worthless. The baseline itself has a bootstrap 95% CI of about
**[0.81, 0.99]** (V1.1); every delta here (+0.0071, −0.043, …) is **inside that noise**. We are
comparing rounding errors against a baseline we cannot measure to two decimals.

The precise, defensible claim is narrower than the "ceiling holds" headline:
> *At n = 34 on the 6-signal / 5-second data, no hand-crafted per-VIN feature or simple model beats
> the modal-4 battery-voltage baseline by a detectable margin.*
Anything stronger ("features are worthless," "space exhausted") is **plausible extrapolation, not proof.**

### 6.2 The single-latent-factor result is the strongest honest evidence
Independent of any single reject, both iterations converge on the same finding: **one signal
(battery/crank-voltage degradation) dominates**, and candidates either proxy it (redundant) or add
noise. The redundancy audit doing real work on z_cold_dip (killing a p=0.048 "winner" as a
re-measurement) is the clearest demonstration.

### 6.3 Where each iteration is genuinely weak
- **V2.1's feature screen was half-hearted by design** — its spec pre-declared B2/B4/B5 as "expect
  HOLD." Its 3-feature rejection is therefore **weak evidence**; its real contribution was
  operational (the pager / A3 / A5), not scientific.
- **V3 over-claimed the GBM probe.** The "GBM 0.843 < linear 0.932 → cap is data not model class"
  framing is **weaker than stated**: that GBM ran on **all 11 features (modal-4 + the 7 noise
  candidates)**, not modal-4 alone, so its underperformance conflates "nonlinear model" with "polluted
  feature set." It is also **one barely-tuned config** at n = 34 with high variance. Honest grade:
  **suggestive / consistent-with data-limited, not decisive.** A clean probe (tuned GBM on modal-4
  only) was not run.
- **V3's interactions used global z-scoring**, not fold-internal — documented SCREEN-GRADE and moot
  only *because nothing survived*; a borderline candidate would have been leaky/unreliable.
- **V3 tested 4 of a large space of interactions**, chosen by intuition. "Interactions reject" really
  means "these 4 reject."

### 6.4 Shared weaknesses (both)
- **Not independent replications.** Same feature matrix, labels, modal-4, SMA-dead exclusions, gate.
  Agreement is **partly structural** — a flaw in the shared foundation would cap both identically.
- **Label noise.** Failure timing derives from warranty/workshop records (V1.1 flagged the
  uncertainty). Part of the "ceiling" may be **irreducible label noise**, which neither iteration can
  separate from feature/sensor limits.
- **Representation scope.** Both test only **hand-crafted per-VIN scalars + simple linear models**.
  Different representations (sequence models, learned embeddings, per-crank waveforms) are untested —
  correctly deemed infeasible at n=34 / 5-second cadence, but that is a **scope limit, not a proof of
  no signal**.

---

## 7. Calibrated bottom line

- **Solidly established:** on this exact data, the battery-voltage signal is essentially the only
  extractable one; marginals (V2.1) and interactions (V3) both reduce to proxies-for-it or noise;
  adding features **hurts** held-out performance (overfit).
- **Plausible but not proven:** that no feature/method could help at all — it might at n≈500, with a
  cleaner model-class test, or with less label noise.
- **Honest verdict:** V2.1 and V3 together don't *prove* the ceiling so much as **repeatedly fail to
  beat it and accumulate strong reasons** (n, sensors, 5-s cadence, single latent factor, label
  noise) to believe it's data-bound. The correct action is unchanged — **freeze modal-4, stop
  hand-crafting features on this data, and pursue instrumentation** (IBS current-clamp / hi-rate VSI
  firmware / larger n) — but the justification is **diminishing-returns + strong priors, not
  mathematical certainty.**

Cross-component note: the last Alternator iteration (V12_ALT_GED, 2026-06-26) hit the identical
pattern — novel features all reject vs a frozen baseline, cap is the data, need new sensors — so this
is now a cross-component conclusion, not an SM quirk.

---

## 8. Successor

A follow-on iteration (**V3.1**, pre-registered 2026-07-02) reframes the approach toward a
State-Engine-First formulation and battery-vs-starter triage rather than more marginal/interaction
features — i.e. it responds to §6 by changing the *representation/question*, not by re-screening the
same scalar space. See the V3.1 plan for details.
