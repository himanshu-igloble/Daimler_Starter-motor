"""
G2_sequence_probes.py — Agent G, V1.1 discovery.

Honest small-n sequence-representation probes, all truck-level LOVO:
  (a) PCA embedding of aligned last-40-masked-week windows of vsi_drive_std
      and vsi_drive_mean (per-VIN z-scored = shape only) -> logistic LOVO.
      PCA refit inside every LOVO train fold (no transform leakage).
      Leak audit: full-data PC scores vs n_weeks_masked / t_start / span_days.
  (b) Functional summaries: per-VIN linear+quadratic trend coefficients on the
      z-scored window (a 2-parameter "sequence model") -> Ridge LOVO.
  (c) Distance-based: Euclidean + (1 - Pearson r) distance matrices on the
      aligned z-scored windows -> 1-NN margin LOVO + kernel-PCA(RBF) probe.
  (e) Empirical capacity demo: tiny LSTM (h=2, 35 params — already 25x over
      the EPV-10 budget) trained per LOVO fold with torch, 3 seeds.

Window alignment: last L=40 masked weeks (active_days>=2). VINs with fewer
masked weeks are linearly resampled to the 40-point grid AFTER z-scoring, so
no probe ingests raw sequence length. Residual length leakage is audited.

Bootstrap: VIN-level resampling (1000x) of out-of-fold scores for 95% CIs.

Outputs: STARTER MOTOR/V1.1/discovery/out/G2_probe_results.csv
         STARTER MOTOR/V1.1/discovery/out/G2_pca_leak_audit.csv
Run: py -3 G2_sequence_probes.py
"""
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.preprocessing import StandardScaler
import warnings
warnings.filterwarnings("ignore")

ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR")
OUT = ROOT / "V1.1" / "discovery" / "out"
OUT.mkdir(parents=True, exist_ok=True)
L = 40
RNG = np.random.default_rng(42)
N_BOOT = 1000
BASELINE = 0.893  # V1 nested-LOVO Ridge 4-feature (C1 audit)

# ── Load ─────────────────────────────────────────────────────────────────────
wk_all = pd.concat([pd.read_parquet(f) for f in sorted((ROOT / "cache/weekly").glob("*.parquet"))],
                   ignore_index=True)
wk_all["week"] = pd.to_datetime(wk_all["week"])
fm = pd.read_csv(ROOT / "results" / "V1_SM_feature_matrix.csv")
vins = fm["vin_label"].tolist()
y = fm["failed"].values.astype(int)

meta = {}
def build_window(vin, col):
    w = wk_all[wk_all["vin_label"] == vin]
    wm = w[w["active_days"] >= 2].sort_values("week")
    v = wm[col].values.astype(float)
    v = pd.Series(v).interpolate(limit_direction="both").values
    meta.setdefault(vin, {})["n_weeks_masked"] = len(wm)
    meta[vin]["t_start_ord"] = wm["week"].min().toordinal()
    meta[vin]["span_days"] = (wm["week"].max() - wm["week"].min()).days
    seg = v[-L:] if len(v) >= L else v
    mu, sd = np.nanmean(seg), np.nanstd(seg)
    z = (seg - mu) / sd if sd > 0 else seg * 0.0
    if len(z) < L:  # shape-preserving resample to the fixed grid (no length info)
        z = np.interp(np.linspace(0, len(z) - 1, L), np.arange(len(z)), z)
    return z

X_std = np.vstack([build_window(v, "vsi_drive_std") for v in vins])    # (34, 40)
X_mean = np.vstack([build_window(v, "vsi_drive_mean") for v in vins])  # (34, 40)
n_weeks = np.array([meta[v]["n_weeks_masked"] for v in vins], float)
t_start = np.array([meta[v]["t_start_ord"] for v in vins], float)
span = np.array([meta[v]["span_days"] for v in vins], float)
print(f"Aligned windows built: {X_std.shape}; VINs needing resample (<{L} masked wks): "
      f"{int((n_weeks < L).sum())} ({', '.join(v for v in vins if meta[v]['n_weeks_masked'] < L)})")


def rank_auroc(scores, labels):
    m = np.isfinite(scores)
    s, l = np.asarray(scores)[m], np.asarray(labels)[m]
    if l.sum() == 0 or (1 - l).sum() == 0:
        return np.nan
    pos, neg = s[l == 1], s[l == 0]
    u = sum((neg < p).sum() + 0.5 * (neg == p).sum() for p in pos)
    return u / (len(pos) * len(neg))


