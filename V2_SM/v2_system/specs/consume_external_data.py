"""
consume_external_data.py — C4 validation stubs for external DICV data.

validate_saledate(csv_path)     — validates the SALEDATE / in-service date CSV
validate_maintenance(csv_path)  — validates the maintenance records CSV

Both functions:
  - Check required columns are present
  - Validate data types and ranges
  - Check VIN label format matches the SM fleet pattern
  - Produce clear error messages with row numbers
  - Dry-run merge preview (does not write files)
  - Return (ok: bool, issues: list[str])

Self-test: run this file directly to exercise 3-row synthetic CSVs per validator
(one valid row, one bad VIN, one bad date).

Usage: py -3 "STARTER MOTOR/V2_program/v2_system/specs/consume_external_data.py"
"""
from __future__ import annotations
import io
import re
import datetime
import sys
from typing import List, Tuple

# ---------------------------------------------------------------------------
# Known VIN labels for the SM fleet (34 trucks)
# These are the production labels used in V1.1 weekly caches and validation CSV.
# ---------------------------------------------------------------------------
KNOWN_NF_VINS = {
    f"VIN{i}_NF_SM" for i in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12,
                                13, 14, 15, 16, 17, 18, 19, 20]
}
KNOWN_F_VINS = {
    f"VIN{i}_F_SM" for i in range(1, 15)  # VIN1_F_SM .. VIN14_F_SM
}
ALL_KNOWN_VINS = KNOWN_NF_VINS | KNOWN_F_VINS
VIN_PATTERN = re.compile(r"^VIN\d+_(F|NF)_SM$")
DATE_FMT = "%Y-%m-%d"

MAINTENANCE_EVENT_TYPES = {
    "starter_replacement", "starter_repair", "battery_replacement",
    "battery_test", "cable_replacement", "terminal_cleaning",
    "alternator_replacement", "electrical_inspection", "roadside_failure",
    "other_electrical",
}


# ---------------------------------------------------------------------------
def _parse_csv(csv_path: str) -> Tuple[List[str], List[List[str]]]:
    """Read CSV into (headers, rows). Accepts a path or a raw CSV string."""
    if "\n" in csv_path or "," in csv_path and not csv_path.endswith(".csv"):
        # treat as raw CSV string (used in self-test)
        text = csv_path
    else:
        with open(csv_path, encoding="utf-8") as f:
            text = f.read()
    reader = [line for line in text.strip().splitlines() if line.strip()]
    if not reader:
        return [], []
    headers = [h.strip().lower() for h in reader[0].split(",")]
    rows = [[c.strip() for c in line.split(",", len(headers) - 1)]
            for line in reader[1:]]
    return headers, rows


def _check_date(val: str, col: str, row_i: int) -> List[str]:
    errs: List[str] = []
    if not val:
        errs.append(f"Row {row_i}: '{col}' is empty")
        return errs
    try:
        d = datetime.datetime.strptime(val, DATE_FMT).date()
        if d.year < 2018 or d.year > 2030:
            errs.append(f"Row {row_i}: '{col}' year {d.year} out of expected range 2018–2030")
    except ValueError:
        errs.append(f"Row {row_i}: '{col}' = '{val}' is not a valid YYYY-MM-DD date")
    return errs


def _check_vin(val: str, row_i: int) -> List[str]:
    errs: List[str] = []
    if not val:
        errs.append(f"Row {row_i}: 'anon_label' is empty")
        return errs
    if not VIN_PATTERN.match(val):
        errs.append(
            f"Row {row_i}: 'anon_label' = '{val}' does not match pattern VINn_(F|NF)_SM"
        )
    elif val not in ALL_KNOWN_VINS:
        errs.append(
            f"Row {row_i}: 'anon_label' = '{val}' not in the 34-truck SM fleet VIN registry "
            f"(new fleet truck? Add to ALL_KNOWN_VINS before processing)"
        )
    return errs


