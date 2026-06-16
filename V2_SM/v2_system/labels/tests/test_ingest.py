"""
Self-test for ingest_feedback.py (D8-C3)

Test plan:
  1. Copy 2 real WOs to a temp dir
  2. Programmatically tick boxes on both:
       WO1: battery degraded + Battery 1 replaced
       WO2: no fault found (false positive)
  3. Ingest → assert 2 rows with correct modes
  4. Re-ingest → still 2 rows (idempotent)
  5. Fabricate an unknown-VIN WO → assert rejection

Usage:
  py -3 tests/test_ingest.py
"""
import sys
import csv
import shutil
import tempfile
import importlib.util
from pathlib import Path

# ── Load ingest_feedback as a module ─────────────────────────────────────────
LABELS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LABELS_DIR))

spec = importlib.util.spec_from_file_location(
    "ingest_feedback", LABELS_DIR / "ingest_feedback.py"
)
ig = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ig)

# ── Real WO files to copy ─────────────────────────────────────────────────────
V2_SYSTEM = LABELS_DIR.parent
WO_DIR = V2_SYSTEM / "workorders" / "out"
WO_VIN10 = WO_DIR / "WO_VIN10_F_SM_2026-06-12.md"
WO_VIN11 = WO_DIR / "WO_VIN11_F_SM_2026-06-12.md"


def patch_wo_text(text: str, ticks: dict) -> str:
    """
    Tick checkboxes in a WO text.
    ticks: dict of {substring_match: True/False}
    E.g. {"Battery degraded": True, "No fault found": True}
    Only matches within the FEEDBACK CAPTURE section.
    """
    import re
    # Find FEEDBACK CAPTURE section offset
    fb_idx = text.find("FEEDBACK CAPTURE")
    if fb_idx == -1:
        return text
    before = text[:fb_idx]
    section = text[fb_idx:]

    for item, checked in ticks.items():
        marker = "[x]" if checked else "[ ]"
        reverse = "[ ]" if checked else "[x]"
        # Match lines containing item (case-insensitive)
        pattern = re.compile(
            r'(- )\[[ xX]\](\s+' + re.escape(item[:20]) + ')',
            re.IGNORECASE
        )
        section = pattern.sub(r'\1' + marker + r'\2', section)

    return before + section


def read_registry(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


PASS_COUNT = 0
FAIL_COUNT = 0


def assert_eq(label: str, actual, expected):
    global PASS_COUNT, FAIL_COUNT
    if actual == expected:
        print(f"  PASS  {label}")
        PASS_COUNT += 1
    else:
        print(f"  FAIL  {label}: expected {expected!r}, got {actual!r}")
        FAIL_COUNT += 1


def run_tests():
    global PASS_COUNT, FAIL_COUNT
    print("=" * 60)
    print("TEST: ingest_feedback.py self-test")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        registry_path = tmp / "label_registry.csv"

        # ── Patch module paths to use temp dir ───────────────────────────
        ig.REGISTRY_CSV = registry_path

        # ── Copy and patch WO1: battery degraded + Battery 1 replaced ────
        wo1_src = WO_VIN10
        wo1_text = wo1_src.read_text(encoding="utf-8")
        wo1_text = patch_wo_text(wo1_text, {
            "Battery degraded": True,
            "Battery 1": True,
        })
        # Also add a technician and date
        import re
        wo1_text = re.sub(r'\*\*Technician:\*\*\s*_{10,}', '**Technician:** J. Singh', wo1_text)
        wo1_text = re.sub(r'\*\*Date of Inspection:\*\*\s*_{5,}', '**Date of Inspection:** 2026-06-15', wo1_text)
        wo1_dest = tmp / "WO_VIN10_F_SM_2026-06-12.md"
        wo1_dest.write_text(wo1_text, encoding="utf-8")

        # ── Copy and patch WO2: no fault found ───────────────────────────
        wo2_src = WO_VIN11
        wo2_text = wo2_src.read_text(encoding="utf-8")
        wo2_text = patch_wo_text(wo2_text, {
            "No fault found": True,
        })
        wo2_text = re.sub(r'\*\*Technician:\*\*\s*_{10,}', '**Technician:** R. Kumar', wo2_text)
        wo2_text = re.sub(r'\*\*Date of Inspection:\*\*\s*_{5,}', '**Date of Inspection:** 2026-06-16', wo2_text)
        wo2_dest = tmp / "WO_VIN11_F_SM_2026-06-12.md"
        wo2_dest.write_text(wo2_text, encoding="utf-8")

        # ── TEST 1: Ingest two WOs ────────────────────────────────────────
        print("\n[TEST 1] Ingest 2 WO files")
        ig.ingest_path(tmp)
        registry = read_registry(registry_path)
        assert_eq("registry has 2 rows", len(registry), 2)

        # VIN10 row
        vin10_rows = [r for r in registry if r["vin"] == "VIN10_F_SM"]
        assert_eq("VIN10_F_SM present", len(vin10_rows), 1)
        if vin10_rows:
            modes = vin10_rows[0]["finding_modes"]
            assert_eq("VIN10 finding_modes contains battery_degraded",
                      "battery_degraded" in modes, True)
            parts = vin10_rows[0]["parts_replaced"]
            assert_eq("VIN10 parts_replaced contains Battery_1",
                      "Battery_1" in parts, True)

        # VIN11 row
        vin11_rows = [r for r in registry if r["vin"] == "VIN11_F_SM"]
        assert_eq("VIN11_F_SM present", len(vin11_rows), 1)
        if vin11_rows:
            assert_eq("VIN11 finding_modes = no_fault_found",
                      vin11_rows[0]["finding_modes"], "no_fault_found")

        # ── TEST 2: Re-ingest (idempotent) ───────────────────────────────
        print("\n[TEST 2] Re-ingest same files (idempotent)")
        ig.ingest_path(tmp)
        registry_after = read_registry(registry_path)
        assert_eq("still 2 rows after re-ingest", len(registry_after), 2)

        # ── TEST 3: Unknown VIN → rejection ──────────────────────────────
        print("\n[TEST 3] Unknown-VIN WO -> rejected")
        bad_wo = tmp / "WO_VIN99_F_SM_2026-06-12.md"
        bad_text = wo1_text.replace("VIN10_F_SM", "VIN99_F_SM")
        bad_wo.write_text(bad_text, encoding="utf-8")

        registry_before = read_registry(registry_path)
        ok, msg = ig.ingest_file(bad_wo, list(registry_before))
        assert_eq("unknown VIN returns ok=False", ok, False)
        assert_eq("rejection message contains ERROR", "ERROR" in msg, True)
        print(f"  (rejection message: {msg})")

        # Registry unchanged after attempted bad ingest
        registry_unchanged = read_registry(registry_path)
        assert_eq("registry still 2 rows after bad ingest attempt",
                  len(registry_unchanged), 2)

    print("\n" + "=" * 60)
    total = PASS_COUNT + FAIL_COUNT
    print(f"Results: {PASS_COUNT}/{total} PASS  |  {FAIL_COUNT} FAIL")
    if FAIL_COUNT == 0:
        print("ALL TESTS PASS")
    else:
        print(f"FAILURES: {FAIL_COUNT}")
    print("=" * 60)
    return FAIL_COUNT == 0


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
