# E1: VIN-level clustering on artifact-free feature subset (n=34 -- suggestive only)
# Anti-leakage: drop vsi_dominant_freq (1/n_weeks artifact); check every PC/cluster vs n_weeks & t_start.
import glob, json
import numpy as np, pandas as pd, polars as pl
from scipy.stats import spearmanr, mannwhitneyu, kruskal
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.cluster import AgglomerativeClustering, DBSCAN, SpectralClustering
from sklearn.metrics import adjusted_rand_score
from scipy.cluster.hierarchy import linkage, fcluster

ROOT = "D:/Daimler-starter_motor_alternator_battery/STARTER MOTOR"
OUT = f"{ROOT}/V1.1/discovery/out"
rng = np.random.default_rng(42)

fm = pd.read_csv(f"{ROOT}/results/V1_SM_feature_matrix.csv")
fm = fm.sort_values("vin_label").reset_index(drop=True)

# ---- leakage axes from weekly caches ----
rows = []
for f in glob.glob(f"{ROOT}/cache/weekly/V1_SM_weekly_*.parquet"):
    w = pl.read_parquet(f)
    obs = w.filter(pl.col("n_rows") > 0)
    rows.append(dict(
        vin_label=w["vin_label"][0],
        n_weeks=obs.height,
        t_start=obs["week"].min(),
        t_end=obs["week"].max(),
        sma_obs_frac=float(obs["sma_obs_rows"].sum() / max(obs["n_rows"].sum(), 1)),
    ))
meta = pd.DataFrame(rows).sort_values("vin_label").reset_index(drop=True)
meta["t_start_ord"] = pd.to_datetime(meta["t_start"]).map(pd.Timestamp.toordinal)
meta["sma_dead"] = (meta["sma_obs_frac"] < 0.01).astype(int)
assert (meta["vin_label"].values == fm["vin_label"].values).all()
print("SMA-dead cohort:", sorted(meta.loc[meta.sma_dead == 1, "vin_label"]))

SILENT_GAP = {"VIN1_F_SM": 72, "VIN4_F_SM": 97, "VIN5_F_SM": 32, "VIN8_F_SM": 37, "VIN9_F_SM": 142}
meta["silent_gap"] = meta["vin_label"].isin(SILENT_GAP).astype(int)

# ---- artifact-free feature subset ----
BANNED = ["vsi_dominant_freq"]  # proven 1/n_weeks artifact (audit B 1.4)
feat_cols = [c for c in fm.columns if c not in ("vin_label", "failed") + tuple(BANNED)]
# pre-screen: any remaining feature with |spearman| vs n_weeks or t_start > 0.6 gets flagged (kept but reported)
contam = []
for c in feat_cols:
    x = fm[c].values
    m = ~np.isnan(x)
    r_nw = spearmanr(x[m], meta["n_weeks"].values[m])[0]
    r_ts = spearmanr(x[m], meta["t_start_ord"].values[m])[0]
    contam.append(dict(feature=c, r_n_weeks=round(r_nw, 3), r_t_start=round(r_ts, 3),
                       flag="WATCH" if max(abs(r_nw), abs(r_ts)) > 0.45 else ""))
contam = pd.DataFrame(contam)
contam.to_csv(f"{OUT}/E1_feature_leakage_contamination.csv", index=False)
print("\nfeatures |r|>0.45 vs leakage axes:")
print(contam[contam.flag == "WATCH"].to_string(index=False))

X = fm[feat_cols].copy()
X = X.fillna(X.median(numeric_only=True))
Xs = StandardScaler().fit_transform(X.values)

# ---- PCA ----
pca = PCA(n_components=min(10, Xs.shape[1]), random_state=42)
Z = pca.fit_transform(Xs)
ev = pca.explained_variance_ratio_
print("\nPCA variance explained:", np.round(ev[:6], 3), "cum:", np.round(np.cumsum(ev[:6]), 3))
load = pd.DataFrame(pca.components_[:4].T, index=feat_cols, columns=["PC1", "PC2", "PC3", "PC4"])
load.round(3).to_csv(f"{OUT}/E1_pca_loadings.csv")
for pc in range(4):
    top = load.iloc[:, pc].abs().sort_values(ascending=False).head(5)
    print(f"PC{pc+1} top loadings:", {k: round(load.iloc[:, pc][k], 2) for k in top.index})

# PC scores vs labels and leakage axes
pc_checks = []
for pc in range(4):
    z = Z[:, pc]
    r_f = spearmanr(z, fm["failed"])[0]
    r_nw = spearmanr(z, meta["n_weeks"])[0]
    r_ts = spearmanr(z, meta["t_start_ord"])[0]
    r_cd = spearmanr(z, meta["sma_dead"])[0]
    pc_checks.append(dict(pc=f"PC{pc+1}", var_expl=round(ev[pc], 3), r_failed=round(r_f, 3),
                          r_n_weeks=round(r_nw, 3), r_t_start=round(r_ts, 3), r_sma_dead=round(r_cd, 3)))
