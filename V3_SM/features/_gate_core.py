"""
_gate_core.py
Verbatim copy of the numeric gate core from V2.1/features/V2_1_feature_gate.py.
No import-time side effects — only constants and function definitions.
"""
import math
from itertools import combinations

import numpy as np
import pandas as pd
from scipy import stats

# ── Production constants (frozen V1.1) ──────────────────────────────────────
ALPHA_MW = 0.10
AUROC_MIN = 0.60
CORR_MAX = 0.85
STABLE_FRAC = 0.80
POOL_CAP = 10
SUBSET_MIN, SUBSET_MAX = 3, 6
RIDGE_ALPHA = 1.0


def ridge_z(Xtr, ytr, Xte, alpha=RIDGE_ALPHA):
    Xtr = Xtr.copy(); Xte = Xte.copy()
    med = np.nanmedian(Xtr, axis=0)
    med = np.where(np.isnan(med), 0.0, med)
    for j in range(Xtr.shape[1]):
        Xtr[np.isnan(Xtr[:, j]), j] = med[j]
        Xte[np.isnan(Xte[:, j]), j] = med[j]
    mu, sd = Xtr.mean(0), Xtr.std(0)
    sd = np.where(sd == 0, 1.0, sd)
    Xtr = (Xtr - mu) / sd; Xte = (Xte - mu) / sd
    yp = 2.0 * ytr - 1.0
    yc = yp - yp.mean()
    k = Xtr.shape[1]
    beta = np.linalg.solve(Xtr.T @ Xtr + alpha * np.eye(k), Xtr.T @ yc)
    return Xte @ beta + yp.mean()


def sigmoid(z):
    return np.where(z >= 0,
                    1.0 / (1.0 + np.exp(-np.abs(z))),
                    np.exp(-np.abs(z)) / (1.0 + np.exp(-np.abs(z))))


def lovo_z(X, yy):
    nn = len(yy)
    z = np.empty(nn)
    idx = np.arange(nn)
    for i in range(nn):
        tr = idx != i
        z[i] = ridge_z(X[tr], yy[tr], X[i:i + 1])[0]
    return z


def rank_auroc(s, l):
    m = np.isfinite(s)
    s, l = s[m], l[m]
    if l.sum() == 0 or (1 - l).sum() == 0:
        return np.nan
    r = stats.rankdata(s)
    n1 = int(l.sum())
    return (r[l == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * (len(l) - n1))


def mw_p(a, b):
    if len(a) == 0 or len(b) == 0:
        return np.nan
    try:
        return float(stats.mannwhitneyu(a, b, alternative="two-sided").pvalue)
    except ValueError:
        return np.nan


def youden_thr(yy, p):
    order = np.argsort(-p)
    ps, ys = p[order], yy[order]
    P, N = ys.sum(), len(ys) - ys.sum()
    tps = np.cumsum(ys); fps = np.cumsum(1 - ys)
    jj = tps / P - fps / N
    distinct = np.r_[np.diff(ps) != 0, True]
    best = np.argmax(np.where(distinct, jj, -np.inf))
    return float(ps[best])


def mcc_at(yy, p, thr):
    pred = (p >= thr).astype(int)
    tp = int(((pred == 1) & (yy == 1)).sum()); tn = int(((pred == 0) & (yy == 0)).sum())
    fp = int(((pred == 1) & (yy == 0)).sum()); fn = int(((pred == 0) & (yy == 1)).sum())
    den = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    return (tp * tn - fp * fn) / den if den > 0 else 0.0


def screen_pool(Xdf, yy, feats):
    nn = len(yy)
    recs = []
    for ft in feats:
        v = Xdf[ft].values.astype(float)
        m = np.isfinite(v)
        if m.sum() < 6 or len(np.unique(yy[m])) < 2:
            recs.append((ft, np.nan, np.nan, False)); continue
        p = mw_p(v[m & (yy == 1)], v[m & (yy == 0)])
        a = rank_auroc(v, yy); a = max(a, 1 - a)
        recs.append((ft, p, a, bool(np.isfinite(p) and p < ALPHA_MW
                                    and np.isfinite(a) and a >= AUROC_MIN)))
    scr = pd.DataFrame(recs, columns=["feature", "mw_p", "auroc", "ok"])
    survivors = scr[scr["ok"]].sort_values("auroc", ascending=False)["feature"].tolist()
    kept = []
    for ft in survivors:
        ok = True
        for kft in kept:
            a_, b_ = Xdf[ft].values.astype(float), Xdf[kft].values.astype(float)
            m = np.isfinite(a_) & np.isfinite(b_)
            if m.sum() >= 4:
                r = stats.spearmanr(a_[m], b_[m])[0]
                if np.isfinite(r) and abs(r) >= CORR_MAX:
                    ok = False; break
        if ok:
            kept.append(ft)
    stable_min = math.ceil(STABLE_FRAC * nn)
    counts = {f: 0 for f in kept}
    for i in range(nn):
        km = np.arange(nn) != i
        ys = yy[km]
        for ft in kept:
            v = Xdf[ft].values.astype(float)[km]
            m = np.isfinite(v)
            p = mw_p(v[m & (ys == 1)], v[m & (ys == 0)])
            if np.isfinite(p) and p < ALPHA_MW:
                counts[ft] += 1
    pool = [f for f in kept if counts[f] >= stable_min]
    pool = (scr[scr["feature"].isin(pool)].sort_values("auroc", ascending=False)
            .head(POOL_CAP)["feature"].tolist())
    rank = scr.sort_values("auroc", ascending=False)["feature"].tolist()
    return pool, rank


def subset_search(Xdf, yy, pool, rank):
    if len(pool) == 0:
        pool = rank[:1]
    k_lo = min(SUBSET_MIN, len(pool))
    k_hi = min(SUBSET_MAX, len(pool))
    best = None
    for k in range(k_lo, k_hi + 1):
        for feats in combinations(pool, k):
            X = Xdf[list(feats)].values.astype(float)
            z = lovo_z(X, yy)
            p = sigmoid(z)
            a = rank_auroc(p, yy)
            thr = youden_thr(yy, p)
            mcc = mcc_at(yy, p, thr)
            cand = (round(a, 10), -k, round(mcc, 10))
            if best is None or cand > best[0]:
                best = (cand, list(feats), z, a)
    return best[1], best[2], best[3]


def nested_lovo(Xdf, yy, feats_all):
    nn = len(yy)
    probs = np.empty(nn)
    details = []
    for i in range(nn):
        tr = np.arange(nn) != i
        df_tr = Xdf.loc[tr].reset_index(drop=True)
        y_tr = yy[tr]
        pool, rank = screen_pool(df_tr, y_tr, feats_all)
        feats, z_in, a_in = subset_search(df_tr, y_tr, pool, rank)
        z_te = ridge_z(df_tr[feats].values.astype(float), y_tr,
                       Xdf.loc[[i], feats].values.astype(float))[0]
        probs[i] = sigmoid(np.array([z_te]))[0]
        details.append({"feats": feats, "pool": pool})
    return probs, details


def plain_lovo(X, yy):
    """Plain 34-fold LOVO (no re-screening) — returns sigmoid probs."""
    n_ = len(yy)
    z = np.empty(n_)
    for i in range(n_):
        tr = np.arange(n_) != i
        z[i] = ridge_z(X[tr], yy[tr], X[i:i+1])[0]
    return sigmoid(z)
