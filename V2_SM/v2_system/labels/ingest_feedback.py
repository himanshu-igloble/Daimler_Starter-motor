"""
Feedback-Label Ingestion Pipeline (D8-C3)

Parses WO FEEDBACK CAPTURE sections → appends to labels/label_registry.csv

Usage:
  py -3 ingest_feedback.py <wo_file_or_dir>   -- ingest one file or all WOs in a dir
  py -3 ingest_feedback.py --status            -- print registry counts + refit status

WO FEEDBACK CAPTURE format (from actual WO files):
  Failure Mode Found (check all that apply):
    - [x] Battery degraded (one or both batteries)
    - [x] Solenoid contacts worn / burned
    - [ ] Brushes / commutator degraded
    - [ ] Cable or terminal fault (corrosion / resistance)
    - [ ] Clutch / pinion engagement fault
    - [x] No fault found (false positive)
    - [x] Other: some free text

  Parts Replaced:
    - [x] Battery 1   Part #: P123  Date replaced: 2026-06-01
    - [ ] Starter motor (full)   Part #: _____________
    ...

  Free Text Findings: (free block)
  Technician: Name
  Date of Inspection: YYYY-MM-DD
  Workshop / Bay: Bay 3
"""
import os
import sys
import csv
import re
from pathlib import Path
from datetime import datetime, timezone

# ── Paths ─────────────────────────────────────────────────────────────────────
THIS_DIR = Path(__file__).resolve().parent
REGISTRY_CSV = THIS_DIR / "label_registry.csv"
V2_SYSTEM = THIS_DIR.parent
CONFIG_JSON = V2_SYSTEM / "v2_config.json"

REGISTRY_VERSION = "1.0.0"
REFIT_TRIGGER_N_FAILURES = 5  # from v2_config governance

# All valid VINs (34 trucks)
ALL_VINS = set([
    "VIN1_F_SM", "VIN2_F_SM", "VIN3_F_SM", "VIN4_F_SM", "VIN5_F_SM",
    "VIN6_F_SM", "VIN7_F_SM", "VIN8_F_SM", "VIN9_F_SM", "VIN10_F_SM",
    "VIN11_F_SM", "VIN12_F_SM", "VIN13_F_SM", "VIN14_F_SM",
    "VIN1_NF_SM", "VIN2_NF_SM", "VIN3_NF_SM", "VIN4_NF_SM", "VIN5_NF_SM",
    "VIN6_NF_SM", "VIN7_NF_SM", "VIN8_NF_SM", "VIN9_NF_SM", "VIN10_NF_SM",
    "VIN11_NF_SM", "VIN12_NF_SM", "VIN13_NF_SM", "VIN14_NF_SM", "VIN15_NF_SM",
    "VIN16_NF_SM", "VIN17_NF_SM", "VIN18_NF_SM", "VIN19_NF_SM", "VIN20_NF_SM",
])

# Failure mode checklist items → canonical labels
FAILURE_MODE_MAP = {
    "battery degraded": "battery_degraded",
    "solenoid contacts worn": "solenoid_contacts",
    "solenoid contacts worn / burned": "solenoid_contacts",
    "brushes / commutator degraded": "brushes_commutator",
    "brushes": "brushes_commutator",
    "cable or terminal fault": "cable_terminal",
    "cable or terminal fault (corrosion / resistance)": "cable_terminal",
    "clutch / pinion engagement fault": "clutch_pinion",
    "clutch": "clutch_pinion",
    "no fault found (false positive)": "no_fault_found",
    "no fault found": "no_fault_found",
    "other": "other",
}

# Parts replaced checklist items → canonical labels
PARTS_MAP = {
    "battery 1": "Battery_1",
    "battery 2": "Battery_2",
    "starter motor (full)": "Starter_motor_full",
    "starter motor": "Starter_motor_full",
    "solenoid only": "Solenoid_only",
    "cables / terminals": "Cables_terminals",
    "cables": "Cables_terminals",
    "other": "Other_part",
}

REGISTRY_FIELDS = [
    "vin", "wo_date", "source_file", "finding_modes", "parts_replaced",
    "technician", "completed_date", "free_text", "ingested_at", "registry_version",
]


# ── Parsing ───────────────────────────────────────────────────────────────────

def extract_vin_from_filename(path: Path) -> str:
    """Extract VIN from WO filename like WO_VIN10_F_SM_2026-06-12.md"""
    m = re.search(r'WO_(VIN\d+(?:_[A-Z]+)+)_\d{4}-\d{2}-\d{2}', path.name)
    if m:
        return m.group(1)
    return None