# ---------------------------------------------------------------------------
def validate_saledate(csv_path: str) -> Tuple[bool, List[str]]:
    """
    Validate the SALEDATE CSV from DICV.

    Required columns: anon_label, saledate
    Optional: inservice_date, gvw_config, spec_notes

    Returns (ok, issues) where ok=True means no blocking errors.
    Warnings (non-blocking) are prefixed 'WARN:'.
    """
    issues: List[str] = []
    headers, rows = _parse_csv(csv_path)

    # -- required columns
    for req in ("anon_label", "saledate"):
        if req not in headers:
            issues.append(f"MISSING REQUIRED COLUMN: '{req}'")
    if issues:
        return False, issues

    ai = headers.index("anon_label")
    si = headers.index("saledate")
    ii = headers.index("inservice_date") if "inservice_date" in headers else None

    seen_vins: set[str] = set()
    for r_i, row in enumerate(rows, start=2):  # row 1 = header
        if len(row) < len(headers):
            row += [""] * (len(headers) - len(row))

        vin = row[ai]
        sale = row[si]
        in_svc = row[ii] if ii is not None else ""

        issues += _check_vin(vin, r_i)
        issues += _check_date(sale, "saledate", r_i)
        if in_svc:
            issues += _check_date(in_svc, "inservice_date", r_i)
            # inservice_date should be >= saledate
            try:
                sd = datetime.datetime.strptime(sale, DATE_FMT).date()
                id_ = datetime.datetime.strptime(in_svc, DATE_FMT).date()
                if id_ < sd:
                    issues.append(
                        f"Row {r_i}: 'inservice_date' {in_svc} is before 'saledate' {sale}"
                    )
                if (id_ - sd).days > 365:
                    issues.append(
                        f"WARN: Row {r_i}: gap between saledate and inservice_date "
                        f"is {(id_ - sd).days} days — unusually long, please verify"
                    )
            except ValueError:
                pass  # already reported above

        if vin and vin in seen_vins:
            issues.append(f"Row {r_i}: duplicate 'anon_label' = '{vin}'")
        elif vin:
            seen_vins.add(vin)

    # -- coverage check
    missing = sorted(ALL_KNOWN_VINS - seen_vins)
    if missing:
        issues.append(
            f"WARN: {len(missing)} known fleet VINs not present in this CSV "
            f"(first 5: {missing[:5]}). Partial delivery — OK if batch split."
        )

    # -- dry-run merge preview
    ok_vins = [r[ai] for r in rows if r[ai] in ALL_KNOWN_VINS
               and len(r) > max(ai, si) and r[si]]
    print(f"[validate_saledate] dry-run preview: {len(ok_vins)} rows would merge cleanly:")
    for vin in ok_vins[:5]:
        row = rows[[r[ai] for r in rows].index(vin)]
        sale = row[si]
        print(f"  {vin} -> saledate={sale}")
    if len(ok_vins) > 5:
        print(f"  ... and {len(ok_vins) - 5} more")

    blocking = [i for i in issues if not i.startswith("WARN:")]
    return len(blocking) == 0, issues


# ---------------------------------------------------------------------------
def validate_maintenance(csv_path: str) -> Tuple[bool, List[str]]:
    """
    Validate the maintenance records CSV from DICV.

    Required columns: anon_label, event_date, event_type, part_description
    Optional: part_number, odometer_km, service_outlet, warranty_claim, technician_notes

    Returns (ok, issues) where ok=True means no blocking errors.
    """
    issues: List[str] = []
    headers, rows = _parse_csv(csv_path)

    for req in ("anon_label", "event_date", "event_type", "part_description"):
        if req not in headers:
            issues.append(f"MISSING REQUIRED COLUMN: '{req}'")
    if issues:
        return False, issues

    ai = headers.index("anon_label")
    ei = headers.index("event_date")
    ti = headers.index("event_type")
    pi = headers.index("part_description")
    oi = headers.index("odometer_km") if "odometer_km" in headers else None

    for r_i, row in enumerate(rows, start=2):
        if len(row) < len(headers):
            row += [""] * (len(headers) - len(row))

        vin = row[ai]
        evt_date = row[ei]
        evt_type = row[ti].lower().strip() if row[ti] else ""
        part_desc = row[pi]
        odo = row[oi] if oi is not None else ""

        issues += _check_vin(vin, r_i)
        issues += _check_date(evt_date, "event_date", r_i)

        if not evt_type:
            issues.append(f"Row {r_i}: 'event_type' is empty")
        elif evt_type not in MAINTENANCE_EVENT_TYPES:
            issues.append(
                f"Row {r_i}: 'event_type' = '{evt_type}' not in controlled vocabulary. "
                f"Use one of: {sorted(MAINTENANCE_EVENT_TYPES)}"
            )

        if not part_desc:
            issues.append(f"Row {r_i}: 'part_description' is empty")

        if odo:
            try:
                odo_int = int(odo)
                if odo_int < 0 or odo_int > 2_000_000:
                    issues.append(
                        f"Row {r_i}: 'odometer_km' = {odo_int} out of range 0–2,000,000"
                    )
            except ValueError:
                issues.append(
                    f"Row {r_i}: 'odometer_km' = '{odo}' is not a valid integer"
                )

    # -- dry-run merge preview (group by VIN)
    ok_rows = [(rows[i][ai], rows[i][ei], rows[i][ti])
               for i in range(len(rows))
               if len(rows[i]) > max(ai, ei, ti)
               and rows[i][ai] in ALL_KNOWN_VINS]
    vin_counts: dict[str, int] = {}
    for vin, _, _ in ok_rows:
        vin_counts[vin] = vin_counts.get(vin, 0) + 1
    print(f"[validate_maintenance] dry-run preview: {len(ok_rows)} rows would merge "
          f"across {len(vin_counts)} VINs:")
    for vin, cnt in sorted(vin_counts.items())[:5]:
        print(f"  {vin}: {cnt} event(s)")
    if len(vin_counts) > 5:
        print(f"  ... and {len(vin_counts) - 5} more VINs")

    blocking = [i for i in issues if not i.startswith("WARN:")]
    return len(blocking) == 0, issues


