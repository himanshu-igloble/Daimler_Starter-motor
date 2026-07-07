# SM Horizon + Window Rules — V1.1 — Deployable Artifact

Loadable packaging of the frozen starter-motor **detection-horizon** and
**alert-channel** rules for V1.1.

> **This is NOT a fitted ML model.** `is_ml_model = False`. It is a deployable
> wrapper around two frozen, deterministic objects — no coefficients are learned
> here. It **replaces per-truck RUL** for the starter motor, because per-truck
> day-precision RUL is *mathematically closed* at n=34 (34 trucks: 14 failed /
> 20 non-failed). Instead of a fake day-count, the deployment ships a validated
> **detection window** plus **alert channels** with their historical leads.

## What it encodes

1. **Detection horizon.** `k* = 10 weeks` (`k_star_sustained`), i.e. a
   **~70-day** validated detection window. The AUROC-vs-lead-week decay curve is
   embedded (`auroc_by_week`): AUROC is **0.9357** at k=0 and stays *in spec*
   through week **16**, decaying as the lead grows.
2. **Three alert channels** (first-to-fire wins), with per-VIN validated
   first-fire leads embedded for reference:
   - `persistence` — E3 sustained-risk persistence
   - `A1_crank_burst` — crank-burst rate spike
   - `A2_battery_cascade` — battery-voltage cascade

## The rule

`classifier RED` → **schedule maintenance within the k*=10-week (~70-day)
detection window**; the alert-channel first-fire gives the observed historical
lead. `AMBER` → watch (re-score); `GREEN` → routine. Tier bands cross-ref the
classifier: GREEN < 0.35 ≤ AMBER < 0.55 ≤ RED.

## Files
| File | What it is |
|---|---|
| `V1_1_SM_horizon_window_bundle.joblib` | plain dict: horizon table + k*, alert channels + per-VIN policy, tier bands, validated-lead summary, honest caveat, environment. No fitted estimator, no custom classes. |
| `V1_1_SM_predict.py` | loader + CLI (`py -3 V1_1_SM_predict.py --tier RED --k-weeks 0`) |
| `V1_1_SM_horizon_curve.csv` | provenance copy of the frozen horizon curve (k=0..26) |
| `V1_1_SM_alert_policy.csv` | provenance copy of the frozen per-VIN alert policy (34 trucks) |
| `V1_1_SM_rules_verification.json` | R1–R3 reconciliation gate results |
| `V1_1_SM_rules_MANIFEST.json` | SHA256 of every file + inputs + env + git commit |

## Quick start
```
py -3 V1_1_SM_predict.py --tier RED --k-weeks 0
```
```python
from V1_1_SM_predict import load_bundle, maintenance_window, horizon_auroc, channel_lead_summary
b = load_bundle()
maintenance_window("RED", b)      # -> action 'schedule within', 70 days / 10 weeks
horizon_auroc(0, b)               # -> 0.9357
channel_lead_summary(b)           # -> median/min/max validated first-fire lead days
```

## Validated alert leads (historical — not guarantees)
Across the **13 of 14** failed trucks that fired a channel (one failed truck was
alert-silent), first-fire lead vs the failure end-date is **median 168 d**
(min **28 d**, max **392 d**, mean **189.0 d**). These are *historical
validation observations*, not forward guarantees.

## Honesty notes
- Deterministic rules + a validated horizon constant, **not a fitted model**.
  No AUROC is (re)fit here; 0.9357 and k*=10 are read from the frozen
  `V1_1_SM_horizon_curve.csv` and reconciled at package time.
- Per-truck day-precision RUL is **closed at n=34** — this window/channel design
  is the honest replacement, not a regression that pretends to predict a date.
- The per-VIN leads describe *what happened on the 34-truck validation fleet*.
  They calibrate expectations for the window; they do not promise a specific
  lead on a new truck.
- Rebuild + re-verify:
  `py -3 "STARTER MOTOR/V1.1/src/V1_1_SM_package_rules.py"`, then
  `py -3 "STARTER MOTOR/V1.1/src/V1_1_SM_rules_smoketest.py"`.