def extract_wo_date_from_filename(path: Path) -> str:
    m = re.search(r'(\d{4}-\d{2}-\d{2})', path.name)
    return m.group(1) if m else ""


def parse_feedback_section(text: str) -> dict:
    """
    Parse the FEEDBACK CAPTURE section of a WO markdown file.
    Returns dict with keys: finding_modes, parts_replaced, technician,
    completed_date, free_text, is_pending.
    """
    # Find FEEDBACK CAPTURE section
    fb_match = re.search(r'FEEDBACK CAPTURE.*?(?=\Z|\Z)', text, re.DOTALL | re.IGNORECASE)
    if not fb_match:
        return None

    section = text[fb_match.start():]

    # Parse checked failure modes: lines like "- [x] Battery degraded..."
    checked_pattern = re.compile(r'-\s+\[([xX ])\]\s+(.+?)$', re.MULTILINE)
    finding_modes = []
    parts_replaced = []

    # Identify section boundaries
    failure_section_match = re.search(
        r'\*\*Failure Mode Found.*?\*\*.*?(?=\*\*Parts Replaced|\Z)',
        section, re.DOTALL | re.IGNORECASE
    )
    parts_section_match = re.search(
        r'\*\*Parts Replaced.*?\*\*.*?(?=\*\*Free Text|\Z)',
        section, re.DOTALL | re.IGNORECASE
    )

    if failure_section_match:
        fm_text = failure_section_match.group(0)
        for m in checked_pattern.finditer(fm_text):
            checked = m.group(1).strip().lower() == "x"
            item_raw = m.group(2).strip()
            if checked:
                item_clean = item_raw.lower()
                # Handle "Other: <text>" lines
                if item_clean.startswith("other"):
                    finding_modes.append("other")
                else:
                    # Match against known keys
                    matched = None
                    for k, v in FAILURE_MODE_MAP.items():
                        if item_clean.startswith(k):
                            matched = v
                            break
                    if matched:
                        finding_modes.append(matched)
                    else:
                        finding_modes.append("other")

    if parts_section_match:
        pr_text = parts_section_match.group(0)
        for m in checked_pattern.finditer(pr_text):
            checked = m.group(1).strip().lower() == "x"
            item_raw = m.group(2).strip()
            if checked:
                item_clean = item_raw.lower()
                matched = None
                for k, v in PARTS_MAP.items():
                    if item_clean.startswith(k):
                        matched = v
                        break
                parts_replaced.append(matched if matched else item_raw[:50])

    # Free text
    free_text = ""
    ft_match = re.search(
        r'\*\*Free Text Findings.*?\*\*.*?```(.*?)```',
        section, re.DOTALL | re.IGNORECASE
    )
    if ft_match:
        ft_raw = ft_match.group(1).strip()
        if ft_raw and ft_raw not in ("(describe observed fault, measurements taken, repair performed)",):
            free_text = ft_raw.replace("\n", " ").strip()

    # Technician
    technician = ""
    t_match = re.search(r'\*\*Technician:\*\*\s*(.+?)$', section, re.MULTILINE | re.IGNORECASE)
    if t_match:
        val = t_match.group(1).strip().replace("______________________________", "").strip()
        if val:
            technician = val

    # Date of Inspection
    completed_date = ""
    d_match = re.search(r'\*\*Date of Inspection:\*\*\s*(.+?)$', section, re.MULTILINE | re.IGNORECASE)
    if d_match:
        val = d_match.group(1).strip().replace("_______________________", "").strip()
        if val and re.match(r'\d{4}-\d{2}-\d{2}', val):
            completed_date = val

    # Determine if pending: no boxes checked AND no technician AND no date
    is_pending = (len(finding_modes) == 0 and not technician and not completed_date)

    return {
        "finding_modes": "|".join(finding_modes) if finding_modes else "PENDING",
        "parts_replaced": "|".join(parts_replaced) if parts_replaced else "",
        "technician": technician,
        "completed_date": completed_date,
        "free_text": free_text,
        "is_pending": is_pending,
    }


# ── Registry I/O ──────────────────────────────────────────────────────────────