pcc = pd.DataFrame(pc_checks)
pcc.to_csv(f"{OUT}/E1_pc_vs_axes.csv", index=False)
print("\nPC vs axes:\n", pcc.to_string(index=False))

# ---- hierarchical (ward) ----
Lnk = linkage(Xs, method="ward")
print("\nWard merge heights (last 6):", np.round(Lnk[-6:, 2], 2))
res = []
for k in [2, 3, 4, 5]:
    lab = fcluster(Lnk, k, criterion="maxclust")
    ari_f = adjusted_rand_score(fm["failed"], lab)
    ari_c = adjusted_rand_score(meta["sma_dead"], lab)
    ari_g = adjusted_rand_score(meta["silent_gap"], lab)
    # leakage check: do clusters separate on n_weeks / t_start?
    kw_nw = kruskal(*[meta["n_weeks"][lab == g] for g in np.unique(lab)])[1] if len(np.unique(lab)) > 1 else np.nan
    kw_ts = kruskal(*[meta["t_start_ord"][lab == g] for g in np.unique(lab)])[1] if len(np.unique(lab)) > 1 else np.nan
    sizes = np.bincount(lab)[1:]
    res.append(dict(method=f"ward_k{k}", sizes=str(list(sizes)), ari_failed=round(ari_f, 3),
                    ari_sma_dead=round(ari_c, 3), ari_silent_gap=round(ari_g, 3),
                    kw_p_n_weeks=round(kw_nw, 4), kw_p_t_start=round(kw_ts, 4)))
    fm[f"ward_k{k}"] = lab

# ---- DBSCAN (eps from 4-NN distance elbow) ----
from sklearn.neighbors import NearestNeighbors
d4 = np.sort(NearestNeighbors(n_neighbors=5).fit(Xs).kneighbors(Xs)[0][:, -1])
for eps in [np.percentile(d4, 50), np.percentile(d4, 75), np.percentile(d4, 90)]:
    lab = DBSCAN(eps=eps, min_samples=3).fit_predict(Xs)
    n_noise = (lab == -1).sum()
    n_cl = len(set(lab)) - (1 if -1 in lab else 0)
    ari_f = adjusted_rand_score(fm["failed"], lab) if n_cl > 0 else np.nan
    res.append(dict(method=f"dbscan_eps{eps:.2f}", sizes=f"clusters={n_cl},noise={n_noise}",
                    ari_failed=round(ari_f, 3) if ari_f == ari_f else "", ari_sma_dead="", ari_silent_gap="",
                    kw_p_n_weeks="", kw_p_t_start=""))

# ---- spectral ----
for k in [2, 3]:
    lab = SpectralClustering(n_clusters=k, affinity="nearest_neighbors", n_neighbors=8,
                             random_state=42, assign_labels="kmeans").fit_predict(Xs)
    ari_f = adjusted_rand_score(fm["failed"], lab)
    ari_c = adjusted_rand_score(meta["sma_dead"], lab)
    kw_nw = kruskal(*[meta["n_weeks"][lab == g] for g in np.unique(lab)])[1]
    res.append(dict(method=f"spectral_k{k}", sizes=str(list(np.bincount(lab))), ari_failed=round(ari_f, 3),
                    ari_sma_dead=round(ari_c, 3), ari_silent_gap=round(adjusted_rand_score(meta['silent_gap'], lab), 3),
                    kw_p_n_weeks=round(kw_nw, 4), kw_p_t_start=""))
    fm[f"spectral_k{k}"] = lab

resdf = pd.DataFrame(res)
resdf.to_csv(f"{OUT}/E1_cluster_results.csv", index=False)
print("\nCLUSTER RESULTS:\n", resdf.to_string(index=False))

# membership table for the chosen views
keep = ["vin_label", "failed", "ward_k2", "ward_k3", "ward_k4", "spectral_k2", "spectral_k3"]
mem = fm[keep].merge(meta[["vin_label", "n_weeks", "t_start", "sma_dead", "silent_gap"]], on="vin_label")
mem.to_csv(f"{OUT}/E1_cluster_membership.csv", index=False)

# ward_k3 composition detail
for k in [2, 3]:
    print(f"\nward_k{k} composition:")
    print(mem.groupby(f"ward_k{k}").agg(n=("vin_label", "size"), n_failed=("failed", "sum"),
                                        n_sma_dead=("sma_dead", "sum"), med_n_weeks=("n_weeks", "median"),
                                        med_t_start=("t_start", "median")).to_string())
meta.to_csv(f"{OUT}/E1_vin_meta.csv", index=False)
print("\nE1 done")
