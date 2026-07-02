"""
patch_business_graphs.py - generate an IP-sanitized business variant of
V1_1_SM_production_graphs.py for the external DICV executive deck.

The compute path (trajectory, LOVO-honest scoring, alert markers, gap masking)
is kept verbatim; ONLY display strings are replaced so that no model names,
validation-protocol names, or internal field names appear on the rendered
PNGs. Output goes to presentation/assets/ instead of graphs/.

Run:  py -3 "STARTER MOTOR/V1.1/presentation/patch_business_graphs.py"
Then: py -3 "STARTER MOTOR/V1.1/src/V1_1_SM_business_graphs.py" <VIN labels>
"""
from pathlib import Path

ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR\V1.1")
SRC = ROOT / "src" / "V1_1_SM_production_graphs.py"
OUT = ROOT / "src" / "V1_1_SM_business_graphs.py"

text = SRC.read_text(encoding="utf-8")

# (old, new) exact-substring replacements; every one must be found.
REPLACEMENTS = [
    # output directory -> presentation assets
    ('GRAPHS = ROOT / "V1.1" / "graphs"',
     'GRAPHS = ROOT / "V1.1" / "presentation" / "assets"'),
    # main risk-line legend label
    ('Causal weekly risk (LOVO-honest)',
     'Weekly vehicle health-risk'),
    # horizon band legend label (keeps the leading unicode <= char)
    ('10-wk validated horizon',
     '10-week validated warning window'),
    # alert-channel legend labels
    ('label="Persistence terminal-flag fire"',
     'label="Sustained electrical-volatility alert"'),
    ('label=f"A1 crank-burst first alarm (×{n_ep} episodes)"',
     'label=f"Crank-anomaly alert (×{n_ep} episodes)"'),
    ('label="A2 battery-cascade fire"',
     'label="Battery-cascade alert"'),
    # internal field name JCOPENDATE -> business wording
    ('\\nJCOPENDATE: {jcopen:%Y-%m-%d}\\n',
     '\\nFailure date: {jcopen:%Y-%m-%d}\\n'),
    ('f" JCOPENDATE {jcopen:%Y-%m-%d}"',
     'f" Failure {jcopen:%Y-%m-%d}"'),
    # y-axis label
    ('"Recalibrated failure probability"',
     '"Failure-risk score"'),
    # DICV voltage threshold codes -> plain labels
    ('f"A1: {VSI_NORMAL_RUNNING}V"', 'f"Normal: {VSI_NORMAL_RUNNING}V"'),
    ('f"A5: {VSI_UNDERVOLTAGE}V"', 'f"Undervoltage: {VSI_UNDERVOLTAGE}V"'),
    ('f"A6: {VSI_MIN_CRANK}V"', 'f"Crank min: {VSI_MIN_CRANK}V"'),
    # sparkline series labels + axis label
    ('"vsi_drive_mean (weekly)"', '"Avg. operating voltage (weekly)"'),
    ('"VSI weekly range (P5-P95)"', '"Operating-voltage range (P5-P95)"'),
    ('ax_spark.set_ylabel("VSI (V)"', 'ax_spark.set_ylabel("Voltage (V)"'),
    # structural-miss annotation (latent: fires only on VIN9-type exports)
    ('"structural miss — SMA-dead + silent gap"',
     '"no advance signal — telemetry ceased before failure"'),
    # SMA-dead notes -> generic wording
    ('"crank features imputed (SMA-dead config)"',
     '"crank telemetry not available for this vehicle"'),
    ('"crank ticks omitted (SMA-dead config)"',
     '"crank events not recorded for this vehicle"'),
    # title / subtitle / footers
    ('fig.suptitle(f"V1.1 Starter Motor Failure-Risk Trajectory  --  {disp_label}",',
     "fig.suptitle(f\"Starter Motor Failure-Risk Trajectory  --  "
     "{disp_label.replace('_SM', '')}\","),
    ('subtitle = (f"Nested-LOVO Ridge (4 feat, AUROC {AUROC_STR})  |  "',
     'subtitle = (f"Predictive Intelligence Engine - continuous vehicle health assessment  |  "'),
    ('subtitle += f"  |  Archetype: {archetype}"',
     'subtitle += "  |  Failure signature: " + str(archetype).split("_", 1)[-1].replace("_", " ")'),
    ('             "Daimler Starter Motor Failure Prediction | V1_1_SM | "\n'
     '             f"nested-LOVO Ridge (4 feat) AUROC {AUROC_STR} | GREEN <0.35 | "\n'
     '             "AMBER 0.35-0.55 | RED >=0.55 | no RUL/failure-date forecast | Confidential",',
     '             "DICV Starter Motor Failure Prediction Program | V1.1 | "\n'
     '             "GREEN <0.35 | AMBER 0.35-0.55 | RED >=0.55 | "\n'
     '             "risk classification - not a failure-date forecast | Confidential",'),
    ('    # Raw-source traceability footnote (display renumbering 2026-06-11)\n'
     '    fig.text(0.98, 0.024, raw_file_note(disp_label).replace("-file ", "-file label: "),\n'
     '             fontsize=8, color="#888888", ha="right", va="bottom", style="italic")\n',
     '    # (raw-source traceability footnote omitted in the business variant)\n'),
    ('             f"V1_1_SM | nested-LOVO AUROC {AUROC_STR} | generated "\n'
     '             f"{datetime.now():%Y-%m-%d}",',
     '             f"Starter Motor V1.1 | generated {datetime.now():%Y-%m-%d}",'),
]

missing = [old for old, _ in REPLACEMENTS if old not in text]
if missing:
    for m in missing:
        print("NOT FOUND:\n---\n" + m + "\n---")
    raise SystemExit(f"{len(missing)} replacement source string(s) not found; aborting.")

for old, new in REPLACEMENTS:
    n = text.count(old)
    assert 1 <= n <= 3, f"unexpected occurrence count {n}: {old[:60]!r}"
    text = text.replace(old, new)

header = (
    '# AUTO-GENERATED by presentation/patch_business_graphs.py - DO NOT EDIT.\n'
    '# Business-sanitized variant of V1_1_SM_production_graphs.py for the\n'
    '# external DICV executive deck: identical data/compute path, display\n'
    '# strings stripped of model/protocol/internal-field names.\n'
)
OUT.write_text(header + text, encoding="utf-8")
print(f"Wrote {OUT} ({len(text) + len(header)} chars, {len(REPLACEMENTS)} replacements applied)")
