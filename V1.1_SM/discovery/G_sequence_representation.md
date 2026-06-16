---
title: "Agent G — Sequence Modeling & Representation Learning Feasibility (SM V1.1 Phase 2)"
status: "complete"
created: "2026-06-10"
---

# Agent G — Sequence Modeling & Representation Learning Feasibility

**Verdict in one line:** Deep sequence models are mathematically out of bounds at 14 failed
trucks / 34 sequences (minimal configs overrun the events-per-parameter budget by 235x–6,275x,
and a 43-parameter LSTM is already seed-unstable with no gain); the sequence-shaped value that
IS extractable is (1) a 2-coefficient trend summary that matches but does not beat the 0.893
engineered baseline, and (2) a prequential earliest-detection horizon of **k\* = 10 weeks
before t_end** (AUROC ≥ 0.836 for k = 0..10, collapsing to ~0.54 at k = 11) — which also
serves as the cleanest epoch-leak disambiguation evidence produced so far.

Baseline for all comparisons: V1 honest nested-LOVO Ridge 4-feature **AUROC 0.893**
(C1 audit, `V1.1/audit/results/C1_audit_results.json`).

---

## 1. Parameter-budget math (rigorous)

Data budget: **14 failed trucks** (the "events" in the events-per-variable sense), **34
labelled sequences** (one label per truck — the 2,636 truck-weeks are correlated within truck
and do not add label information), 20,471 crank events (unlabelled at the event level).
The classical events-per-variable guideline for logistic-type risk models is EPV ≥ 10
(Peduzzi et al., 1996, J Clin Epidemiol); modern prediction-model sample-size work argues
this is *optimistic* and that required EPV is often 20+ (van Smeden et al.; Riley et al.,
BMJ 2020). At EPV = 10 the entire fleet supports **≈ 1.4 estimated parameters**. Counts below
are exact for the formulas stated in `scripts/G1_param_budget.py`, computed for configurations
*smaller than anything published* — i.e., maximally generous to the deep models.

| Architecture | Minimal config | Params | Per failed truck | Overrun vs EPV-10 budget |
|---|---|---:|---:|---:|
| LSTM | 1 layer, h=8, univariate | 329 | 23.5 | 235x |
| BiLSTM | 1 bidir layer, h=8 | 657 | 46.9 | 469x |
| TCN | 2 res blocks, 8 ch, k=3 | 489 | 34.9 | 349x |
| Transformer encoder | 1 layer, d=16, 1 head | 2,273 | 162.4 | 1,624x |
| TFT | minimal d=16 (4 GRNs + 2 LSTMs + MHA) | 8,785 | 627.5 | 6,275x |
| Informer | 1 ProbSparse layer d=16 + distil | 3,057 | 218.4 | 2,184x |
| PatchTST | patch=8, 1 layer d=16 | 2,385 | 170.4 | 1,704x |
| TimeXer | 1 layer d=16, self+cross attn | 3,537 | 252.6 | 2,526x |
| **V1 Ridge (baseline)** | 4 engineered features | **5** | 0.4 | 4x |
| **PCA3 + logistic (probe a)** | 3 components | **4** | 0.3 | 3x |

Full table: `out/G1_param_budget.csv`.

**LSTM / BiLSTM.** The smallest non-degenerate univariate LSTM (h=8) carries 329 parameters
— 23.5 per failed truck where the guideline allows 0.07. Gating structure (4 weight blocks)
means parameters scale as 4h(h+i+1); there is no h small enough to fit the budget that still
has memory capacity beyond a hand-coded exponential smoother. BiLSTM doubles this for a
backward pass that is causally inadmissible for prequential deployment anyway (it reads the
future). Empirical confirmation in §2e: even h=2 (43 params) is seed-unstable.

**TCN.** Dilated causal convolutions need ≥2 blocks to cover a 40-week receptive field at
k=3; 8 channels is the floor below which it is a fixed smoothing kernel. 489 params, 349x
over budget — and a TCN's inductive bias (local translation-invariant motifs) is exactly
what our physics says doesn't exist here (the signal is a single terminal rise, which a
1-parameter slope captures; §2b).

**Vanilla Transformer encoder.** Attention has no parameter-free configuration: Q/K/V/O
projections alone cost 4d² (1,088 at d=16). With FFN, layer norms, input projection: 2,273
params. Attention additionally needs enough sequences to learn *what to attend to*; with 34
sequences of length 40 there are 34 attention-pattern examples — fewer examples than the d=16
embedding has dimensions per token.

