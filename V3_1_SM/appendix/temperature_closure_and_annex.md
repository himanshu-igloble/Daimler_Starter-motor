---
title: "V3.1 Starter Motor — Theme-1 Temperature Closure & Forward Annex"
status: "complete"
created: "2026-07-02"
program: "SM V3.1"
sources: "V3_1_gate_summary.json (C2), V3 temperature_infeasibility.md, spec §9"
---

# Theme-1 (Ambient Temperature) — Closure with Evidence & Forward Annex

Ambient temperature is the single most-requested "obvious" starter-stress covariate and the
one the SM dataset structurally cannot supply. This annex closes the theme **with evidence**
for the current 34-truck fleet and specifies the concrete data asks that would re-open it for
the 500-truck program.

---

## 1. Why temperature is data-blocked on the current fleet

The SM data has **no GPS / lat-long / region channel** and no temperature signal. Ambient
temperature therefore cannot be joined from any weather source — there is no geo-anchor to
join on. This was established in `V3/appendix/temperature_infeasibility.md` and re-confirmed
in the V3.1 data-reality probes (P0-6: 6 signals + timestamp only; failed file adds only
SALEDATE / JCOPENDATE / Failure_type).

**User decision (2026-07-02):** no per-VIN region data is available for the 34-truck fleet.
Theme 1 stays closed for V3.1; this annex is the forward path only.

---

## 2. Every temperature-adjacent proxy has now been tested — and is null

| Proxy | Construction | Result | Source |
|---|---|---|---|
| Month-of-year seasonality | Kruskal–Wallis of VSI by calendar month | KW p = **0.90** (drive VSI) / **0.95** (rest VSI) — null | V1.1 E4 |
| Day-night / hour-of-day | `night_start_fraction_delta90` (00:00–05:00 share) | AUROC **0.500**, MW p **0.90** — null | V3 F4b |
| Cold-start dip depth | `z_cold_dip_delta90` (soak-conditioned dip) | **redundant** r ≈ 0.92–0.94 vs champion dip | V2.1 B4 |
| Cold-start rate | `cold_start_fraction_delta90` | MW p = **1.0** — null | V3 F1b |
| **Within-VIN seasonal dip contrast** | **`dip_seasonal_contrast` (C2)** | **REJECT — see §3** | **V3.1** |

The within-VIN contrast (C2) was the one genuinely-untested temperature-adjacent construction:
it dodges the no-GPS problem by making **each VIN its own climate control** (winter dip median
minus summer dip median, same truck). It is the last idea in this theme that the data could
support at all.

---

## 3. C2 `dip_seasonal_contrast` — the final construction, closed

**Definition (spec §7.2).** median dip_depth over non-artifact events in Dec–Feb minus median
over Apr–Jun, within the VIN's L40-masked span (pooling across calendar years if the span
spans more than one); null unless ≥ 15 qualifying events in *each* window; no Δ90 (it is
already a within-VIN contrast).

**Physics.** An aging battery/starter should amplify cold-morning dips; a rising winter-minus-
summer dip contrast would be a within-VIN thermal-degradation signature.

**Result (`V3_1_gate_summary.json`).**

| Metric | Value | Threshold | Verdict |
|---|---|---|---|
| n_nonnull | **16 / 34** | — | high null rate (≥ 15 events / window is demanding) |
| MW p | **0.8269** | ≤ 0.10 | FAIL |
| Oriented AUROC | **0.5089** | ≥ 0.60 | FAIL (at chance) |
| max \|r\| vs modal-4 | 0.786 (dip_depth_last90_delta) | < 0.85 | no flag (overlap documented) |
| E2 Δ | −0.0357 | ≥ +0.01 | largest negative in the set |
| BH-FDR adjusted p | 0.9885 | — | not significant |

**Verdict: REJECT.** The within-VIN winter-minus-summer dip contrast carries no SM failure
signal at n = 16. **Theme 1 is now closed with evidence, not assumption.** Every path from
"temperature matters for starters" to "a feature this dataset can compute" has been walked and
found null.

---

## 4. Forward path (500-truck program), cheapest-first

| Rank | Data ask | What it unlocks | Cost |
|---|---|---|---|
| 1 | **Per-VIN operating-region mapping** | Join regional climatology (IMD normals / Open-Meteo daily) by region — **no per-truck GPS needed**; recovers monsoon / winter / summer exposure as a real covariate rather than a duty proxy | Lowest — a fleet-registry field, no new hardware |
| 2 | **GPS + weather archive** (ERA5 / Open-Meteo) | Per-crank ambient temperature by lat-long-time interpolation; enables true thermal-stress and temp-normalized cranking-load features | Medium — GPS channel on the telematics unit |
| 3 | **SPN 171 Ambient Air Temperature** (J1939 CAN) | Direct ambient at the vehicle; no external join | Medium — CAN channel enable |
| 4 | **SPN 110 Engine Coolant Temperature** (J1939 CAN) | **Coolant-at-key-on is the best available crank thermal proxy** — it captures the actual thermal state the starter cranks against (cold engine ⇒ higher oil-drag torque ⇒ higher inrush) | Medium — CAN channel enable; highest physics value of the four |

**Recommendation.** For the 500-truck program, ask for **region mapping (rank 1) + SPN 110
coolant (rank 4)** together: the cheapest exposure covariate plus the highest-value thermal
proxy. Note that `monsoon_start_share` already surfaced as the strongest raw exploratory
separator (AUROC 0.7357) — but it is a **duty proxy, t_start-leak-adjacent**, not temperature;
region + coolant are what would let a genuine thermal feature be pre-registered for V3.2.

*C2 numbers cited from `V3_1_gate_summary.json`. Prior-proxy numbers from V1.1 E4, V2.1 B4,
V3 F1b/F4b. Fleet: SM, n = 34 (C2 n = 16). SCREEN-GRADE caveat applies.*
