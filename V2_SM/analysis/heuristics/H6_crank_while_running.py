"""
H6_crank_while_running.py — V2 Heuristic Intelligence Layer
============================================================
Operational abuse metric: crank-while-running events
Definition: SMA=1 AND RPM>400 in the same sample, EXCLUDING crank-start context
            (i.e., RPM>400 must have been sustained in the PREVIOUS row too —
            ruling out the normal crank-to-run transition).

Data source: V1_SM_crank_events.parquet (has rpm_max_15s but not raw RPM-per-row);
             if field is insufficient, lazy-scan raw parquet files.

This is an OPERATIONAL ABUSE metric only. We do NOT claim failure prediction
unless the data shows a statistically significant F vs NF difference.

Outputs:
  out/H6_crank_while_running.csv — per VIN: total events, rate per truck-year,
                                    failed vs NF group stats
"""
from pathlib import Path
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR")
OUT_DIR = ROOT / "V2_program" / "analysis" / "heuristics" / "out"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── try events parquet first ─────────────────────────────────────────────────
ev = pd.read_parquet(ROOT / "cache/events/V1_SM_crank_events.parquet")
ev["ts_start"] = pd.to_datetime(ev["ts_start"])
print(f"Crank events loaded: {len(ev)} rows, columns: {ev.columns.tolist()}")

# The crank events parquet has: vin_label, failed, event_id, ts_start, n_rows,
# multi_sample, dur_s, artifact, baseline_vsi, min_vsi_crank, dip_depth,
# rpm_max_15s, success, recovery_slope, retry_within_120s, days_before_t_end
#
# rpm_max_15s = max RPM in the first 15 seconds of the event
# This captures events where RPM was already elevated at crank start
# BUT: this is per crank event, not raw sample-level SMA+RPM joint scan.
#
# Proxy for "crank while engine running": rpm_max_15s at START of event > 400
# combined with the artifact flag. Non-artifact events where the engine was
# already turning (rpm_max_15s at crank start > 400) are our closest proxy.
#
# Limitation: rpm_max_15s is the MAX in the first 15s which may include the
# engine spin-up. We use a stricter threshold (>500 RPM) to reduce false positives
# from the crank-to-run transition, and report counts with this caveat.

RPM_THRESHOLD = 500   # RPM at start of crank event to flag as possible CWR

# Filter to non-artifact events only
ev_clean = ev[ev["artifact"] == False].copy()

# Flag events where RPM was high at crank start (proxy for crank-while-running)
ev_clean["cwr_proxy"] = ev_clean["rpm_max_15s"] > RPM_THRESHOLD

print(f"\nNon-artifact crank events: {len(ev_clean)}")
print(f"CWR proxy events (rpm_max_15s > {RPM_THRESHOLD}): {ev_clean['cwr_proxy'].sum()}")

# Load t_start / t_end for truck-year normalization
dq = pd.read_csv(ROOT / "results" / "V1_SM_data_quality.csv",
                 parse_dates=["t_end", "t_start"])
vin_years = {r["vin_label"]: (r["t_end"] - r["t_start"]).days / 365.25
             for _, r in dq.iterrows()}
vin_labels = dq["vin_label"].tolist()

# Per-VIN stats
rows = []
for vin in vin_labels:
    sub = ev_clean[ev_clean["vin_label"] == vin]
    failed = 1 if "_F_" in vin else 0
    total_events = len(sub)
    cwr_events = sub["cwr_proxy"].sum()
    yr = vin_years.get(vin, 1.0)
    rows.append({
        "vin_label": vin,
        "failed": failed,
        "total_crank_events": total_events,
        "cwr_proxy_events": int(cwr_events),
        "cwr_rate_per_year": round(cwr_events / yr if yr > 0 else np.nan, 2),
        "truck_years": round(yr, 2),
    })

df = pd.DataFrame(rows)
df.to_csv(OUT_DIR / "H6_crank_while_running.csv", index=False)
print(f"\nSaved H6_crank_while_running.csv")

# Group stats
f_rows = df[df["failed"] == 1]
nf_rows = df[df["failed"] == 0]

print("\n=== H6 CRANK-WHILE-RUNNING PROXY (rpm_max_15s > 500 at crank start) ===")
print(f"\nFailed (n={len(f_rows)}):")
print(f"  Total CWR proxy events: {f_rows['cwr_proxy_events'].sum()}")
print(f"  Mean per truck: {f_rows['cwr_proxy_events'].mean():.1f}")
print(f"  Mean rate / truck-year: {f_rows['cwr_rate_per_year'].mean():.2f}")
print(f"  Trucks with CWR proxy: {(f_rows['cwr_proxy_events'] > 0).sum()}/{len(f_rows)}")

print(f"\nNon-Failed (n={len(nf_rows)}):")
print(f"  Total CWR proxy events: {nf_rows['cwr_proxy_events'].sum()}")
print(f"  Mean per truck: {nf_rows['cwr_proxy_events'].mean():.1f}")
print(f"  Mean rate / truck-year: {nf_rows['cwr_rate_per_year'].mean():.2f}")
print(f"  Trucks with CWR proxy: {(nf_rows['cwr_proxy_events'] > 0).sum()}/{len(nf_rows)}")

print("\nPer-VIN detail:")
print(df[["vin_label", "failed", "cwr_proxy_events", "cwr_rate_per_year",
          "truck_years"]].to_string(index=False))

# Mann-Whitney U test for F vs NF rates
from scipy.stats import mannwhitneyu
f_rates = f_rows["cwr_rate_per_year"].values
nf_rates = nf_rows["cwr_rate_per_year"].values
if len(f_rates) >= 3 and len(nf_rates) >= 3:
    try:
        stat, p_val = mannwhitneyu(f_rates, nf_rates, alternative="greater")
        print(f"\nMann-Whitney U (F > NF rates): U={stat:.1f}, p={p_val:.4f}")
        if p_val < 0.05:
            print("  Significant difference — failed trucks show higher CWR proxy rate.")
        else:
            print("  No significant difference — insufficient to claim failure prediction.")
    except Exception as e:
        print(f"  Mann-Whitney failed: {e}")

print("\nCAVEAT: rpm_max_15s is the MAXIMUM in the first 15 seconds of a crank event,")
print("not a per-sample SMA=1 AND RPM>400 joint check. This is a proxy only.")
print("True crank-while-running detection requires raw telemetry scan.")
print("This metric should be treated as an OPERATIONAL ABUSE indicator,")
print("not as a failure predictor, unless validated with raw data.")
