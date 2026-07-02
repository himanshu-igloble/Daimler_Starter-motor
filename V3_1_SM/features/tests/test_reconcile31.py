import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _gate_core as G
import _v31_lib as L
import V3_1_feature_gate as GATE            # import must expose reconcile()


def test_e0_reconciliation_and_sv5():
    recon = GATE.reconcile()
    assert recon["pass"] is True
    assert abs(recon["computed"] - 0.9357) <= 0.002
