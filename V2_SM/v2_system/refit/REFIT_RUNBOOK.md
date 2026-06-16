# SM V2 Refit Runbook

**System:** Starter Motor V2 — Predictive Maintenance  
**Harness:** `STARTER MOTOR/V2_program/v2_system/refit/run_refit.py`  
**Last updated:** 2026-06-12

---

## 1. When to Refit

Refit is triggered by any one of the following conditions:

| Condition | Threshold | How detected |
|-----------|-----------|--------------|
| New failure labels | >= 5 new confirmed failures added to the label set | `--labels` argument; S0 checks count automatically |
| Calibration drift | Slope outside [0.5, 2.0] on live deployment OOF estimates | G3 gate in weekly monitor output; pass `--force` to harness |
| Population shift | PSI > 0.2 on any feature in the current model pool | PSI computed by `monitors/governance_monitors.py`; pass `--force` |

Refit is NOT triggered by:
- Trucks aging or accumulating new weeks of telemetry alone
- Changes to alert thresholds or heuristics (H1/H2/H5 are config, not model)
- Watchlist additions

---

## 2. How to Run

### 2a. Self-test (identity check, ~20 min, no new data needed)

```bash
py -3 "STARTER MOTOR/V2_program/v2_system/refit/run_refit.py" --self-test --perm-n 20
```

Expected: All S1–S3 gates PASS, nested AUROC = 0.9321 ± 0.002.  
Use for: CI pipeline smoke test, onboarding verification, post-merge sanity check.

### 2b. Production refit with new failure labels

```bash
py -3 "STARTER MOTOR/V2_program/v2_system/refit/run_refit.py" \
    --labels "path/to/updated_labels.csv" \
    --perm-n 200
```

The labels CSV must have a `VIN` column. New VINs not in the baseline
`V1.1/audit/probe1_labels_per_vin.csv` are counted as new failures.

If refit is triggered by calibration slope or PSI (not label count), use `--force`:

```bash
py -3 "STARTER MOTOR/V2_program/v2_system/refit/run_refit.py" \
    --labels "path/to/labels.csv" \
    --perm-n 200 --force
```

### 2c. Runtime budget

| Stage | Expected wall-clock |
|-------|-------------------|
| S0 trigger check | < 5 s |
| S1 feature build | ~60 s |
| S2 nested LOVO (main) | ~2–3 min |
| S2 permutation (N=200) | ~25 min |
| S3 gates | < 60 s |
| S4 comparison report | < 10 s |
| S5 artifact write | < 10 s |
| **Total (perm-n 200)** | **~30 min** |
| **Self-test (perm-n 20)** | **~5 min** |

If S1 alone exceeds 10 minutes, check Polars lazy usage — the weekly parquets
should load in < 30 s on the project machine.

---

## 3. Reviewing the Comparison Report

All artifacts land in `refit/out/refit_<UTCtimestamp>/`:

```
refit/out/refit_20260612T120000Z/
  feature_matrix.csv           10-feature matrix (34 rows)
  feature_matrix_L40control.csv  L40-clipped control matrix
  feature_admissibility.csv    per-feature admissibility audit
  predictions.csv              per-VIN OOF probs + tiers
  model_spec.json              full protocol + headline metrics
  gates.json                   G1–G6 verdicts
  comparison_report.md         human-readable delta vs baseline
  run.log                      timestamped stage output
```

### Checklist before promotion

Open `comparison_report.md` and verify each item:

- [ ] **Nested AUROC >= baseline** or delta is within bootstrap CI overlap  
- [ ] **G1 PASS** — fixed-L40 control drop <= 0.05 (confirms no observation-length leak)  
- [ ] **G6 PASS** — zero banned-token hits in winner subset features  
- [ ] **G3 slope in [0.5, 2.0]** — if outside, ship tiers only (no probabilities)  
- [ ] **Top movers review** — scroll the per-VIN delta table; flag any NF truck
  whose prob_recal jumped > 0.15 (possible false-alarm amplification)  
- [ ] **Subset change** (if any) — requires domain-level justification; confirm the
  removed feature is inadmissible or degraded, not just unlucky in this fold  
- [ ] **Restatement note** drafted (see Section 4 below)  

---

## 4. How to Promote (Manual Config Bump)

**Never deploy by editing config.json directly from the refit output. Always follow this sequence:**

### Step 1 — Write the restatement note