def boot_ci(scores, labels, n=N_BOOT):
    scores, labels = np.asarray(scores), np.asarray(labels)
    vals = []
    for _ in range(n):
        idx = RNG.integers(0, len(labels), len(labels))
        a = rank_auroc(scores[idx], labels[idx])
        if np.isfinite(a):
            vals.append(a)
    return (np.percentile(vals, 2.5), np.percentile(vals, 97.5), len(vals))


results = []
def record(name, scores, note=""):
    a = rank_auroc(scores, y)
    lo, hi, nv = boot_ci(scores, y)
    results.append({"probe": name, "lovo_auroc": round(a, 4),
                    "ci95_lo": round(lo, 4), "ci95_hi": round(hi, 4),
                    "n_boot_valid": nv, "vs_baseline_0.893": round(a - BASELINE, 4),
                    "note": note})
    print(f"  {name:<46} AUROC={a:.4f}  CI95=[{lo:.3f},{hi:.3f}]  d_base={a-BASELINE:+.3f}")
    return a


# ── (a) PCA embedding, PCA refit per LOVO fold ──────────────────────────────
print("\n(a) PCA-as-linear-autoencoder probes (k=3 components, LOVO-refit):")
def pca_lovo(X, k=3):
    oof = np.zeros(len(y))
    for i in range(len(y)):
        tr = np.ones(len(y), bool); tr[i] = False
        pca = PCA(n_components=k, random_state=0).fit(X[tr])
        Ztr, Zte = pca.transform(X[tr]), pca.transform(X[~tr])
        clf = LogisticRegression(C=1.0, max_iter=2000).fit(Ztr, y[tr])
        oof[i] = clf.predict_proba(Zte)[0, 1]
    return oof

oof = pca_lovo(X_std);  record("a1 PCA3(vsi_drive_std) + logistic", oof)
oof = pca_lovo(X_mean); record("a2 PCA3(vsi_drive_mean) + logistic", oof)
oof = pca_lovo(np.hstack([X_std, X_mean])); record("a3 PCA3(std||mean concat) + logistic", oof)

# Leak audit: full-data PCA scores vs leakage proxies
audit_rows = []
for label, X in (("vsi_drive_std", X_std), ("vsi_drive_mean", X_mean)):
    pca = PCA(n_components=3, random_state=0).fit(X)
    Z = pca.transform(X)
    for j in range(3):
        r_n = stats.spearmanr(Z[:, j], n_weeks)[0]
        r_t = stats.spearmanr(Z[:, j], t_start)[0]
        r_s = stats.spearmanr(Z[:, j], span)[0]
        a_pc = rank_auroc(Z[:, j], y)
        audit_rows.append({"matrix": label, "pc": j + 1,
                           "explained_var": round(pca.explained_variance_ratio_[j], 4),
                           "auroc_vs_label": round(max(a_pc, 1 - a_pc), 4),
                           "spearman_n_weeks": round(r_n, 3),
                           "spearman_t_start": round(r_t, 3),
                           "spearman_span_days": round(r_s, 3),
                           "leak_flag": "LEAK" if max(abs(r_n), abs(r_t), abs(r_s)) >= 0.5
                                        else ("watch" if max(abs(r_n), abs(r_t), abs(r_s)) >= 0.4 else "ok")})
aud = pd.DataFrame(audit_rows)
print("\nPCA leak audit (full-data PC scores vs leakage proxies):")
print(aud.to_string(index=False))
aud.to_csv(OUT / "G2_pca_leak_audit.csv", index=False)

# ── (b) Functional summaries: linear + quadratic trend coefficients ─────────
print("\n(b) Functional trend-coefficient probes:")
def trend_feats(X):
    xg = np.linspace(0, 1, L)
    F = np.zeros((len(X), 4))
    for i, z in enumerate(X):
        c2, c1, _ = np.polyfit(xg, z, 2)   # quadratic
        s1 = np.polyfit(xg, z, 1)[0]       # linear slope
        s_last = np.polyfit(xg[-8:], z[-8:], 1)[0]  # slope of final 8 wks
        F[i] = [s1, c1, c2, s_last]
    return F

def ridge_lovo(F):
    oof = np.zeros(len(y))
    for i in range(len(y)):
        tr = np.ones(len(y), bool); tr[i] = False
        sc = StandardScaler().fit(F[tr])
        m = Ridge(alpha=1.0).fit(sc.transform(F[tr]), y[tr])
        oof[i] = m.predict(sc.transform(F[~tr]))[0]
    return oof

