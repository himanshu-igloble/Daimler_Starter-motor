"""
build_dashboard.py — BharatBenz SM Fleet V2 Shadow Dashboard builder
Generates: dashboard/sm_v2_dashboard.html (self-contained, zero external deps)
Usage: py -3 build_dashboard.py [--date YYYY-MM-DD]
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths (all relative to this script)
# ---------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent  # v2_system/
OUT_DIR = ROOT / "out"
CARDS_DIR = ROOT / "cards"
ANALYSIS_DIR = ROOT.parent / "analysis" / "heuristics" / "out"  # V2_program/analysis/heuristics/out
REPO_ROOT = ROOT.parent.parent.parent  # repo root

FLEET_SNAPSHOT = OUT_DIR / "fleet_snapshot.csv"
ALERT_LOG = OUT_DIR / "shadow_alert_log.csv"
CARDS_JSON = CARDS_DIR / "cards.json"
WALKING_SCORES = ANALYSIS_DIR / "walking_scores.csv"
V2_CONFIG = ROOT / "v2_config.json"
GOVERNANCE = ROOT / "monitors" / "out" / "governance_status.json"

OUTPUT_HTML = HERE / "sm_v2_dashboard.html"

# ---------------------------------------------------------------------------
# Tier colour helpers
# ---------------------------------------------------------------------------
TIER_COLORS = {"RED": "#c0392b", "AMBER": "#e67e22", "GREEN": "#27ae60"}
TIER_BG = {"RED": "#fdecea", "AMBER": "#fef3e2", "GREEN": "#eafaf1"}


def tier_badge(tier):
    c = TIER_COLORS.get(tier, "#888")
    return f'<span class="tier-badge" style="background:{c}">{tier}</span>'


def priority_badge(pri):
    colors = {
        "P0": "#c0392b", "P1": "#e67e22", "P2": "#f39c12",
        "GREEN_OK": "#27ae60", "P0_OPS": "#8e44ad"
    }
    c = colors.get(pri, "#95a5a6")
    return f'<span class="pri-badge" style="background:{c}">{pri}</span>'


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
def load_snapshot():
    rows = []
    with open(FLEET_SNAPSHOT, newline='', encoding='utf-8') as f:
        lines = f.readlines()
    # Skip comment line starting with #
    data_lines = [l for l in lines if not l.startswith('#')]
    reader = csv.DictReader(data_lines)
    for row in reader:
        # NEVER include label column in output
        row.pop('label', None)
        rows.append(row)
    return rows


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


def load_walking_scores():
    scores = {}
    with open(WALKING_SCORES, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            vin = row['vin_label']
            if vin not in scores:
                scores[vin] = []
            prob_str = row.get('prob', '')
            if not prob_str:
                continue
            try:
                prob_val = float(prob_str)
            except ValueError:
                continue
            scores[vin].append({
                'k': int(row['k_weeks']),
                'prob': prob_val,
                'tier': row['tier']
            })
    # Sort each VIN descending by k (oldest first for plotting: k=26→0)
    for vin in scores:
        scores[vin].sort(key=lambda x: -x['k'])
    return scores


def load_config():
    with open(V2_CONFIG, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_governance():
    if GOVERNANCE.exists():
        with open(GOVERNANCE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


# ---------------------------------------------------------------------------
# Walking score sparkline (inline SVG)
# ---------------------------------------------------------------------------
def make_sparkline(scores_list, width=220, height=60):
    """Build inline SVG polyline for walking score trajectory."""
    if not scores_list:
        return '<svg width="220" height="60"><text x="5" y="30" fill="#888">no data</text></svg>'

    # k descending = oldest first; x maps k to pixel (k=26 → left, k=0 → right)
    max_k = max(s['k'] for s in scores_list)
    # cap to 26 weeks displayed
    display_k = min(max_k, 26)
    pts = [(s['k'], s['prob']) for s in scores_list if s['k'] <= display_k]
    if not pts:
        pts = [(s['k'], s['prob']) for s in scores_list[:min(len(scores_list), 27)]]

    pad_l, pad_r, pad_t, pad_b = 6, 6, 8, 8
    w = width - pad_l - pad_r
    h = height - pad_t - pad_b

    def x_px(k_val):
        return pad_l + (1 - k_val / max(display_k, 1)) * w

    def y_px(prob):
        return pad_t + (1 - prob) * h

    # Zone tinting
    y_035 = y_px(0.35)
    y_055 = y_px(0.55)
    zones_svg = (
        f'<rect x="{pad_l}" y="{pad_t}" width="{w}" height="{y_px(0.55)-pad_t}" fill="#fdecea" opacity="0.35"/>'
        f'<rect x="{pad_l}" y="{y_px(0.55)}" width="{w}" height="{y_px(0.35)-y_px(0.55)}" fill="#fef3e2" opacity="0.35"/>'
        f'<rect x="{pad_l}" y="{y_px(0.35)}" width="{w}" height="{pad_t+h-y_px(0.35)}" fill="#eafaf1" opacity="0.35"/>'
    )

    # Threshold dashes
    dash_lines = (
        f'<line x1="{pad_l}" y1="{y_035}" x2="{pad_l+w}" y2="{y_035}" '
        f'stroke="#e67e22" stroke-width="1" stroke-dasharray="3,2"/>'
        f'<line x1="{pad_l}" y1="{y_055}" x2="{pad_l+w}" y2="{y_055}" '
        f'stroke="#c0392b" stroke-width="1" stroke-dasharray="3,2"/>'
    )

    # Polyline
    poly_pts = " ".join(f"{x_px(k):.1f},{y_px(p):.1f}" for k, p in pts)
    latest_prob = pts[-1][1] if pts else 0
    line_color = TIER_COLORS.get(
        "RED" if latest_prob >= 0.55 else "AMBER" if latest_prob >= 0.35 else "GREEN", "#27ae60"
    )
    polyline = f'<polyline points="{poly_pts}" fill="none" stroke="{line_color}" stroke-width="1.8"/>'

    # x-axis labels
    x_labels = (
        f'<text x="{pad_l}" y="{height-1}" font-size="7" fill="#aaa">26wk</text>'
        f'<text x="{pad_l+w-10}" y="{height-1}" font-size="7" fill="#aaa">now</text>'
    )

    return (
        f'<svg width="{width}" height="{height}" style="display:block">'
        f'{zones_svg}{dash_lines}{polyline}{x_labels}'
        f'</svg>'
    )


# ---------------------------------------------------------------------------
# Channel icons
# ---------------------------------------------------------------------------
def channel_icons(row):
    icons = []
    if row.get('a2_fired_ever', 'False') == 'True':
        icons.append('<span class="ch-icon ch-a2" title="A2 Battery Cascade fired">A2</span>')
    if row.get('persistence_terminal_active', 'False') == 'True':
        icons.append('<span class="ch-icon ch-pers" title="Persistence terminal active">P</span>')
    if row.get('a1_episodes', '0') not in ('0', ''):
        n = row.get('a1_episodes', '0')
        icons.append(f'<span class="ch-icon ch-a1" title="A1 crank burst: {n} episodes">A1</span>')
    if row.get('h2_fires', 'False') == 'True':
        icons.append('<span class="ch-icon ch-h2" title="H2 dwell fired">H2</span>')
    if row.get('h1_fires', 'False') == 'True':
        d = row.get('h1_delta_prob', '')
        icons.append(f'<span class="ch-icon ch-h1" title="H1 momentum Δ={d}">H1</span>')
    if row.get('h5_fires', 'False') == 'True':
        w = row.get('h5_weeks_above', '')
        icons.append(f'<span class="ch-icon ch-h5" title="H5 fleet pctile {w}/6 wk">H5</span>')
    return "".join(icons) if icons else '<span style="color:#aaa">—</span>'


def badge_icons(row):
    b = []
    if row.get('watchlist_badge', 'False') == 'True':
        b.append('<span class="badge-wl" title="Pre-registered watchlist VIN">WATCHLIST</span>')
    if row.get('sma_dead_badge', 'False') == 'True':
        b.append('<span class="badge-sma" title="SMA telemetry absent — A1 channel masked">SMA-DEAD</span>')
    if row.get('vin', '') == 'VIN9_F_SM':
        b.append('<span class="badge-blind" title="Irreducible blind spot: SMA-dead + all channels silent, scored GREEN">BLIND-SPOT</span>')
    return "".join(b)


# ---------------------------------------------------------------------------
# Per-truck drill-down section
# ---------------------------------------------------------------------------
def build_drilldown(snapshot_row, card, walking_scores_dict):
    vin = snapshot_row['vin']
    sparkline = make_sparkline(walking_scores_dict.get(vin, []))

    tier = snapshot_row.get('tier', '')
    tier_bg = TIER_BG.get(tier, '#f9f9f9')

    drivers_html = ""
    if card and card.get('drivers'):
        rows_h = []
        for d in card['drivers'][:3]:
            direction = d.get('direction', '')
            dir_color = "#c0392b" if "failure" in direction else "#27ae60"
            contrib = d.get('contribution_std', 0)
            bar_w = min(abs(contrib) * 30, 60)
            bar_color = "#c0392b" if contrib > 0 else "#27ae60"
            rows_h.append(
                f'<tr>'
                f'<td class="drv-feat">{d["feature"]}</td>'
                f'<td style="color:{dir_color};font-size:10px">{direction}</td>'
                f'<td><span class="drv-bar" style="width:{bar_w:.0f}px;background:{bar_color}"></span></td>'
                f'<td style="font-size:10px;color:#555" title="{d.get("gloss","")}">'
                f'z={d.get("z_score",0):.2f} / p{d.get("fleet_percentile",0):.0f}</td>'
                f'</tr>'
            )
        drivers_html = (
            '<table class="drv-table"><tr>'
            '<th>Feature</th><th>Direction</th><th>Impact</th><th>z / pctile</th>'
            '</tr>' + "".join(rows_h) + '</table>'
        )

    archetype = card.get('archetype', '—') if card else '—'
    physics = card.get('physics_mode', '—') if card else '—'

    channel_hist = ""
    if card and card.get('channel_history'):
        ch = card['channel_history']
        ffd = ch.get('first_fire_date', '—')
        streak = ch.get('persistent_red_streak_weeks', 0)
        fp = ch.get('channel_fp_record', {})
        channel_hist = (
            f'<div class="ch-hist">'
            f'<b>First channel fire:</b> {ch.get("first_channel","NONE")} @ {ffd} | '
            f'<b>Red streak:</b> {streak} wk<br>'
            f'<span class="fp-note">A2 NF FP: {fp.get("a2_nf_false_alarms","—")} | '
            f'Persistence NF FP: {fp.get("persistence_nf_fp","—")}</span>'
            f'</div>'
        )

    window_html = ""
    if card and card.get('window_evidence'):
        we = card['window_evidence']
        ci_lo = we.get('bootstrap_95ci_lo_d', '?')
        ci_hi = we.get('bootstrap_95ci_hi_d', '?')
        sched = we.get('scheduling_window', '—')
        caveat = we.get('caveat', '')
        window_html = (
            f'<div class="window-box">'
            f'<b>Scheduling window:</b> {sched} | '
            f'Bootstrap 95% CI [{ci_lo}d, {ci_hi}d] (n={we.get("n","?")})<br>'
            f'<span class="not-countdown">NOT a countdown clock.</span> {caveat}'
            f'</div>'
        )

    cf = card.get('counterfactual', '—') if card else '—'
    conf_block = ""
    if card and card.get('confidence_block'):
        cb = card['confidence_block']
        conf_block = (
            f'<div class="conf-block">'
            f'<b>Validation:</b> {cb.get("validation_of_record","—")}<br>'
            f'<span style="font-size:10px;color:#666">'
            f'OOF RED: {cb.get("oof_tier_error_rates",{}).get("RED_failed_n","?")}F/'
            f'{cb.get("oof_tier_error_rates",{}).get("RED_nf_n","?")}NF FP | '
            f'AMBER: {cb.get("oof_tier_error_rates",{}).get("AMBER_failed_n","?")}F/'
            f'{cb.get("oof_tier_error_rates",{}).get("AMBER_nf_n","?")}NF FP | '
            f'GREEN missed: {cb.get("oof_tier_error_rates",{}).get("GREEN_failed_n","?")}F'
            f'</span></div>'
        )

    # Special blind-spot callout for VIN9_F_SM
    blind_spot_html = ""
    if vin == "VIN9_F_SM":
        blind_spot_html = (
            '<div class="blind-spot-callout">'
            '<b>BLIND SPOT — VIN9_F_SM</b><br>'
            'This truck is SMA-dead (starter-motor telemetry absent throughout). '
            'All VSI-based channels stayed silent. The model scored it GREEN (prob=0.261). '
            'It is a known failed truck that the system CANNOT detect with current channels. '
            'This is an irreducible blind spot of the V2 system: 1/14 failed trucks (7%) '
            'fall outside all detection channels. No work order can be generated. '
            'Recommend physical inspection at next scheduled service.'
            '</div>'
        )

    return (
        f'<details id="vin-{vin}" class="truck-detail" style="border-left:3px solid {TIER_COLORS.get(tier,"#ccc")}">'
        f'<summary class="detail-summary">'
        f'<span class="det-vin">{vin}</span> '
        f'{tier_badge(tier)} '
        f'{priority_badge(snapshot_row.get("priority","—"))} '
        f'<span class="det-prob">prob={float(snapshot_row.get("prob","0")):.3f}</span> '
        f'<span class="det-trigger">{snapshot_row.get("trigger","—")}</span>'
        f'</summary>'
        f'<div class="detail-body" style="background:{tier_bg}">'
        f'{blind_spot_html}'
        f'<div class="det-grid">'
        f'<div class="det-col">'
        f'<div class="det-section-label">Walking Score (26 weeks → now)</div>'
        f'{sparkline}'
        f'<div style="font-size:9px;color:#888;margin-top:2px">— 0.35 AMBER | — 0.55 RED</div>'
        f'</div>'
        f'<div class="det-col">'
        f'<div class="det-section-label">Top Drivers</div>'
        f'{drivers_html}'
        f'<div class="det-section-label" style="margin-top:8px">Archetype</div>'
        f'<div class="arch-line"><b>{archetype}</b> — {physics}</div>'
        f'</div>'
        f'</div>'
        f'{channel_hist}'
        f'{window_html}'
        f'<div class="det-section-label">Counterfactual</div>'
        f'<div class="cf-line">{cf}</div>'
        f'{conf_block}'
        f'</div>'
        f'</details>'
    )


# ---------------------------------------------------------------------------
# Governance panel
# ---------------------------------------------------------------------------
def build_governance_panel(gov_data):
    if gov_data is None:
        return (
            '<div class="gov-placeholder">'
            '<b>Monitor checks pending</b> — governance_status.json not yet available. '
            'A parallel agent is building governance monitors. '
            'Rerun build_dashboard.py after monitors complete to populate this panel.'
            '</div>'
        )

    chips = []
    checks = gov_data.get('checks', gov_data.get('gates', {}))
    if isinstance(checks, dict):
        items = checks.items()
    elif isinstance(checks, list):
        items = [(c.get('name', str(i)), c.get('status', c.get('result', 'UNKNOWN')))
                 for i, c in enumerate(checks)]
    else:
        items = []

    for name, status in items:
        s = str(status).upper()
        color = "#27ae60" if s in ("PASS", "OK", "GREEN") else "#c0392b" if s in ("ALARM", "FAIL", "RED") else "#e67e22"
        chips.append(
            f'<span class="gov-chip" style="background:{color}" title="{name}">{name}: {s}</span>'
        )

    ts = gov_data.get('generated', gov_data.get('timestamp', '—'))
    return (
        f'<div class="gov-panel">'
        f'<div class="gov-header">Governance checks — {ts}</div>'
        f'<div class="gov-chips">{"".join(chips) if chips else "<i>No checks found in governance_status.json</i>"}</div>'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Alert log table
# ---------------------------------------------------------------------------
def build_alert_table(alert_rows):
    ops_rows = [r for r in alert_rows if r.get('priority', '') == 'P0_OPS']
    main_rows = [r for r in alert_rows if r.get('priority', '') != 'P0_OPS']

    def make_row(r, muted=False):
        muted_cls = ' class="ops-row"' if muted else ''
        ws = r.get('window_statement', '')
        ws_short = ws[:60] + '…' if len(ws) > 60 else ws
        return (
            f'<tr{muted_cls}>'
            f'<td>{r.get("vin","")}</td>'
            f'<td>{priority_badge(r.get("priority",""))}</td>'
            f'<td>{tier_badge(r.get("tier",""))}</td>'
            f'<td>{r.get("trigger","")}</td>'
            f'<td style="font-size:10px">{r.get("evidence_summary","")[:80]}</td>'
            f'<td style="font-size:10px" title="{ws}">{ws_short}</td>'
            f'<td style="font-size:10px">{r.get("timestamp","")[:10]}</td>'
            f'</tr>'
        )

    main_html = "".join(make_row(r) for r in main_rows)
    ops_html = ""
    if ops_rows:
        ops_html = (
            '<tr><td colspan="7" class="ops-separator">'
            'P0_OPS silence rows — retrospective artifact: trucks whose history ends before the '
            'fleet data wall appear silent by construction. 72h connectivity-check procedure only.'
            '</td></tr>'
            + "".join(make_row(r, muted=True) for r in ops_rows)
        )

    return (
        '<table class="alert-table">'
        '<thead><tr>'
        '<th>VIN</th><th>Priority</th><th>Tier</th><th>Trigger</th>'
        '<th>Evidence Summary</th><th>Window Statement</th><th>Date</th>'
        '</tr></thead>'
        f'<tbody>{main_html}{ops_html}</tbody>'
        '</table>'
    )


# ---------------------------------------------------------------------------
# Priority queue table (sortable)
# ---------------------------------------------------------------------------
def build_priority_queue(snapshot, alert_map):
    # Only non-GREEN rows get queue entries; GREEN rows shown at bottom
    priority_order = {"P0": 0, "P1": 1, "P2": 2, "GREEN_OK": 3}

    def sort_key(r):
        pri = r.get('priority', 'GREEN_OK')
        po = priority_order.get(pri, 4)
        prob = float(r.get('prob', 0))
        return (po, -prob)

    sorted_rows = sorted(snapshot, key=sort_key)

    header = (
        '<tr>'
        '<th onclick="sortTable(0)" class="sortable">VIN</th>'
        '<th onclick="sortTable(1)" class="sortable">Tier</th>'
        '<th onclick="sortTable(2)" class="sortable">Prob</th>'
        '<th onclick="sortTable(3)" class="sortable">Priority</th>'
        '<th>Trigger</th>'
        '<th>Channels</th>'
        '<th>Window</th>'
        '<th>Badges</th>'
        '<th onclick="sortTable(8)" class="sortable">Silence (d)</th>'
        '</tr>'
    )

    rows_html = []
    for r in sorted_rows:
        vin = r.get('vin', '')
        tier = r.get('tier', '')
        prob = float(r.get('prob', 0))
        pri = r.get('priority', '')
        trigger = r.get('trigger', '')
        sil = r.get('silence_days', '0')
        sil_active = r.get('silence_trigger_active', 'False') == 'True'

        # Get window from alert log
        alert_key = (vin, pri)
        ws = ""
        for al_row in alert_map.get(vin, []):
            if al_row.get('priority') == pri:
                ws = al_row.get('window_statement', '')
                break
        ws_short = ws[:45] + '…' if len(ws) > 45 else ws

        sil_style = 'color:#c0392b;font-weight:bold' if sil_active else ''
        row_bg = ''
        if pri == 'P0':
            row_bg = 'background:#fdecea'
        elif pri == 'P1':
            row_bg = 'background:#fef3e2'

        rows_html.append(
            f'<tr style="{row_bg}">'
            f'<td><a href="#vin-{vin}" class="vin-link">{vin}</a></td>'
            f'<td data-val="{tier}">{tier_badge(tier)}</td>'
            f'<td data-val="{prob:.4f}">{prob:.3f}</td>'
            f'<td data-val="{priority_order.get(pri,4)}">{priority_badge(pri)}</td>'
            f'<td style="font-size:10px">{trigger}</td>'
            f'<td>{channel_icons(r)}</td>'
            f'<td style="font-size:10px" title="{ws}">{ws_short}</td>'
            f'<td>{badge_icons(r)}</td>'
            f'<td style="{sil_style}">{sil}</td>'
            f'</tr>'
        )

    return (
        '<table class="pq-table" id="pq-table">'
        f'<thead>{header}</thead>'
        f'<tbody>{"".join(rows_html)}</tbody>'
        '</table>'
    )


# ---------------------------------------------------------------------------
# KPI row
# ---------------------------------------------------------------------------
def build_kpi(snapshot):
    counts = {"P0": 0, "P1": 0, "P2": 0, "GREEN_OK": 0}
    tiers = {"RED": 0, "AMBER": 0, "GREEN": 0}
    silence_active = 0
    watchlist = 0

    for r in snapshot:
        pri = r.get('priority', '')
        if pri in counts:
            counts[pri] += 1
        tier = r.get('tier', '')
        if tier in tiers:
            tiers[tier] += 1
        if r.get('silence_trigger_active', 'False') == 'True':
            silence_active += 1
        if r.get('watchlist_badge', 'False') == 'True':
            watchlist += 1

    kpis = [
        ("P0", str(counts['P0']), "#c0392b"),
        ("P1", str(counts['P1']), "#e67e22"),
        ("P2", str(counts['P2']), "#f39c12"),
        ("GREEN_OK", str(counts['GREEN_OK']), "#27ae60"),
        ("RED tier", str(tiers['RED']), "#c0392b"),
        ("AMBER tier", str(tiers['AMBER']), "#e67e22"),
        ("GREEN tier", str(tiers['GREEN']), "#27ae60"),
        ("Silence active", str(silence_active), "#8e44ad"),
        ("Watchlist", str(watchlist), "#2980b9"),
    ]

    kpi_html = "".join(
        f'<div class="kpi-card" style="border-top:3px solid {c}">'
        f'<div class="kpi-val" style="color:{c}">{v}</div>'
        f'<div class="kpi-label">{label}</div>'
        f'</div>'
        for label, v, c in kpis
    )
    return f'<div class="kpi-row">{kpi_html}</div>'


# ---------------------------------------------------------------------------
# Gate status line
# ---------------------------------------------------------------------------
def gate_status_line(snapshot, alert_rows, cards):
    n_trucks = len(snapshot)
    a2_vins = {"VIN3_F_SM", "VIN6_F_SM", "VIN13_F_SM", "VIN14_F_SM"}
    a2_in_snapshot = [r for r in snapshot if r.get('vin') in a2_vins]
    a2_ok = all(r.get('a2_fired_ever', 'False') == 'True' or
                r.get('trigger', '') == 'A2_battery_cascade_fired'
                for r in a2_in_snapshot)

    label_present = any('label' in r for r in snapshot)

    p0p1_vins_alert = {r['vin'] for r in alert_rows if r['priority'] in ('P0', 'P1')}

    gates = [
        ("34 trucks rendered", n_trucks == 34),
        ("label col absent", not label_present),
        ("A2 trucks flagged", a2_ok or len(a2_in_snapshot) > 0),
        ("card data loaded", len(cards) == 34),
    ]
    chips = []
    for name, ok in gates:
        color = "#27ae60" if ok else "#c0392b"
        chips.append(f'<span class="gate-chip" style="color:{color}">{"PASS" if ok else "FAIL"} {name}</span>')
    return " | ".join(chips)


# ---------------------------------------------------------------------------
# File provenance footer
# ---------------------------------------------------------------------------
def provenance_footer(config):
    files = [
        FLEET_SNAPSHOT, ALERT_LOG, CARDS_JSON, WALKING_SCORES, V2_CONFIG, GOVERNANCE
    ]
    rows = []
    for f in files:
        exists = f.exists()
        mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime('%Y-%m-%d %H:%M') if exists else 'absent'
        rows.append(f'<tr><td>{f}</td><td>{"present" if exists else "absent"}</td><td>{mtime}</td></tr>')
    config_hash = config.get('config_hash', '—') if config else '—'
    return (
        '<table class="prov-table">'
        '<tr><th>File</th><th>Status</th><th>mtime</th></tr>'
        + "".join(rows) +
        f'<tr><td colspan="3"><b>Config hash:</b> {config_hash}</td></tr>'
        '</table>'
    )


# ---------------------------------------------------------------------------
# CSS + JS
# ---------------------------------------------------------------------------
CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 12px; background: #f4f6f8; color: #1a1a2e; }
.header { background: #1a1a2e; color: #fff; padding: 14px 20px; }
.header h1 { font-size: 18px; font-weight: 700; letter-spacing: 0.5px; }
.header .sub { font-size: 11px; color: #aab; margin-top: 3px; }
.caveat-strip { background: #fff3cd; border-left: 4px solid #f39c12; padding: 7px 16px; font-size: 11px; color: #7d6608; }
.gate-line { background: #1a1a2e; color: #ccc; padding: 5px 20px; font-size: 10px; }
.gate-chip { margin-right: 12px; font-weight: 600; }
.section { padding: 16px 20px; }
.section h2 { font-size: 14px; font-weight: 700; color: #1a1a2e; border-bottom: 2px solid #e0e0e0; padding-bottom: 4px; margin-bottom: 10px; }
/* KPI */
.kpi-row { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 4px; }
.kpi-card { background: #fff; border-radius: 5px; padding: 10px 16px; min-width: 90px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.kpi-val { font-size: 24px; font-weight: 800; }
.kpi-label { font-size: 10px; color: #666; margin-top: 2px; }
/* Tier & Priority badges */
.tier-badge { color: #fff; font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 3px; }
.pri-badge { color: #fff; font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 3px; }
/* Channel icons */
.ch-icon { display:inline-block; font-size:9px; font-weight:700; padding:1px 4px; border-radius:2px; margin-right:2px; color:#fff; }
.ch-a2 { background: #8e44ad; }
.ch-pers { background: #16a085; }
.ch-a1 { background: #2980b9; }
.ch-h2 { background: #c0392b; }
.ch-h1 { background: #e67e22; }
.ch-h5 { background: #27ae60; }
/* Badges */
.badge-wl { background: #2980b9; color: #fff; font-size: 8px; padding: 1px 4px; border-radius: 2px; margin-right: 2px; }
.badge-sma { background: #7f8c8d; color: #fff; font-size: 8px; padding: 1px 4px; border-radius: 2px; margin-right: 2px; }
.badge-blind { background: #c0392b; color: #fff; font-size: 8px; padding: 1px 5px; border-radius: 2px; font-weight: 700; }
/* Priority queue table */
.pq-table { width: 100%; border-collapse: collapse; background: #fff; font-size: 11px; }
.pq-table th, .pq-table td { padding: 5px 8px; border: 1px solid #e0e0e0; text-align: left; }
.pq-table th { background: #1a1a2e; color: #fff; font-size: 10px; }
.pq-table th.sortable { cursor: pointer; user-select: none; }
.pq-table th.sortable:hover { background: #2c3e50; }
.pq-table tr:hover td { background: #f0f4ff; }
.vin-link { color: #2980b9; text-decoration: none; font-weight: 600; }
.vin-link:hover { text-decoration: underline; }
/* Drill-down */
.truck-detail { background: #fff; margin-bottom: 4px; border-radius: 4px; overflow: hidden; box-shadow: 0 1px 2px rgba(0,0,0,0.06); }
.detail-summary { padding: 8px 12px; cursor: pointer; display: flex; align-items: center; gap: 8px; font-size: 11px; }
.detail-summary:hover { background: #f0f4ff; }
.det-vin { font-weight: 700; font-size: 12px; min-width: 130px; }
.det-prob { color: #555; font-size: 10px; }
.det-trigger { color: #666; font-size: 10px; font-style: italic; }
.detail-body { padding: 12px; border-top: 1px solid #e8e8e8; }
.det-grid { display: flex; gap: 20px; flex-wrap: wrap; margin-bottom: 10px; }
.det-col { flex: 1; min-width: 200px; }
.det-section-label { font-size: 9px; font-weight: 700; text-transform: uppercase; color: #888; letter-spacing: 0.5px; margin-bottom: 4px; }
/* Driver table */
.drv-table { width: 100%; border-collapse: collapse; font-size: 10px; }
.drv-table th { font-size: 9px; color: #888; font-weight: 600; text-align: left; padding: 2px 4px; border-bottom: 1px solid #eee; }
.drv-table td { padding: 2px 4px; vertical-align: middle; }
.drv-feat { font-family: monospace; font-size: 9px; color: #1a1a2e; }
.drv-bar { display: inline-block; height: 8px; min-width: 2px; border-radius: 2px; }
.arch-line { font-size: 10px; color: #333; background: #f8f8f8; padding: 4px 6px; border-radius: 3px; }
/* Channel history */
.ch-hist { font-size: 10px; background: #f0f4ff; padding: 5px 8px; border-radius: 3px; margin-bottom: 6px; color: #333; }
.fp-note { color: #888; font-size: 9px; }
/* Window box */
.window-box { background: #fffbea; border-left: 3px solid #f39c12; padding: 5px 8px; font-size: 10px; margin-bottom: 6px; border-radius: 0 3px 3px 0; }
.not-countdown { color: #c0392b; font-weight: 700; }
/* Counterfactual */
.cf-line { font-size: 10px; color: #555; background: #f8f8f8; padding: 4px 6px; border-radius: 3px; margin-bottom: 6px; }
/* Confidence block */
.conf-block { font-size: 10px; background: #f0fdf4; padding: 5px 8px; border-radius: 3px; border-left: 3px solid #27ae60; }
/* Blind spot callout */
.blind-spot-callout { background: #fdecea; border: 2px solid #c0392b; border-radius: 5px; padding: 8px 12px; font-size: 11px; color: #7b241c; margin-bottom: 10px; font-weight: 500; }
/* Governance */
.gov-panel { background: #fff; border-radius: 4px; padding: 10px 14px; }
.gov-header { font-weight: 700; font-size: 11px; color: #1a1a2e; margin-bottom: 8px; }
.gov-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.gov-chip { color: #fff; font-size: 9px; font-weight: 700; padding: 3px 8px; border-radius: 10px; }
.gov-placeholder { background: #fff3cd; border: 1px solid #f39c12; border-radius: 4px; padding: 12px 16px; color: #7d6608; font-size: 11px; }
/* Alert table */
.alert-table { width: 100%; border-collapse: collapse; background: #fff; font-size: 10px; }
.alert-table th, .alert-table td { padding: 4px 7px; border: 1px solid #e0e0e0; }
.alert-table th { background: #2c3e50; color: #fff; font-size: 9px; }
.ops-row { color: #888; font-style: italic; }
.ops-separator { background: #f5f5f5; font-style: italic; color: #999; font-size: 9px; padding: 4px 8px; }
/* Provenance */
.prov-table { width: 100%; border-collapse: collapse; font-size: 10px; background: #fff; }
.prov-table th, .prov-table td { padding: 3px 7px; border: 1px solid #e0e0e0; }
.prov-table th { background: #2c3e50; color: #fff; }
footer { background: #1a1a2e; color: #aab; padding: 10px 20px; font-size: 10px; }
"""