def load_registry() -> list:
    if not REGISTRY_CSV.exists():
        return []
    with open(REGISTRY_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_registry(rows: list):
    REGISTRY_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REGISTRY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def already_ingested(rows: list, source_file: str) -> bool:
    return any(r.get("source_file") == source_file for r in rows)


# ── Ingest ────────────────────────────────────────────────────────────────────

def ingest_file(wo_path: Path, registry: list) -> tuple:
    """Ingest a single WO file. Returns (added: bool, message: str)."""
    source_file = str(wo_path.resolve())

    # Idempotent: skip if already ingested
    if already_ingested(registry, source_file):
        return False, f"SKIP (already ingested): {wo_path.name}"

    text = wo_path.read_text(encoding="utf-8")

    # Must have FEEDBACK CAPTURE section
    if "FEEDBACK CAPTURE" not in text:
        return False, f"SKIP (no FEEDBACK CAPTURE section): {wo_path.name}"

    # Extract VIN
    vin = extract_vin_from_filename(wo_path)
    if vin is None:
        # Try to extract from file header
        m = re.search(r'Work Order:\s*(VIN\S+)', text)
        if m:
            vin = m.group(1).strip()
    if vin is None or vin not in ALL_VINS:
        return False, f"ERROR (unknown VIN '{vin}'): {wo_path.name}"

    wo_date = extract_wo_date_from_filename(wo_path)
    fb = parse_feedback_section(text)
    if fb is None:
        return False, f"SKIP (feedback parse failed): {wo_path.name}"

    row = {
        "vin": vin,
        "wo_date": wo_date,
        "source_file": source_file,
        "finding_modes": fb["finding_modes"],
        "parts_replaced": fb["parts_replaced"],
        "technician": fb["technician"],
        "completed_date": fb["completed_date"],
        "free_text": fb["free_text"],
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "registry_version": REGISTRY_VERSION,
    }
    registry.append(row)
    status = "PENDING" if fb["is_pending"] else "INGESTED"
    return True, (f"{status}: {wo_path.name}  vin={vin}  "
                  f"modes={fb['finding_modes']}  parts={fb['parts_replaced']}")


def ingest_path(target: Path):
    registry = load_registry()
    original_len = len(registry)

    if target.is_file():
        files = [target]
    elif target.is_dir():
        files = sorted(target.glob("WO_*.md"))
    else:
        print(f"ERROR: path not found: {target}")
        sys.exit(1)

    if not files:
        print(f"No WO_*.md files found in {target}")
        return

    added = 0
    for f in files:
        ok, msg = ingest_file(f, registry)
        print(f"  {'+ ' if ok else '  '}{msg}")
        if ok:
            added += 1

    if added > 0:
        save_registry(registry)
        print(f"\nIngested {added} new record(s). Registry now has {len(registry)} rows.")
    else:
        print(f"\nNo new records added. Registry has {original_len} rows.")


# ── Status ────────────────────────────────────────────────────────────────────

def cmd_status():
    registry = load_registry()
    total = len(registry)

    pending = sum(1 for r in registry if r.get("finding_modes") == "PENDING")
    no_fault = sum(1 for r in registry if r.get("finding_modes") == "no_fault_found")
    with_findings = sum(
        1 for r in registry
        if r.get("finding_modes") not in ("PENDING", "", "no_fault_found")
    )

    # Failure labels: finding_mode != no_fault_found AND parts include starter replacement
    # "Failure label" definition from LABELS_README: replacement event
    # parts_replaced includes Starter_motor_full or Solenoid_only = replacement event
    failure_labels = [
        r for r in registry
        if r.get("finding_modes", "") not in ("PENDING", "", "no_fault_found")
        and any(
            part in r.get("parts_replaced", "")
            for part in ("Starter_motor_full", "Solenoid_only")
        )
    ]
    n_failure_labels = len(failure_labels)

    print("=" * 50)
    print("LABEL REGISTRY STATUS")
    print("=" * 50)
    print(f"  Total registry rows:     {total}")
    print(f"  PENDING (no findings):   {pending}")
    print(f"  No fault found:          {no_fault}")
    print(f"  With findings:           {with_findings}")
    print(f"")
    print(f"  FAILURE LABELS:          {n_failure_labels}")
    print(f"  (finding != no-fault AND starter/solenoid replaced)")
    print(f"")
    print(f"  Refit trigger threshold: >= {REFIT_TRIGGER_N_FAILURES} failure labels")
    if n_failure_labels >= REFIT_TRIGGER_N_FAILURES:
        print(f"  REFIT TRIGGER: *** REACHED *** → run refit/run_refit.py --labels")
    else:
        remaining = REFIT_TRIGGER_N_FAILURES - n_failure_labels
        print(f"  Refit trigger: NOT reached ({remaining} more failure label(s) needed)")
    print("=" * 50)

    if total > 0:
        print(f"\nVIN breakdown:")
        from collections import Counter
        vin_counts = Counter(r["vin"] for r in registry)
        for vin, n in sorted(vin_counts.items()):
            print(f"  {vin}: {n} record(s)")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    if sys.argv[1] == "--status":
        cmd_status()
    else:
        target = Path(sys.argv[1])
        ingest_path(target)