**TFT.** The Temporal Fusion Transformer is the largest by construction: variable-selection
GRNs, encoder/decoder LSTMs, static enrichment, interpretable MHA. A stripped d=16 build is
8,785 params (627 per failed truck). TFT's selling points (multi-horizon quantile forecasts,
variable selection) presuppose a forecasting target with thousands of time steps × entities;
our target is a single binary label per truck.

**Informer.** ProbSparse attention reduces attention *compute* from O(L²) to O(L log L); it
does not reduce *parameter* count (same projections) and its distilling convolutions add
more. 3,057 params. Informer exists for length-512+ horizons; our sequences are length 40.

**PatchTST.** Patching (patch=8 → 9 tokens) shrinks the token count, not the budget: the
patch embedding plus one encoder layer is 2,385 params. PatchTST's published wins come from
channel-independence across *many* series for self-supervised pretraining — we have 34 series
and (see §3) no admissible pretraining corpus at the weekly level.

**TimeXer.** Adds exogenous-variable cross-attention to a PatchTST-style backbone: 3,537
params minimal. The exogenous pathway is the only conceptually attractive part (cranks as
endogenous, duty cycle as exogenous), but it is the most parameter-hungry pathway of all.

**Why transfer learning / pretraining does not rescue this.** (i) There is no public
pretraining corpus of heavy-truck fleet telematics at weekly-aggregate or crank-event
granularity; general time-series foundation models are pretrained on electricity, traffic,
weather and finance series whose dynamics share nothing with starter-circuit voltage
signatures, so the fine-tuning step still has to re-estimate what matters — from 14 events.
(ii) Even frozen-backbone linear probing of a pretrained encoder produces an embedding of
dimension ≫ 1.4, putting us back over the budget at the *head* alone unless we compress to
≤3 dims — which is exactly the PCA probe in §2a, done honestly. (iii) Domain shift is not a
nuance here: our windows are 40 points long, irregular, gap-masked, with a known epoch
confound; any pretrained representation that ingests raw length or timestamps inherits the
n_weeks/t_start leak (Phase-1 finding: n_weeks alone scores AUROC 0.952).

Note: `torch 2.5.1` *is* installed in this environment — the constraint is data, not
tooling, and §2e uses torch to demonstrate the point empirically.

---

## 2. Honest sequence probes (truck-level LOVO, fixed last-40-masked-week windows, per-VIN z-scored)

Setup: last L=40 masked weeks (active_days ≥ 2) of `vsi_drive_std` and `vsi_drive_mean`,
per-VIN z-scored (shape only, no amplitude, no length). 4 failed VINs with < 40 masked weeks
(VIN2/3/4/5_F_SM) are shape-preserving resampled to the 40-point grid — no probe ingests raw
length. Residual leakage is audited per component. Bootstrap = 1,000 VIN-level resamples.
Results: `out/G2_probe_results.csv`; script `scripts/G2_sequence_probes.py`.

### (a) PCA-as-linear-autoencoder (PCA refit inside every LOVO train fold)

| Probe | LOVO AUROC | 95% CI | vs 0.893 |
|---|---:|---|---:|
| PCA3(vsi_drive_std) + logistic | 0.868 | [0.692, 0.996] | −0.025 |
| PCA3(vsi_drive_mean) + logistic | 0.686 | [0.476, 0.865] | −0.207 |
| PCA3(std ‖ mean concat) + logistic | 0.900 | [0.757, 0.993] | +0.007 |

**Leak audit** (`out/G2_pca_leak_audit.csv`): PC1 of the std matrix — the component carrying
nearly all the discrimination (alone AUROC 0.932) — has Spearman r = +0.50 vs n_weeks,
−0.52 vs t_start, +0.55 vs span_days: **LEAK-flagged by the Phase-1 PROXY ≥ 0.5 standard.**
PC3 of the mean matrix is also flagged (r_span −0.52). So the only PCA configuration that
nominally matches the baseline (0.900) leans on a component entangled with the recruitment
epoch. A linear autoencoder cannot beat the engineered features, and what it finds first is
partially the leak — exactly as Phase 1 predicted for any representation fed whole windows.

### (b) Functional trend summaries (2-coefficient "sequence model")

Per-VIN linear slope, quadratic coefficients, and final-8-week slope fit on the z-scored
window:

| Probe | LOVO AUROC | 95% CI | vs 0.893 |
|---|---:|---|---:|
| trend coeffs of std window + Ridge | 0.918 | [0.817, 0.996] | +0.025 |
| trend coeffs of mean window + Ridge | 0.639 | [0.447, 0.826] | −0.254 |
| std + mean coeffs (8 feats) + Ridge | 0.925 | [0.825, 1.000] | +0.032 |

