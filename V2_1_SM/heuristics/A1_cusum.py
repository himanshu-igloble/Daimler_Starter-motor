"""A1_cusum.py — directional (downward) CUSUM + EWMA change-point on per-VIN
weekly rest-VSI median. Detects battery-cascade step-downs while ignoring NF
battery-replacement step-ups. Params frozen in params/A1_cusum_params.json.

Sanity gate: must alarm on the known E5 rest-VSI down-steps (VIN14_F, VIN6_F,
VIN2_F, VIN3_F) and is checked against NF down-steps (e.g. VIN10_NF -3.0 V).

Run: py -3 "STARTER MOTOR/V2.1/heuristics/A1_cusum.py"
"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR\V2.1")
sys.path.insert(0, str(HERE / "heuristics"))
import _heuristic_lib as L  # noqa: E402

P = json.loads((HERE / "params" / "A1_cusum_params.json").read_text())
OUT = HERE / "heuristics" / "out"


def cusum_down(x, baseline_weeks, k, h):
    """Standardized one-sided downward CUSUM. x: weekly series (nan allowed).
    Returns (first_alarm_pos_in_finite_index_space, n_episodes, alarm_finite_idxs).
    Alarm positions are indices into the ORIGINAL x array."""
    fin = np.where(np.isfinite(x))[0]
    if len(fin) < baseline_weeks + 1:
        return None, 0, []
    base = x[fin[:baseline_weeks]]
    mu0, sd0 = float(np.mean(base)), float(np.std(base))
    if sd0 == 0:
        sd0 = 1e-6
    C = 0.0
    in_alarm = False
    n_ep = 0
    first = None
    alarms = []
    for i in fin[baseline_weeks:]:
        z = (x[i] - mu0) / sd0
        C = max(0.0, C - z - k)          # accumulates on downward deviation
        if C > h:
            if not in_alarm:
                n_ep += 1
                in_alarm = True
            if first is None:
                first = int(i)
            alarms.append(int(i))
        if C == 0.0:
            in_alarm = False
    return first, n_ep, alarms


def ewma_down(x, baseline_weeks, lam, Lsig):
    """Downward EWMA control chart. Returns first alarm index into x or None."""
    fin = np.where(np.isfinite(x))[0]
    if len(fin) < baseline_weeks + 1:
        return None
    base = x[fin[:baseline_weeks]]
    mu0, sd0 = float(np.mean(base)), float(np.std(base))
    if sd0 == 0:
        sd0 = 1e-6
    z = mu0
    for t, i in enumerate(fin[baseline_weeks:], start=1):
        z = lam * x[i] + (1 - lam) * z
        sd_ewma = sd0 * np.sqrt(lam / (2 - lam) * (1 - (1 - lam) ** (2 * t)))
        if z < mu0 - Lsig * sd_ewma:
            return int(i)
    return None


def main():
    tend, years = L.load_tend_years()
    series = L.load_rest_vsi_series(active_days_min=P["active_days_min"])

    cusum_recs, ewma_recs = [], []
    for vin, df in series.items():
        label = 1 if "_F_" in vin else 0
        x = df[P["rest_vsi_col"]].astype(float).values
        weeks = df["week"].values
        seq = pd.DataFrame({"cut_date": weeks})

        first_c, n_ep_c, _ = cusum_down(x, P["baseline_weeks"], P["cusum_k_sigma"], P["cusum_h_sigma"])
        rows_c = [first_c] if first_c is not None else []
        rec_c = L.fires_to_record(vin, label, seq, rows_c, tend)
        rec_c["n_episodes"] = n_ep_c
        cusum_recs.append(rec_c)

        first_e = ewma_down(x, P["baseline_weeks"], P["ewma_lambda"], P["ewma_L_sigma"])
        rows_e = [first_e] if first_e is not None else []
        rec_e = L.fires_to_record(vin, label, seq, rows_e, tend)
        ewma_recs.append(rec_e)

    df_c = pd.DataFrame(cusum_recs)
    df_e = pd.DataFrame(ewma_recs)
    df_c.to_csv(OUT / "A1_cusum_fires.csv", index=False)

    sum_c = L.summarize(df_c, years, "A1_cusum")
    sum_e = L.summarize(df_e, years, "A1_ewma")
    pd.DataFrame([sum_c, sum_e]).to_csv(OUT / "A1_cusum_summary.csv", index=False)

    print("=== A1 CUSUM (down) ===", sum_c)
    print("=== A1 EWMA  (down) ===", sum_e)

    e5 = pd.read_csv(L.ROOT / "V1.1" / "discovery" / "out" / "E5_step_changes_all.csv")
    gt_down = e5[(e5.signal == "vsi_rest_median") & (e5.step_V <= -1.0) & (e5.snr >= 3)
                 & (e5.vin_label.str.contains("_F_"))]["vin_label"].tolist()
    fired = set(df_c[df_c.ever_fires]["vin_label"])
    hit = [v for v in gt_down if v in fired]
    print(f"\nSANITY: E5 strong F down-steps {gt_down}")
    print(f"        A1 CUSUM fired on {len(hit)}/{len(gt_down)} of them: {hit}")
    if len(gt_down) and len(hit) < max(1, len(gt_down) - 1):
        print("  WARNING: A1 misses most E5 ground-truth down-steps — inspect baseline/threshold.")

    ok, reason = L.accept(sum_c)
    print(f"\nACCEPT-BAR (A1_cusum): {'SHIP-CANDIDATE' if ok else 'DOES NOT CLEAR'} | {reason}")


if __name__ == "__main__":
    main()
