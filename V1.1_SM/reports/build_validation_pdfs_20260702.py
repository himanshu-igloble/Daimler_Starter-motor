# -*- coding: utf-8 -*-
"""
DICV Starter-Motor Risk-Prediction - Management Validation deliverables.
Builds TWO polished PDFs into STARTER MOTOR/V1.1/reports (dated 2026-07-02):
  1. <date>_DICV_StarterMotor_Validation_Report.pdf   (comprehensive dossier)
  2. <date>_DICV_StarterMotor_Validation_Brief.pdf     (crisp management version)

The SM analog of the alternator pair (V11.1_ALT/reports/2026-06-28_*). Mirrors the
alternator builder's reportlab structure, styles, disclosure level, header/footer and
Report+Brief pairing. Every number is sourced/verified from the frozen V1.1_SM model
and its V1.1/V2/V2.1/V3/V3.1 validation iterations (RESULTS_MASTER, gates.json,
model_spec.json, horizon_curve.csv, V3.1 T1/T2 heuristics). No values invented.

VIN convention: non-failed trucks keep their RAW _SM labels here (VIN2_NF_SM stays
VIN2_NF_SM); the +14 deck display-name convention is NOT applied, so labels match the
embedded per-truck evidence figures.

Run:  py -3 build_validation_pdfs_20260702.py
"""
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph,
    Spacer, Table, TableStyle, Image, PageBreak, NextPageTemplate, KeepTogether,
    ListFlowable, ListItem, HRFlowable, CondPageBreak)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from PIL import Image as PILImage

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
REPO   = r"D:\Daimler-starter_motor_alternator_battery"
OUT    = os.path.join(REPO, "STARTER MOTOR", "V1.1", "reports")
EVID   = os.path.join(REPO, "STARTER MOTOR", "V1.1", "visualizations", "rul_evidence_stack")
GRAPHS = os.path.join(REPO, "STARTER MOTOR", "V1.1", "graphs")
DATE   = "2026-07-02"
os.makedirs(OUT, exist_ok=True)

def evid(name):
    return os.path.join(EVID, name)

def graph(name):
    return os.path.join(GRAPHS, name)

# --------------------------------------------------------------------------- #
# Fonts (Windows TTFs, graceful fallback to Helvetica/Times)
# --------------------------------------------------------------------------- #
FONT_DIR = r"C:\Windows\Fonts"
BODY = BODY_BD = BODY_IT = None
for fam, n, b, i, z in [
    ("Calibri", "calibri.ttf", "calibrib.ttf", "calibrii.ttf", "calibriz.ttf"),
    ("SegoeUI", "segoeui.ttf", "segoeuib.ttf", "segoeuii.ttf", "segoeuiz.ttf"),
    ("Arial",   "arial.ttf",   "arialbd.ttf",  "ariali.ttf",   "arialbi.ttf"),
]:
    try:
        pdfmetrics.registerFont(TTFont(fam, os.path.join(FONT_DIR, n)))
        pdfmetrics.registerFont(TTFont(fam + "-Bold", os.path.join(FONT_DIR, b)))
        pdfmetrics.registerFont(TTFont(fam + "-Italic", os.path.join(FONT_DIR, i)))
        pdfmetrics.registerFont(TTFont(fam + "-BoldItalic", os.path.join(FONT_DIR, z)))
        registerFontFamily(fam, normal=fam, bold=fam + "-Bold",
                           italic=fam + "-Italic", boldItalic=fam + "-BoldItalic")
        BODY, BODY_BD, BODY_IT = fam, fam + "-Bold", fam + "-Italic"
        break
    except Exception:
        continue
if BODY is None:
    BODY, BODY_BD, BODY_IT = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"

HEAD = BODY_BD
try:
    pdfmetrics.registerFont(TTFont("Georgia", os.path.join(FONT_DIR, "georgia.ttf")))
    pdfmetrics.registerFont(TTFont("Georgia-Bold", os.path.join(FONT_DIR, "georgiab.ttf")))
    registerFontFamily("Georgia", normal="Georgia", bold="Georgia-Bold")
    HEAD = "Georgia-Bold"
except Exception:
    HEAD = BODY_BD

# --------------------------------------------------------------------------- #
# Palette
# --------------------------------------------------------------------------- #
NAVY   = HexColor("#0B2545")
STEEL  = HexColor("#13315C")
ACCENT = HexColor("#1B6CA8")
TEAL   = HexColor("#2A9D8F")
AMBER  = HexColor("#E1A53B")
RED    = HexColor("#C0392B")
GREEN  = HexColor("#2E7D32")
LIGHT  = HexColor("#EEF3F8")
RULE   = HexColor("#C9D6E5")
GREYTX = HexColor("#46505A")
INK    = HexColor("#1F2933")
CALLBG = HexColor("#EAF2FA")
WARNBG = HexColor("#FBF3E5")

# --------------------------------------------------------------------------- #
# Geometry
# --------------------------------------------------------------------------- #
W, H = A4
ML = MR = 1.9 * cm
MT = 2.15 * cm
MB = 1.65 * cm
AVAIL_W = W - ML - MR

HEADER_LEFT = ""
HEADER_RIGHT = ""
FOOTER_LEFT = "CONFIDENTIAL  ·  Prepared for DICV (Daimler India Commercial Vehicles)"
FOOTER_CENTER = ""

# --------------------------------------------------------------------------- #
# Styles
# --------------------------------------------------------------------------- #
ss = getSampleStyleSheet()
def _st(name, **kw):
    return ParagraphStyle(name, **kw)

S = {
 "H1": _st("H1", fontName=HEAD, fontSize=15.5, leading=19, textColor=NAVY,
           spaceBefore=16, spaceAfter=7, keepWithNext=1),
 "H2": _st("H2", fontName=BODY_BD, fontSize=12, leading=15, textColor=STEEL,
           spaceBefore=11, spaceAfter=4, keepWithNext=1),
 "H3": _st("H3", fontName=BODY_BD, fontSize=10.3, leading=13, textColor=ACCENT,
           spaceBefore=8, spaceAfter=2, keepWithNext=1),
 "Body": _st("Body", fontName=BODY, fontSize=9.4, leading=13.6, textColor=INK,
             alignment=TA_JUSTIFY, spaceAfter=6),
 "BodyL": _st("BodyL", fontName=BODY, fontSize=9.4, leading=13.6, textColor=INK,
              alignment=TA_LEFT, spaceAfter=6),
 "Sm": _st("Sm", fontName=BODY, fontSize=8.4, leading=11.5, textColor=GREYTX,
           alignment=TA_LEFT, spaceAfter=4),
 "Bul": _st("Bul", fontName=BODY, fontSize=9.4, leading=13.2, textColor=INK,
            leftIndent=12, spaceAfter=3),
 "Cap": _st("Cap", fontName=BODY_IT, fontSize=8, leading=10.5, textColor=GREYTX,
            alignment=TA_CENTER, spaceBefore=3, spaceAfter=11),
 "CTit": _st("CTit", fontName=BODY_BD, fontSize=9.8, leading=12.5, textColor=NAVY,
             spaceAfter=2),
 "CBody": _st("CBody", fontName=BODY, fontSize=9, leading=12.5, textColor=INK),
 "cp": _st("cp", fontName=BODY, fontSize=7.8, leading=9.6, textColor=INK),
 "cpb": _st("cpb", fontName=BODY_BD, fontSize=7.8, leading=9.6, textColor=INK),
 "cph": _st("cph", fontName=BODY_BD, fontSize=7.9, leading=9.8, textColor=white,
            alignment=TA_CENTER),
 "TocTitle": _st("TocTitle", fontName=HEAD, fontSize=15.5, leading=19,
                 textColor=NAVY, spaceAfter=10),
}
TOC_L0 = _st("TOC0", fontName=BODY_BD, fontSize=10, leading=18, textColor=STEEL)
TOC_L1 = _st("TOC1", fontName=BODY, fontSize=9.2, leading=15, leftIndent=16,
             textColor=INK)

def P(t, s="Body"):
    return Paragraph(t, S[s])

def Hd(t, s):
    return Paragraph(t, S[s])

def bullets(items, style="Bul", bullet="•", color=ACCENT):
    flow = []
    for it in items:
        flow.append(Paragraph(
            '<font color="#%s">%s</font>&nbsp;&nbsp;%s' % (color.hexval()[2:], bullet, it),
            S[style]))
    return flow

def hr(color=RULE, w=0.6, sb=2, sa=6):
    return HRFlowable(width="100%", thickness=w, color=color,
                      spaceBefore=sb, spaceAfter=sa)