Create a dated file in `docs/`:
```
docs/YYYY-MM-DD-HH-MM-SS-sm-v2-refit-<version>.md
```
Include:
- Trigger reason (N new labels / calibration drift / PSI)
- Summary of metric deltas (AUROC, slope, Brier)
- Subset change and justification (if applicable)
- Gate verdicts
- Decision: PROMOTE / NO-CHANGE / INVESTIGATE

### Step 2 — Update `v2_config.json`

Edit `STARTER MOTOR/V2_program/v2_system/v2_config.json`:

```json
"config_version": "<bump minor version>",
"model": {
  "features": ["<new modal subset>"],
  "validation_of_record": {
    "auroc_nested": <refit value>,
    "bootstrap_95ci_N200": [<lo>, <hi>],
    "permutation_p": <value>,
    "permutation_N": <N used>,
    "calibration_slope": <slope>,
    "brier_score": <brier>
  }
}
```

### Step 3 — Recompute and update the config hash

```bash
py -3 -c "
import json, hashlib
with open('STARTER MOTOR/V2_program/v2_system/v2_config.json') as f:
    raw = f.read()
# remove the hash line first, then hash the remainder
cfg = json.loads(raw)
del cfg['config_hash']
canonical = json.dumps(cfg, indent=2, sort_keys=True)
print(hashlib.sha256(canonical.encode()).hexdigest())
"
```

Insert the printed hash into `config_hash` field.

### Step 4 — Commit and tag

```bash
git add "STARTER MOTOR/V2_program/v2_system/v2_config.json"
git add "docs/<restatement-note>.md"
git commit -m "feat(v2-sm-refit): promote model to v<N> — AUROC <X>"
git tag v2.<N>-sm-refit-<date>
```

---

## 5. Worked Example: V1 → V1.1 Restatement

This is the canonical prior refit for reference.

**Trigger:** Admissibility audit (X1) found vsi_dominant_freq leaked observation
length — it was added to the banned-feature list. Full re-run with V1.1 10-feature
pool under the same nested protocol.

**Key metric changes:**

| Metric | V1 | V1.1 | Delta |
|--------|-----|------|-------|
| Nested AUROC | 0.8929 | 0.9321 | +0.0392 |
| Calibration slope | n/a (tiers only) | 0.86 | — |
| Winner subset | 4 features (incl. vsi_dominant_freq) | 4 features (clean pool) | different |
| G6 PASS | No (banned freq feature) | Yes | |

**Decision:** PROMOTE. The improvement was attributable to removing the leaking
feature, not optimistic model search. V1.1 was deployed as the new
validation-of-record with the restatement evidence published in:
`STARTER MOTOR/V1.1/audit/C_model_audit.md` (V1 restated 0.9214 → 0.8929, optimism
+0.0285 disclosed) and `STARTER MOTOR/V1.1/reports/V1_1_SM_comparison_report.md`
(full V1 vs V1.1 comparison table).

**Key lesson:** A refit showing AUROC *increase* after removing a feature is
a diagnostic signal of removed leakage, not overfitting — check G1 first.

---

## 6. Rollback

If a promoted refit turns out to produce worse live alerts:

1. Restore the previous `v2_config.json` from git history:
   ```bash
   git checkout <prior-tag> -- "STARTER MOTOR/V2_program/v2_system/v2_config.json"
   ```
2. Publish a rollback note in `docs/` explaining what was observed and why rollback
   was preferred over a new refit.
3. Re-run `V2_weekly_pipeline.py` — it reads config on startup, no model files to swap.
4. The rolled-back refit artifacts remain in `refit/out/` for audit; do not delete them.

---

## 7. Governance Reminders

- **NEVER AUTO-DEPLOY**: the harness always ends with the manual-review banner
- **Banned feature classes** (G6 enforced automatically):
  - observation_length, gap_counts, calendar_position,
    periodogram 1/n artifacts (vsi_dominant_freq family)
- **VIN independence**: ALT and SM VINs are different physical trucks.
  Never cross-reference alternator and starter motor VIN numbers.
- **Trigger count is a floor, not a target**: if only 3 new failures arrive but
  calibration slope is 0.3, use `--force` and document the reason.
- **Permutation count** does not affect the AUROC point estimate; N=20 is only
  for plumbing verification. Production refits should use N >= 200.

---

*End of runbook. For questions about the harness internals, see docstrings in*
*`run_refit.py` and the source attribution comments pointing to X1/X2 origins.*
