# V2 Model Registry and Alert Replay

## Purpose

The registry provides a single, hash-locked audit snapshot that pins:
- All input file fingerprints (sha256 per CSV)
- Production model artifacts (coefficients, scaler, Platt parameters) with their own artifact_hash
- Decision rules verbatim from v2_config.json
- Validation-of-record metrics (nested LOVO AUROC 0.9321, CI [0.8107, 0.9861])

Every historical alert can be **replayed and verified** from this pinned state, satisfying Phase D item 2 of the V2 roadmap.

## Files

| File | Description |
|------|-------------|
| `build_registry.py` | Generates `registry.json` deterministically |
| `registry.json` | The pinned registry artifact (check in after each legitimate build) |
| `replay_alert.py` | CLI replay tool |
| `REGISTRY_README.md` | This file |

## Replay Semantics (IMPORTANT)

**What replay does:**
1. Verifies every input file's sha256 against the pinned registry (INPUT DRIFT detection)
2. Verifies the production model `artifact_hash` (coefficient tamper detection)
3. Re-executes the **DECISION LAYER** from raw inputs:
   - Tier classification from walking-score k=0 probabilities
   - Heuristics H1 (momentum), H2 (consecutive RED dwell), H5 (fleet percentile)
   - Channel states from alert_policy and alert_validation CSVs
   - Alert precedence rules (A2 > H2 > RED > AMBER > GREEN)
   - Window matrix lookup
4. Diffs recomputed fields against the logged snapshot/alert rows

**What replay does NOT do:**
- Re-train the nested LOVO model (34-fold outer, inner feature selection)
- Recompute per-cut walking scores from raw telemetry
- Replace or re-derive the production model fit from scratch (it verifies the pinned fit)

The fleet_snapshot tier/prob values originated from the **walking-score engine** (LOVO per cut), not the production refit. Replay therefore pins INPUT FINGERPRINTS for the walking scores and re-executes the decision layer on top of them. The production model artifact_hash is verified to prove the pinned coefficients have not drifted.

## Audit Trail Story

```
Alert fires (fleet_snapshot.csv row)
  |
  v
Registry is built (build_registry.py)
  -> pins sha256 of all 8 input files at alert time
  -> pins production model artifact_hash (sha256 of coefficients/scaler/Platt)
  -> pins decision rules verbatim from v2_config.json
  -> registry.json committed to git (immutable audit record)
  |
  v
Audit request arrives (any future time)
  |
  v
replay_alert.py --vin <VIN> [--registry registry.json]
  -> verifies all 8 input sha256s (INPUT DRIFT detection)
  -> verifies artifact_hash (model tamper detection)
  -> re-executes decision layer from pinned inputs
  -> prints REPLAY MATCH or field-level MISMATCH table
```

## Usage

### Build (or rebuild) the registry

```sh
py -3 build_registry.py
```

Registry is written to `registry.json`. Deterministic: same inputs → identical bytes (except `generated`, which tracks fleet_snapshot mtime).

### Replay a single VIN

```sh
py -3 replay_alert.py --vin VIN10_F_SM
```

### Replay all 34 trucks

```sh
py -3 replay_alert.py --all
```

Expected output: `34/34 REPLAY MATCH`

### Replay against an alternate registry (tamper testing)

```sh
py -3 replay_alert.py --vin VIN10_F_SM --registry /path/to/old_registry.json
```

## Regenerating After a Legitimate Config Bump

When the config version is incremented (e.g., 2.1.0-B → 2.2.0):

1. Update `v2_config.json` with new parameters
2. Update `config_hash` field in `v2_config.json` by running:
   ```python
   import hashlib, json
   with open('v2_config.json', encoding='utf-8') as f:
       cfg = json.load(f)
   stripped = {k: v for k, v in cfg.items() if k != 'config_hash'}
   new_hash = hashlib.sha256(
       json.dumps(stripped, sort_keys=True, separators=(',',':'), ensure_ascii=False)
       .encode('utf-8')
   ).hexdigest()
   print(new_hash)
   ```
3. Run `py -3 build_registry.py` — aborts if config_hash mismatch
4. Commit both `v2_config.json` and the new `registry.json`

## Registry Top-Level Keys

| Key | Content |
|-----|---------|
| `schema_version` | Registry format version (1.0.0) |
| `generated` | fleet_snapshot.csv mtime (UTC) — deterministic, not wall-clock |
| `config` | config_version + config_hash (verified against v2_config.json) |
| `validation_of_record` | Nested LOVO AUROC 0.9321, CI, permutation p, calibration slope |
| `production_model` | features, impute_medians, scaler_mean/scale, ridge_coef/intercept, platt_a/b, artifact_hash |
| `input_fingerprints` | {key: {path, sha256}} for all 8 input files |
| `decision_rules` | tier_thresholds, heuristics, channels, alert_precedence, window_matrix — verbatim from config |

## Pipeline Wiring Instructions (Stage 6.5)

A parallel agent owns `V2_weekly_pipeline.py`. Add Stage 6.5 after Stage 6 (dashboard) and before Stage 7 (any downstream delivery step). Insert the following call in the pipeline's stage sequence:

```python
# Stage 6.5 — Registry snapshot (run after fleet_snapshot.csv is written)
def stage_6_5_registry(cfg: dict, config_path: Path, out_dir: Path) -> bool:
    """Rebuild registry.json to pin current input fingerprints and model artifacts."""
    import subprocess, sys
    registry_script = config_path.parent / "registry" / "build_registry.py"
    result = subprocess.run(
        [sys.executable, str(registry_script)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"[STAGE 6.5 FAIL] Registry build failed:\n{result.stderr}")
        return False
    print(f"[STAGE 6.5 OK] Registry built: {result.stdout.strip().splitlines()[-1]}")
    return True
```

And wire it into the run sequence after `stage_6_dashboard(...)`:

```python
ok_65 = stage_6_5_registry(cfg, config_path, out_dir)
if not ok_65:
    abort("Stage 6.5 registry build failed — alert cannot be considered replayable")
```