oof = ridge_lovo(trend_feats(X_std));  record("b1 lin+quad+final8 slopes (std) + Ridge", oof)
oof = ridge_lovo(trend_feats(X_mean)); record("b2 lin+quad+final8 slopes (mean) + Ridge", oof)
oof = ridge_lovo(np.hstack([trend_feats(X_std), trend_feats(X_mean)]))
record("b3 trend coeffs (std+mean, 8 feats) + Ridge", oof)

# ── (c) Distance-based: 1-NN margin + kernel-PCA ────────────────────────────
print("\n(c) Distance-based probes:")
def dist_mats(X):
    n = len(X)
    De = np.sqrt(((X[:, None, :] - X[None, :, :]) ** 2).sum(-1))
    C = np.corrcoef(X)
    Dc = 1.0 - C
    return De, Dc

for label, X in (("std", X_std), ("mean", X_mean)):
    De, Dc = dist_mats(X)
    for dlab, D in (("eucl", De), ("1-corr", Dc)):
        # 1-NN margin: closer to nearest failed than nearest NF among train fold
        oof = np.zeros(len(y))
        for i in range(len(y)):
            tr = np.ones(len(y), bool); tr[i] = False
            d = D[i][tr]; yt = y[tr]
            oof[i] = d[yt == 0].min() - d[yt == 1].min()   # >0 -> failed-like
        record(f"c {dlab} 1-NN margin ({label})", oof)
    # kernel-PCA probe on RBF of Euclidean distances (gamma from train median)
    oof = np.zeros(len(y))
    for i in range(len(y)):
        tr = np.ones(len(y), bool); tr[i] = False
        med = np.median(De[tr][:, tr][np.triu_indices(tr.sum(), 1)])
        K_tr = np.exp(-(De[tr][:, tr] / med) ** 2)
        K_te = np.exp(-(De[~tr][:, tr] / med) ** 2)
        from sklearn.decomposition import KernelPCA
        kp = KernelPCA(n_components=3, kernel="precomputed").fit(K_tr)
        Ztr, Zte = kp.transform(K_tr), kp.transform(K_te)
        clf = LogisticRegression(C=1.0, max_iter=2000).fit(Ztr, y[tr])
        oof[i] = clf.predict_proba(Zte)[0, 1]
    record(f"c kernelPCA3(RBF-eucl) + logistic ({label})", oof)

# ── (e) Tiny LSTM empirical demo (torch, h=2, 35 params) ────────────────────
print("\n(e) Tiny-LSTM capacity demo (h=2, LOVO, 3 seeds):")
try:
    import torch
    import torch.nn as nn

    class TinyLSTM(nn.Module):
        def __init__(self, h=2):
            super().__init__()
            self.lstm = nn.LSTM(1, h, batch_first=True)
            self.head = nn.Linear(h, 1)
        def forward(self, x):
            o, _ = self.lstm(x)
            return self.head(o[:, -1, :]).squeeze(-1)

    n_par = sum(p.numel() for p in TinyLSTM().parameters())
    print(f"  TinyLSTM(h=2) parameters: {n_par}")
    Xt_full = torch.tensor(X_std[:, :, None], dtype=torch.float32)
    yt_full = torch.tensor(y, dtype=torch.float32)
    aurocs = []
    for seed in (0, 1, 2):
        torch.manual_seed(seed)
        oof = np.zeros(len(y))
        for i in range(len(y)):
            tr = np.ones(len(y), bool); tr[i] = False
            model = TinyLSTM()
            opt = torch.optim.Adam(model.parameters(), lr=0.02)
            lossf = nn.BCEWithLogitsLoss()
            Xtr, ytr = Xt_full[tr], yt_full[tr]
            for ep in range(300):
                opt.zero_grad()
                loss = lossf(model(Xtr), ytr)
                loss.backward(); opt.step()
            with torch.no_grad():
                oof[i] = torch.sigmoid(model(Xt_full[~tr]))[0].item()
        a = record(f"e TinyLSTM h=2 ({n_par}p) seed={seed} (std)", oof)
        aurocs.append(a)
    print(f"  TinyLSTM seed spread: {min(aurocs):.3f} - {max(aurocs):.3f} "
          f"(range {max(aurocs)-min(aurocs):.3f})")
except ImportError:
    print("  torch not available — skipped (param math stands alone)")

res = pd.DataFrame(results)
res.to_csv(OUT / "G2_probe_results.csv", index=False)
print("\nSaved ->", OUT / "G2_probe_results.csv")