**Leak audit:** the dominant feature, `std_slope` (alone AUROC 0.950), carries
r = −0.56/+0.54/−0.58 vs n_weeks/t_start/span — PROXY-flagged. The G3b control recomputed it
on a fixed L=20 window where **no VIN needs resampling** (fleet minimum = 22 masked weeks):
AUROC stays 0.871 but r_span actually rises to −0.63 (`out/G3_L20_control.csv`). The
correlation is therefore *label-mediated* (failed trucks genuinely have both short spans and
rising within-week VSI std), not a mechanical window artifact — the same ambiguity status as
the B2 `vsi_std_ratio` family. The prequential result (§2d) is what finally disambiguates it.
Bottom line: a 2-parameter trend fit recovers the entire sequence signal; +0.03 over baseline
is far inside the bootstrap CI and is **not** claimed as an improvement.

### (c) Distance-based (DTW-free)

| Probe | LOVO AUROC | 95% CI | vs 0.893 |
|---|---:|---|---:|
| Euclidean 1-NN margin (std) | 0.914 | [0.811, 0.993] | +0.021 |
| 1−Pearson 1-NN margin (std) | 0.907 | [0.782, 0.993] | +0.014 |
| kernel-PCA3(RBF) + logistic (std) | 0.896 | [0.754, 0.993] | +0.003 |
| (same three on mean windows) | 0.657–0.729 | — | −0.16 to −0.24 |

Nearest-neighbour shape matching ties the baseline. Consistent story: the std-window *shape*
contains one discriminative degree of freedom (the terminal rise) and every method — PCA,
polynomial, 1-NN, kernel — finds the same thing and saturates at ≈ 0.89–0.92.

### (e) Tiny-LSTM capacity demonstration (torch, LOVO, 3 seeds)

The smallest possible LSTM (h=2, **43 parameters** — still 31x over the EPV-10 budget),
trained per LOVO fold on the std windows: AUROC **0.854 / 0.882 / 0.918** across seeds 0/1/2
(spread 0.064). It never beats the 2-coefficient polynomial of §2b, and its seed variance
alone is twice the largest probe-vs-baseline difference observed. This is the empirical face
of the budget table: at n=34, even 43 parameters buy instability, not signal.

### (d) Earliest-detection / prequential horizon (HIGH VALUE)

For each offset k = 0..26 weeks before each VIN's t_end (failed and NF trucks truncated
identically), causal versions of the four honest features (`vsi_withinwk_std_ratio_30d`,
`vsi_std_ratio_30d`, cohort-masked 90-day failed-crank rate, 12-week VSI-range Theil-Sen
trend) were computed on a fixed L=40 basis ending at the cut, then scored with LOVO Ridge
(per-fold median imputation; SMA-dead cohort VIN8_F/VIN9_F + 5 NF masked on the crank
channel). Curve: `out/G3_horizon_curve.csv`; script `scripts/G3_prequential_horizon.py`.

| k (weeks before t_end) | 0 | 2 | 4 | 6 | 8 | **10** | **11** | 13 | 15 | 17 | 20 | 26 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LOVO AUROC | 0.861 | 0.871 | 0.918 | 0.868 | 0.921 | **0.857** | **0.536** | 0.514 | 0.738 | 0.788 | 0.375 | 0.577 |

- **Sustained AUROC ≥ 0.75 holds for k = 0..10 (range 0.836–0.921), then collapses to ≈
  chance at k = 11. Earliest actionable horizon: k\* = 10 weeks (~70 days) before t_end.**
- An isolated bump at k = 15–17 (0.74–0.79, CIs spanning 0.56–0.93) is not sustained and is
  not counted.
- Coverage stays high through k = 10 (all 34 trucks usable; crank channel 79% by design of
  the cohort mask), so the cliff is not a data-availability artifact.
- **This is the leak disambiguation Phase 1 could not deliver:** n_weeks, t_start and
  span_days are *constant per truck across all k*. If the k=0 discrimination were
  epoch/length leak, the curve would be flat in k. Instead it decays to chance once the
  causal cut precedes the terminal rise — the signal is **time-locked to failure**, not to
  recruitment. The PROXY flags on `std_slope`/PC1 (§2a/b) are therefore label-mediated
  collinearity, not the driver of the discrimination.

**V1.1 deliverable implication:** score the fleet weekly with the causal feature set; expect
alerts to become reliable inside a ~10-week pre-failure window, with essentially no earlier
warning channel (consistent with the Phase-1 lead-time verdict and the alternator finding
that abrupt electrical failure modes do not telegraph).