# ---------------------------------------------------------------------------
# SELF-TEST
# ---------------------------------------------------------------------------
def _run_self_tests() -> None:
    print("=" * 70)
    print("SELF-TEST: validate_saledate — 3 synthetic rows")
    print("=" * 70)

    # Row 1: valid
    # Row 2: bad VIN format (wrong suffix)
    # Row 3: bad date format
    sd_csv_valid = (
        "anon_label,saledate,inservice_date\n"
        "VIN1_F_SM,2023-04-15,2023-04-22\n"
    )
    sd_csv_bad_vin = (
        "anon_label,saledate,inservice_date\n"
        "VIN99_BADFORMAT,2023-06-01,2023-06-05\n"
    )
    sd_csv_bad_date = (
        "anon_label,saledate,inservice_date\n"
        "VIN2_NF_SM,15/04/2023,2023-04-22\n"
    )

    # Test valid row
    ok, issues = validate_saledate(sd_csv_valid)
    assert ok, f"FAIL: expected ok=True for valid row, got issues={issues}"
    print(f"[1] Valid row -> ok={ok}, issues={[i for i in issues if not i.startswith('WARN')]}")

    # Test bad VIN
    ok, issues = validate_saledate(sd_csv_bad_vin)
    assert not ok, f"FAIL: expected ok=False for bad VIN, got ok={ok}"
    vin_issues = [i for i in issues if "anon_label" in i.lower() or "VIN99" in i]
    assert vin_issues, f"FAIL: expected a VIN-related error message, got: {issues}"
    print(f"[2] Bad VIN -> ok={ok}, blocking issue: {vin_issues[0]}")

    # Test bad date
    ok, issues = validate_saledate(sd_csv_bad_date)
    assert not ok, f"FAIL: expected ok=False for bad date, got ok={ok}"
    date_issues = [i for i in issues if "saledate" in i.lower() or "YYYY" in i]
    assert date_issues, f"FAIL: expected a date-related error message, got: {issues}"
    print(f"[3] Bad date -> ok={ok}, blocking issue: {date_issues[0]}")

    print()
    print("=" * 70)
    print("SELF-TEST: validate_maintenance — 3 synthetic rows")
    print("=" * 70)

    # Row 1: valid starter_replacement
    # Row 2: bad VIN
    # Row 3: bad date
    mt_csv_valid = (
        "anon_label,event_date,event_type,part_description,odometer_km\n"
        "VIN3_F_SM,2025-09-01,battery_replacement,Lucas TVS 12V 200Ah battery x2,95000\n"
    )
    mt_csv_bad_vin = (
        "anon_label,event_date,event_type,part_description,odometer_km\n"
        "VIN_WRONG_FORMAT,2025-03-01,starter_replacement,Bosch 0001416009 24V 5.4kW,78000\n"
    )
    mt_csv_bad_date = (
        "anon_label,event_date,event_type,part_description,odometer_km\n"
        "VIN7_F_SM,March-2025,starter_repair,Brush set replacement,67000\n"
    )

    ok, issues = validate_maintenance(mt_csv_valid)
    assert ok, f"FAIL: expected ok=True for valid maint row, got issues={issues}"
    print(f"[1] Valid row -> ok={ok}, issues={[i for i in issues if not i.startswith('WARN')]}")

    ok, issues = validate_maintenance(mt_csv_bad_vin)
    assert not ok, f"FAIL: expected ok=False for bad VIN in maintenance, got ok={ok}"
    vin_issues = [i for i in issues if "anon_label" in i.lower() or "VIN_WRONG" in i]
    assert vin_issues, f"FAIL: expected a VIN error, got: {issues}"
    print(f"[2] Bad VIN -> ok={ok}, blocking issue: {vin_issues[0]}")

    ok, issues = validate_maintenance(mt_csv_bad_date)
    assert not ok, f"FAIL: expected ok=False for bad date in maintenance, got ok={ok}"
    date_issues = [i for i in issues if "event_date" in i.lower() or "YYYY" in i]
    assert date_issues, f"FAIL: expected a date error, got: {issues}"
    print(f"[3] Bad date -> ok={ok}, blocking issue: {date_issues[0]}")

    print()
    print("ALL SELF-TESTS PASSED")


if __name__ == "__main__":
    _run_self_tests()