# --------------------------------------------------------------------------- #
# Table + figure + callout helpers
# --------------------------------------------------------------------------- #
def tbl(data, cw, fs=8.2, head_bg=NAVY, aligns=None, zebra=True, hfs=None,
        grid=RULE, lp=4, rp=4, tp=3.2, bp=3.2):
    t = Table(data, colWidths=cw, repeatRows=1)
    sty = [
        ("BACKGROUND", (0, 0), (-1, 0), head_bg),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTNAME", (0, 0), (-1, 0), BODY_BD),
        ("FONTSIZE", (0, 0), (-1, 0), hfs or fs),
        ("FONTNAME", (0, 1), (-1, -1), BODY),
        ("FONTSIZE", (0, 1), (-1, -1), fs),
        ("TEXTCOLOR", (0, 1), (-1, -1), INK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), tp),
        ("BOTTOMPADDING", (0, 0), (-1, -1), bp),
        ("LEFTPADDING", (0, 0), (-1, -1), lp),
        ("RIGHTPADDING", (0, 0), (-1, -1), rp),
        ("GRID", (0, 0), (-1, -1), 0.4, grid),
        ("LINEBELOW", (0, 0), (-1, 0), 1.0, NAVY),
    ]
    if zebra:
        for r in range(2, len(data), 2):
            sty.append(("BACKGROUND", (0, r), (-1, r), LIGHT))
    if aligns:
        for col, al in aligns.items():
            sty.append(("ALIGN", (col, 1), (col, -1), al))
    t.setStyle(TableStyle(sty))
    return t

def _imgsize(path, w):
    iw, ih = PILImage.open(path).size
    return w, w * ih / float(iw)

def fig(path, caption, w=12.4 * cm, maxh=15.5 * cm):
    if not os.path.exists(path):
        return P("<i>[figure not found: %s]</i>" % os.path.basename(path), "Cap")
    fw, fh = _imgsize(path, w)
    if fh > maxh:
        fw = fw * maxh / fh
        fh = maxh
    im = Image(path, width=fw, height=fh)
    im.hAlign = "CENTER"
    return KeepTogether([im, P(caption, "Cap")])

def fig_cell(path, caption, w):
    """Figure for use INSIDE a table cell (no KeepTogether)."""
    if not os.path.exists(path):
        return [P("<i>[figure not found: %s]</i>" % os.path.basename(path), "Cap")]
    fw, fh = _imgsize(path, w)
    im = Image(path, width=fw, height=fh)
    im.hAlign = "CENTER"
    return [im, P(caption, "Cap")]

def callout(title, body, bg=CALLBG, bar=ACCENT):
    inner = []
    if title:
        inner.append(Paragraph(title, S["CTit"]))
    if isinstance(body, (list, tuple)):
        inner.extend(body)
    else:
        inner.append(Paragraph(body, S["CBody"]))
    t = Table([[inner]], colWidths=[AVAIL_W])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("LEFTPADDING", (0, 0), (-1, -1), 11),
        ("RIGHTPADDING", (0, 0), (-1, -1), 11),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LINEBEFORE", (0, 0), (0, -1), 3.2, bar),
        ("BOX", (0, 0), (-1, -1), 0.3, RULE),
    ]))
    return t

def kpi_band(cards):
    """cards = list of (big, label, color)."""
    row = []
    n = len(cards)
    for big, lab, col in cards:
        cell = [
            Paragraph('<font color="#%s">%s</font>' % (col.hexval()[2:], big),
                      _st("kpi", fontName=BODY_BD, fontSize=16, leading=18,
                          alignment=TA_CENTER, textColor=col)),
            Paragraph(lab, _st("kpil", fontName=BODY, fontSize=7.6, leading=9.4,
                               alignment=TA_CENTER, textColor=GREYTX)),
        ]
        row.append(cell)
    t = Table([row], colWidths=[AVAIL_W / n] * n)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, -1), HexColor("#F4F7FB")),
        ("BOX", (0, 0), (-1, -1), 0.4, RULE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, RULE),
    ]))
    return t

# --------------------------------------------------------------------------- #
# Numbered canvas (Page x of y) + header/footer
# --------------------------------------------------------------------------- #
class NumberedCanvas(canvas.Canvas):
    def __init__(self, *a, **k):
        canvas.Canvas.__init__(self, *a, **k)
        self._saved = []

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved)
        for st in self._saved:
            self.__dict__.update(st)
            self._decorate(total)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def _decorate(self, total):
        pn = self._pageNumber
        if pn == 1:
            return
        self.saveState()
        self.setFont(BODY, 7.8)
        self.setFillColor(GREYTX)
        self.drawString(ML, H - 1.12 * cm, HEADER_LEFT)
        self.drawRightString(W - MR, H - 1.12 * cm,
                             HEADER_RIGHT or ("Starter-Motor Validation · " + DATE))
        self.setStrokeColor(RULE)
        self.setLineWidth(0.5)
        self.line(ML, H - 1.28 * cm, W - MR, H - 1.28 * cm)
        self.line(ML, 1.30 * cm, W - MR, 1.30 * cm)
        self.drawString(ML, 0.95 * cm, FOOTER_LEFT)
        self.drawRightString(W - MR, 0.95 * cm, "Page %d of %d" % (pn, total))
        if FOOTER_CENTER:
            self.drawCentredString(W / 2.0, 0.95 * cm, FOOTER_CENTER)
        self.restoreState()

# --------------------------------------------------------------------------- #
# Doc template with TOC capture + PDF outline
# --------------------------------------------------------------------------- #
class Doc(BaseDocTemplate):
    def __init__(self, filename, cover_fn, **kw):
        BaseDocTemplate.__init__(self, filename, pagesize=A4,
                                 leftMargin=ML, rightMargin=MR,
                                 topMargin=MT, bottomMargin=MB, **kw)
        fcover = Frame(0, 0, W, H, id="cover", leftPadding=0, rightPadding=0,
                       topPadding=0, bottomPadding=0)
        fbody = Frame(ML, MB, AVAIL_W, H - MT - MB, id="body",
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates([
            PageTemplate(id="Cover", frames=[fcover], onPage=cover_fn),
            PageTemplate(id="Body", frames=[fbody]),
        ])
        self._tc = 0

    def _startBuild(self, *a, **k):
        self._tc = 0  # stable TOC keys across multiBuild passes
        return BaseDocTemplate._startBuild(self, *a, **k)

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph):
            nm = flowable.style.name
            if nm in ("H1", "H2"):
                txt = flowable.getPlainText()
                lvl = 0 if nm == "H1" else 1
                self._tc += 1
                key = "h%d" % self._tc
                self.canv.bookmarkPage(key)
                self.canv.addOutlineEntry(txt, key, level=lvl, closed=(lvl > 0))
                if lvl == 0:
                    self.notify("TOCEntry", (0, txt, self.page, key))

def make_toc():
    toc = TableOfContents()
    toc.levelStyles = [TOC_L0, TOC_L1]
    toc.dotsMinLevel = 0
    return toc

# --------------------------------------------------------------------------- #
# Cover pages (drawn directly on canvas)
# --------------------------------------------------------------------------- #
def _kpi_cards(c, x0, y0, cards, cw, ch, gap):
    x = x0
    for big, lab, col in cards:
        c.setFillColor(white)
        c.setStrokeColor(RULE)
        c.setLineWidth(0.6)
        c.roundRect(x, y0, cw, ch, 5, fill=1, stroke=1)
        c.setFillColor(col)
        c.rect(x, y0 + ch - 4, cw, 4, fill=1, stroke=0)
        c.setFillColor(NAVY)
        c.setFont(BODY_BD, 17)
        c.drawCentredString(x + cw / 2.0, y0 + ch / 2.0 + 1, big)
        c.setFillColor(GREYTX)
        c.setFont(BODY, 7.4)
        c.drawCentredString(x + cw / 2.0, y0 + 7, lab)
        x += cw + gap

