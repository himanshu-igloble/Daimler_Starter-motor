---
title: "V3.1 Starter Motor — Data-Reality Memo (Phase 0 Probes)"
status: "complete"
created: "2026-07-02"
program: "SM V3.1"
sources: "P0_heartbeat.json, P0_duplicates.json, P0_dropout_taxonomy.json, P0_sma_observability.json, P0_gap_census.json, P0_gap_hist.csv, V3_1_state_params.json"
---

# V3.1 Starter Motor — Data-Reality Memo

Phase 0 probes tune state-engine definitions before any candidate is scored. They run
label-blind on signals + timestamps only, across all 34 SM VINs (14 F + 20 NF), and never
accept or reject a candidate — so they carry no multiplicity cost. Every number below is
cited from a `state/out/P0_*.json` artifact or `P0_gap_hist.csv`. SCREEN-GRADE caveat
(n = 34) applies to any label-adjacent reading.

---

## P0-1 — Heartbeat hypothesis: REFUTED

**Question.** Are the chains of 15–16-minute gaps that dominate the record an ignition-OFF
dwell signature (a stationary "heartbeat")?

**Pre-registered decision rule (spec §4).** Heartbeat CONFIRMED iff ≥ 70 % of sampled
chains *end* in a crank-or-RPM-rise within 120 s **AND** ≥ 70 % *begin* ≤ 120 s after RPM
falls to 0/null.

**Result (`P0_heartbeat.json`).**

| Metric | Value | Threshold | Verdict |
|---|---|---|---|
| Chains evaluated | 6,800 | — | — |
| `start_ok_frac` (chain begins right after RPM→0) | **0.9832** | ≥ 0.70 | PASS |
| `end_ok_frac` (chain ends at a restart) | **0.1587** | ≥ 0.70 | **FAIL** |
| `confirmed` | **false** | both | **REFUTED** |

**Interpretation.** The start condition passes decisively — chains almost always begin
right after the engine stops. The end condition fails hard: only 15.87 % of chains close
with a wake/crank. The most consistent reading is that the TCU emits ~15-minute heartbeats
for a while after shutdown, then drops into a deeper sleep; the *chain-end is not the
vehicle waking up*, so the end of a heartbeat chain does not mark the next start.

**Consequence (binding for the state engine).**

1. No `OFF_DWELL` episode type is emitted (fleet `off_dwell_hours` = 0.0 in the weekly
   rollup — the state engine honored the refutation by construction).
2. Soak is measured only via **in-band `ENGINE_OFF` adjacency** to each crank, not via a
   reconstructed off-dwell span. This still covered **0.7102** of cranks fleet-wide
   (SV-4) — materially better than feared.
3. The measurable-soak distribution is **biased short**: long parks fall into
   `UNKNOWN_GAP` (→ NaN soak), not into a measured overnight dwell. Fleet
   `unknown_gap_hours` = 288,936.8 vs `off_hours` = 12,976.0 confirms the scale of the
   unmeasured tail. **Every soak / hot-restart catalog value therefore describes the
   measurable subset only** and the soak family is classified Experimental.

Gap-length evidence (`P0_gap_hist.csv`): the 14- and 15-minute bins hold 213,107 and
659,515 gaps respectively — the two orders-of-magnitude spike that defines the heartbeat
band [14, 18] min. Everything above ~18 min falls off a cliff.

---

## P0-2 — Duplicate timestamps: quantified, deterministic rule adopted

Duplicate timestamps are pervasive (`P0_duplicates.json`): from **21,153** (VIN5_F_SM) to
**421,321** (VIN16_NF_SM) duplicated-timestamp rows per VIN. Adopted rule (spec §4): stable
sort, keep all rows, `dt = 0` treated as same-instant; the state of a duplicated instant is
the **highest-priority state** among its rows (CRANK > ENGINE_OFF > IDLE > DRIVE > UNKNOWN).
This matches the frozen crank extractor and makes the engine deterministic.

**Data-quality VIN of note (NaT catch, quality review).** All 20 NF VINs carried NaT
(not-a-time) timestamps (failed VINs carried none); left unhandled these crashed
`derive_trips` and polluted the duplicate census. The root fix in `load_vin` drops NaT
before sorting. The most affected VIN, **VIN18_NF_SM, fell from 1,010,522 to 320,750**
duplicated-timestamp rows after the fix — and 320,750 is the value now recorded in
`P0_duplicates.json`. The failed-vs-NF NaT asymmetry (zero NaT in any failed VIN, NaT in
every NF VIN) is itself a telematics-config observation worth one line: the two cohorts
were not exported by an identical pipeline.

---

## P0-3 — Dropout taxonomy for > 1 h gaps: three classes, all 34 VINs

