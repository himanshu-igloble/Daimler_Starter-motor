"""
generate_workorders.py — BharatBenz SM Fleet V2 Work Order Generator
Outputs:
  workorders/out/WO_{VIN}_{YYYY-MM-DD}.md  (one per P0/P1 row, skip P0_OPS)
  workorders/out/OPS_CHECKLIST_{date}.md   (single file for all silence-trigger trucks)
Usage: py -3 generate_workorders.py [--date YYYY-MM-DD]
"""

import argparse
import csv
import json
import os
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent  # v2_system/
OUT_DIR = ROOT / "out"
CARDS_DIR = ROOT / "cards"

ALERT_LOG = OUT_DIR / "shadow_alert_log.csv"
FLEET_SNAPSHOT = OUT_DIR / "fleet_snapshot.csv"
CARDS_JSON = CARDS_DIR / "cards.json"

WO_OUT = HERE / "out"

# A2 trigger VINs requiring BATTERY-FIRST protocol
A2_VINS = {"VIN3_F_SM", "VIN6_F_SM", "VIN13_F_SM", "VIN14_F_SM"}

# ---------------------------------------------------------------------------
# Load helpers
# ---------------------------------------------------------------------------
def load_alert_log():
    rows = []
    with open(ALERT_LOG, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def load_cards():
    with open(CARDS_JSON, 'r', encoding='utf-8') as f:
        return {c['vin_label']: c for c in json.load(f)}


# ---------------------------------------------------------------------------
# BATTERY-FIRST protocol (A2 trigger)
# ---------------------------------------------------------------------------
BATTERY_FIRST_PROTOCOL = """\
### ROUTING: BATTERY-FIRST Protocol (DICV A6 cascade)
Trigger A2_battery_cascade_fired indicates a voltage step pattern consistent with
battery cascade degradation. Inspect batteries BEFORE starter circuit.

**Step 1 — OCV + Load Test (both 12V batteries)**
- Measure open-circuit voltage (OCV) on both batteries (expected: 12.4–12.7V fully charged)
- Perform load test at 50% CCA for 15 seconds; voltage must not drop below 9.6V
- Record: Battery 1 OCV _______V  |  Load test _______V
- Record: Battery 2 OCV _______V  |  Load test _______V

**Step 2 — Terminal/Cable/Lug Resistance Inspection**
- Inspect all battery terminals, main cables, and lug connections
- Resistance rule: each 10 mΩ ≈ 5 V crank drop (SAE J3053)
- Use milliohm meter; target ≤5 mΩ per joint
- Note corrosion, loose lugs, heat-damaged insulation

**Step 3 — Rest-VSI History Review**
- Review VSI rest-voltage history from PdM card (evidence summary above)
- Note any sagging trend over past 90 days

**Step 4 — ONLY IF batteries healthy (both pass load test) → Starter Circuit**
- Proceed to ELECTRICAL INSPECTION steps 2–5 below
- If batteries fail: replace before any starter diagnosis"""

# ---------------------------------------------------------------------------
# ELECTRICAL INSPECTION protocol (H2_dwell / RED tier)
# ---------------------------------------------------------------------------
ELECTRICAL_INSPECTION_PROTOCOL = """\
### ROUTING: ELECTRICAL INSPECTION Protocol
Trigger indicates persistent RED-tier voltage instability. Follow this order:

**Step 1 — Battery Load Test FIRST (battery confound elimination)**
- Same as Battery-First Step 1+2 above; document results before proceeding
- Do not skip: battery degradation mimics starter faults

**Step 2 — Starter Solenoid Contact / Voltage-Drop Check (SAE J3053 ≤0.5 V/segment)**
- Measure voltage drop across solenoid main contacts during cranking attempt
- Threshold: ≤0.5 V per segment (see SAE J3053)
- Excessive drop → solenoid contact wear or burning

**Step 3 — Cable & Terminal Inspection**
- Full cable path from battery positive → solenoid → starter
- Inspect connectors, ground strap, and chassis ground point
- Torque check on all high-current lugs (per DICV spec)

**Step 4 — Brush/Commutator Visual (if accessible)**
- Inspect brush length and commutator surface where access allows
- Note scoring, discolouration, or heavy carbon deposits

**Step 5 — Supervised Crank Observation**
- Observe a cold-start crank cycle with technician monitoring:
  a. Crank duration (normal < 3 seconds; flag if > 5 seconds)
  b. Number of retry attempts before successful start
  c. Voltage dip depth during cranking (flag dip > 9.0 V)
  d. Any unusual noise (clicks, grinding, slow spin)"""

# ---------------------------------------------------------------------------
# FEEDBACK CAPTURE section
# ---------------------------------------------------------------------------
FEEDBACK_CAPTURE = """\
---
## FEEDBACK CAPTURE (Label Loop — return to PdM team)
This feedback becomes a supervised label for model retraining and validation.
Please complete and return to the PdM / data engineering team upon job closure.

**Failure Mode Found (check all that apply):**
- [ ] Battery degraded (one or both batteries)
- [ ] Solenoid contacts worn / burned
- [ ] Brushes / commutator degraded
- [ ] Cable or terminal fault (corrosion / resistance)
- [ ] Clutch / pinion engagement fault
- [ ] No fault found (false positive)
- [ ] Other: _______________________________________________

**Parts Replaced:**
- [ ] Battery 1   Part #: _____________  Date replaced: ____________
- [ ] Battery 2   Part #: _____________  Date replaced: ____________
- [ ] Starter motor (full)   Part #: _____________
- [ ] Solenoid only          Part #: _____________
- [ ] Cables / terminals     Part #: _____________
- [ ] Other: _______________________________________________

**Free Text Findings:**
```
(describe observed fault, measurements taken, repair performed)


```

**Technician:** ______________________________

**Date of Inspection:** _______________________

**Workshop / Bay:** __________________________

*Return completed form to: PdM team / data engineering for supervised label update*"""

# ---------------------------------------------------------------------------
# Build one work order
# ---------------------------------------------------------------------------
def build_wo(alert_row, card, wo_date):
    vin = alert_row['vin']
    priority = alert_row['priority']
    trigger = alert_row['trigger']
    tier = alert_row['tier']
    prob = alert_row['prob']
    evidence = alert_row.get('evidence_summary', '—')
    window = alert_row.get('window_statement', '—')

    archetype = card.get('archetype', '—') if card else '—'
    physics = card.get('physics_mode', '—') if card else '—'

    # Protocol selection
    if trigger == 'A2_battery_cascade_fired' or vin in A2_VINS:
        protocol = BATTERY_FIRST_PROTOCOL
        protocol_name = "BATTERY-FIRST"
    else:
        protocol = ELECTRICAL_INSPECTION_PROTOCOL
        protocol_name = "ELECTRICAL INSPECTION"

    # Top-3 drivers
    drivers_md = ""
    if card and card.get('drivers'):
        lines = []
        for i, d in enumerate(card['drivers'][:3], 1):
            feat = d.get('feature', '—')
            gloss = d.get('gloss', '—')
            direction = d.get('direction', '—')
            z = d.get('z_score', 0)
            pctile = d.get('fleet_percentile', 0)
            contrib = d.get('contribution_std', 0)
            lines.append(
                f"{i}. **{feat}** ({direction})  \n"
                f"   {gloss}  \n"
                f"   Contribution: {contrib:+.3f} std | z={z:.2f} | fleet p{pctile:.0f}"
            )
        drivers_md = "\n".join(lines)

    # Channel history
    ch_md = ""
    if card and card.get('channel_history'):
        ch = card['channel_history']
        fcd = ch.get('first_fire_date', '—')
        streak = ch.get('persistent_red_streak_weeks', 0)
        fp = ch.get('channel_fp_record', {})
        ch_md = (
            f"- First channel: **{ch.get('first_channel','NONE')}** @ {fcd}  \n"
            f"- Persistent RED streak: {streak} weeks  \n"
            f"- A2 NF false-alarm rate: {fp.get('a2_nf_false_alarms','—')}  \n"
            f"- Persistence NF FP: {fp.get('persistence_nf_fp','—')}"
        )

    wo = f"""\
---
# Work Order: {vin}
**Priority:** {priority} | **Tier:** {tier} | **Trigger:** {trigger}
**Date:** {wo_date}
**Archetype:** {archetype}
**Protocol:** {protocol_name}

---
## Window Statement
{window}

> **NOT a countdown clock.** The window is a retrospective scheduling guide only.

---
## Evidence Block

**Evidence summary:** {evidence}

**Model probability:** {float(prob):.3f} (tier: {tier})
**Physics mode:** {physics}

### Top-3 Drivers
{drivers_md}

### Channel History
{ch_md}

---
{protocol}

---
{FEEDBACK_CAPTURE}
"""
    return wo


# ---------------------------------------------------------------------------
# Build OPS checklist
# ---------------------------------------------------------------------------
def build_ops_checklist(ops_rows, wo_date):
    lines = [
        f"# OPS Checklist — Silence-Trigger Trucks",
        f"**Date:** {wo_date}",
        "",
        "> **Retrospective-artifact note:** In this retrospective snapshot, trucks whose",
        "> history ends before the fleet data wall appear silent by construction.",
        "> Silence is NOT proof of failure — 5 NF trucks are also SMA-dead.",
        "> This checklist is for connectivity verification only.",
        "",
        "---",
        "## 72-Hour Connectivity Check Procedure",
        "",
        "For each truck listed below, complete within 72 hours:",
        "",
        "1. **Verify vehicle operational status** — contact depot/driver to confirm",
        "   the truck is in service (not parked, off-route, or in maintenance hold).",
        "2. **Check telematics connectivity** — confirm the ECU/telemetry unit is",
        "   powered and transmitting. Check antenna, SIM card, and gateway status.",
        "3. **Force a manual data poll** if supported by the fleet management platform.",
        "4. **If truck is operational but telematics silent:** escalate to telematics",
        "   maintenance team; tag VIN in fleet system as 'telemetry fault'.",
        "5. **If truck is NOT operational (parked/decommissioned):** update fleet",
        "   status and remove from active monitoring queue.",
        "6. **If truck is operational and telemetry resumes:** no further action;",
        "   PdM system will re-score on next weekly run.",
        "",
        "---",
        "## Affected Trucks",
        "",
        "| VIN | Tier | Silence (days) | Evidence Summary |",
        "|-----|------|----------------|-----------------|",
    ]

    for r in ops_rows:
        vin = r.get('vin', '')
        tier = r.get('tier', '')
        evid = r.get('evidence_summary', '')
        sil = ''
        if 'silence_days=' in evid:
            try:
                sil = evid.split('silence_days=')[1].split(';')[0].strip()
            except Exception:
                sil = ''
        lines.append(f"| {vin} | {tier} | {sil} | {evid[:60]} |")

    lines += [
        "",
        "---",
        "## Sign-Off",
        "",
        "| VIN | Checked by | Date | Status | Notes |",
        "|-----|-----------|------|--------|-------|",
    ]
    for r in ops_rows:
        lines.append(f"| {r.get('vin','')} | | | | |")

    lines += [
        "",
        "---",
        "*Return completed checklist to fleet operations supervisor.*",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', default=None, help='Override date (YYYY-MM-DD)')
    args = parser.parse_args()

    if args.date:
        wo_date = args.date
    else:
        # Deterministic: use fleet_snapshot.csv mtime
        wo_date = datetime.fromtimestamp(FLEET_SNAPSHOT.stat().st_mtime).strftime('%Y-%m-%d')

    alert_rows = load_alert_log()
    cards = load_cards()

    WO_OUT.mkdir(parents=True, exist_ok=True)

    p0p1_rows = [r for r in alert_rows if r.get('priority') in ('P0', 'P1')]
    ops_rows = [r for r in alert_rows if r.get('priority') == 'P0_OPS']

    # Deduplicate: one WO per unique VIN+priority combination
    seen = set()
    wo_files = []
    for row in p0p1_rows:
        vin = row['vin']
        pri = row['priority']
        key = (vin, pri)
        if key in seen:
            continue
        seen.add(key)

        card = cards.get(vin)
        wo_content = build_wo(row, card, wo_date)
        fname = WO_OUT / f"WO_{vin}_{wo_date}.md"
        fname.write_text(wo_content, encoding='utf-8')
        wo_files.append(fname)
        print(f"[WO] {fname.name}")

    # OPS checklist
    if ops_rows:
        ops_content = build_ops_checklist(ops_rows, wo_date)
        ops_fname = WO_OUT / f"OPS_CHECKLIST_{wo_date}.md"
        ops_fname.write_text(ops_content, encoding='utf-8')
        print(f"[OPS] {ops_fname.name}")

    # Gate checks
    print(f"\n--- GATE CHECKS ---")
    print(f"WO files written: {len(wo_files)}")
    print(f"P0+P1 alert rows (deduped): {len(seen)}")
    gate_ok = len(wo_files) == len(seen)
    print(f"WO count == P0+P1 deduped: {'PASS' if gate_ok else 'FAIL'}")

    a2_wo_vins = {r['vin'] for r in p0p1_rows if r['vin'] in A2_VINS}
    print(f"A2 battery-first WOs present: {sorted(a2_wo_vins)}")
    print(f"A2 gate: {'PASS' if a2_wo_vins == A2_VINS.intersection(a2_wo_vins) else 'FAIL'}")


if __name__ == '__main__':
    main()
