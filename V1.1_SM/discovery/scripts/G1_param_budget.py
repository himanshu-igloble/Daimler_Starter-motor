"""
G1_param_budget.py — Agent G, V1.1 discovery (sequence modeling feasibility).

Exact / formula-based minimal-configuration parameter counts for each requested
deep sequence architecture, set against the SM data budget:
  - 14 failed trucks (the "events" in the events-per-variable sense)
  - 34 truck sequences total (one label per truck)
  - ~2,636 truck-weeks of weekly aggregates (correlated within truck; the
    effective sample size for a per-truck label is 34, not 2,636)

Counting conventions:
  LSTM layer params       = 4 * (h*(h+i) + h)            (i=input dim, h=hidden)
  GRU layer params        = 3 * (h*(h+i) + h)
  Conv1d params           = k * c_in * c_out + c_out
  MHA (d_model=d)         = 4*d*d + 4*d                  (Q,K,V,O proj + biases)
  FFN (d -> f -> d)       = d*f + f + f*d + d
  LayerNorm               = 2*d
Minimal configs are deliberately tiny (smaller than anything published works
with) to make the comparison maximally generous to the deep models.

Output: STARTER MOTOR/V1.1/discovery/out/G1_param_budget.csv
Run: py -3 G1_param_budget.py
"""
from pathlib import Path
import pandas as pd

OUT = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR\V1.1\discovery\out")
OUT.mkdir(parents=True, exist_ok=True)

N_FAILED = 14          # events (EPV denominator)
N_SEQ = 34             # labelled sequences
TRUCK_WEEKS = 2636     # correlated within-truck observations


def lstm(i, h):       return 4 * (h * (h + i) + h)
def gru(i, h):        return 3 * (h * (h + i) + h)
def conv1d(k, ci, co): return k * ci * co + co
def mha(d):           return 4 * d * d + 4 * d
def ffn(d, f):        return d * f + f + f * d + d
def ln(d):            return 2 * d
def linear(i, o):     return i * o + o


rows = []

# ── LSTM: 1 layer, input=1 (weekly vsi_drive_std), h=8, sigmoid head ────────
h = 8
p = lstm(1, h) + linear(h, 1)
rows.append(("LSTM", f"1 layer, h={h}, univariate input, linear head", p))

# ── BiLSTM: same but bidirectional ───────────────────────────────────────────
p = 2 * lstm(1, h) + linear(2 * h, 1)
rows.append(("BiLSTM", f"1 bidir layer, h={h}, univariate, linear head", p))

# ── TCN: 2 residual blocks, 8 channels, kernel 3, dilations 1,2 ─────────────
c = 8
blk = lambda ci: 2 * conv1d(3, c, c) + (conv1d(1, ci, c) if ci != c else 0)
p = (2 * conv1d(3, 1, c) + conv1d(1, 1, c)) + blk(c) + linear(c, 1)
rows.append(("TCN", f"2 residual blocks, {c} ch, k=3, dilations (1,2), head", p))

# ── Vanilla Transformer encoder: d=16, 1 layer, 1 head, FFN 32 ──────────────
d, f = 16, 32
p = linear(1, d) + mha(d) + ffn(d, f) + 2 * ln(d) + linear(d, 1)
rows.append(("Transformer encoder", f"1 layer, d_model={d}, 1 head, FFN={f}, learned input proj", p))

# ── TFT: minimal honest accounting (variable-selection GRNs + LSTM enc/dec +
#    static enrichment + interpretable MHA + position-wise GRN), d=16 ────────
# A GRN at width d costs ~ 2*(d*d+d) + d*d+d + 2*d (two dense + gate + LN) ≈ 3d²+5d
grn = lambda d: 3 * d * d + 5 * d
d = 16
p = (2 * grn(d)            # variable selection (past + static)
     + lstm(d, d) + lstm(d, d)   # encoder + decoder LSTM
     + grn(d)               # static enrichment
     + mha(d) + grn(d)      # interpretable MHA + position-wise GRN
     + 2 * ln(d) + linear(d, 1))
rows.append(("TFT", f"minimal d={d}: 4 GRNs + 2 LSTMs + MHA + head", p))

# ── Informer: ProbSparse attention has the SAME parameter count as full MHA;
#    minimal = 1 enc layer d=16 + distilling conv + head ─────────────────────
d, f = 16, 32
p = linear(1, d) + mha(d) + ffn(d, f) + 2 * ln(d) + conv1d(3, d, d) + linear(d, 1)
rows.append(("Informer", f"1 ProbSparse enc layer d={d} + distil conv, head", p))

# ── PatchTST: patch_len=8, stride=4 -> patch embed 8->d, 1 enc layer d=16 ───
d, f, plen = 16, 32, 8
p = linear(plen, d) + mha(d) + ffn(d, f) + 2 * ln(d) + linear(d, 1)
rows.append(("PatchTST", f"patch_len={plen}, 1 enc layer d={d}, FFN={f}", p))

# ── TimeXer: endogenous patch tokens + exogenous variate token, cross+self
#    attention, 1 layer d=16 ─────────────────────────────────────────────────
d, f, plen = 16, 32, 8
p = (linear(plen, d) + linear(1, d)    # endo patch embed + exo variate embed
     + mha(d) + mha(d)                  # self-attn + cross-attn
     + ffn(d, f) + 3 * ln(d) + linear(d, 1))
rows.append(("TimeXer", f"1 layer d={d}, patch+variate embed, self+cross attn", p))

# ── Reference points ─────────────────────────────────────────────────────────
rows.append(("V1 Ridge baseline", "4 engineered features, alpha=1.0", 5))
rows.append(("Logistic on 3 PCA comps", "PCA(3) + logistic (probe 2a)", 4))

df = pd.DataFrame(rows, columns=["architecture", "minimal_config", "n_params"])
df["params_per_failed_truck"] = (df["n_params"] / N_FAILED).round(1)
df["params_per_sequence"] = (df["n_params"] / N_SEQ).round(1)
# classical EPV guideline: >=10 events per estimated parameter
df["max_params_at_EPV10"] = N_FAILED // 10  # = 1
df["budget_overrun_x"] = (df["n_params"] / (N_FAILED / 10)).round(0).astype(int)

print(f"Data budget: {N_FAILED} failed trucks, {N_SEQ} sequences, ~{TRUCK_WEEKS} truck-weeks")
print(f"EPV>=10 guideline budget: {N_FAILED/10:.1f} parameters\n")
print(df.to_string(index=False))
df.to_csv(OUT / "G1_param_budget.csv", index=False)
print("\nSaved ->", OUT / "G1_param_budget.csv")
