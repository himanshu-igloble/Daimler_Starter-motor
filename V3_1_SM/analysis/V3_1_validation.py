# STARTER MOTOR/V3.1/analysis/V3_1_validation.py
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "features"))
import _gate_core as G
import _v31_lib as L

OUT = HERE / "out"; OUT.mkdir(exist_ok=True)
GATE = L.V31_OUT / "V3_1_gate_summary.json"
assert GATE.exists(), "DISCIPLINE VIOLATION: run the gate (Task 9) before any catalog label stats"
S = json.loads(GATE.read_text())

# BH-FDR over the E1 MW p-values
e1 = [e for e in S["E1"] if e["mw_p"] is not None]
p = np.array([e["mw_p"] for e in e1]); order = np.argsort(p); n = len(p)
adj = np.empty(n); prev = 1.0
for rank_i, idx in list(enumerate(order))[::-1]:
    prev = min(prev, p[idx] * n / (rank_i + 1)); adj[idx] = prev
bh = {e1[i]["feature"]: {"p_raw": float(p[i]), "p_bh": round(float(adj[i]), 4)} for i in range(n)}

# correlation matrix: candidates + modal
mat = pd.read_csv(L.SMROOT / "V1.1" / "results" / "V1_1_SM_feature_matrix.csv")
y = mat["failed"].astype(int).values
cols = {m: mat[m].values.astype(float) for m in L.GP["modal_subset"]}
for c in [e["feature"] for e in S["E1"]]:
    cache = pd.read_csv(L.V31_OUT / f"{c}_cache.csv")
    cols[c] = np.array([dict(zip(cache["vin_label"], cache[c])).get(v, np.nan) for v in mat["vin_label"]])
cm = pd.DataFrame(cols).corr(method="pearson")
cm.to_csv(OUT / "correlation_matrix.csv")

# EXPLORATORY catalog stats (post-gate only; never feeds V3.1 gating)
cat = pd.read_csv(L.V31_OUT / "V3_1_SM_catalog.csv")
rows = []
for c in [c for c in cat.columns if c != "vin_label"]:
    arr = cat[c].values.astype(float)
    fv, nfv = arr[y == 1], arr[y == 0]
    fv, nfv = fv[np.isfinite(fv)], nfv[np.isfinite(nfv)]
    if len(fv) >= 3 and len(nfv) >= 3:
        a = G.rank_auroc(np.nan_to_num(arr, nan=np.nanmean(arr)), y)
        rows.append({"feature": c, "n_nonnull": int(np.isfinite(arr).sum()),
                     "mw_p": round(float(G.mw_p(fv, nfv)), 4), "auroc_oriented": round(float(max(a, 1 - a)), 4),
                     "status": "EXPLORATORY_POST_GATE"})
pd.DataFrame(rows).sort_values("mw_p").to_csv(OUT / "catalog_exploratory_stats.csv", index=False)

(OUT / "V3_1_validation.json").write_text(json.dumps({
    "baseline_nonnested": S["modal_nonnested_auroc"], "baseline_nested": L.GP["reconcile_nested"],
    "bh_fdr": bh, "min_bh_p": round(float(adj.min()), 4) if n else None,
    "verdicts": S["verdicts"]}, indent=2))
print(json.dumps({"min_bh_p": round(float(adj.min()), 4) if n else None}, indent=2))
