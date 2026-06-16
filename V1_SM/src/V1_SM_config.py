"""V1_SM config — starter motor pipeline constants. Single source of truth."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]   # repo root (…/Daimler-starter_motor_alternator_battery)
SM_FAILED = ROOT / "Data/processed/starter_motor_complete/2026-03-06-12-38-23-starter_motor_failed.parquet"
SM_NONFAIL = ROOT / "Data/processed/starter_motor_complete/2026-03-06-12-39-14-starter_motor_non_failed.parquet"

OUT = ROOT / "STARTER MOTOR"
CACHE_WEEKLY = OUT / "cache/weekly"
CACHE_EVENTS = OUT / "cache/events"
RESULTS = OUT / "results"
GRAPHS = OUT / "graphs"
REPORTS = OUT / "reports"

VERSION = "V1_SM"
FILE_PREFIX = "V1_SM_"

# Fleet
N_FAILED, N_NONFAILED = 14, 20
N_VINS = 34

# Sentinels (docs/column_dictionary.md)
SENT_U16 = 65535.0          # CSP, RPM, ANR
SENT_ANR_NEG = -5000.0      # ANR
VSI_SENTINEL_LOW = 0.0      # VSI <= 0   -> null (no data)
VSI_SENTINEL_HIGH = 255.0   # VSI >= 255 -> null (uint8 max sentinel)
VSI_SCALE_TRIGGER = 36.0    # raw > 36 V means the recording needs rescaling (near no-op in SM files)
VSI_SCALE_FACTOR = 0.2      # Actual V = Raw x VSI_SCALE_FACTOR

# Crank event extraction (Finding 3, prelim analysis)
CRANK_MAX_INTRA_GAP_S = 10      # split event if gap between SMA=1 rows exceeds
CRANK_MAX_PLAUSIBLE_DUR_S = 60  # longer => artifact=True (flag, never drop)
CRANK_BASELINE_WINDOW_S = (-90, -10)   # (start_s, end_s) offsets from crank onset; negative = before
CRANK_RECOVERY_WINDOW_S = 45    # post-crank recovery observation
CRANK_SUCCESS_RPM = 550         # DICV S1/S6: RPM >= 550 within event+15s = success
MIN_EVENTS_PER_VIN = 50         # KT reliability floor
CRANK_RETRY_WINDOW_S = 120      # next-event start within this of prior event end = retry
CRANK_RPM_POST_S = 15           # RPM success window extends this far past event end
CRANK_SAMPLE_WIDTH_S = 5.0      # telemetry sample width added to dur_s (median dt = 5s)

# Regime & alert thresholds (DICV rules; used by weekly cache + features)
RPM_DRIVE_THRESH = 700     # RPM > this -> driving/charging regime
VSI_ALERT_LOW = 21.0       # DICV A5 severe-low voltage
VSI_ALERT_HIGH = 32.0      # DICV A4 battery rejection

# Silent-failure gap VINs (prelim analysis 2026-06-09): telemetry ends before JCOPENDATE
GAP_VINS = {"VIN1_F_SM": 72, "VIN4_F_SM": 97, "VIN5_F_SM": 32,
            "VIN8_F_SM": 37, "VIN9_F_SM": 142}   # gap in days
assert all(k.endswith("_F_SM") for k in GAP_VINS), "GAP_VINS keys must be failed SM VINs"

# Modelling
LOVO_FOLDS = 34
RIDGE_ALPHA = 1.0
RANDOM_STATE = 42
SUBSET_MIN, SUBSET_MAX = 4, 8   # exhaustive search, INCLUSIVE both ends (fewer-features lesson)
N_BOOTSTRAP = 200
N_PERMUTATION = 1000

def vin_label(raw_vin: str, failed: bool) -> str:
    """VIN3 + failed=True -> 'VIN3_F_SM'. NEVER use raw labels downstream."""
    return f"{raw_vin}_{'F' if failed else 'NF'}_SM"
