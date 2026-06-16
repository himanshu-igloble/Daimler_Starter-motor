---
title: "Agent D — Failure Physics: Heavy-Duty 24V Starter Motor Failure Modes, Telematics Observability, and V1.1 Feature Guidance"
status: "complete"
created: "2026-06-10"
author: "Agent D (Failure Physics researcher), V1.1 enhancement program"
---

# Starter Motor Failure Physics — Research Synthesis for V1.1

**Scope:** BharatBenz 5528T (24V/120Ah lead-acid, ~550–600 RPM crank-complete, 300–500A cranking peak), long-haul fleet, 14 failed + 20 non-failed SM trucks. Telemetry: VSI/SMA/RPM/CSP/ANR/GED at ~5 s sampling, ~0.2 V effective voltage resolution, no current, no temperature, no SoC.

**Sources:** literature + patents (cited in §8), `KT_daimler/KT_startermotor_alternator.md` (DICV KT), `docs/column_dictionary.md`, V1 empirical results (`STARTER MOTOR/reports/V1_SM_final_report.md`). Where literature is thin, claims are explicitly marked **[engineering judgment]**.

---

## 1. Failure-Mode Taxonomy — Heavy-Duty 24V Diesel Starter

A heavy-duty pre-engaged starter (e.g., SEG/Bosch HX/HEF class fitted to CV platforms) has: a series-wound or PM DC motor (brushes + commutator + armature + field), a pull-in/hold-in solenoid whose copper disc bridges the 150–350A main circuit (Murugesan et al. 2014), a pinion on an overrunning (sprag) clutch driven through a reduction gear, engaging the flywheel ring gear, plus the low-current control circuit (key switch / start relay, <20A).

### Prevalence — what literature actually supports

Quantitative failure-mode *distribution* data for HD truck starters is essentially **not publicly available** (warranty data is proprietary). What is citable:

- **Battery dominates starting-system breakdowns overall**: ADAC 2025 roadside statistics attribute **45.4%** of all car breakdowns to the starter battery; starter motor + alternator + general electrics together are ~**10.6%** (passenger-car data, directionally valid for CVs). This is the single most important number for the battery-confound section (§3).
- **Design life**: conventional starters are designed for roughly **30,000–50,000 start cycles** (trade sources; Argonne ANL-15/05 studied stop/start durability but the PDF is 403-blocked — number not independently verified). At this fleet's ~10–30 starts/day, that is nominally 3–10+ years; the observed ~1–2-year failures are **premature, consistent with DICV's part-quality hypothesis** rather than cycle exhaustion.
- **Solenoid contact resistance growth is the canonical electrical EOL path**: Murugesan et al. measured worn (flat, pitted) solenoid power contacts at **10–15 mΩ** vs ~0.02–0.05 mΩ for fresh geometry — a 200–500x increase; "starter end-of-life is reached when the output is not sufficient for minimal cranking speed."
- **DICV KT** (this fleet, long-haul): solenoid wear / part quality dominant; brush/armature gives 60–120 d of declining crank voltage; bearing seizure sudden.

### Taxonomy with progression timescales

