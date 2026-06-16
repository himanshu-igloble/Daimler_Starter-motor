"""
V1_1_SM_vin_display_map.py — DISPLAY-LEVEL VIN renumbering for V1.1 SM graphs/decks
====================================================================================
Convention (2026-06-11, user-specified): sequential fleet numbering — failed
trucks first, then non-failed continue the sequence.

  Failed:     VIN1_F_SM  .. VIN14_F_SM   — UNCHANGED (identity-mapped).
  Non-failed: old VIN{k}_NF_SM -> new VIN{k+14}_NF_SM
              (old VIN1_NF -> VIN15_NF, ..., old VIN20_NF -> VIN34_NF).

SCOPE: display/naming change for GRAPHS and PRESENTATIONS ONLY. Canonical data
artifacts (results CSVs/JSON/parquet, reports) retain the ORIGINAL labels — the
audit trail references them. Graph/deck scripts import this module and map
old -> new at render time.

NAME-COLLISION NOTE: new names VIN15_NF..VIN20_NF refer to DIFFERENT physical
trucks than the OLD names VIN15_NF..VIN20_NF (new VIN15-20_NF = raw NF-file
VIN1-6; old VIN15-20_NF = raw NF-file VIN15-20). Traceability table:
  STARTER MOTOR/V1.1/results/V1_1_SM_vin_naming_map.csv

Run `py -3 V1_1_SM_vin_display_map.py` to (re)write that CSV.
"""
from __future__ import annotations

import re

N_FAILED = 14
N_NF = 20

# ---------------------------------------------------------------------------
# Canonical mapping: old (results-artifact) label -> new (display) label
# ---------------------------------------------------------------------------
OLD_TO_NEW: dict[str, str] = {}
for _k in range(1, N_FAILED + 1):
    OLD_TO_NEW[f"VIN{_k}_F_SM"] = f"VIN{_k}_F_SM"                # identity
for _k in range(1, N_NF + 1):
    OLD_TO_NEW[f"VIN{_k}_NF_SM"] = f"VIN{_k + N_FAILED}_NF_SM"   # +14 shift

NEW_TO_OLD: dict[str, str] = {v: k for k, v in OLD_TO_NEW.items()
                              if "_NF_" in k} | {f"VIN{_k}_F_SM": f"VIN{_k}_F_SM"
                                                 for _k in range(1, N_FAILED + 1)}


def display_label(old: str) -> str:
    """Old results-artifact label -> new display label (failed: unchanged)."""
    return OLD_TO_NEW.get(old, old)


def raw_file_note(new_label: str) -> str:
    """Raw-source-file provenance for a NEW display label.

    raw_file_note('VIN17_NF_SM') -> 'raw NF-file VIN3'   (k_new - 14)
    raw_file_note('VIN5_F_SM')   -> 'raw F-file VIN5'
    """
    m = re.fullmatch(r"VIN(\d+)_(F|NF)_SM", new_label)
    if not m:
        raise ValueError(f"unrecognized VIN label: {new_label!r}")
    k, cohort = int(m.group(1)), m.group(2)
    if cohort == "F":
        return f"raw F-file VIN{k}"
    return f"raw NF-file VIN{k - N_FAILED}"


# ---------------------------------------------------------------------------
# Prose mapper for presentation text (handles VINk_NF_SM, VINk_NF, and
# slash-compound forms like 'VIN2/5/8/15_NF'). Failed labels untouched.
# ---------------------------------------------------------------------------
_NF_TOKEN = re.compile(r"VIN(\d+(?:/\d+)*)_NF(_SM)?")


def map_nf_text(text: str) -> str:
    """Replace every old-style NF VIN reference in prose with the new label.

    'VIN1_NF'          -> 'VIN15_NF'
    'VIN20_NF_SM'      -> 'VIN34_NF_SM'
    'VIN2/5/8/15_NF'   -> 'VIN16/19/22/29_NF'
    Failed references (VINk_F / VINk_F_SM) are left unchanged.
    Single-pass re.sub: never double-shifts.
    """
    def _sub(m: re.Match) -> str:
        nums = "/".join(str(int(n) + N_FAILED) for n in m.group(1).split("/"))
        return f"VIN{nums}_NF{m.group(2) or ''}"
    return _NF_TOKEN.sub(_sub, text)


# ---------------------------------------------------------------------------
# Traceability CSV writer
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import csv
    from pathlib import Path

    out = Path(__file__).resolve().parent.parent / "results" / "V1_1_SM_vin_naming_map.csv"
    rows = []
    for k in range(1, N_FAILED + 1):
        old = f"VIN{k}_F_SM"
        rows.append((old, OLD_TO_NEW[old], "failed", f"VIN{k}"))
    for k in range(1, N_NF + 1):
        old = f"VIN{k}_NF_SM"
        rows.append((old, OLD_TO_NEW[old], "non_failed", f"VIN{k}"))
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["old_label", "new_label", "cohort", "raw_file_vin"])
        w.writerows(rows)
    print(f"Wrote {out} ({len(rows)} rows)")
    # self-checks
    assert len(OLD_TO_NEW) == 34
    assert display_label("VIN1_NF_SM") == "VIN15_NF_SM"
    assert display_label("VIN20_NF_SM") == "VIN34_NF_SM"
    assert display_label("VIN9_F_SM") == "VIN9_F_SM"
    assert raw_file_note("VIN17_NF_SM") == "raw NF-file VIN3"
    assert raw_file_note("VIN5_F_SM") == "raw F-file VIN5"
    assert map_nf_text("VIN2/5/8/15_NF") == "VIN16/19/22/29_NF"
    assert map_nf_text("VIN20_NF_SM and VIN8_F_SM") == "VIN34_NF_SM and VIN8_F_SM"
    print("All self-checks passed.")