---

## 3. Representation-learning verdict

**PCA stands in for autoencoders exactly** (a linear AE with MSE loss converges to the PCA
subspace), and §2a shows the result: the best 3-dim linear code of the weekly windows scores
0.900 with its dominant direction leak-entangled. Nonlinear AEs, VAEs, contrastive/Siamese
and SSL schemes all *add capacity* (encoder + decoder/projection heads, easily 10³–10⁴
params) without adding a single label or failed truck. Specifics:

- **VAE:** the KL-regularized latent needs enough data to estimate a posterior per dimension;
  at 34 samples the posterior collapses to the prior or memorizes.
- **Contrastive / Siamese:** needs pair labels. Same-truck-different-window pairs encode
  *truck identity* (≈ duty cycle + epoch — the leak); failed-vs-NF pairs give 14×20 = 280
  pairs drawn from only 34 independent units — pseudo-replication, not sample size.
- **SSL on weekly series:** pretext tasks (masking, forecasting) on 34 × ~78 weeks ≈ 2.6k
  correlated points cannot pretrain anything bigger than the polynomial fit of §2b.

**What data volume would change the answer.** The one defensible deep path is
self-supervised pretraining at the *raw 5-second* level, where the corpus is ~106M rows
(SM fleet) / ~204M (both fleets): pretext tasks such as masked VSI reconstruction or
next-window prediction over millions of crank/rest segments could legitimately train a
small (10⁴–10⁵ param) crank-event encoder, which would then be frozen and pooled per truck
into ≤3 dims for a linear head — keeping the *supervised* parameter count inside budget.
Honest sizing: this is a multi-week effort (segment extraction at scale, pretext design that
respects the SMA-dead cohort and VSI sentinels/rescaling, leakage-safe pooling), its
supervised ceiling is still gated by 14 failed trucks (CIs like [0.75, 1.0] will not narrow),
and the §2 saturation evidence says the weekly shape signal is one degree of freedom deep —
so the realistic upside is better *event-level* features (dip morphology), not a better
classifier. **Recommended status: documented future option for a phase with more failures
(n_failed ≥ 30–50), not a V1.1 work item.**

---

## 4. Predictive uncertainty (bootstrap, 1,000 VIN-level resamples)

| Winner candidate | LOVO AUROC | 95% CI |
|---|---:|---|
| V1 baseline (nested, from C1) | 0.893 | [0.746, 1.000] |
| b3 trend coeffs (std+mean) + Ridge | 0.925 | [0.825, 1.000] |
| b1 trend coeffs (std) + Ridge | 0.918 | [0.817, 0.996] |
| c Euclidean 1-NN margin (std) | 0.914 | [0.811, 0.993] |
| Prequential @ k=10 (500 resamples) | 0.857 | [0.696, 0.975] |

All CIs overlap the baseline's almost completely. No probe is declared a winner over the
engineered features; the honest claim is *equivalence via a 2-parameter representation* plus
the new horizon evidence.

---

## 5. Recommendation for V1.1

1. **No deep sequence model** (LSTM/BiLSTM/TCN/Transformer/TFT/Informer/PatchTST/TimeXer):
   235x–6,275x over the events-per-parameter budget; 43-param LSTM already seed-unstable.
2. **Adopt the prequential scoring cadence as the V1.1 deliverable framing:** weekly causal
   re-scoring with the honest feature set, with a stated detection horizon of **≤ 10 weeks
   before failure** (AUROC 0.836–0.921 inside the window, chance outside it).
3. **Cite the k-decay curve as the epoch-leak disambiguation** for the vsi-std family —
   strengthens, not changes, the V1 model card.
4. Optionally log the 2-coefficient `std_slope_L20` trend as a *diagnostic* channel
   (equivalent information to `vsi_withinwk_std_ratio_30d`; do not add to the model — Phase-1
   "fewer features better" stands).
5. Keep raw-5s SSL crank-encoder pretraining on the shelf, contingent on a future fleet with
   ≥ 30–50 failures.

## Artifacts

| Path | Content |
|---|---|
| `scripts/G1_param_budget.py` → `out/G1_param_budget.csv` | architecture parameter counts |
| `scripts/G2_sequence_probes.py` → `out/G2_probe_results.csv`, `out/G2_pca_leak_audit.csv` | probes a/b/c/e + leak audits |
| `scripts/G3_prequential_horizon.py` → `out/G3_horizon_curve.csv`, `out/G3_L20_control.csv` | prequential horizon + L20 control |
