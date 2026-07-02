import sys, json
from pathlib import Path
import numpy as np, pandas as pd
from scipy import stats
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
import _gate_core as G
import _v3_lib as L

SMROOT = L.SMROOT
OUT = SMROOT / "V3" / "features" / "out"
P = json.loads((SMROOT / "V3" / "params" / "V3_gate_params.json").read_text())
MODAL = P["modal_subset"]; SMA_DEAD = set(P["sma_dead"])
CANDS = ["dose_dip_x_starts","weakbat_cold_load","reg_instab_x_usage","sag_under_load",
         "cold_start_fraction_delta90","ged3_rate_delta90","night_start_fraction_delta90"]

def proxy_frame(order):
    wk = L.load_weekly(); px = L.build_px(); rows = []
    for v in order:
        w = wk[wk["vin_label"] == v]; w = w[w["active_days"] >= 2].sort_values("week")
        if len(w) == 0 or v not in px.index or px.loc[v].isna().any():
            rows.append({"vin_label": v, "n_weeks": np.nan, "t_start": np.nan, "span": np.nan}); continue
        weeks = w["week"].values
        rows.append({"vin_label": v, "n_weeks": float(len(w)),
                     "t_start": float(pd.Timestamp(weeks[0]).toordinal()),
                     "span": float((pd.Timestamp(weeks[-1]) - pd.Timestamp(weeks[0])).days)})
    return pd.DataFrame(rows).set_index("vin_label")

def spearman(a, b):
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 6: return np.nan
    r = stats.spearmanr(a[m], b[m])[0]
    return float(r) if np.isfinite(r) else np.nan

def main():
    mat = pd.read_csv(SMROOT / "V1.1" / "results" / "V1_1_SM_feature_matrix.csv")
    order = mat["vin_label"].tolist(); y = mat["failed"].astype(int).values

    a_modal = G.rank_auroc(G.plain_lovo(mat[MODAL].values.astype(float), y), y)
    recon = {"computed": round(float(a_modal), 4), "expected": P["reconcile_expected_nonnested"],
             "pass": bool(abs(a_modal - P["reconcile_expected_nonnested"]) <= P["reconcile_tol"])}
    if not recon["pass"]:
        print("RECONCILE FAIL", recon); sys.exit(1)

    prox = proxy_frame(order)
    mat_ext = mat.copy(); E1 = []
    for c in CANDS:
        cache = pd.read_csv(OUT / f"{c}_cache.csv")
        cmap = dict(zip(cache["vin_label"], cache[c]))
        arr = np.array([np.nan if (v in SMA_DEAD and c != "ged3_rate_delta90") else cmap.get(v, np.nan)
                        for v in order], dtype=float)
        mat_ext[c] = arr
        fv, nfv = arr[y == 1], arr[y == 0]
        fv, nfv = fv[np.isfinite(fv)], nfv[np.isfinite(nfv)]
        mw = G.mw_p(fv, nfv)
        a_raw = G.rank_auroc(np.nan_to_num(arr, nan=(np.nanmean(arr) if np.isfinite(arr).any() else 0.0)), y)
        auroc = max(a_raw, 1 - a_raw) if np.isfinite(a_raw) else np.nan
        rprx = {t: spearman(arr, prox[t].values.astype(float)) for t in ["n_weeks","t_start","span"]}
        rmod = {m: (float(pd.Series(arr).corr(mat[m])) if np.isfinite(arr).sum() >= 6 else np.nan) for m in MODAL}
        proxy_flag = any(np.isfinite(v) and abs(v) > P["proxy_leak_spearman_max"] for v in rprx.values())
        redun_flag = any(np.isfinite(v) and abs(v) >= P["corr_max_redundancy"] for v in rmod.values())
        e1_pass = bool(np.isfinite(mw) and mw <= P["alpha_mw"] and np.isfinite(auroc)
                       and auroc >= P["auroc_min"] and not proxy_flag and not redun_flag)
        E1.append({"feature": c, "n_nonnull": int(np.isfinite(arr).sum()),
                   "mw_p": round(float(mw), 4) if np.isfinite(mw) else None,
                   "auroc": round(float(auroc), 4) if np.isfinite(auroc) else None,
                   "r_proxy": {k: (round(v, 3) if np.isfinite(v) else None) for k, v in rprx.items()},
                   "r_vs_modal": {k: (round(v, 3) if np.isfinite(v) else None) for k, v in rmod.items()},
                   "proxy_flag": bool(proxy_flag), "redundancy_flag": bool(redun_flag), "e1_pass": e1_pass})

    def make_X(cols): return mat_ext[MODAL + cols].values.astype(float)
    E2 = {}
    for c in CANDS:
        a_c = G.rank_auroc(G.plain_lovo(make_X([c]), y), y)
        E2[c] = {"auroc": round(float(a_c), 4), "delta": round(float(a_c - a_modal), 4)}

    survivors = [c for c in CANDS
                 if next(e for e in E1 if e["feature"] == c)["e1_pass"] and E2[c]["delta"] >= P["e2_add_threshold"]]
    E3 = None
    if survivors:
        probs, _ = G.nested_lovo(mat_ext, y, MODAL + survivors)
        E3 = {"survivors": survivors, "nested_auroc": round(float(G.rank_auroc(probs, y)), 4),
              "baseline_nested": P["reconcile_nested"]}

    verdicts = {}
    for c in CANDS:
        e1 = next(e for e in E1 if e["feature"] == c); d = E2[c]["delta"]
        if e1["proxy_flag"] or e1["redundancy_flag"]:
            verdicts[c] = {"verdict": "REJECT", "reason": "E1 proxy/redundancy flag"}
        elif not e1["e1_pass"]:
            verdicts[c] = {"verdict": "REJECT", "reason": f"E1 fail (mw_p={e1['mw_p']}, auroc={e1['auroc']})"}
        elif d >= P["e2_add_threshold"]:
            verdicts[c] = {"verdict": "ADD", "reason": f"E2 delta=+{d}"}
        elif d > 0:
            verdicts[c] = {"verdict": "SOFT_SIGNAL", "reason": f"E1-pass, E2 delta=+{d} < +0.01"}
        else:
            verdicts[c] = {"verdict": "REJECT", "reason": f"E2 delta={d} <= 0"}

    summary = {"reconciliation": recon, "modal_nonnested_auroc": round(float(a_modal), 4),
               "n_candidates": len(CANDS), "E1": E1, "E2": E2, "E3": E3, "verdicts": verdicts}
    (OUT / "V3_gate_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({"reconcile": recon["pass"], "verdicts": {c: verdicts[c]["verdict"] for c in CANDS}}, indent=2))

if __name__ == "__main__":
    main()