| # | Mode | Mechanism | Progression | Symptom horizon (symptomatic → dead) |
|---|------|-----------|-------------|----------------------------------------|
| 1 | **Solenoid main contacts** (disc + studs) | Arc erosion/pitting at each make/break of 150–350A; pitted area → higher contact resistance → I²R heating → accelerated erosion (self-reinforcing). Repeat attempts on a low battery cause *uneven* contact wear (Murugesan). | Slow resistance creep for thousands of cycles, then **avalanche** | Intermittent click-no-crank / retries over **days–weeks**, occasionally months **[eng. judgment; field-guide consensus]** |
| 2 | **Solenoid coil** (pull-in/hold-in winding) | Thermal degradation, especially from prolonged cranking; hold-in failure → chatter (rapid engage/release); pull-in open → dead | Abrupt or short intermittent phase | **Hours–days** |
| 3 | **Brush wear** | Carbon brushes at peak current density ~1000 A/cm² (Ueckerk, *Wear* 2003, via Murugesan); wear to minimum length → spring force collapse → rising brush-commutator resistance; brush fault → *less* current drawn → longer crank → more wear (positive feedback) | Gradual, then accelerating | **Weeks–months** of slowly degrading crank performance (KT: 60–120 d) |
| 4 | **Commutator wear / bar burning / glazing** | Paired with #3; arcing creates dead bars → no-crank dependent on armature rest position | Gradual + positional intermittency | Weeks–months |
| 5 | **Armature / field winding** | Insulation breakdown (overheating from long cranks) → shorted turns (weak torque, high current) or open (dead) | Mostly abrupt once shorted | **Minutes–days** |
| 6 | **Bearings / bushings** | Bushing wear → armature drag on pole shoes (slow, hot cranks); seizure | Wear gradual, seizure **sudden** (KT-confirmed) | Seizure: **zero warning** |
| 7 | **Pinion / Bendix / overrunning clutch** | Worn/chipped pinion teeth ride the ring gear (grinding, late mesh); sprag clutch slip → motor free-spins, engine never turns | Intermittent, position-dependent | Days–weeks of intermittent grind/free-spin |
| 8 | **Flywheel ring gear** | Localized milled/broken teeth → no-start only when flywheel stops at the damaged sector | Intermittent (position lottery) → sudden total | Days–weeks intermittent, or instant |
| 9 | **Wiring / main cable / grounds** | Corrosion adds series resistance (>0.5 V drop at cranking current = defective per Fluke practice); reduces current to motor | Slow seasonal creep (monsoon corrosion plausible for this fleet) | Months, but weakly expressed |
| 10 | **Start relay / control circuit** | Low-current circuit failure: key turned, nothing energizes | Abrupt or intermittent | Often **no SMA event generated at all** |

---

## 2. Mode → Observable → Lead Time → Observability Verdict (this telemetry, 5 s)

### What 5-second averaged VSI destroys vs preserves

**Destroyed (sub-sample physics):**
- **Inrush/engagement transient** (~50–300 ms, locked-rotor inrush far above the 300–500A running draw) — completely invisible.
- **Dip shape and true minimum** — DICV S4's instantaneous 16–18V appears as ~21–24V after 5 s averaging (V1: failed min-VSI 21.3 vs NF 21.6V). The *depth difference* between a healthy and a degraded crank (~0.5–2 V instantaneous) is compressed below the ~0.2 V resolution + averaging noise floor.
- **Crank duration deltas < 5 s** — ~93% of cranks quantize to a single sample; KT's claimed 2.2 s → 3.2 s shift is sub-quantum.
- **Solenoid chatter** (sub-second click-clack from hold-in failure), grinding duration, voltage ripple from commutator dead bars.

**Preserved (event-scale physics):**
- **Crank event existence and count** (SMA 0→1 edges), and therefore **retry clustering** (multiple SMA events within seconds–minutes — the driver re-keying *is* a multi-second-scale behavior).
- **Failed starts**: SMA=1 with no RPM rise to ~550–600 within a bounded window (DICV S6, superseded by direct SMA).
- **Extended cranks ≥ 2 samples** (≥ ~5–10 s true duration) — the pathological tail, even if the healthy mean is unresolvable.
- **Pre-crank resting voltage** (engine-off VSI before the first crank — slow, fully resolvable).
- **Post-start recovery / charge acceptance** (VSI climb to ~28 V over tens of seconds — resolvable).
- **Calendar structure**: time-of-day, rest-duration before crank, season (ambient proxy).

### Per-mode mapping

