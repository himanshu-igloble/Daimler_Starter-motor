import sys, json
from pathlib import Path
import numpy as np, pandas as pd
from scipy import stats
HERE = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(HERE / "features"))
import _v3_lib as L
SMROOT = L.SMROOT
AOUT = SMROOT / "V3" / "analysis" / "out"; AOUT.mkdir(parents=True, exist_ok=True)
FOUT = SMROOT / "V3" / "features" / "out"
CANDS = ["dose_dip_x_starts","weakbat_cold_load","reg_instab_x_usage","sag_under_load",
         "cold_start_fraction_delta90","ged3_rate_delta90","night_start_fraction_delta90"]
MODAL = ["vsi_withinwk_std_ratio_30d_w","rest_vsi_p05_delta90","vsi_range_trend","dip_depth_last90_delta"]

def safe_mw(a, b):
    a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    if len(a) == 0 or len(b) == 0: return np.nan
    try:
        return float(stats.mannwhitneyu(a, b, alternative="two-sided").pvalue)
    except ValueError:
        return np.nan

def main():
    mat = pd.read_csv(SMROOT / "V1.1" / "results" / "V1_1_SM_feature_matrix.csv")
    y = mat["failed"].astype(int).values
    for c in CANDS:
        cache = pd.read_csv(FOUT / f"{c}_cache.csv")
        mat[c] = mat["vin_label"].map(dict(zip(cache["vin_label"], cache[c])))
    feats = MODAL + CANDS
    X = mat[feats].copy()
    Ximp = X.fillna(X.median(numeric_only=True)).values

    X.corr().round(3).to_csv(AOUT / "correlation_matrix.csv")

    pvals = {c: safe_mw(X[c].values[y == 1], X[c].values[y == 0]) for c in CANDS}
    ps = pd.Series(pvals).dropna().sort_values(); m = len(ps)
    bh = {k: float(min(1.0, p * m / (i + 1))) for i, (k, p) in enumerate(ps.items())}

    sk = {}
    try:
        from sklearn.feature_selection import mutual_info_classif
        from sklearn.inspection import permutation_importance
        from sklearn.ensemble import HistGradientBoostingClassifier
        from sklearn.model_selection import LeaveOneGroupOut
        from sklearn.metrics import roc_auc_score
        mi = dict(zip(feats, mutual_info_classif(Ximp, y, discrete_features=False, random_state=0).round(4).tolist()))
        gbm = HistGradientBoostingClassifier(max_depth=2, max_iter=120, l2_regularization=1.0, min_samples_leaf=5, random_state=0)
        logo = LeaveOneGroupOut(); groups = np.arange(len(y)); preds = np.zeros(len(y))
        for tr, te in logo.split(Ximp, y, groups):
            gbm.fit(Ximp[tr], y[tr]); preds[te] = gbm.predict_proba(Ximp[te])[:, 1]
        gbm_auroc = float(roc_auc_score(y, preds))
        gbm.fit(Ximp, y)
        perm = permutation_importance(gbm, Ximp, y, n_repeats=30, random_state=0)
        pi = dict(zip(feats, perm.importances_mean.round(4).tolist()))
        try:
            import shap
            expl = shap.TreeExplainer(gbm); sv = expl.shap_values(Ximp)
            arr = sv[1] if isinstance(sv, list) else sv
            shap_summary = dict(zip(feats, np.abs(arr).mean(axis=0).round(4).tolist()))
        except Exception as e:
            shap_summary = {"error": str(e)}
        sk = {"sklearn_available": True, "mutual_info": mi, "gbm_lovo_auroc": round(gbm_auroc, 4),
              "permutation_importance": pi, "shap_mean_abs": shap_summary}
    except ImportError as e:
        sk = {"sklearn_available": False, "error": str(e),
              "note": "MI/GBM/permutation/SHAP skipped — sklearn not in py -3"}

    gate = json.loads((FOUT / "V3_gate_summary.json").read_text())
    survivors = [e["feature"] for e in gate["E1"] if e["e1_pass"]]
    fold_safe = "n/a - no E1 survivors" if not survivors else {"survivors": survivors}

    out = {"mw_p": {k: (round(v, 4) if np.isfinite(v) else None) for k, v in pvals.items()},
           "bh_fdr": {k: round(v, 4) for k, v in bh.items()},
           "baseline_nonnested": 0.9357, "baseline_nested": 0.9321,
           "fold_safe_reverify": fold_safe, "sklearn_block": sk,
           "note": "GBM AUROC (if present) is a SCREEN-GRADE model-class probe (n=34, high variance); not a shipped model."}
    (AOUT / "V3_validation.json").write_text(json.dumps(out, indent=2))
    print(json.dumps({"gbm_lovo_auroc": sk.get("gbm_lovo_auroc"), "sklearn": sk.get("sklearn_available"),
                      "bh_fdr_min": (min(out["bh_fdr"].values()) if out["bh_fdr"] else None)}, indent=2))

if __name__ == "__main__":
    main()