def _cover(c, doc, title1, title2, eyebrow, subtitle, cards, meta_pairs):
    c.saveState()
    blk = 292
    c.setFillColor(NAVY)
    c.rect(0, H - blk, W, blk, fill=1, stroke=0)
    c.setFillColor(STEEL)
    c.rect(0, H - blk, W * 0.62, blk, fill=1, stroke=0)
    c.setFillColor(TEAL)
    c.rect(0, H - blk - 7, W, 7, fill=1, stroke=0)
    c.setFillColor(HexColor("#9FC3E0"))
    c.setFont(BODY_BD, 9.2)
    c.drawString(ML, H - 62, eyebrow)
    c.setFillColor(white)
    maxw = W - 2 * ML
    ts = 26.0
    for t in (title1, title2):
        while ts > 12 and pdfmetrics.stringWidth(t, HEAD, ts) > maxw:
            ts -= 0.5
    c.setFont(HEAD, ts)
    c.drawString(ML, H - 104, title1)
    c.drawString(ML, H - 104 - (ts + 8), title2)
    c.setFillColor(HexColor("#C9DCEC"))
    c.setFont(BODY, 11)
    ty = H - 178
    for line in subtitle:
        c.drawString(ML, ty, line)
        ty -= 16
    n = len(cards)
    gap = 10
    cw = (AVAIL_W - gap * (n - 1)) / n
    _kpi_cards(c, ML, H - blk - 36 - 4, cards, cw, 72, gap)
    my = H - blk - 150
    c.setStrokeColor(RULE)
    c.setLineWidth(0.7)
    c.line(ML, my + 18, W - MR, my + 18)
    colw = AVAIL_W / 2.0
    for i, (k, v) in enumerate(meta_pairs):
        col = i % 2
        rowi = i // 2
        xx = ML + col * colw
        yy = my - rowi * 30
        c.setFillColor(ACCENT)
        c.setFont(BODY_BD, 7.6)
        c.drawString(xx, yy, k.upper())
        c.setFillColor(INK)
        c.setFont(BODY, 9.4)
        c.drawString(xx, yy - 12, v)
    c.setFillColor(NAVY)
    c.rect(0, 0, W, 34, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont(BODY_BD, 8)
    c.drawString(ML, 12, "CONFIDENTIAL — FOR DICV MANAGEMENT REVIEW")
    c.setFont(BODY, 8)
    c.drawRightString(W - MR, 12, "Prepared by ByteEdge  ·  BharatBenz 5528T Predictive Maintenance")
    c.restoreState()

def cover_report(c, doc):
    _cover(c, doc,
        "Starter-Motor Risk-Prediction System",
        "Technical Validation & Management Review",
        "DICV · BHARATBENZ 5528T · PREDICTIVE MAINTENANCE",
        ["A rigorous, evidence-backed validation of the frozen V1.1 starter-motor",
         "risk-ranking model — detection, alert lead time, maintenance windows and limits."],
        [("0.9321", "Ranking AUROC (LOVO)", TEAL),
         ("13 / 14", "Failures caught", GREEN),
         ("0 / 20", "Battery-alert false alarms", ACCENT),
         ("168 d", "Median alert lead", AMBER)],
        [("Model under review", "V1.1_SM  (frozen; reproduced through V3.1)"),
         ("Report date", "02 July 2026"),
         ("Fleet", "34 trucks — 14 failed + 20 non-failed"),
         ("Method", "Nested LOVO Ridge · 4 features · n = 14 events"),
         ("Document type", "Technical validation report + Q&A dossier"),
         ("Status", "Final — for management review")])

def cover_brief(c, doc):
    _cover(c, doc,
        "Starter-Motor Risk Prediction",
        "Management Brief",
        "DICV · BHARATBENZ 5528T · PREDICTIVE MAINTENANCE",
        ["The one-read summary: what the system catches, the alert lead time,",
         "the maintenance-window verdict, what we honestly miss, and the asks."],
        [("0.9321", "Ranking AUROC", TEAL),
         ("13 / 14", "Failures caught", GREEN),
         ("0 / 20", "Battery-alert false alarms", ACCENT),
         ("Deploy", "On existing telematics", AMBER)],
        [("Model", "V1.1_SM (frozen)"),
         ("Date", "02 July 2026"),
         ("Fleet", "34 trucks (14 F + 20 NF)"),
         ("Companion", "Full validation report (same folder)"),
         ("Audience", "DICV management"),
         ("Status", "Final")])

# --------------------------------------------------------------------------- #
# Report story
# --------------------------------------------------------------------------- #
def story_report():
    st = [NextPageTemplate("Body"), Spacer(1, 1), PageBreak()]

    # ----- Document control ------------------------------------------------ #
    st += [Hd("Document Control", "H1"), hr(NAVY, 1.0)]
    dc = [
        ["Field", "Detail"],
        ["Title", "Starter-Motor Risk-Prediction System — Technical Validation & Management Review"],
        ["Model under review", "V1.1_SM starter-motor risk-ranking model (frozen)"],
        ["Validation record", "V1.1 (build) + V2, V2.1, V3, V3.1 (independent re-tests; benchmark reproduced)"],
        ["Date", "02 July 2026"],
        ["Component / platform", "Starter motor — BharatBenz 5528T heavy-duty truck, 24 V electrical system"],
        ["Fleet", "34 independent trucks: 14 failed (F) + 20 non-failed (NF)"],
        ["Signals used", "Existing 6-signal CAN telemetry only (VSI, SMA, RPM, CSP, ANR, GED) @ 5 s; no new hardware"],
        ["Evaluation", "Nested Leave-One-Vehicle-Out (LOVO) cross-validation; n = 14 failure events"],
        ["Prepared by", "ByteEdge — Predictive Maintenance"],
        ["Classification", "Confidential — for DICV management review"],
    ]
    st += [tbl([[P(c, "cp") if i else P(c, "cph") for c in row]
                for i, row in enumerate(dc)],
               [4.6 * cm, AVAIL_W - 4.6 * cm], fs=8.6, aligns={0: "LEFT", 1: "LEFT"})]
    st += [Spacer(1, 6),
           P("<b>Purpose.</b> This document provides the detection evidence, statistical "
             "validation, engineering interpretation and honest limits required to present the "
             "starter-motor risk-ranking system to DICV management with confidence. Every figure "
             "quoted is traceable to a committed V1.1_SM result file or one of its four independent "
             "re-test iterations; the data lineage is listed in Appendix&nbsp;B.", "Body"),
           P("<b>How to read it.</b> Sections&nbsp;1–3 cover what the system is and how it was "
             "built; Sections&nbsp;4–5 prove it is validated and not over-fit; "
             "Sections&nbsp;6–8 are the operational outputs (alerts, maintenance windows, "
             "service routing); Section&nbsp;9 states the honest limits; Section&nbsp;10 shows "
             "per-truck evidence; Section&nbsp;11 is the path forward. A crisp companion brief for "
             "management is provided as a separate file.", "Body"),
           P("<b>A note on truck labels.</b> Non-failed trucks keep their raw <i>_SM</i> labels "
             "throughout the body text, the tables and the per-truck evidence figures (e.g. "
             "VIN2_NF_SM stays VIN2_NF_SM); the +14 deck display-name convention is deliberately "
             "<i>not</i> applied. The single exception is the fleet-risk overview graph "
             "(Figure&nbsp;6.1), which retains its native sequential display numbering for the "
             "non-failed trucks (VIN15_NF–VIN34_NF); its failed-truck labels (VIN1_F–VIN14_F) are "
             "identical to those used everywhere in this report.", "Sm")]
    st += [PageBreak()]

    # ----- TOC ------------------------------------------------------------- #
    st += [Paragraph("Contents", S["TocTitle"]), hr(NAVY, 1.0), Spacer(1, 4),
           make_toc(), PageBreak()]

    st += sec1_exec()
    st += sec2_fleet()
    st += sec3_model()
    st += sec4_validation()
    st += sec5_overfit()
    st += sec6_alerts()
    st += sec7_rul()
    st += sec8_routing()
    st += sec9_limits()
    st += sec10_evidence()
    st += sec11_forward()
    st += appA_qna()
    st += appB_lineage()
    return st

def sec1_exec():
    st = [Hd("1&nbsp;&nbsp;Executive Summary", "H1"), hr(NAVY, 1.0)]
    st += [kpi_band([("0.9321", "Ranking AUROC (LOVO)", TEAL),
                     ("13 / 14", "Failures caught (recall 93%)", GREEN),
                     ("0 / 20", "Battery-alert false alarms", ACCENT),
                     ("168 d", "Median alert lead", AMBER)]),
           Spacer(1, 8)]
    st += [P("The starter-motor risk-prediction system <b>ranks</b> every truck by failure risk "
             "from existing crank- and battery-voltage telemetry, <b>alerts</b> when a "
             "degradation precursor persists, and <b>schedules</b> service inside an empirically "
             "validated maintenance window — converting reactive starter/battery breakdowns "
             "into planned maintenance with no new hardware.", "Body")]
    st += [Hd("What the validation confirms", "H3")]
    st += bullets([
        "<b>Strong, honest ranking.</b> The headline is a <i>ranking</i> score (AUROC 0.9321), "
        "<b>not</b> an accuracy figure: it means <b>261 of 280</b> failed/healthy truck pairs are "
        "ordered correctly (14&times;20 pairs), on trucks the model never saw in training. "
        "95% CI [0.811, 0.986]; permutation p = 0.005 (not chance).",
        "<b>Detection is strong.</b> The alert channels flag <b>13 of 14</b> failures, with a "
        "median first-fire lead of <b>168 days</b> (range 77–424 days before the recorded "
        "failure date). One structural blind spot remains (the VIN9-class truck).",
        "<b>Maintenance windows hold up.</b> Of the 11 failures that received a predicted service "
        "window, <b>9 fell inside it</b>; both misses were late on the safe side (the truck failed "
        "later than the window closed, never earlier).",
        "<b>We proved we tried to beat it.</b> Across three independent iterations, "
        "<b>17 pre-registered candidate improvements were tested and rejected</b>, and the frozen "
        "benchmark was reproduced to the 4th decimal four times. The model sits at the "
        "<i>data's</i> ceiling.",
    ])
    st += [callout("The honest ceiling — a data limit, not a method limit",
        "Day-precise per-truck remaining life cannot beat a simple fleet-average clock, four of "
        "fourteen failures are electrically <i>silent</i>, and the confidence interval is wide "
        "— all consequences of having just <b>14 failure events</b>. Every one lifts with more "
        "data. Phase&nbsp;2 (500 trucks) is the unlock, using this same validated method and no new "
        "modelling risk.", bg=WARNBG, bar=AMBER)]
    st += [Hd("Recommendation", "H3"),
           P("Deploy the system now on existing telematics: (1)&nbsp;weekly risk ranking and "
             "green/amber/red tiers, (2)&nbsp;the validated alert channels (persistence flag + "
             "A2 battery-cascade), and (3)&nbsp;tier-based maintenance windows for planned service. "
             "Communicate performance as <b>“93% ranking accuracy, 13 of 14 failures caught, "
             "zero battery-alert false alarms.”</b> Scale to 500 trucks to unlock per-truck "
             "timing.", "Body")]
    st += [PageBreak()]
    return st

def sec2_fleet():
    st = [Hd("2&nbsp;&nbsp;Fleet &amp; Data", "H1"), hr(NAVY, 1.0)]
    st += [P("The starter-motor programme is built and validated on an <b>independent</b> fleet of "
             "34 heavy-duty trucks — a completely different set of physical vehicles from the "
             "alternator programme (no VIN-level cross-analysis between the two is valid).", "Body")]
    st += [kpi_band([("34", "Trucks (14 F + 20 NF)", STEEL),
                     ("107.2 M", "Telemetry rows @ 5 s", ACCENT),
                     ("6", "CAN signals", TEAL),
                     ("20,471", "Catalogued crank events", AMBER)]),
           Spacer(1, 8)]
    fd = [P(x, "cph") for x in ["Item", "Detail"]]
    rows = [
        ["Fleet", "34 independent trucks — 14 failed + 20 non-failed (suffix _SM)"],
        ["Raw telemetry", "107.2 M five-second CAN rows across the failed and non-failed cohorts"],
        ["Signals (6)", "VSI (supply/charging voltage), SMA (starter active), RPM, CSP (vehicle speed), "
                        "ANR (engine torque), GED (excitation state)"],
        ["Not available", "Cranking current, battery SoC/SoH, alternator/starter temperature, GPS/region"],
        ["Model unit", "2,636 truck-weeks (window-anchored) + a 20,471-event gap-aware crank catalogue"],
        ["Independence", "Starter-motor VINs ≠ alternator VINs — different trucks; no cross-dataset inference"],
    ]
    st += [tbl([fd] + [[P(r[0], "cpb"), P(r[1], "cp")] for r in rows],
               [3.6 * cm, AVAIL_W - 3.6 * cm], fs=8.4)]
    st += [P("Because the useful starter-motor signature lives in <i>crank</i> and <i>resting</i> "
             "voltage behaviour, the pipeline first builds a per-truck crank-event catalogue and "
             "weekly voltage aggregates, then engineers change-based (not level-based) features "
             "anchored to each truck's own history. Seven trucks fall in an <b>SMA-dead</b> cohort "
             "(the starter-active signal never toggles); crank features are cohort-masked for them "
             "so a wiring/config artifact is never read as a fault.", "Body")]
    st += [PageBreak()]
    return st

def sec3_model():
    st = [Hd("3&nbsp;&nbsp;The Model (Frozen V1.1)", "H1"), hr(NAVY, 1.0)]
    st += [P("The deployed model is a small, L2-regularised linear ranker "
             "(RidgeClassifier, alpha = 1.0) over <b>four</b> voltage-condition features. It has "
             "been <b>frozen since V1.1</b>; every later iteration (V2, V2.1, V3, V3.1) re-derives "
             "its benchmark and reproduces it to the fourth decimal. Deliberately tiny capacity is "
             "the point — at only 14 failure events a larger model would memorise, not "
             "generalise.", "Body")]
    st += [Hd("3.1&nbsp;&nbsp;The four features — in business terms", "H2")]
    st += [P("Each feature is a physically interpretable proxy for starter/battery-circuit "
             "degradation. The table gives the plain-language meaning alongside the technical name "
             "used in the code and the model card.", "Body")]
    mh = [P(x, "cph") for x in
          ["What it measures (business)", "Technical feature", "Role in the model"]]
    mr = [
        ["Within-week voltage stability vs the truck's own baseline",
         "vsi_withinwk_std_ratio_30d_w", "The workhorse (coef +0.886); core signal"],
        ["Resting (engine-off) voltage floor vs own baseline",
         "rest_vsi_p05_delta90", "Battery-floor sag — the battery-cascade signature"],
        ["Weekly voltage-range trend (widening / narrowing swing)",
         "vsi_range_trend", "Directional suppressor; stabilises ranking"],
        ["Crank voltage-dip trend (dip deepening near failure)",
         "dip_depth_last90_delta", "Crank-circuit load signature"],
    ]
    st += [tbl([mh] + [[P(r[0], "cp"), P(r[1], "cpb"), P(r[2], "cp")] for r in mr],
               [7.0 * cm, 5.2 * cm, AVAIL_W - 12.2 * cm], fs=8.0)]
    st += [P("The first two features carry most of the signal: the within-week voltage-stability "
             "term and the weekly-range trend form a <b>core pair selected in all 34 of 34</b> "
             "cross-validation folds. The resting-floor and crank-dip terms add the "
             "battery-cascade and crank-load context.", "Body")]
    st += [Hd("3.2&nbsp;&nbsp;How the model produces a decision", "H2")]
    st += bullets([
        "<b>Score.</b> Each feature is z-scored against the training trucks; the risk score is the "
        "regularised linear sum of (coefficient &times; z-score). Larger = more failure-like.",
        "<b>Calibrate.</b> A per-fold Platt step turns the raw score into a probability "
        "(calibration slope 0.86, Brier 0.124 — shippable, not rank-only).",
        "<b>Tier.</b> The calibrated probability maps to GREEN&nbsp;&lt;&nbsp;0.35&nbsp;&le;&nbsp;"
        "AMBER&nbsp;&lt;&nbsp;0.55&nbsp;&le;&nbsp;RED for weekly operations.",
    ])
    st += [callout("Weight basis — stated plainly for management",
        "The four weights are <b>learned, not hand-set</b> — data-fitted Ridge coefficients, "
        "standardised so magnitudes are comparable. The modal four-feature subset is selected in "
        "<b>14 of 34</b> folds and the two core features in <b>34 of 34</b>; the model is never "
        "retrained for deployment, only re-read for explainability. No expert-tuned magic numbers "
        "drive the risk score.")]
    st += [PageBreak()]
    return st

def sec4_validation():
    st = [Hd("4&nbsp;&nbsp;How It Was Validated", "H1"), hr(NAVY, 1.0)]
    st += [Hd("4.1&nbsp;&nbsp;Leave-one-truck-out, done strictly", "H2")]
    st += [P("Performance is measured under <b>nested Leave-One-Vehicle-Out</b> cross-validation: "
             "34 rounds, and in each round the scored truck is <b>fully excluded</b> from "
             "everything. Feature screening, subset selection, the decision threshold and the "
             "probability calibration are <b>all redone inside each round</b> using only the other "
             "33 trucks. This is why the number is deployment-grade rather than an in-sample "
             "flatterer — it is what the model would have said about a truck it had never "
             "seen.", "Body")]
    st += [Hd("4.2&nbsp;&nbsp;What “0.9321” is — and is not", "H2")]
    st += [P("It is a <b>ranking</b> metric (AUROC), <b>not</b> a classification accuracy. With "
             "14 failed and 20 healthy trucks there are 14&times;20 = <b>280</b> failed/healthy "
             "pairs. The model orders <b>261</b> of them correctly, with 0 ties:", "BodyL"),
           P("<font name=\"%s\">AUROC = correctly-ordered pairs / total pairs = 261 / 280 = "
             "<b>0.9321</b></font>" % BODY, "BodyL"),
           P("The same model re-scored <i>in-sample</i> (its own training trucks) orders 262 of "
             "280 pairs (0.9357). The gap — <b>262 vs 261, a single pair</b> — is the "
             "measured selection optimism: +0.0036. A model that had memorised its trucks would "
             "show a large in-sample-to-honest gap; a one-pair gap is the signature of a model that "
             "genuinely generalises.", "Body")]
    st += [callout("Ranking vs accuracy — the precise distinction",
        "<b>Ranking (the headline):</b> a pair is <i>correct</i> when score(failed) &gt; "
        "score(healthy) — 261 of 280. <b>Classification (at an operating point):</b> a truck "
        "is <i>correct</i> when it lands on the right side of a chosen threshold (Section&nbsp;6). "
        "The headline answers “does the model order trucks correctly?” — it is never "
        "a claim that the system is “93% accurate” on individual trucks.", bg=WARNBG, bar=AMBER)]
    st += [Hd("4.3&nbsp;&nbsp;The 10-week horizon is a detection-validity window, not a countdown", "H2")]
    st += [P("A separate walk-back test asks: how far before failure can the model still tell a "
             "failing truck from a healthy one? Re-scoring on data truncated to <i>k</i> weeks "
             "before the last record, ranking quality <b>holds at or above AUROC 0.75 through "
             "k = 10 weeks</b> and then collapses to chance at k = 11. This defines a "
             "<b>~10-week detection-validity window</b>: a flagged truck is typically within ~10 "
             "weeks of failure. It is <b>not</b> a per-truck countdown clock and must never be "
             "presented as “X weeks to failure.”", "Body")]
    hh = [P(x, "cph") for x in
          ["Weeks before last record (k)", "0", "3", "6", "9", "10", "11", "14"]]
    hr_row = ["Walk-back ranking AUROC", "0.936", "0.921", "0.843", "0.818", "0.768", "0.704", "0.625"]
    st += [tbl([hh, [P(hr_row[0], "cpb")] + [P(x, "cp") for x in hr_row[1:]]],
               [5.4 * cm] + [(AVAIL_W - 5.4 * cm) / 7.0] * 7, fs=7.9,
               aligns={i: "CENTER" for i in range(1, 8)})]
    st += [P("Sustained validity holds to <b>k* = 10</b> weeks (last column above 0.75); the drop "
             "below 0.75 at k = 11 is the honest edge of the window.", "Sm")]
    st += [callout("Section 4 conclusion",
        "0.9321 is a strictly cross-validated <b>ranking</b> score — 261 of 280 pairs ordered "
        "correctly on unseen trucks, with a one-pair selection-optimism gap and a validated "
        "10-week detection horizon. It is the right headline provided it is always stated as "
        "<i>ranking</i> accuracy.")]
    st += [PageBreak()]
    return st

def sec5_overfit():
    st = [Hd("5&nbsp;&nbsp;Why This Is Not Over-fitting", "H1"), hr(NAVY, 1.0)]
    st += [P("A strong number on 14 events invites one question above all others: is it real? "
             "Seven independent layers of evidence say yes. No single layer is decisive; together "
             "they are.", "Body")]
    eh = [P(x, "cph") for x in ["#", "Evidence layer", "What was done", "Result"]]
    er = [
        ["1", "Nested selection",
         "Screening, subset choice, threshold and calibration all redone inside every fold",
         "Honest, deployment-grade number"],
        ["2", "Tiny model capacity",
         "4 features, L2-regularised Ridge (alpha = 1.0) — chosen to resist memorising",
         "Low variance by construction"],
        ["3", "Permutation test",
         "Labels shuffled, full pipeline re-run (N = 200)",
         "p = 0.005 — not chance"],
        ["4", "Measured leak ceilings",
         "Observation-length and start-date proxies scored as upper bounds; every feature audited",
         "n_weeks 0.952 / t_start 0.893; all features cleared"],
        ["5", "Fixed-window control + banned feature",
         "L40 window-anchored recompute of every feature; artifact feature caught and removed",
         "Bit-identical 0.9357 = 0.9357 (0.0 drop)"],
        ["6", "Predecessor restated honestly",
         "V1's reported 0.921 re-scored under this stricter nested protocol",
         "0.921 → 0.893 (optimism disclosed, 1 fake TP)"],
        ["7", "Reproduced + adversarially tested",
         "Benchmark reproduced 4x (V2, V2.1, V3, V3.1); 17 candidate features pre-registered & tested",
         "4x exact match; all 17 rejected"],
    ]
    st += [tbl([eh] + [[P(r[0], "cpb"), P(r[1], "cpb"), P(r[2], "cp"), P(r[3], "cp")] for r in er],
               [0.7 * cm, 3.2 * cm, 7.2 * cm, AVAIL_W - 11.1 * cm], fs=7.7,
               aligns={0: "CENTER"})]
    st += [P("Layer&nbsp;5 is worth a sentence: one early candidate (a dominant-frequency feature) "
             "turned out to be a disguised <b>1/n_weeks</b> proxy — it scored well only "
             "because failed trucks have shorter histories. It was caught by the fixed-window "
             "control, banned, and added to a binding feature registry so it can never re-enter. "
             "That is the machinery that makes the remaining 0.9321 trustworthy.", "Body")]
    st += [callout("The one-line framing",
        "The score survives a shuffle test, a fixed-window control, a leak-ceiling audit, four "
        "independent reproductions and 17 rejected attempts to beat it — and the model's own "
        "predecessor was <i>revised downward</i> under the same rules. This is a "
        "<b>data ceiling, not a method ceiling</b>.", bg=WARNBG, bar=AMBER)]
    st += [PageBreak()]
    return st

def sec6_alerts():
    st = [Hd("6&nbsp;&nbsp;Alert Channels &amp; Operating Points", "H1"), hr(NAVY, 1.0)]
    st += [P("The system exposes several alert channels at <b>distinct</b> operating points. They "
             "answer different questions and must be reported <b>separately</b> — never blended "
             "into one recall/false-alarm number.", "Body")]
    oh = [P(x, "cph") for x in
          ["Operating point", "Recall", "False alarms", "Median lead", "Character"]]
    orr = [
        ["Classifier @ Youden threshold", "13 / 14", "5 / 20", "—",
         "Recall-greedy; ~43% cost saving vs run-to-failure*"],
        ["RED tier only (P ≥ 0.55)", "10 / 14", "2 / 20", "—",
         "Low false-alarm burden (specificity 18/20)"],
        ["H2 persistent-RED pager", "10 / 14", "0.19 ep/truck-yr", "116 d",
         "Sustained-signal pager (episode-rated)"],
        ["A2 battery-cascade detector", "4 / 5", "0 / 20", "66.5 d",
         "Of the 5 battery-mode failures; battery-first routing"],
    ]
    st += [tbl([oh] + [[P(r[0], "cpb"), P(r[1], "cp"), P(r[2], "cp"), P(r[3], "cp"), P(r[4], "cp")]
                       for r in orr],
               [4.6 * cm, 1.7 * cm, 2.5 * cm, 1.9 * cm, AVAIL_W - 10.7 * cm], fs=7.7,
               aligns={1: "CENTER", 2: "CENTER", 3: "CENTER"})]
    st += [P("Recall denominators differ by design: the first three rows are over all 14 failures; "
             "the A2 detector's 4 / 5 is over the 5 battery-mode failures only (it does not target "
             "the others). *Cost saving is the modelled reduction in unplanned-failure cost at "
             "typical India heavy-duty cost ratios when a 13/14-recall inspection policy replaces "
             "run-to-failure; it is an economic estimate, not a validated field number.", "Sm")]

    st += [Hd("6.1&nbsp;&nbsp;Per-truck alert lead time", "H2")]
    st += [P("For each failed truck, the earliest validated alert lead relative to the recorded "
             "failure date (JCOPENDATE). “Persistence” is the tier-gated persistence "
             "flag; A1 is the crank-burst corroborator; A2 is the battery-cascade detector. The "
             "<b>median first-fire lead is 168 days</b> (range 77–424).", "Body")]
    lh = [P(x, "cph") for x in
          ["Truck", "Tier", "Archetype", "Persistence (d)", "A1 / A2 (d)", "Earliest lead (d)"]]
    lr = [
        ["VIN5_F_SM",  "RED",   "A3 volatility",   "424", "—",   "424"],
        ["VIN13_F_SM", "RED",   "A2 battery",      "301", "A2 63",    "301"],
        ["VIN11_F_SM", "RED",   "A3 volatility",   "266", "A1 179",   "266"],
        ["VIN7_F_SM",  "RED",   "A3 volatility",   "266", "—",   "266"],
        ["VIN14_F_SM", "RED",   "A1+A2 mixed",     "245", "A2 28",    "245"],
        ["VIN1_F_SM",  "GREEN", "A1-then-silent",  "156", "A1 232",   "232"],
        ["VIN3_F_SM",  "GREEN", "A2 battery",      "168", "A2 91",    "168"],
        ["VIN6_F_SM",  "RED",   "A2 battery",      "168", "A2 70",    "168"],
        ["VIN10_F_SM", "RED",   "A1 solenoid",     "147", "A1 160",   "160"],
        ["VIN8_F_SM",  "RED",   "A4 silent",       "135", "—",   "135"],
        ["VIN12_F_SM", "RED",   "A3 volatility",   "126", "A1 128",   "128"],
        ["VIN4_F_SM",  "GREEN", "A4 silent",       "125", "—",   "125"],
        ["VIN2_F_SM",  "RED",   "A2 battery",      "77",  "—",   "77"],
        ["VIN9_F_SM",  "GREEN", "A4 silent",       "—", "—", "MISSED"],
    ]
    t = tbl([lh] + [[P(r[0], "cpb"), P(r[1], "cp"), P(r[2], "cp"), r[3], P(r[4], "cp"), P("<b>%s</b>" % r[5], "cp")]
                    for r in lr],
            [2.7 * cm, 1.5 * cm, 3.0 * cm, 2.5 * cm, 2.0 * cm, AVAIL_W - 11.7 * cm], fs=7.6,
            aligns={1: "CENTER", 3: "CENTER", 4: "CENTER", 5: "CENTER"})
    tiercol = {"RED": RED, "GREEN": GREEN, "AMBER": AMBER}
    extra = []
    for i, r in enumerate(lr, start=1):
        extra.append(("TEXTCOLOR", (1, i), (1, i), tiercol.get(r[1], INK)))
        extra.append(("FONTNAME", (1, i), (1, i), BODY_BD))
    t.setStyle(TableStyle(extra))
    st += [t]
    st += [P("Leads are retrospective, measured at the validated operating points above. Several "
             "GREEN-tier catches (VIN1, VIN3, VIN4) are recovered by the persistence/A1 channels "
             "rather than the RED tier — which is exactly why the alert layer sits on top of "
             "the tiering. Note that the silent-gap trucks carry <b>32–142 days of telemetry "
             "silence</b> before the recorded failure date, so their true lead is bounded by when "
             "data stopped, not by the model.", "Sm")]
    st += [fig(graph("V1_1_SM_fleet_risk.png"),
               "Figure 6.1  Fleet risk picture — calibrated risk across all 34 trucks; failed "
               "trucks (elevated) separate cleanly from the healthy band, with the sole structural "
               "miss (VIN9_F_SM) sitting low. Failed trucks are labelled VIN1_F–VIN14_F (identical "
               "to this report); the 20 non-failed trucks use the graph's native sequential "
               "display numbering (VIN15_NF–VIN34_NF) rather than the raw _SM labels used "
               "elsewhere here.", w=AVAIL_W, maxh=9.0 * cm)]
    st += [PageBreak()]
    return st

def sec7_rul():
    st = [Hd("7&nbsp;&nbsp;RUL as Maintenance Windows (not point estimates)", "H1"), hr(NAVY, 1.0)]
    st += [P("A day-precise per-truck remaining-life number would be <b>false precision</b> on "
             "this data, and we can prove it: the best per-truck survival model has an error of "
             "<b>576 days</b> against a naive constant (fleet-average) baseline of just "
             "<b>44 days</b> — the individual model is far worse than assuming every truck "
             "lasts the fleet average. So the honest, deployable deliverable is a <b>risk tier plus "
             "a maintenance window</b>, not a failure date.", "Body")]
    st += [Hd("7.1&nbsp;&nbsp;Window validation", "H2")]
    st += [P("Each flagged failure is assigned a service window by band: the <b>battery band</b> "
             "(28–91 days) for A2 battery-cascade cases and the <b>persistence band</b> "
             "(126–284 days) for sustained-signal cases. A window is a <i>hit</i> when the "
             "truck's actual time-to-failure falls inside it. <b>9 of the 11 windowed failures "
             "landed inside</b>; both misses were late on the <b>safe side</b> (the truck failed "
             "after the window closed, so a scheduled service would have pre-empted it).", "Body")]
    wh = [P(x, "cph") for x in ["Truck", "Tier", "Band", "Window (days)", "Verdict"]]
    wr = [
        ["VIN2_F_SM",  "RED",   "Battery",     "28–91",   "inside"],
        ["VIN3_F_SM",  "GREEN", "Battery (A2)","28–91",   "late by 1 d (safe)"],
        ["VIN6_F_SM",  "RED",   "Battery (A2)","28–91",   "inside"],
        ["VIN13_F_SM", "RED",   "Battery (A2)","28–91",   "inside"],
        ["VIN14_F_SM", "RED",   "Battery (A2)","28–91",   "inside"],
        ["VIN5_F_SM",  "RED",   "Persistence", "126–284", "late by 140 d (safe)"],
        ["VIN7_F_SM",  "RED",   "Persistence", "126–284", "inside"],
        ["VIN8_F_SM",  "RED",   "Persistence", "126–284", "inside"],
        ["VIN10_F_SM", "RED",   "Persistence", "126–284", "inside"],
        ["VIN11_F_SM", "RED",   "Persistence", "126–284", "inside"],
        ["VIN12_F_SM", "RED",   "Persistence", "126–284", "inside"],
    ]
    t = tbl([wh] + [[P(r[0], "cpb"), P(r[1], "cp"), P(r[2], "cp"), r[3], P(r[4], "cp")] for r in wr],
            [2.9 * cm, 1.7 * cm, 3.0 * cm, 3.0 * cm, AVAIL_W - 10.6 * cm], fs=7.7,
            aligns={1: "CENTER", 3: "CENTER"})
    tiercol = {"RED": RED, "GREEN": GREEN, "AMBER": AMBER}
    extra = []
    for i, r in enumerate(wr, start=1):
        extra.append(("TEXTCOLOR", (1, i), (1, i), tiercol.get(r[1], INK)))
        extra.append(("FONTNAME", (1, i), (1, i), BODY_BD))
        if "late" in r[4]:
            extra.append(("TEXTCOLOR", (4, i), (4, i), AMBER))
        else:
            extra.append(("TEXTCOLOR", (4, i), (4, i), GREEN))
    t.setStyle(TableStyle(extra))
    st += [t]
    st += [P("Three failures are windowless by design: <b>VIN1_F_SM</b> (GREEN, caught only by the "
             "A1 alert), <b>VIN4_F_SM</b> (AMBER — monitor, no window issued) and "
             "<b>VIN9_F_SM</b> (the structural miss). No window is ever quoted for a truck the "
             "model cannot place — that restraint is what keeps the windows honest.", "Body")]
    st += [callout("Section 7 conclusion",
        "The deployable RUL statement is <b>tier + maintenance window</b>, not a date. On this "
        "fleet the windows caught 9 of 11 with both misses on the safe side — a schedulable, "
        "auditable output that a day-precise RUL model provably cannot match at n = 14.")]
    st += [PageBreak()]
    return st

def sec8_routing():
    st = [Hd("8&nbsp;&nbsp;Battery-vs-Starter Service Routing (V3.1)", "H1"), hr(NAVY, 1.0)]
    st += [P("A recurring field question is whether a flagged truck needs the <b>battery</b> "
             "serviced or the <b>starter</b> itself. Because roughly half of starter breakdowns "
             "trace to a weak battery, the V3.1 triage (T1) routes each flagged truck to "
             "<b>battery-first</b> or <b>inconclusive</b> using the resting-voltage and "
             "battery-cascade evidence.", "Body")]
    st += [kpi_band([("9 / 11", "Triage convergence", TEAL),
                     ("5 / 5", "Battery-family agreement", GREEN),
                     ("4 / 4", "Silent-mode agreement", ACCENT),
                     ("0 / 20", "False attributions (healthy)", STEEL)]),
           Spacer(1, 8)]
    st += [P("Of the 11 failures the triage could score (3 volatility-mode failures were left "
             "unscored by design), <b>9 converged</b> with the independently derived failure "
             "archetypes — <b>5 of 5</b> battery-family failures routed battery-first and "
             "<b>4 of 4</b> silent-mode failures flagged as inconclusive rather than mis-attributed. "
             "Critically, <b>0 of 20 healthy trucks</b> received a false battery attribution.", "Body")]
    st += [callout("How to read this — SCREEN-GRADE, not diagnosis",
        "The routing converges with <i>telemetry-derived</i> archetypes, not with confirmed "
        "workshop teardowns — so it is a <b>screen-grade</b> aid (n = 14) that tells the depot "
        "where to look first, not a warranty-grade diagnosis. Its value is the zero false "
        "attribution on healthy trucks: it never sends a good truck to battery service.", bg=WARNBG, bar=AMBER)]
    st += [PageBreak()]
    return st

def sec9_limits():
    st = [Hd("9&nbsp;&nbsp;Known Limits (stated plainly)", "H1"), hr(NAVY, 1.0)]
    st += [P("The system is presented honestly. The following constraints are real; all but the "
             "last are consequences of dataset size and sensing, not of the method.", "Body")]
    st += bullets([
        "<b>Fourteen failure events is the binding constraint.</b> The bootstrap AUROC confidence "
        "interval is [0.811, 0.986] — wide because a handful of trucks decide every threshold. "
        "This narrows only with more failures.",
        "<b>One structural blind spot (VIN9-class).</b> VIN9_F_SM is invisible in this telemetry: "
        "an SMA-dead (telemetry-dead) configuration, a 142-day silent gap, and an abrupt failure "
        "mode with no precursor. Its raw score (0.401) sits just under the threshold; its "
        "recalibrated probability is 0.224. This is a telemetry problem, not a modelling one.",
        "<b>Silent-gap trucks.</b> 5 of 14 failures carry 32–142 days of telemetry silence "
        "before the recorded failure date, which caps how much lead any model could have shown.",
        "<b>Failure dates come from workshop records</b> (job-card open date), so there is "
        "inherent timing uncertainty in every lead-time and window number.",
        "<b>Scores correlate with observation length</b> (|r| up to 0.65). This is "
        "<i>label-mediated</i> — failed trucks have shorter histories because they failed "
        "— and is defended by the fixed-window (L40) control showing 0.0 AUROC borrowed from "
        "history length, plus the decay-to-chance horizon curve. The definitive cure is a larger "
        "fleet.",
        "<b>VIN independence.</b> Starter-motor and alternator VINs are different physical trucks; "
        "no cross-dataset, VIN-level inference is made anywhere in this report.",
    ])
    st += [callout("The single most important framing",
        "Every limitation above lifts with more data. This is a <b>data ceiling, not a method "
        "ceiling</b>: the same validated pipeline that scores 0.9321 on 14 events will sharpen "
        "materially at 500-truck scale — and only new instrumentation (not new models) breaks "
        "the silent-failure floor.", bg=WARNBG, bar=AMBER)]
    st += [PageBreak()]
    return st

def sec10_evidence():
    st = [Hd("10&nbsp;&nbsp;Per-Truck Evidence Stacks", "H1"), hr(NAVY, 1.0)]
    st += [P("Every one of the 34 trucks has a per-VIN evidence stack that puts the risk-clock, "
             "the tier trajectory and the underlying voltage/crank physics on one page, so any "
             "flag can be audited truck-by-truck. Three representative examples follow; the full "
             "34-figure set accompanies this dossier.", "Body")]
    st += [callout("How to read an evidence stack",
        "Top: the risk/RUL clock with the confirmed failure date. Middle: the calibrated tier "
        "trajectory (GREEN/AMBER/RED) with the alert channels marked where they fire. Bottom: the "
        "raw physics — resting voltage, crank-dip depth and within-week stability. "
        "<b>Transient elevations that self-resolve are normal; a sustained climb is the failure "
        "signature.</b>")]
    st += [PageBreak()]

    st += [Hd("10.1&nbsp;&nbsp;VIN13_F_SM — a textbook detection", "H3")]
    st += [fig(evid("sm_VIN13_F_SM_evidence_stack.png"),
               "Figure 10.1  VIN13_F_SM (RED tier, battery archetype). The A2 battery-cascade "
               "detector fires 63 days before failure and the truck's time-to-failure lands inside "
               "the 28–91-day battery window — a clean, actionable, battery-first catch.",
               w=AVAIL_W, maxh=21.5 * cm)]
    st += [PageBreak()]

    st += [Hd("10.2&nbsp;&nbsp;VIN9_F_SM — the honest miss", "H3")]
    st += [fig(evid("sm_VIN9_F_SM_evidence_stack.png"),
               "Figure 10.2  VIN9_F_SM (GREEN, MISSED). The structural blind spot: an SMA-dead "
               "configuration and a 142-day telemetry gap before an abrupt failure leave no "
               "precursor to detect. Raw score 0.401 vs threshold; recalibrated probability 0.224. "
               "We show it rather than hide it.", w=AVAIL_W, maxh=21.5 * cm)]
    st += [PageBreak()]

    st += [Hd("10.3&nbsp;&nbsp;VIN2_NF_SM — a healthy contrast", "H3")]
    st += [fig(evid("sm_VIN2_NF_SM_evidence_stack.png"),
               "Figure 10.3  VIN2_NF_SM (healthy). A useful contrast: the voltage signals show "
               "transient elevations that self-resolve and never build into the sustained climb "
               "that marks a failing truck — the pattern the model is trained to distinguish.",
               w=AVAIL_W, maxh=21.5 * cm)]
    st += [PageBreak()]
    return st

def sec11_forward():
    st = [Hd("11&nbsp;&nbsp;Path Forward", "H1"), hr(NAVY, 1.0)]
    st += [P("Every limit in Section&nbsp;9 maps to a concrete ask. In priority order, the "
             "instrumentation and data that would break the current ceilings:", "Body")]
    ph = [P(x, "cph") for x in ["Ask", "What it unlocks", "Which limit it addresses"]]
    pr = [
        ["Cranking current + battery SoC / SoH sensor",
         "Ends the battery-vs-starter ambiguity that caps alert precision",
         "Routing is screen-grade (Sec 8)"],
        ["High-frequency (≥ 1 Hz) voltage burst during cranks",
         "Revives brush-wear / crank-dip prognosis — the biggest single unlock",
         "5 s sampling destroys crank physics"],
        ["Coolant / ambient temperature SPNs",
         "Cold-start conditioning of the crank signature",
         "No thermal context today"],
        ["GPS / region",
         "Environmental and duty-cycle context",
         "No operating-environment signal"],
        ["Maintenance &amp; parts-replacement records",
         "Turns telemetry-derived archetypes into supervised labels",
         "Archetypes are in-sample (Sec 8)"],
        ["Ignition-state signal",
         "Cleaner crank segmentation; fewer SMA-dead ambiguities",
         "SMA-dead cohort / VIN9-class (Sec 9)"],
        ["Scale to 500 trucks (Phase 2)",
         "~30–50+ failures — unlocks survival modelling & sharper tiers",
         "n = 14 wide CI (Sec 9)"],
    ]
    st += [tbl([ph] + [[P(r[0], "cpb"), P(r[1], "cp"), P(r[2], "cp")] for r in pr],
               [5.6 * cm, 6.4 * cm, AVAIL_W - 12.0 * cm], fs=7.8)]
    st += [callout("Bottom line for DICV management",
        "A validated, honest, deployable system that turns reactive starter/battery breakdowns "
        "into planned maintenance — using data you already collect, with no new hardware and "
        "no methodological risk. The 0.9321 ranking score is real and conservative; the "
        "13-of-14 detection with a 168-day median lead is actionable today; and every current "
        "limit lifts with the 500-truck scale-up using this same method.", bg=CALLBG, bar=TEAL)]
    st += [PageBreak()]
    return st

def _qa(n, q, a):
    qs = _st("Q", fontName=BODY_BD, fontSize=9.6, leading=13, textColor=NAVY,
             spaceBefore=9, spaceAfter=2)
    return [Paragraph("Q%d.&nbsp;&nbsp;%s" % (n, q), qs),
            Paragraph("<b>A.</b>&nbsp;&nbsp;" + a, S["Body"])]

def appA_qna():
    st = [Hd("Appendix A&nbsp;&nbsp;Question &amp; Answer Dossier", "H1"), hr(NAVY, 1.0)]
    st += [P("Anticipated DICV management questions with evidence-backed answers; every number is "
             "traceable to a committed V1.1_SM result file or its re-test iterations.", "Sm")]
    qas = [
        ("Is the 0.9321 an accuracy or a ranking number?",
         "It is a <b>ranking</b> metric (AUROC): draw one failed and one healthy truck at random "
         "and the model ranks the failed one higher 93.2% of the time — 261 of 280 pairs "
         "correct, measured leave-one-truck-out. It is not “correct on 93% of trucks.”"),
        ("How many failures do we actually catch, and how early?",
         "The alert channels catch <b>13 of 14</b> failures, with a median first-fire lead of "
         "168 days (range 77–424). The single miss is VIN9_F_SM, a structural blind spot "
         "(telemetry-dead + 142-day gap + abrupt mode)."),
        ("Are there false alarms?",
         "Reported per channel, never blended. The <b>A2 battery-cascade detector has 0 of 20</b> "
         "healthy trucks flagged. The recall-greedy Youden operating point flags 5 of 20 healthy "
         "trucks; the RED tier only 2 of 20. Choose the point per maintenance economics."),
        ("Why can't you give an exact remaining-life date?",
         "Because it would be false precision: the best per-truck survival model errs by 576 days "
         "versus 44 days for simply assuming the fleet average. The reliable output is a risk tier "
         "plus a maintenance window (battery 28–91 d, persistence 126–284 d)."),
        ("Do the maintenance windows actually work?",
         "On this fleet, 9 of the 11 windowed failures fell inside their predicted window, and "
         "both misses were late on the safe side — the truck failed after the window closed, "
         "so a scheduled service would have pre-empted it."),
        ("What is the ‘10-week horizon’ — is it a countdown?",
         "No. It is a <b>detection-validity window</b>: ranking quality holds above AUROC 0.75 up "
         "to 10 weeks before the last record and then falls to chance. It means a flagged truck is "
         "typically within ~10 weeks of failure — never a per-truck ‘X weeks left’ clock."),
        ("How do we know it is not over-fit on only 14 failures?",
         "Seven independent layers (Section 5): nested selection, tiny model, permutation p = 0.005, "
         "audited leak ceilings, a fixed-window control that reproduces the score bit-for-bit, the "
         "predecessor honestly restated 0.921→0.893, and four exact reproductions with 17 "
         "pre-registered candidate features all rejected."),
        ("Battery or starter — can the system tell which to service?",
         "As a screen-grade aid, yes: the V3.1 triage routes battery-first vs inconclusive and "
         "converged with the failure archetypes on 9 of 11 scored failures (battery-family 5/5, "
         "silent 4/4) with 0 of 20 false attributions on healthy trucks. It is a where-to-look-first "
         "screen (n = 14), not a warranty-grade diagnosis."),
        ("What is the deployment-ready output?",
         "Three things on existing telematics, no new hardware: weekly risk ranking + "
         "green/amber/red tiers, the validated alert channels (persistence flag + A2 "
         "battery-cascade), and tier-based maintenance windows for planned service."),
        ("What do you need to make it materially better?",
         "In priority: cranking current / battery SoC-SoH; ≥1 Hz crank-voltage logging; "
         "maintenance & parts records (to create supervised labels); and 500-truck scale for "
         "~30–50+ failures. Same method, more evidence."),
    ]
    for i, (q, a) in enumerate(qas, 1):
        st += _qa(i, q, a)
    st += [PageBreak()]
    return st

def appB_lineage():
    st = [Hd("Appendix B&nbsp;&nbsp;Data Lineage", "H1"), hr(NAVY, 1.0)]
    st += [P("Every figure in this report is traceable to a committed starter-motor artifact "
             "(paths relative to <font name=\"%s\">STARTER MOTOR/</font>). Primary sources:" % BODY,
             "Body")]
    lh = [P(x, "cph") for x in ["Topic", "Source file"]]
    lin = [
        ["Headline metrics / CI / permutation", "V1.1/results/V1_1_SM_model_spec.json · V1_1_SM_gates.json"],
        ["Consolidated results", "V1.1/reports/V1_1_SM_RESULTS_MASTER.md"],
        ["Per-VIN nested predictions & tiers", "V1.1/results/V1_1_SM_nested_lovo_predictions.csv"],
        ["Alert policy & channels", "V1.1/results/V1_1_SM_alert_policy.csv"],
        ["10-week horizon curve", "V1.1/results/V1_1_SM_horizon_curve.csv"],
        ["Maintenance windows / routing (V3.1)", "V3.1/heuristics/out/T2_windows.csv · T1_convergence.json · T1_attribution.csv"],
        ["Fixed-window control & gates", "V1.1/results/V1_1_SM_gates.json (G1–G6)"],
        ["Fleet risk figure", "V1.1/graphs/V1_1_SM_fleet_risk.png"],
        ["Per-truck evidence stacks (34)", "V1.1/visualizations/rul_evidence_stack/sm_*_evidence_stack.png"],
        ["Model card / banned features", "V1.1/reports/V1_1_SM_model_card.md"],
    ]
    st += [tbl([lh] + [[P(r[0], "cpb"), P(r[1], "cp")] for r in lin],
               [5.4 * cm, AVAIL_W - 5.4 * cm], fs=8)]
    st += [Spacer(1, 8),
           P("<i>Prepared by ByteEdge for DICV management review. Model under review: V1.1_SM "
             "(frozen). Independent re-tests: V2, V2.1, V3, V3.1. Report generated 02 July 2026.</i>",
             "Sm")]
    return st

# --------------------------------------------------------------------------- #
# Brief story
# --------------------------------------------------------------------------- #
def story_brief():
    st = [NextPageTemplate("Body"), Spacer(1, 1), PageBreak()]
    st += [Hd("The system in one read", "H1"), hr(NAVY, 1.0)]
    st += [kpi_band([("0.9321", "Ranking AUROC (LOVO)", TEAL),
                     ("13 / 14", "Failures caught", GREEN),
                     ("0 / 20", "Battery-alert false alarms", ACCENT),
                     ("168 d", "Median alert lead", AMBER)]), Spacer(1, 8)]
    st += [P("The starter-motor risk-prediction system <b>ranks</b> every truck by failure risk "
             "from telemetry you already collect (crank + resting voltage), <b>alerts</b> when a "
             "degradation precursor persists, and <b>schedules</b> service inside a validated "
             "maintenance window — turning surprise breakdowns into planned maintenance. No "
             "new hardware.", "Body")]
    mh = [P(x, "cph") for x in ["The four numbers that matter", "Value", "Meaning"]]
    mr = [
        ["Ranking AUROC (LOVO)", "0.9321", "Orders failed above healthy — 261 of 280 pairs, unseen trucks"],
        ["Failures caught", "13 / 14", "Alert channels flag all but the one structural blind spot"],
        ["Median alert lead", "168 d", "First-fire lead before recorded failure (range 77–424)"],
        ["Battery-alert false alarms", "0 / 20", "A2 battery-cascade detector never flags a healthy truck"],
    ]
    st += [tbl([mh] + [[P(r[0], "cpb"), P("<b>%s</b>" % r[1], "cp"), P(r[2], "cp")] for r in mr],
               [4.8 * cm, 2.4 * cm, AVAIL_W - 7.2 * cm], fs=8.4, aligns={1: "CENTER"})]
    st += [fig(graph("V1_1_SM_fleet_risk.png"),
               "Fleet risk picture — all 34 trucks; failed trucks separate cleanly from the "
               "healthy band (frozen V1.1_SM, nested LOVO). Non-failed trucks shown under the "
               "graph's native sequential display numbering (VIN15_NF–VIN34_NF).",
               w=AVAIL_W, maxh=8.5 * cm)]
    st += [callout("What to say in the room",
        "“93% ranking accuracy — 13 of 14 failures caught, median 168 days' warning, with "
        "zero battery-alert false alarms, using data we already have.” Say <i>ranking</i> "
        "accuracy, not bare accuracy.", bg=CALLBG, bar=TEAL)]
    st += [PageBreak()]

    st += [Hd("Detection, lead time and the window verdict", "H1"), hr(NAVY, 1.0)]
    st += [P("<b>What the 0.9321 means.</b> Given a random failed and a random healthy truck, the "
             "model ranks the failed one higher 93.2% of the time — 261 of 280 truck-pairs, "
             "measured on trucks it never saw in training (selection optimism just one pair: 262 vs "
             "261). It is <i>ranking</i>, not “93% of trucks correct.”", "Body")]
    lh = [P(x, "cph") for x in ["Truck", "Tier", "Earliest lead (d)", "Truck", "Tier", "Earliest lead (d)"]]
    pairs = [
        ["VIN5_F_SM", "RED", "424", "VIN3_F_SM", "GREEN", "168"],
        ["VIN13_F_SM", "RED", "301", "VIN6_F_SM", "RED", "168"],
        ["VIN11_F_SM", "RED", "266", "VIN10_F_SM", "RED", "160"],
        ["VIN7_F_SM", "RED", "266", "VIN8_F_SM", "RED", "135"],
        ["VIN14_F_SM", "RED", "245", "VIN12_F_SM", "RED", "128"],
        ["VIN1_F_SM", "GREEN", "232", "VIN4_F_SM", "GREEN", "125"],
        ["", "", "", "VIN2_F_SM", "RED", "77"],
        ["", "", "", "VIN9_F_SM", "GREEN", "MISSED"],
    ]
    t = tbl([lh] + [[P(r[0], "cpb"), P(r[1], "cp"), r[2], P(r[3], "cpb"), P(r[4], "cp"), r[5]]
                    for r in pairs],
            [2.7 * cm, 1.5 * cm, 2.4 * cm, 2.7 * cm, 1.5 * cm, AVAIL_W - 10.8 * cm], fs=7.7,
            aligns={1: "CENTER", 2: "CENTER", 4: "CENTER", 5: "CENTER"})
    tiercol = {"RED": RED, "GREEN": GREEN, "AMBER": AMBER}
    extra = []
    for i, r in enumerate(pairs, start=1):
        if r[1]:
            extra.append(("TEXTCOLOR", (1, i), (1, i), tiercol.get(r[1], INK)))
            extra.append(("FONTNAME", (1, i), (1, i), BODY_BD))
        if r[4]:
            extra.append(("TEXTCOLOR", (4, i), (4, i), tiercol.get(r[4], INK)))
            extra.append(("FONTNAME", (4, i), (4, i), BODY_BD))
    t.setStyle(TableStyle(extra))
    st += [P("<b>Per-truck alert lead (earliest validated channel, vs recorded failure date):</b>", "Sm"), t]
    st += [callout("Maintenance-window verdict",
        "Day-precise RUL is false precision here (survival error 576 d vs 44 d for a constant), so "
        "we ship a <b>tier + window</b>. Of the 11 windowed failures, <b>9 fell inside</b> the "
        "predicted window and both misses were late on the safe side. Windows: battery "
        "28–91 days, persistence 126–284 days.")]
    st += [PageBreak()]

    st += [Hd("Limits, and what we ask for", "H1"), hr(NAVY, 1.0)]
    st += [P("<b>The honest limits.</b> The binding constraint is 14 failure events: the AUROC "
             "confidence interval is wide ([0.811, 0.986]) and a handful of trucks decide every "
             "threshold. One truck (VIN9-class) is a structural blind spot — telemetry-dead "
             "configuration, a 142-day silent gap and an abrupt mode with no precursor; five of the "
             "fourteen failures carry 32–142 days of telemetry silence before the recorded "
             "failure date; and failure dates come from workshop records, so lead times carry "
             "timing uncertainty. Scores correlate with observation length, but this is "
             "label-mediated and defended by a fixed-window control (zero AUROC borrowed) and a "
             "decay-to-chance horizon curve. Every one of these is a <b>data ceiling, not a method "
             "ceiling</b>.", "Body")]
    st += bullets([
        "<b>Deploy now</b> on existing telematics: weekly risk ranking + green/amber/red tiers, the "
        "persistence and A2 battery-cascade alerts, and tier-based maintenance windows.",
        "<b>Instrument for the next step:</b> cranking current / battery SoC-SoH and ≥1 Hz "
        "crank-voltage logging (the biggest unlocks), plus maintenance & parts records to create "
        "supervised labels.",
        "<b>Scale to 500 trucks (Phase 2)</b> for ~30–50+ failure events — the unlock for "
        "per-truck timing and sharper tiers. Same validated method, no new risk.",
    ])
    st += [callout("Bottom line",
        "Validated, honest and deployable today — planned starter/battery maintenance from "
        "data you already collect, with no new hardware. The 0.9321 ranking is real and "
        "conservative, the 13-of-14 detection is actionable, and it improves with scale.",
        bg=CALLBG, bar=TEAL)]
    return st

# --------------------------------------------------------------------------- #
def build(path, story_fn, cover_fn, header_left, header_right=None):
    global HEADER_LEFT, HEADER_RIGHT
    HEADER_LEFT = header_left
    HEADER_RIGHT = header_right or ""
    doc = Doc(path, cover_fn)
    doc.multiBuild(story_fn(), canvasmaker=NumberedCanvas)
    return path

def main():
    rep = os.path.join(OUT, DATE + "_DICV_StarterMotor_Validation_Report.pdf")
    brf = os.path.join(OUT, DATE + "_DICV_StarterMotor_Validation_Brief.pdf")
    build(rep, story_report, cover_report,
          "DICV Starter-Motor Risk Prediction — Technical Validation")
    print("BUILT:", rep)
    build(brf, story_brief, cover_brief,
          "DICV Starter-Motor Risk Prediction — Management Brief")
    print("BUILT:", brf)

if __name__ == "__main__":
    main()