Long gaps (> 1 h) are classified (`P0_dropout_taxonomy.json`): resume-with-RPM > 500 in the
first 5 rows ⇒ `DROPOUT_RUNNING`; resume-with-SMA = 1 ≤ 300 s ⇒ `OFF_CONFIRMED`; else
`UNKNOWN_GAP`. `DROPOUT_RUNNING` is common on high-volume NF trucks (e.g. VIN11_NF 57,
VIN18_NF 47, VIN13_NF 41); `OFF_CONFIRMED` is rare fleet-wide (0–5 per VIN — a direct
consequence of the P0-1 refutation: the record seldom captures a clean off→SMA restart);
`UNKNOWN_GAP` is the residual and the reason the long-park tail is unmeasured. This taxonomy
feeds the T3 data-health monitor and the C1 `dropout_share_delta90` candidate.

---

## P0-4 — Timezone codification: IST (vehicle-local)

The timestamp field is tz-naive at microsecond precision. Codified as **vehicle-local IST**
(single-zone India operations), carried verbatim from V3 F4b. This governs C2 seasonal
windows and any catalog time-of-day split. No cross-zone ambiguity exists for this fleet, so
the codification is a documentation contract rather than a transform.

---

## P0-5 — SMA observability audit: DETECTOR-LIMITED (not a literal undercount)

`P0_sma_observability.json` compares engine-run starts detected by an RPM≥550 recovery rule
against SMA = 1 events in the preceding 120 s. The `undercount_frac` sits at **0.90–0.99
across every VIN** (min 0.9042 VIN11_NF_SM, max 0.9906 VIN5_F_SM).

**This is a detector limitation, not a literal SMA undercount.** The RPM-recovery rule
counts every RPM dip-and-recover — most of which are in-drive transients, not true engine
starts — so the ~0.90–0.99 "undercount" is dominated by the detector over-counting run
events, not by SMA missing real cranks. The derived covariate `sma_undercount_factor`
(catalog #33) is therefore labeled **Experimental** and must NOT be read as "SMA missed 90 %
of starts." It documents the config-confound surface (SMA event rates already differ ~10×
across the SMA-dead cohort) rather than a defect in the SMA channel.

---

## P0-6 — Constants & sentinel reality: masking retained as a no-op contract

`P0_gap_census.json` and the constants memo confirm the frozen data contract:

| Constant | Reality in SM data | Action |
|---|---|---|
| VSI | Already in **volts** (rest median ≈ 28 V, crank median ≈ 21–22 V); **no 0 / 255 sentinels** observed; missing = NaN | Existing cleaning kept verbatim; VSI × 0.2 rescale is a harmless no-op here |
| RPM | **No 65535 sentinel** observed; missing = NaN; RPM = 0 rows exist (engine-off partially in-band) | ENGINE_OFF observable directly |
| CSP | 65535 sentinel nulled before classification | Frozen |
| Crank success | `rpm_max_15s ≥ 550` | Contract with event catalog |
| baseline_vsi | mean VSI in [t_start − 90 s, t_start − 10 s], ≥ 3 valid readings | Contract with A-family features |

**Masking-as-no-op is deliberate.** The V1.1 cleaning path masks sentinels that do not occur
in this dataset. Rather than delete the masking (and diverge from the frozen contract), it is
retained as an explicit no-op so the SM path and the frozen ALT/SM cleaning stay
byte-compatible. A column-dictionary correction note (VSI-in-volts / sentinel reality) is
filed per Definition-of-Done item 8.

---

## Summary

| Probe | Outcome | Downstream effect |
|---|---|---|
| P0-1 Heartbeat | **REFUTED** (start 0.9832 / end 0.1587) | No OFF_DWELL; soak via in-band adjacency (0.7102); soak family Experimental |
| P0-2 Duplicates | 21k–421k/VIN; deterministic rule | NaT root-fix (VIN18_NF 1.01M→320,750); F-vs-NF NaT asymmetry noted |
| P0-3 Dropout taxonomy | 3 classes, all 34 VINs | T3 monitor + C1 candidate inputs |
| P0-4 Timezone | IST vehicle-local | C2 windows, time-of-day splits |
| P0-5 SMA observability | **DETECTOR-LIMITED** (0.90–0.99) | `sma_undercount_factor` Experimental, not a literal undercount |
| P0-6 Constants | VSI volts, no 0/255, no RPM 65535 | Masking retained as no-op; dictionary note filed |

*All P0 numbers cited from `state/out/P0_*.json` and `P0_gap_hist.csv`. Fleet: SM, n = 34
(14 F / 20 NF). Probes are label-blind; SCREEN-GRADE caveat applies to interpretation.*
