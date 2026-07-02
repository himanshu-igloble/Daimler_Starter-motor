---
title: "V3 Starter Motor — Ambient Temperature Infeasibility"
status: "complete"
created: "2026-07-01"
program: "SM V3"
---

# Ambient Temperature — Infeasibility Note

## Status: CLOSED (data-blocked)

Per-start ambient temperature reconstruction is infeasible for the SM dataset. This note
records the verification steps and the data that would unlock the temperature channel.

---

## 1. No Location Channel — Verified

The SM dataset contains exactly 6 signal columns plus timestamp: CSP, RPM, ANR, GED,
VSI, SMA. There is **no GPS latitude/longitude**, no depot identifier, no route segment,
no region code, and no vehicle home-base field anywhere in the dataset.

This was confirmed via two independent checks:

1. **Column dictionary** (`docs/column_dictionary.md`): the canonical signal reference
   lists all 6 signals and their valid ranges/sentinels. No location or geographic field
   appears in the dictionary.

2. **Repository-wide signal search**: a grep of the full SM data pipeline and feature
   scripts confirms that no field named `lat`, `lon`, `latitude`, `longitude`, `depot`,
   `region`, `location`, or `GPS` exists in any SM data file or feature extraction script.

Without a geographic anchor, weather-API or meteorological-station interpolation cannot
be performed: there is no coordinate to query for historical daily temperature, and no
depot registry to map VINs to operating regions.

---

## 2. Derivable Proxies — Already Null

Two indirect temperature proxies were derivable from existing signals and were tested
in prior iterations:

### 2.1 Seasonality (Month Effect on VSI) — V1.1 E4

The month-of-year was used as a proxy for ambient temperature in V1.1 E4. A Kruskal–Wallis
test for a month effect on VSI (both driving and resting distributions) found:
- Drive-state VSI: KW p = 0.90
- Rest-state VSI: KW p = 0.95

Both are null — there is no detectable seasonal VSI signal. Seasonal temperature variation
does not manifest in these VSI features at fleet level. This proxy is closed.

### 2.2 Cold-Start Voltage Dip Depth — V2.1 B3/B4

The cold-start voltage dip depth (VSI dip on starts preceded by ≥ 6 h rest, treated as a
thermal proxy for battery state at low ambient temperature) was tested in V2.1. It was
rejected as redundant with the incumbent `dip_depth_last90_delta` (Pearson r ≈ 0.92 –
0.94, above the 0.85 redundancy cut). Even as a temperature proxy it carries no
incremental information beyond the feature already in the modal-4 set.

### 2.3 Night-Start Fraction — V3 F4b (NOT a Temperature Proxy)

`night_start_fraction_delta90` was included in V3 as a **usage/circadian** feature only,
explicitly NOT as a temperature proxy. The spec (§4.2) and candidates JSON note this
distinction. It was tested and rejected on its own merits (MW p = 0.9029, AUROC = 0.5000).
It does not provide temperature information even as an indirect route.

---

## 3. Why Temperature Matters (and Cannot Be Ignored)

Cold-ambient-temperature conditions are physically significant for starter motor health:
- Battery internal resistance increases at low temperatures, reducing available cranking
  current and amplifying voltage dip.
- Oil viscosity increases at low temperatures, increasing cranking load on the starter motor.
- Lead-acid cold-cranking capacity (CCA at −18°C) can be 30–50% below rated capacity,
  stressing solenoid contacts.

If per-vehicle ambient temperature were available, features such as crank-voltage-dip
normalized to expected cold-crank dip (a temperature-adjusted stress index) and
cold-season start frequency could be constructed. These would be genuinely novel relative
to the existing feature set. At present, none of this is computable.

---

## 4. What Would Unlock Temperature

Two paths would make per-start ambient temperature computable:

### Path A: Per-vehicle GPS + Timestamp → Weather Archive

If the telematics system records GPS coordinates (latitude, longitude) per vehicle per day,
historical ambient temperature can be retrieved from public weather APIs (e.g., Open-Meteo,
ERA5 reanalysis) or meteorological station archives by nearest-station interpolation. This
requires:
- GPS field in the CAN/telematics log, OR
- A vehicle-to-depot registry with depot GPS coordinates.
At 5-second telemetry cadence, daily GPS snapshots are sufficient for temperature lookup.

### Path B: Onboard Ambient or Coolant Temperature CAN Channel

Many J1939-compliant ECUs expose SPN 171 (Ambient Air Temperature) or SPN 110 (Engine
Coolant Temperature) on the CAN bus. If these SPNs are logged alongside the existing 6
signals, they provide a direct per-start temperature measurement without requiring
external weather data. Coolant temperature at key-on is a particularly useful proxy for
thermal state of the starter motor and battery at the time of each crank event.

---

## 5. Conclusion

Ambient temperature cannot be reconstructed from the current SM dataset. This is a
confirmed data gap, not an engineering choice. V3 spends zero modeling effort on
temperature. The two derivable proxies are already null (seasonality) or redundant
(cold-dip). The data that would unlock this channel is specified above and is included
in the new-data roadmap (`appendix/new_data_roadmap.md`, path (c) notes).