| Mode | Expected signature in VSI@5s / SMA / RPM | Expected lead time *as observable here* | Verdict |
|------|------------------------------------------|------------------------------------------|---------|
| 1. Solenoid contacts | **Retry clusters** (SMA event bursts minutes apart), rising **failed-start rate** (SMA=1, no RPM rise), occasional success after retries; successful cranks look *normal* (engagement is near-binary). Worn contacts reduce motor current (Murugesan: old starter 184–207A vs new 235–257A), so battery-rail dip does **not** reliably deepen. | **Days–weeks** of intermittency before total failure | **PARTIALLY OBSERVABLE** — via retry/failed-start events, *not* via voltage |
| 2. Solenoid coil | Chatter invisible (<5 s); net effect = failed start or repeated brief SMA events | Hours–days | **PARTIALLY** (only the retry/fail residue) |
| 3. Brush wear | Physically: slowly lengthening cranks + slowly deepening dips over 60–120 d. At 5 s/0.2 V both are below the floor until cranks cross the 2-sample threshold (≥ ~5–10 s) very late; multi-sample-crank fraction creeps up; eventual failed starts | Physics offers 60–120 d; **instrument delivers ~last weeks** (extended-crank tail + failed starts) | **PARTIALLY — channel exists in physics, mostly destroyed by sampling** |
| 4. Commutator | Position-dependent intermittent no-crank → failed-start + retry events with no trend in successful cranks | Days–weeks | **PARTIALLY** (indistinguishable from mode 1 in this data) |
| 5. Windings | Abrupt: sudden cluster of failed starts / one terminal no-start. Shorted-turn phase (slow crank, high current) invisible without current | ~0 (abrupt) to days | **EFFECTIVELY INVISIBLE pre-event** |
| 6. Bearings | Bushing-drag phase: longer cranks + deeper dips (same destroyed channel as #3); seizure: single sudden no-start, possibly deep dip on locked rotor (one 5 s sample, ambiguous) | Seizure: **zero** | **INVISIBLE** (seizure), partially for drag phase |
| 7. Pinion/clutch | **Free-spin signature**: SMA=1, motor spins unloaded → *shallower* dip + RPM stays 0 → recorded as failed start. Grinding → retries. Note: unloaded free-spin vs loaded no-crank could in principle differ in dip depth, but 5 s averaging makes the contrast unreliable | Days–weeks intermittent | **PARTIALLY** (as undifferentiated failed-start/retry events) |
| 8. Ring gear | Position-lottery no-starts → sporadic failed starts/retries with long clean gaps; no voltage trend | Days–weeks, erratic | **PARTIALLY** (low event rate, hard to separate from noise) |
| 9. Wiring/connections | Series R reduces starter current: *slower RPM rise*, marginally longer cranks; battery-rail dip may *shallow* (less current) — counterintuitive and below resolution | Months in physics; ~nothing observable | **MOSTLY INVISIBLE** |
| 10. Relay/control | Key turned, no SMA=1 logged (if SMA reflects the energized circuit) → **the failure produces missing data, not events**. Candidate explanation for some of the 5/14 silent-gap VINs only if ignition-off telemetry also stops | None | **INVISIBLE** (possibly *anti-observable*: absence of cranks) |
| — Battery (confound) | Deep dips + slow RPM rise + long cranks + retries + **low pre-crank resting VSI + poor charge acceptance + winter-morning worsening** | Weeks–months (resting V trend is slow and resolvable) | **OBSERVABLE — better-observed than any starter mode** |

**Blunt summary:** at 5 s sampling, every starter-internal failure mode collapses onto a *single observable syndrome* — **failed-start events and retry clusters in the final weeks** — plus a battery-side channel that is genuinely well-observed but is a confound. Mode-level diagnosis from this telemetry is not achievable; V1's `Failure_type` column (being enumerated by another agent) may label the workshop finding, but the telemetry cannot independently verify sub-modes.

---

## 3. Battery-Confound Analysis

A weakening battery (higher internal resistance, lower SoC) produces deeper dips, slower RPM rise, longer cranks, more retries — i.e., **it mimics modes 1, 3, 6, 9 simultaneously**, and per ADAC it is ~4x more prevalent than starter failure as a breakdown cause. Worse, the DICV cascade (A6) means a weak battery *causes* starter wear (deeper current demand, longer engagements, uneven solenoid contact erosion per Murugesan), so the confound is also a causal pathway: a "Starter Motor" job card may terminate a battery-led cascade.

### Disambiguation matrix (VSI + SMA + RPM only)

| Signature | Battery weakness | Starter wear (solenoid/brush) |
|-----------|------------------|-------------------------------|
| **Pre-crank resting VSI after ≥6–8 h rest** (lead-acid OCV ↔ SoC, needs ≥4 h rest to depolarize — Battery Univ. BU-903) | **Low and/or declining trend**; first-morning value is the cleanest battery probe in this dataset | **Normal** — starter does not touch open-circuit voltage |
| Post-start charge acceptance (resting → ~28 V climb time; KT §10.5) | Slow (>15 s = sulfation) | Normal |
| Dip depth (5 s avg) conditioned on resting V | Deep dip *with* low resting V | Worn solenoid contacts pass **less** current → dip not deeper (Murugesan old-starter data); deep-dip-with-normal-resting-V is rare for starter-side faults |
| RPM rise given successful crank | Slow rise *everywhere*, gradually worsening | Near-binary: normal rise when contact made, nothing when not |
| Failure-event texture | **Graded** (progressively longer/slower cranks) | **Intermittent/binary** (clean crank or click-no-crank; retry succeeds) |
| Temperature/season correlation | **Strong**: winter mornings, post-rest (R_internal ~1.5x at 10–20 °C per KT §9.1); monsoon self-discharge | Weak — contact pitting and tooth damage are event-count-driven, not thermally gated **[eng. judgment]** |
| Recovery after alternator charging (long highway leg → next crank) | Improves (SoC restored) unless SoH-degraded | No improvement |

**Operational rule for V1.1:** treat `resting_vsi` (level + trend, rest-conditioned), charge-acceptance time, and winter-morning-conditioned dip as an explicit **battery covariate block**. A truck whose failed-start/retry rate rises *while the battery block stays clean* is the highest-confidence starter-side signal this data can produce. A truck where both rise together is "cascade — inspect battery first" (matches the V1 deployment advice and DICV A6).

---

## 4. Reconciling V1 Empirics with Physics

**(a) Why last-90-day failed-crank rate works (AUROC 0.74) but lifetime rate doesn't (NF higher, 15.9% vs 9.7%).**
Two stacked reasons. *Physics:* solenoid contact erosion is flat-then-avalanche — resistance creeps harmlessly for thousands of cycles, then pitting reduces the contact spot, I²R heating accelerates erosion, and intermittent no-make appears only in the terminal phase. The informative quantity is the **recent change against the truck's own baseline**, never the lifetime level. *Measurement:* the lifetime "failed-crank" rate is dominated by non-degradation events — accessory/key-on cranks, aborted starts, bump-start behavior, CAN dropouts during the RPM-rise window — i.e., it measures duty and data quality, which differ by cohort (NF trucks have 616 vs 371 active days and different null rates). A level contaminated by usage *should not* discriminate; physics says only the late delta is signal. The V1 finding is exactly what the failure mechanism predicts.

**(b) Is the +3% duration finding (vs KT's +48%) consistent with solenoid-dominant failure?** Yes, doubly so. First, solenoid contact failure barely lengthens *successful* cranks — engagement is near-binary (make → normal crank; no-make → failed start/retry). Duration lengthening is the brush/battery signature, which KT itself says is the *secondary* mode in long-haul. Second, even if a 2.2 → 3.2 s shift existed, 5 s sampling quantizes ~93% of cranks to one sample; a +1 s true shift moves only the tail probability of crossing the 2-sample boundary, which appears as roughly the observed few-percent effect. The V1 result does not refute KT's physics — it shows the duration channel is **below the instrument's quantum**, and that the discriminative residue migrates into event-rate features, which is precisely where V1 found it (`failed_crank_rate_last90`).

**(c) Is "no long lead time" physically expected? — honest answer: largely yes, for this fleet, with one caveat.**
Literature on starter PHM is thin (most starting-system patents — US11808243, US8272360, US10408183 — assume per-crank current/voltage waveforms or cycle counting at the ECU, none of which exists here; battery-crank-SoH patents US10830826/US8111037 require temperature-conditioned per-crank minima, also unavailable). What the failure physics supports: solenoid contacts, engagement hardware, windings, and bearing seizure all have **symptomatic horizons of zero to a few weeks** — the long-lead modes (brush/commutator, 60–120 d; wiring corrosion, months) express through exactly the channels (dip depth millivolt-trends, sub-second duration growth) that 5 s averaging destroys. So: *the physics offers a 60–120 d channel for one mode family, but this instrument cannot read it; for the dominant (solenoid/part-quality) modes, even perfect instrumentation would only buy days-to-weeks.* The V1 lead-time null (trend battery fires on 90% of healthy trucks) additionally shows the VSI-trend channel measures battery/season/duty variation, not starter wear — consistent with battery being the dominant voltage-shaping component (ADAC 45.4%). **A validated long-lead starter-specific channel should not be expected from this data; V1.1 should aim at a days-to-weeks alarm built on failed-start/retry dynamics, not a 60–120 d forecast.**

**(d) Silent-gap VINs (5/14).** Physics adds one hypothesis: control-circuit/total-electrical failures and dead-vehicle scenarios (mode 10, or cascade endpoint where the truck no longer starts at all) produce *absence* of telemetry rather than signatures — the gap itself is the terminal symptom. This cannot be used as a feature (leakage, as V1 correctly ruled) but explains why the missed failure (VIN8_F_SM) is a gap VIN.

---

## 5. V1.1 Feature Recommendations (ranked: physics-plausibility x observability)

| Rank | Feature | Construction | Mode targeted | Why it should work |
|------|---------|--------------|---------------|--------------------|
| 1 | **Retry clustering** | SMA event bursts: ≥2 crank events within 120 s (and within 10 min) without intervening sustained RPM>600; daily burst count; last-30/60/90 d rate vs own-baseline ratio | Solenoid contacts, pinion/ring gear, commutator | The driver re-keying converts sub-second contact failures into multi-second event patterns the 5 s grid *can* see; canonical solenoid-intermittency signature |
| 2 | **Failed-start rate, daily resolution, own-baseline delta** | SMA=1 with no RPM ≥ 550 within 15 s; daily rate; CUSUM/delta vs first-90-d baseline (re-test the VIN1_F_SM spike with ≥3 daily values instead of weekly) | All engagement + contact modes | Already V1's only crank-physics winner; daily aggregation fixes the insufficient-data verdicts; own-baseline removes the duty confound that killed the lifetime version |
| 3 | **First-crank-of-day battery probe** | For first SMA event after ≥6 h engine-off: pre-crank resting VSI, first-attempt success flag, retries-to-success | **Battery confound control** + cascade detection | Overnight rest = depolarized OCV = cleanest SoC/SoH read this data allows (BU-903); a controlled daily experiment hiding inside the data; separates battery-led from starter-led trucks (§3) |
| 4 | **Extended-crank tail rate** | P(crank spans ≥2 samples) and ≥3 samples, last-90 d vs baseline; plus max crank length per week | Brush/commutator, bushing drag, weak battery | The *tail*, unlike the mean, survives quantization; pathological ≥10 s cranks are unambiguous |
| 5 | **RPM-rise lag proxy** | Samples from SMA onset until first RPM ≥ 550 (0/1/2+); weekly P(lag ≥ 2 samples); season-conditioned | Brush wear, wiring R, battery | Coarse (5 s quanta) but a distribution shift is measurable over hundreds of cranks; condition on month to strip ambient effect |
| 6 | **Post-crank recovery / charge acceptance** | Time (samples) from crank end to VSI ≥ 27.5 V; weekly median | Battery block (covariate) | KT §10.5 channel; resolvable at 5 s; feeds the §3 disambiguation, not the starter score directly |
| 7 | **Seasonal/ambient conditioning** | Month + hour-of-day as ambient proxy (no temperature sensor); winter-morning-only versions of dip depth and lag; *interaction*, not standalone feature | Confound control | KT §9.1: winter deepens dips 1–2 V and raises R_internal ~1.5x; an unconditioned trend feature partly measures the calendar (the likely driver of V1's 90% NF trend false-positives) |
| 8 (exploratory) | **Free-spin discrimination** | Among failed starts: dip depth shallow vs deep (unloaded spin vs loaded stall) | Overrunning clutch vs contacts | Physically real contrast, probably below 5 s resolution — cheap to test, low expectation |

Anti-recommendations (chasing destroyed channels): absolute dip depth as primary feature; mean crank duration; any per-crank waveform analytics; inrush-related anything.

---

## 6. Honest "Invisible Modes" List — do not chase in V1.1

| Mode | Why invisible | Verdict |
|------|---------------|---------|
| Bearing **seizure** | Sudden mechanical event; zero electrical precursor at any sampling rate without vibration/current data | Never predictable here (KT agrees: "sudden") |
| Armature/field **winding short or open** | Abrupt; precursor (rising current at constant voltage) needs current sensing | Never predictable here |
| **Ring-gear tooth breakage** (sudden form) | Mechanical, position-lottery; no voltage expression | Not predictable; only its *intermittent* prelude (retries) is visible if it occurs |
| **Relay / control circuit / ignition switch** | Failure suppresses SMA events instead of generating them | Anti-observable; at most expressible as "cranking activity stopped" — confounded with parking/telemetry loss |
| **Solenoid weld-closed** (contacts stick) | Rare, instantaneous; starter stays engaged after start — would need post-start SMA=1 with RPM>600, theoretically visible but a single-sample curiosity | Not a prediction target |
| **Mounting/flywheel alignment** degradation | Acoustic/vibration phenomenon | Invisible |
| **Brush wear, the gradual phase** | *Physically progressive but instrumentally invisible*: the 60–120 d declining-crank-voltage channel lives in sub-sample dip shape and sub-second duration growth; 5 s/0.2 V destroys it until the terminal weeks | The honest reclassification: not "no lead time exists," but "this instrument cannot read the lead-time channel that exists" |

**Program-level implication:** V1.1's realistic ceiling is (i) the existing recent-window risk classifier, plus (ii) a **days-to-weeks intermittency alarm** (features 1–2) with the battery block (features 3, 6, 7) routing the work order to battery-first vs starter-first inspection. A 60–120 d starter-specific forecast requires event-based high-frequency crank logging (DICV's stated post-2026 path, KT §15.2) — not more feature engineering on 5 s data.

---

## 7. Cross-checks against repo ground truth

- KT §6.3 solenoid-dominant claim — consistent with the V1 observation that only *event-rate change* (not duration/dip level) discriminates (§4b).
- KT §12.2 lead-time table (crank duration 60–120 d, dip 30–60 d, failed-crank rate 30–60 d) — should be read as *physics horizons*, not validated telemetry horizons; V1 §6 validated none of them as lead-time channels, which §2/§4c explains rather than contradicts.
- DICV A6 cascade — strengthened by Murugesan's uneven-contact-wear-from-low-battery-retries mechanism; the cascade is bidirectional (weak battery accelerates solenoid wear; failing starter's long cranks drain and heat the battery).
- The `Failure_type` enumeration (Agent task, parallel) should be checked against §2's prediction: telemetry cannot distinguish sub-modes, so if `Failure_type` contains sub-mode labels, they are workshop diagnoses usable for *stratifying* failed VINs (e.g., did retry-cluster VINs map to solenoid jobs?) but not for training mode-specific detectors at n=14.

---

## 8. Citations

Peer-reviewed / primary:
1. Murugesan, V.M., Chandramohan, G., et al., "Analysis of Automobile Starter Solenoid Switch for Improved Life," *Automatika* 55(3):256–264, 2014. DOI 10.7305/automatika.2014.12.405 — https://hrcak.srce.hr/file/196629 (read in full: contact resistance 10–15 mΩ worn vs ~0.02–0.05 mΩ new; old starter draws 184–207A vs new 235–257A; voltage dip tables; uneven contact wear from low-battery retries; starter EOL definition; brush current density 1000 A/cm² via Ueckerk, *Wear*, 2003)
2. Bayir, R., et al., "Condition Monitoring and Fault Diagnosis of Serial Wound Starter Motor with Learning Vector Quantization Network," *J. Applied Sciences* 8(18), 2008 — https://scialert.net/fulltext/?doi=jas.2008.3148.3156 (six starter faults diagnosable — but from voltage *and current* waveforms)
3. Murugesan, V.M., et al., "An overview of automobile starting system faults and fault diagnosis methods," *J. Eng. Applied Sci.* 7(7), 2012 — https://www.researchgate.net/publication/274701478_An_overview_of_automobile_starting_system_faults_and_fault_diagnosis_methods (abstract-level access)
4. Kassim, M., et al., OCV parameters & energy recovery for lead-acid SoH, *J. Energy Storage*, 2021 — https://www.sciencedirect.com/science/article/abs/pii/S2352152X21011610 (paywalled; abstract only)

Patents (mechanism documentation, no fleet statistics):
5. US 11,808,243 — Starter solenoid contact health monitor — https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/11808243
6. US 10,830,826 — Crank health of a battery (min crank voltage ↔ internal resistance, temperature-conditioned trending) — https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10830826
7. US 8,111,037 — Battery SoH from voltage during vehicle starting — https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/8111037
8. US 8,272,360 — Energy management with supplementary starter diagnostic (per-start monitoring: long cranks, thermal stress, wear) — https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/8272360
9. US 10,408,183 — Engine starter durability for stop/start (engine speed at pinion engagement → starter life consumption) — https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10408183

Industry / field statistics & practice:
10. ADAC 2025 breakdown statistics (via VISION mobility): battery 45.4% of breakdowns; starter/alternator/electrics ~10.6% — https://vision-mobility.de/en/news/adac-statistics-breakdowns-continue-to-rise-even-with-electric-cars-the-starter-battery-is-failing-390210.html
11. Argonne National Laboratory, "Stop and Restart Effects on Modern Vehicle Starting System Components" (ANL, 2015) — https://publications.anl.gov/anlpubs/2015/05/115925.pdf — **fetch returned 403; cycle-life figures below taken from secondary trade sources instead**
12. Battery University BU-903, "How to Measure State-of-Charge" (OCV–SoC, ≥4 h rest requirement) — https://www.batteryuniversity.com/article/bu-903-how-to-measure-state-of-charge
13. Fluke, "How to Check Starter Circuit Voltage Drop" (>0.5 V cable/connection drop = excessive) — https://www.fluke.com/en-us/learn/blog/digital-multimeters/how-to-check-starter-circuit-voltage-drop-with-a-multimeter
14. Rick's Free Auto Repair Advice, starter life factors (~50k design cycles; spin-down brush wear claim — **trade source, unverified**) — https://ricksfreeautorepairadvice.com/how-long-a-starter-lasts-the-factors-that-affect-starter-life/ ; lifespan ranges — https://diycarexpert.com/how-long-do-starter-motors-last/
15. SEG Automotive, commercial-vehicle starter motors — https://www.seg-automotive.com/automotive-solutions/starter-motors/starter-motors-for-commercial-vehicles/
16. Denso Aftermarket, starter troubleshooting — https://www.denso-am.eu/news/starter-troubleshooting
17. Trade/field diagnostic guides for failure-mode symptomatology (solenoid click, grinding, ring-gear position dependence): https://aplcargo.com/truck-starter-clicks-solenoid-vs-motor-guide/ ; https://engineerfix.com/how-to-fix-a-starter-grinding-noise/ ; https://themotorguy.com/how-to-tell-if-a-starter-solenoid-is-faulty-with-common-symptoms-and-fixes/ ; https://carinterior.alibaba.com/question/starter-ring-gear-problems-explained ; https://www.partcatalog.com/blogs/electrical-charging-and-starting/signs-your-starter-solenoid-is-failing-symptoms-to-watch

Repo sources: `KT_daimler/KT_startermotor_alternator.md`; `docs/column_dictionary.md`; `STARTER MOTOR/reports/V1_SM_final_report.md`; `STARTER MOTOR/Plan/V1_SM_plan.md`.

**Honesty notes:** no public fleet-level failure-mode distribution for HD starters exists (warranty data proprietary) — the "solenoid-dominant in long-haul" prior rests on the DICV KT plus mechanism plausibility. All symptom-horizon durations in §1/§2 not tied to a citation are engineering judgment from field-guide consensus and mechanism reasoning, and are marked accordingly. The Argonne cycle-life report could not be retrieved (403). PHM-literature searches found no published starter-motor RUL study on telematics-grade (≥1 s) data — the niche appears genuinely unpublished, not merely unfound.