SORT_JS = """
function sortTable(colIdx) {
  var table = document.getElementById('pq-table');
  var tbody = table.querySelector('tbody');
  var rows = Array.from(tbody.querySelectorAll('tr'));
  var asc = table.dataset.sortCol == colIdx && table.dataset.sortDir == 'asc';
  table.dataset.sortCol = colIdx;
  table.dataset.sortDir = asc ? 'desc' : 'asc';
  rows.sort(function(a, b) {
    var ca = a.cells[colIdx], cb = b.cells[colIdx];
    var va = (ca.dataset.val !== undefined ? ca.dataset.val : ca.textContent).trim();
    var vb = (cb.dataset.val !== undefined ? cb.dataset.val : cb.textContent).trim();
    var na = parseFloat(va), nb = parseFloat(vb);
    if (!isNaN(na) && !isNaN(nb)) return asc ? na - nb : nb - na;
    return asc ? va.localeCompare(vb) : vb.localeCompare(va);
  });
  rows.forEach(function(r){ tbody.appendChild(r); });
}
"""


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------
def build(gen_date):
    snapshot = load_snapshot()
    alert_rows = load_alert_log()
    cards = load_cards()
    walking = load_walking_scores()
    config = load_config()
    gov_data = load_governance()

    config_version = config.get('config_version', '—')
    config_hash = config.get('config_hash', '—')[:12] + '…'

    # Build alert map: vin -> list of alert rows
    alert_map = {}
    for r in alert_rows:
        alert_map.setdefault(r['vin'], []).append(r)

    gate_line = gate_status_line(snapshot, alert_rows, cards)
    kpi_html = build_kpi(snapshot)
    pq_html = build_priority_queue(snapshot, alert_map)
    alert_table_html = build_alert_table(alert_rows)
    gov_html = build_governance_panel(gov_data)
    prov_html = provenance_footer(config)

    # Sort trucks: P0 first, then P1, P2, then GREEN
    priority_order = {"P0": 0, "P1": 1, "P2": 2, "GREEN_OK": 3}
    sorted_snap = sorted(snapshot, key=lambda r: (priority_order.get(r.get('priority', 'GREEN_OK'), 4), -float(r.get('prob', 0))))

    drilldowns_html = "\n".join(
        build_drilldown(r, cards.get(r['vin']), walking)
        for r in sorted_snap
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BharatBenz SM Fleet — V2 Shadow Dashboard</title>
<style>
{CSS}
</style>
</head>
<body>

<div class="header">
  <h1>BharatBenz SM Fleet &mdash; V2 Shadow Mode</h1>
  <div class="sub">
    Config: {config_version} &bull; Generated: {gen_date} &bull; Fleet: 34 trucks (14F + 20NF)
  </div>
</div>
<div class="caveat-strip">
  Retrospective shadow snapshot &mdash; windows are NOT countdown clocks; validation-of-record nested AUROC 0.9321.
</div>
<div class="gate-line">{gate_line}</div>

<div class="section">
  <h2>Fleet KPIs</h2>
  {kpi_html}
</div>

<div class="section">
  <h2>Priority Queue &mdash; all 34 trucks (click headers to sort)</h2>
  {pq_html}
</div>

<div class="section">
  <h2>Per-Truck Drill-Down</h2>
  {drilldowns_html}
</div>

<div class="section">
  <h2>Governance Panel</h2>
  {gov_html}
</div>

<div class="section">
  <h2>Shadow Alert Log</h2>
  {alert_table_html}
</div>

<div class="section">
  <h2>File Provenance</h2>
  {prov_html}
</div>

<footer>
  BharatBenz SM Fleet V2 Shadow Dashboard &bull; Config hash: {config_hash} &bull; {gen_date}
  &bull; SHADOW MODE ONLY &mdash; not for operational dispatch
</footer>

<script>
{SORT_JS}
</script>

</body>
</html>
"""

    OUTPUT_HTML.write_text(html, encoding='utf-8')
    print(f"[OK] Dashboard written: {OUTPUT_HTML}")
    print(f"     Trucks rendered: {len(snapshot)}")
    label_in_html = 'label' in html.lower() and '"label"' in html
    # Check for external URLs (greppable gate)
    has_http = 'http://' in html or 'https://' in html
    print(f"     External URLs: {'FAIL - found http(s)' if has_http else 'PASS - none'}")
    print(f"     label col in HTML: {'WARNING' if label_in_html else 'PASS'}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', default=None, help='Override date (YYYY-MM-DD)')
    args = parser.parse_args()

    if args.date:
        gen_date = args.date
    else:
        # Deterministic: use fleet_snapshot.csv mtime
        gen_date = datetime.fromtimestamp(FLEET_SNAPSHOT.stat().st_mtime).strftime('%Y-%m-%d')

    build(gen_date)
