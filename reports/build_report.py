"""Build the PDF results report from results/*.json and figures/*.png.

    python reports/build_report.py
"""
import json
import os
from datetime import date

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Image, Table,
                                TableStyle, PageBreak, KeepTogether, NextPageTemplate, CondPageBreak)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.lib.utils import ImageReader

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FIG = os.path.join(ROOT, "figures")
RES = os.path.join(ROOT, "results")
EQ = os.path.join(ROOT, "reports", "build")
OUT = os.path.join(ROOT, "reports", "Cislunar_Solar_Sailing_Cattle_Run_Study_Report.pdf")

FD = "/usr/share/fonts/truetype/crosextra/"
pdfmetrics.registerFont(TTFont("Carlito", FD + "Carlito-Regular.ttf"))
pdfmetrics.registerFont(TTFont("Carlito-Bold", FD + "Carlito-Bold.ttf"))
pdfmetrics.registerFont(TTFont("Carlito-Italic", FD + "Carlito-Italic.ttf"))
pdfmetrics.registerFont(TTFont("Carlito-BoldItalic", FD + "Carlito-BoldItalic.ttf"))
from reportlab.pdfbase.pdfmetrics import registerFontFamily
registerFontFamily("Carlito", normal="Carlito", bold="Carlito-Bold", italic="Carlito-Italic", boldItalic="Carlito-BoldItalic")

INK = colors.HexColor("#0b0b0b"); INK2 = colors.HexColor("#52514e"); MUTED = colors.HexColor("#898781")
NAVY = colors.HexColor("#0d366b"); BLUE = colors.HexColor("#1c5cab"); TINT = colors.HexColor("#eef4fc")
GRID = colors.HexColor("#d9d8d1"); HEAD = colors.HexColor("#e8eef7"); WARN = colors.HexColor("#fdf3e7")

ST = {
    "body": ParagraphStyle("body", fontName="Carlito", fontSize=10.5, leading=14.8, textColor=INK, spaceAfter=6),
    "small": ParagraphStyle("small", fontName="Carlito", fontSize=9, leading=11.5, textColor=INK2),
    "cap": ParagraphStyle("cap", fontName="Carlito-Italic", fontSize=9, leading=11.5, textColor=INK2, spaceBefore=3, spaceAfter=10),
    "H1": ParagraphStyle("H1", keepWithNext=1, fontName="Carlito-Bold", fontSize=19, leading=23, textColor=NAVY, spaceBefore=4, spaceAfter=10),
    "H2": ParagraphStyle("H2", keepWithNext=1, fontName="Carlito-Bold", fontSize=13.5, leading=17, textColor=BLUE, spaceBefore=10, spaceAfter=5),
    "H3": ParagraphStyle("H3", keepWithNext=1, fontName="Carlito-Bold", fontSize=11, leading=14, textColor=INK, spaceBefore=6, spaceAfter=3),
    "bullet": ParagraphStyle("bullet", fontName="Carlito", fontSize=10.5, leading=14, textColor=INK, leftIndent=14,
                             bulletIndent=3, spaceAfter=3),
    "cell": ParagraphStyle("cell", fontName="Carlito", fontSize=8.8, leading=11.2, textColor=INK),
    "cellb": ParagraphStyle("cellb", fontName="Carlito-Bold", fontSize=8.8, leading=10.6, textColor=INK),
    "callt": ParagraphStyle("callt", fontName="Carlito-Bold", fontSize=10.5, leading=13.5, textColor=NAVY, spaceAfter=3),
    "call": ParagraphStyle("call", fontName="Carlito", fontSize=10.2, leading=13.6, textColor=INK),
    "toc1": ParagraphStyle("toc1", fontName="Carlito-Bold", fontSize=11, leading=15, leftIndent=0),
    "toc2": ParagraphStyle("toc2", fontName="Carlito", fontSize=10, leading=13, leftIndent=16, textColor=INK2),
}


def load(name):
    with open(os.path.join(RES, f"{name}.json")) as f:
        return json.load(f)


def f0(x):
    return "n/a" if x is None else f"{x:,.0f}"


def f1(x):
    return "n/a" if x is None else f"{x:,.1f}"


def f2(x):
    return "n/a" if x is None else f"{x:,.2f}"


def f3(x):
    return "n/a" if x is None else f"{x:.3f}"


def P_(t, s="body"):
    return Paragraph(t, ST[s])


def bullets(items):
    return [Paragraph(t, ST["bullet"], bulletText="•") for t in items]


def fig(name, cap, w=6.6):
    p = os.path.join(FIG, name)
    ir = ImageReader(p)
    iw, ih = ir.getSize()
    h = w * ih / iw
    if h > 7.6:
        w, h = w * 7.6 / h, 7.6
    return KeepTogether([Image(p, width=w * inch, height=h * inch), Paragraph(cap, ST["cap"])])


def eq(name, w=None):
    p = os.path.join(EQ, f"{name}.png")
    ir = ImageReader(p)
    iw, ih = ir.getSize()
    sc = 72.0 / 220 * 0.95
    W, H = iw * sc, ih * sc
    if w and W > w * inch:
        H *= w * inch / W; W = w * inch
    im = Image(p, width=W, height=H)
    im.hAlign = "CENTER"
    return [Spacer(1, 3), im, Spacer(1, 6)]


def table(rows, widths, header_rows=1, zebra=True, font=8.8, align_right_cols=()):
    data = []
    for i, r in enumerate(rows):
        data.append([c if not isinstance(c, str) else Paragraph(c, ST["cellb"] if i < header_rows else ST["cell"]) for c in r])
    t = Table(data, colWidths=[w * inch for w in widths], repeatRows=header_rows, hAlign="LEFT")
    sty = [("FONTNAME", (0, 0), (-1, -1), "Carlito"), ("FONTSIZE", (0, 0), (-1, -1), font),
           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, header_rows - 1), (-1, header_rows - 1), 0.8, NAVY),
           ("BACKGROUND", (0, 0), (-1, header_rows - 1), HEAD), ("LINEBELOW", (0, header_rows), (-1, -1), 0.25, GRID),
           ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
           ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    if zebra:
        for i in range(header_rows, len(rows)):
            if (i - header_rows) % 2 == 1:
                sty.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f7f7f5")))
    t.setStyle(TableStyle(sty))
    return t


def callout(title, body, color=TINT):
    inner = [Paragraph(title, ST["callt"])] + [Paragraph(b, ST["call"]) for b in (body if isinstance(body, list) else [body])]
    t = Table([[inner]], colWidths=[6.6 * inch])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), color), ("LEFTPADDING", (0, 0), (-1, -1), 10),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 8),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 9)]))
    return KeepTogether([Spacer(1, 4), t, Spacer(1, 8)])


class Doc(BaseDocTemplate):
    def __init__(self, fn, **kw):
        super().__init__(fn, pagesize=letter, leftMargin=0.95 * inch, rightMargin=0.95 * inch,
                         topMargin=0.85 * inch, bottomMargin=0.85 * inch, title="Cislunar Solar Sailing for DARPA Cattle Run - Results Report",
                         author="Cattle Run cislunar solar-sail study", subject="Mission simulation results", **kw)
        fr = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="F")
        self.addPageTemplates([PageTemplate(id="cover", frames=[fr], onPage=self._cover),
                               PageTemplate(id="body", frames=[fr], onPage=self._page)])
        self._hn = 0

    def _cover(self, c, d):
        c.saveState()
        c.setFillColor(colors.HexColor("#0d366b"))
        c.rect(0, letter[1] - 4.05 * inch, letter[0], 4.05 * inch, stroke=0, fill=1)
        c.restoreState()

    def _page(self, c, d):
        c.saveState()
        c.setFont("Carlito", 8.5)
        c.setFillColor(MUTED)
        c.drawString(self.leftMargin, 0.5 * inch, "Cislunar Solar Sailing for DARPA Cattle Run — Simulation Study Results")
        c.drawRightString(letter[0] - self.rightMargin, 0.5 * inch, f"{d.page}")
        c.setStrokeColor(GRID); c.setLineWidth(0.5)
        c.line(self.leftMargin, 0.62 * inch, letter[0] - self.rightMargin, 0.62 * inch)
        c.restoreState()

    def beforeDocument(self):
        self._hn = 0          # keep bookmark keys identical across multiBuild passes

    def afterFlowable(self, fl):
        if isinstance(fl, Paragraph) and fl.style.name in ("H1", "H2"):
            lvl = 0 if fl.style.name == "H1" else 1
            txt = fl.getPlainText()
            key = f"h{self._hn}"; self._hn += 1
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(txt, key, lvl, closed=lvl > 0)
            self.notify("TOCEntry", (lvl, txt, self.page, key))


def H1(t):
    return Paragraph(t, ST["H1"])


def H2(t):
    return Paragraph(t, ST["H2"])


def H3(t):
    return Paragraph(t, ST["H3"])


def build():
    q1, q2, q3, q4 = load("q1_transit"), load("q2_inclination"), load("q3_cislunar_transfers"), load("q4_pole_sitter")
    q5, q6, q7, q8 = load("q5_in_irons"), load("q6_fov"), load("q7_hybrid"), load("q8_lowest_orbit")
    dt = load("design_trades")
    designs = load("designs")
    story = []

    # ------------------------------------------------------------------ cover
    story += [Spacer(1, 0.25 * inch),
              Paragraph("<font color='#ffffff'>CISLUNAR SOLAR SAILING FOR DARPA CATTLE RUN</font>",
                        ParagraphStyle("c0", fontName="Carlito-Bold", fontSize=12.5, leading=16, textColor=colors.white)),
              Spacer(1, 10),
              Paragraph("<font color='#ffffff'>Mission Simulation Study: Results Report</font>",
                        ParagraphStyle("c1", fontName="Carlito-Bold", fontSize=30, leading=34, textColor=colors.white)),
              Spacer(1, 8),
              Paragraph("<font color='#cde2fb'>Transit times, launch geometry, cislunar transfers, pole-sitting, "
                        "'in-irons' limits, field of view, hybrid manoeuvrability and the lowest acceptable "
                        "demonstration orbit for distributed solar sails</font>",
                        ParagraphStyle("c2", fontName="Carlito", fontSize=12.5, leading=16, textColor=colors.white)),
              Spacer(1, 0.55 * inch)]
    im = Image(os.path.join(FIG, "q3_orbit_catalog_3d.png"), width=5.6 * inch, height=5.6 * inch * 0.66)
    story += [im, Spacer(1, 10)]
    info = [["Prepared for", "Cattle Run proposal team (DARPA-SN-27-03, Proposers Day 10 November 2026)"],
            ["Date", "1 November 2026"],
            ["Basis", "Objectives & outline (ObjectivesAndOutline.docx); reference library in Resources/; "
                      "open-source simulator in simulator/ (this repository)"],
            ["Deliverables", "This report (PDF) and the companion briefing (PPTX); all figures, results JSON and code are "
                             "reproducible with <font face='Carlito-Bold'>python simulator/run_all.py</font>"]]
    story.append(table([["", ""]] + info, [1.25, 5.35], header_rows=1, zebra=False))
    story += [NextPageTemplate("body"), PageBreak()]

    # ------------------------------------------------------------------ TOC
    toc = TableOfContents()
    toc.levelStyles = [ST["toc1"], ST["toc2"]]
    story += [Paragraph("Contents", ST["H1"]), toc, PageBreak()]

    # ------------------------------------------------------------------ data shortcuts
    td = q1["transit_days"]
    LEO, GTO, GEO = "LEO 1,000 km (28.5 deg)", "GTO, perigee raised to 1,000 km", "GEO (35,786 km)"
    crs = "0.123"
    m_s = q3["matrix_sail_days"]; m_h = q3["matrix_hybrid_days"]; names = q3["matrix_names"]
    def M(mat, a, b):
        return mat[names.index(a)][names.index(b)]
    tli = q3["tli_capture"]
    core = ["DRO", "EML1", "EML2", "NRHO"]; l45 = ["EML4", "EML5"]
    def rng(mat, A, Bs):
        v = [M(mat, a, b) for a in A for b in Bs if a != b]
        return min(v), max(v)
    core_s, core_h = rng(m_s, core, core), rng(m_h, core, core)
    l45_s, l45_h = rng(m_s, core, ["EML4"]), rng(m_h, core, ["EML4"])
    llo_s, llo_h = rng(m_s, ["LLO (LRO)"], core + ["EML4"]), rng(m_h, ["LLO (LRO)"], core + ["EML4"])
    red = [1 - M(m_h, a, b) / M(m_s, a, b) for a in core for b in core if a != b]
    red45 = [1 - M(m_h, a, "EML4") / M(m_s, a, "EML4") for a in core]
    redllo = 1 - M(m_h, "LLO (LRO)", "EML2") / M(m_s, "LLO (LRO)", "EML2")
    ets = q3["energy_times"]["sail"]
    ratios = [v["p25_d"] / v["median_d"] for o in ets for v in ets[o].values() if v["median_d"]]
    succ = [v["success"] for o in ets for v in ets[o].values() if v["median_d"]]
    rates = [abs(v["dC"]) / v["median_d"] for o in ets for v in ets[o].values() if v["median_d"] and abs(v["dC"]) > 0.05]
    cfg = {c["config"]: c for c in q5["configs"]}
    op = q5["operational_in_irons"]
    acc = q6["access"]["DRO 70k / maneuver"]
    env = {e["design"]: e for e in q7["envelopes"]}
    rs = q7["reachable_stats"]
    be = q8["break_even_alt_km"]; mg = q8["alt_drag_loss_le_25pct_km"]
    b60 = q4["budgets"]["below pole 60,000 km"]; b100 = q4["budgets"]["below pole 100,000 km"]
    bmin = q4["budgets"]["min-demand (el>=45, a_c=0.00)"]

    # ------------------------------------------------------------------ executive summary
    story += [H1("Executive summary")]
    story.append(P_(
        "DARPA's <b>Cattle Run</b> program (Special Notice DARPA-SN-27-03) seeks cost-effective cislunar constellations "
        "built from autonomous spacecraft that use solar sails or other renewable propulsion for station keeping and "
        "manoeuvring over long missions. The first step is a demonstrator launched <i>below GEO</i> to show sufficient "
        "acceleration, accurate vehicle control and autonomous GNC; later steps fly multiple spacecraft in cislunar "
        "space. This study built an end-to-end, GPU-capable simulator from the project outline and used it, together "
        "with the reference library, to answer the eight study questions. Results are given for a Solar Cruiser-class "
        f"conventional sail (<b>CR-S</b>: 1,653 m<super>2</super>, 111 kg, a<sub>c</sub> = {designs['CR-S']['a_c_mm_s2']:.3f} mm/s<super>2</super>), "
        f"a hybrid with a 20 mN gimballed SEP module (<b>CR-H</b>: a<sub>c</sub> = {designs['CR-H']['a_c_mm_s2']:.3f} mm/s<super>2</super> "
        f"+ SEP {designs['CR-H']['a_sep_mm_s2']:.3f} mm/s<super>2</super>) and parametric sweeps of characteristic acceleration."))
    story.append(table([
        ["#", "Question", "Answer (headline numbers)"],
        ["1", "Transit time from GTO, GEO, TLI, LEO to cislunar space",
         f"CR-S reaches lunar distance in <b>{f0(td[GEO][crs])} d</b> from GEO, <b>{f0(td[GTO][crs])} d</b> from a perigee-raised GTO and "
         f"<b>{f0(td[LEO][crs])} d</b> from 1,000 km LEO; times scale as 1/a<sub>c</sub> (66 d from GEO at 1 mm/s<super>2</super>). "
         f"TLI reaches lunar distance in {f1(q1['tli_ballistic_days_to_326000km'])} d; sail capture to halo energy takes "
         f"~{f0(tli['sail']['median_d'])} d (hybrid {f0(tli['hybrid']['median_d'])} d)."],
        ["2", "Optimal launch inclination",
         f"Match the lunar orbit plane at arrival: {q2['lunar_inclination_2028']:.1f} deg (2028) falling to {q2['lunar_inclination_2030']:.1f} deg (2030). "
         "A standard 28.5 deg Cape Canaveral launch / 27 deg GTO is within 1 % of optimal; SSO launches cost ~130-140 extra days."],
        ["3", "Transit to/between DRO, LRO-class LLO, EML1/2/4/5",
         f"EML1/EML2 halos, NRHO and DRO are mutually reachable in {f0(core_s[0])}-{f0(core_s[1])} d with the sail "
         f"({f0(core_h[0])}-{f0(core_h[1])} d hybrid); L4/L5 in {f0(l45_s[0])}-{f0(l45_s[1])} d; any leg to or from a 100 km LLO "
         f"takes {f0(llo_s[0])}-{f0(llo_s[1])} d, dominated by a {f0(q3['lunar_spiral']['sail']['up_days'])} d lunar spiral "
         f"(hybrid {f0(llo_h[0])}-{f0(llo_h[1])} d)."],
        ["4", "Lunar pole-sitter requirements",
         f"Static hovering 60,000-100,000 km below the south pole needs {f2(b100['a_req_mm_s2'])}-{f2(b60['a_req_mm_s2'])} mm/s<super>2</super> "
         f"continuously ({f0(b100['by_ac']['0.000']['dv_km_s_per_yr'])}-{f0(b60['by_ac']['0.000']['dv_km_s_per_yr'])} km/s per year). A sail can never "
         "hold it alone; synodic-period coverage orbits need a<sub>c</sub> >= 0.58-1.7 mm/s<super>2</super> (5-14x CR-S)."],
        ["5", "'No travel' / 'in irons' region",
         f"Al/CP1 sail: zero thrust within {f1(cfg['Al/CP1 sail (CR-S)']['nogo_half_angle_deg_tau0'])} deg of the Sun direction, "
         f"&lt;5 % a<sub>c</sub> within {f1(cfg['Al/CP1 sail (CR-S)']['nogo_half_angle_deg_tau5pct'])} deg; in irons "
         f"{100*op['Al/CP1 sail (CR-S)']['orbit_raising']:.0f} % of the time in orbit raising and "
         f"{100*op['Al/CP1 sail (CR-S)']['isotropic_SK']:.0f} % for random station-keeping demands. Every hybrid variant removes it."],
        ["6", "Field of view: fixed vs gimballed bus",
         f"Propulsion-driven attitude puts a body-fixed 10 deg instrument on Earth only {100*acc['Earth (HGA, 10 deg beam)']['Fixed, boresight on sail normal']:.0f} % "
         f"of the time; a +/-60 deg two-axis gimbal raises it to {100*acc['Earth (HGA, 10 deg beam)']['Gimbal +/-60 deg']:.0f} % "
         f"({100*acc['SDA field, anti-Sun hemisphere (camera, 15 deg)']['Gimbal +/-60 deg']:.0f} % for anti-Sun SDA fields) and solar power from "
         f"{100*acc['Solar array power (fraction of max)']['Fixed, boresight on sail normal']:.0f} % to {100*acc['Solar array power (fraction of max)']['Gimbal +/-60 deg']:.0f} %."],
        ["7", "Hybrid manoeuvrability and acceleration",
         f"CR-H: {f3(env['CR-H']['away_from_sun'])}/{f3(env['CR-H']['perpendicular'])}/{f3(env['CR-H']['toward_sun'])} mm/s<super>2</super> "
         f"(away/perpendicular/toward Sun) vs {f3(env['CR-S']['away_from_sun'])}/{f3(env['CR-S']['perpendicular'])}/0 for CR-S; "
         f"7-day reach from a DRO {f0(rs['CR-H hybrid']['7']['max_disp_km']/1e3)}k km vs {f0(rs['CR-S sail']['7']['max_disp_km']/1e3)}k km; "
         f"hybrid is lighter than SEP-only above {f1(q7['mass_trade']['notes']['hybrid_beats_sep_above_km_s'])} km/s cumulative delta-v."],
        ["8", "Lowest acceptable orbit for the demonstrator",
         f"Drag equals sail thrust at {f0(q8['f_criterion']['Solar minimum (F10.7=70)']['h_mean'])}/{f0(q8['f_criterion']['Moderate (F10.7=150)']['h_mean'])}/"
         f"{f0(q8['f_criterion']['Solar maximum (F10.7=230)']['h_mean'])} km (solar min/moderate/max). A robust demo needs <b>~1,000 km</b> "
         f"(900 km in dawn-dusk SSO); from a 550 km rideshare a stowed-sail SEP climb takes "
         f"{f0(q8['sep_climb_550_to_1000km']['moderate']['days'])} d and {f1(q8['sep_climb_550_to_1000km']['moderate']['propellant_kg'])} kg."],
    ], [0.3, 1.75, 4.55]))
    story.append(Spacer(1, 8))
    story.append(callout("Recommendations", [
        "<b>1. Baseline a hybrid sail.</b> A Solar Cruiser-class sail with a small two-axis gimballed SEP module (CR-H) removes the "
        "in-irons region, doubles manoeuvre reach, and decouples power and pointing from propulsion at a 20 kg (18 %) mass cost.",
        "<b>2. Fly the below-GEO demonstrator at ~1,000 km in a dawn-dusk sun-synchronous orbit</b> (no eclipses, ~20 % faster "
        "raising than noon-midnight, drag < 25 % of sail thrust even at solar maximum). If only a 550 km rideshare is available, "
        "climb with the sail stowed using SEP before deployment.",
        "<b>3. Launch cislunar elements from Cape Canaveral (28.5 deg) or into a 27 deg GTO</b>; raise perigee to ~1,000 km before sail "
        "deployment (75 m/s) and use DRO, NRHO and L1/L2 halos as constellation slots; reach L4/L5 within 2-3 months.",
        "<b>4. Do not baseline a lunar pole-sitter.</b> Provide south-pole coverage with two spacecraft in NRHO/L2-halo orbits; reserve "
        "pole-sitting for a far-term sail (a<sub>c</sub> >= 1 mm/s<super>2</super>) or a short SEP-dominated campaign.",
        "<b>5. Gimbal the bus (or payload) relative to the sail</b> and carry antennas on both faces; use reflectivity-control devices "
        "plus centre-of-mass shift for propellant-free momentum management."]))
    story.append(fig("q7_reachable_2d.png", "Figure ES-1 - Why the hybrid: positions reachable from a 70,000 km DRO in 3 days (grey) "
                     "and 7 days (colour). The sail's reach is lopsided away from the Sun; the hybrid reaches every direction."))
    story.append(PageBreak())

    # ------------------------------------------------------------------ 1 introduction
    story += [H1("1. Program context and study objectives")]
    story.append(P_(
        "The Cattle Run Proposers Day (10 November 2026) frames a two-phase program: a rapid demonstrator below "
        "geosynchronous orbit, then multiple spacecraft operating in cislunar space. The project objectives document "
        "restates these as four mission objectives and asks for an inclusive simulator that covers the trip from Earth to and "
        "within cislunar space, estimates transit times, contrasts conventional and hybrid sails, uses PyTorch to exploit GPUs, "
        "pre-processes mission profiles for the design options and produces 2-D and 3-D plots for presentations."))
    story.append(table([
        ["Mission objective (DARPA / outline)", "How this study addresses it"],
        ["Cost-effective cislunar constellation", "Orbit slots (DRO, NRHO, L1/L2 halos, L4/L5), transfer-time matrix, deployment and phasing times (Sections 4-5)"],
        ["Autonomous spacecraft using solar sails or other renewable propulsion", "Locally optimal on-board steering laws (closed form / table driven) used throughout; hybrid SEP allocation"],
        ["Station keeping and manoeuvrability over long durations", "In-irons statistics (Q5), reachable sets and response times (Q7), propellant-free momentum management"],
        ["Launch below GEO to show acceleration, control and autonomous GNC", "Drag, gravity-gradient, atomic-oxygen and solar-cycle analysis of candidate orbits (Q8)"],
    ], [2.6, 4.0]))
    story.append(Spacer(1, 6))
    story.append(P_("The design options and variables listed in the outline - conventional vs hybrid sail, fixed vs gimballed SEP, "
                    "repeatedly deployable/retractable sail, embedded electrochromic films, single- vs double-sided film, mass, sail "
                    "material and size, SEP thrust and specific impulse, rigid booms vs spin deployment and gimbal range - are all "
                    "parameters of the simulator and are traded in Section 12."))

    # ------------------------------------------------------------------ 2 simulator
    story += [H1("2. Simulation framework")]
    story.append(P_("The simulator (<font face='Carlito-Bold'>simulator/cislunar_sail</font>) is a Python package with an "
                    "array-backend abstraction: every batched propagator and steering law runs unchanged on NumPy or on PyTorch "
                    "tensors (CPU or CUDA GPU; select with <font face='Carlito-Bold'>CISLUNAR_BACKEND=torch</font>). Thousands of "
                    "trajectories - Sun phases, launch seasons, design points, steering commands - are propagated in lock-step, "
                    "which is how the Monte-Carlo-style ensembles in this report were produced."))
    story.append(table([
        ["Module", "Content"],
        ["sail", "Optical force model (Eq. 1-2), material catalogue, locally optimal cone-angle tables, force envelopes, "
                 "sail+SEP allocation with gimbal limits and drag-aware steering, membrane temperature"],
        ["environment", "Sun and Moon ephemerides (18.6-yr nodal cycle), cylindrical Earth/Moon shadows, NRLMSIS 2.x density "
                        "tables vs altitude, local time and solar activity (F10.7 = 70/150/230)"],
        ["earth_orbit", "Orbit-averaged Gauss equations in modified equinoctial elements (non-singular) with J2, eclipses, drag, "
                        "SEP mass flow; batched RK4; Moon-centred variant; Cowell integrator with Sun + Moon gravity for validation"],
        ["cr3bp", "Earth-Moon CR3BP with rotating Sun line (non-autonomous), optional solar tidal gravity (BCR4BP), shadows, "
                  "differential correction and continuation for Lyapunov, halo, NRHO and DRO families, batched RK4"],
        ["designs", "Heritage and study design points; parametric sail-system mass model (membrane, booms, deployer, RCD, "
                    "retraction) calibrated on ACS3 and Solar Cruiser; SEP sizing after Ceriotti & McInnes"],
        ["analyses", "One module per study question (q1-q8) plus design trades; run_all.py regenerates every JSON and figure"],
    ], [1.2, 5.4]))
    story.append(Spacer(1, 6))
    story.append(H2("2.1 Physical models"))
    story.append(P_("The sail force uses the McInnes non-ideal optical model with the Rios-Reyes & Scheeres coefficients. "
                    "<b>s</b> is the photon direction (Sun to sail), <b>n</b> the normal of the lit face, alpha the cone angle:"))
    story += eq("eq_force", 6.3) + eq("eq_coeffs", 6.5)
    story.append(P_("Characteristic acceleration a<sub>c</sub> is always quoted for the real (non-ideal) film at 1 AU with the lit "
                    "face normal to the Sun; this is ~9 % below the ideal 2PA/m formula used in some flight-project quotes "
                    "(e.g. ACS3's 0.045 mm/s<super>2</super>). In the Earth-Moon rotating frame (Earth at -mu, Moon at 1-mu) the "
                    "dynamics and the rate of change of the Jacobi constant C, used to measure energy changes between orbits, are:"))
    story += eq("eq_jacobi", 6.3)
    story.append(P_("Steering is locally optimal: for any desired direction (velocity for energy, the gradient of apogee radius "
                    "for apogee raising, an arbitrary control demand for station keeping) the cone angle that maximises the "
                    "useful force component is taken from a precomputed table; the sail feathers edge-on when nothing useful "
                    "is available. For hybrids the SEP thrust may point within the gimbal range of either sail-normal direction, "
                    "and a brute-force search over cone angle finds the best combined component, optionally penalising drag."))
    story.append(H2("2.2 Validation against the reference library"))
    val = q1["cowell_validation"]
    story.append(table([
        ["Benchmark", "Reference value", "Simulator"],
        ["Optimal cone angle / thrust fraction for thrust perpendicular to sunlight (ideal sail)", "35.26 deg / 0.385 (McInnes 1999)", "35.25 deg / 0.385"],
        ["Orbit-averaged transverse thrust fraction, Sun in plane (ideal sail)", "0.4393 (McInnes Sec. 4.4.4)", "0.4393"],
        ["Spiral from GEO to 326,000 km at a<sub>c</sub> = 0.5/0.2/0.1 mm/s<super>2</super>", "104/259/519 d (quasi-circular estimate)", "95/243/492 d (eccentricity grows)"],
        ["ACS3 SMA rise in 180 days, 715 km / 900 km SSO (Dono 2023)", "+301 km / +340 km", "+212 to +338 km / +353 to +371 km (F10.7 150 to 70)"],
        ["Minimum altitude for ACS3 orbit raising (Wilkie 2023)", "~691 km (mean activity)", "647 km noon-midnight SSO (F10.7 = 150)"],
        ["Averaged vs Cowell (Sun+Moon gravity), raised GTO, 60 days", "-", f"apogee {val[-1]['ra_avg_km']:,.0f} vs {val[-1]['ra_cowell_km']:,.0f} km (0.1 %)"],
        ["Earth-Moon L1/L2 Jacobi constants", "3.1883 / 3.1722", "3.18834 / 3.17216"],
        ["9:2 NRHO (Gateway reference)", "x0 1.0221, z0 -0.1821, vy0 -0.1033, 6.56 d, perilune ~3,250 km",
         "1.02202, -0.18210, -0.10326, 6.56 d, 3,249 km"],
        ["Hover acceleration below the lunar south pole (Ozimek, Grebow & Howell)", "contours 0.58-1.7 mm/s<super>2</super> near L1/L2",
         "map reproduced (Fig. 4.1); 1.77 mm/s<super>2</super> at 60,000 km"],
    ], [2.75, 2.05, 1.8]))
    story.append(Spacer(1, 4))
    story.append(fig("q1_model_validation.png", "Figure 2.1 - Orbit-averaged propagation (J2 only) against direct Cowell integration "
                     "with J2, solar and lunar gravity for a perigee-raised GTO spiral at a<sub>c</sub> = 0.5 mm/s<super>2</super>.", 6.0))

    # ------------------------------------------------------------------ 3 designs
    story += [H1("3. Spacecraft configurations and design points")]
    story.append(P_("Heritage sailcraft anchor the performance range; three study designs bracket the Cattle Run options. "
                    "CR-S reuses the Solar Cruiser sail system (TRL-6 quadrant tested 2022-2024); CR-H adds a 20 kg SEP module "
                    "(20 mN Hall thruster at ~350 W, Isp 1,500 s, 6 kg xenon/krypton, two-axis +/-30 deg gimbal); CR-HR adds a "
                    "motorised re-spooling deployer; CR-A is a far-term 4,000 m<super>2</super> sail on 1 um film."))
    rows = [["Design", "Mass (kg)", "Area (m<super>2</super>)", "Film", "a<sub>c</sub> (mm/s<super>2</super>)", "Loading (g/m<super>2</super>)",
             "SEP", "SEP accel. (mm/s<super>2</super>)", "SEP dv (km/s)"]]
    for k in ("LS2", "ACS3", "NEAS", "SC", "CR-S", "CR-H", "CR-HR", "CR-A"):
        d = designs[k]
        sep = "-" if d["sep_thrust_mN"] == 0 else f"{d['sep_thrust_mN']:.0f} mN, {d['isp_s']:.0f} s, +/-{d['gimbal_deg']:.0f} deg"
        rows.append([d["name"], f0(d["mass_kg"]), f0(d["area_m2"]), d["material"].split(" (")[0], f3(d["a_c_mm_s2"]),
                     f1(d["sail_loading_g_m2"]), sep, f3(d["a_sep_mm_s2"]) if d["a_sep_mm_s2"] else "-",
                     f2(d["sep_dv_km_s"]) if d["sep_dv_km_s"] else "-"])
    story.append(table(rows, [1.55, 0.5, 0.5, 0.95, 0.6, 0.6, 0.95, 0.5, 0.45]))
    story.append(Spacer(1, 6))
    story.append(KeepTogether([table([
        ["Film / model", "r", "s", "eps_f / eps_b", "Thrust efficiency", "Max force angle (deg)", "No-go cone (deg)", "T at normal incidence"],
        ["Ideal", "1", "1", "-", "1.000", "~90", "~0", "-"],
        ["Al/CP1 2.5 um (Solar Cruiser, NEA Scout)", "0.88", "0.94", "0.05 / 0.55", f3(dt['efficiency']['Al/CP1 2.5 um (NEA Scout, Solar Cruiser)']),
         "55.5", "34.5", f"{dt['thermal_peak_C']['Al/CP1 2.5 um (NEA Scout, Solar Cruiser)']:.0f} C"],
        ["Al/PEN/Cr 2.1 um (ACS3)", "0.90", "0.82", "0.03 / 0.60", f3(dt['efficiency']['Al/PEN/Cr 2.1 um (ACS3)']), "49.2", "40.8",
         f"{dt['thermal_peak_C']['Al/PEN/Cr 2.1 um (ACS3)']:.0f} C"],
        ["Al/CP1/Al double-sided", "0.88", "0.94", "0.05 / 0.05", f3(dt['efficiency']['Al/CP1/Al double-sided 2.5 um']), "57.1", "32.9",
         f"{dt['thermal_peak_C']['Al/CP1/Al double-sided 2.5 um']:.0f} C"],
    ], [1.9, 0.35, 0.35, 0.75, 0.75, 0.85, 0.75, 0.9]),
        Paragraph("Table 3.1/3.2 - Design points (non-ideal a<sub>c</sub>) and film optical properties (McInnes 1999 Table 2.1; "
                  "ACS3 appendix in Wilkie 2023).", ST["cap"])]))
    story.append(fig("dt_ac_vs_area.png", "Figure 3.1 - Characteristic acceleration against sail area for 10/50/100 kg bus-plus-payload "
                     "masses, rigid booms (thick) and spin deployment (thin), from the calibrated mass model, with heritage points."))

    # ------------------------------------------------------------------ Q1
    story += [CondPageBreak(3.3 * inch), H1("4. Q1 - Transit time from GTO, GEO, TLI and LEO to cislunar space")]
    story.append(P_("<b>Method.</b> Batched orbit-averaged propagation with locally optimal apogee-raising steering and "
                    "perigee protection, eclipses and J2; six launch seasons per case (Sun geometry), arrival when the "
                    "osculating apogee reaches 326,000 km (the Earth-Moon L1 distance). The L1 energy 'gateway' (Jacobi "
                    "constant C = C<sub>L1</sub>) is already crossed at r<sub>a</sub> ~ 260,000 km, after which lunar gravity "
                    "and sail steering complete the capture (Section 6). Hybrid cases use CR-H with its 6 kg of propellant and, "
                    "for reference, unlimited propellant."))
    rows = [["Start orbit", "0.045 (ACS3)", "0.07", "0.10", "0.123 (CR-S)", "0.2", "0.3", "0.5", "1.0", "CR-H 6 kg", "CR-H unlimited"]]
    for k in (LEO, GTO, GEO):
        r = td[k]
        rows.append([k, f0(r["0.045"]), f0(r["0.07"]), f0(r["0.1"]), f"<b>{f0(r['0.123'])}</b>", f0(r["0.2"]), f0(r["0.3"]),
                     f0(r["0.5"]), f0(r["1"]), f0(r["CR-H (6 kg prop)"]),
                     f"{f0(r['CR-H unlimited prop'])} ({f0(r['CR-H unlimited prop used kg'])} kg)"])
    story.append(table(rows, [1.6, 0.5, 0.4, 0.4, 0.55, 0.4, 0.4, 0.4, 0.4, 0.5, 0.85]))
    story.append(Paragraph("Table 4.1 - Median days to lunar-distance apogee vs characteristic acceleration (mm/s<super>2</super>); "
                           "'n/a' = longer than 10 years.", ST["cap"]))
    story.append(fig("q1_transit_vs_ac.png", "Figure 4.1 - Transit time to lunar distance against a<sub>c</sub> for three start orbits "
                     "(bands: spread over launch seasons) and the CR-H hybrid (diamonds)."))
    gs = q1["gto_standard"]["moderate"]
    story.append(H3("Findings"))
    story += bullets([
        f"Transit time is essentially Delta-v / (useful fraction x a<sub>c</sub>): from GEO the spiral needs ~2.1 km/s and the "
        "sail delivers ~0.4 a<sub>c</sub> on average, so a<sub>c</sub> = 0.1 mm/s<super>2</super> takes ~1.8 years.",
        f"Starting low is expensive: 1,000 km LEO takes {f1(td[LEO][crs]/365.25)} years for CR-S versus {f1(td[GEO][crs]/365.25)} years from GEO. "
        "LEO also adds drag, eclipses and atomic oxygen (Section 11), so LEO is a demonstration orbit, not a staging orbit.",
        f"Standard GTO (250 km perigee) is survivable only if the sail holds an edge-on attitude through every 10 km/s perigee pass: "
        f"with ~1 % residual drag area the drag-aware law lifts perigee to {f0(gs['rp_final_km'][1])} km in 120 days for CR-S. "
        f"The robust option is a {f0(q1['gto_standard']['perigee_raise_dv_m_s'])} m/s perigee raise to 1,000 km before deployment.",
        f"TLI places the spacecraft at lunar distance in {f1(q1['tli_ballistic_days_to_326000km'])} days; the sail must then shed "
        f"energy to be captured (C from {f2(tli['sail']['C_tli'])} to the EML2-halo value {f2(tli['sail']['C_target'])}): "
        f"median {f0(tli['sail']['median_d'])} d for CR-S and {f0(tli['hybrid']['median_d'])} d for CR-H. Ballistic lunar transfers "
        "(CAPSTONE, ~4 months) reach the same orbits with almost no propulsion and are an attractive alternative.",
        "The hybrid's 6 kg of propellant shortens transits only modestly (CR-H is 18 % heavier, so its sail is weaker); with "
        f"unlimited SEP it reaches lunar distance from GEO in {f0(td[GEO]['CR-H unlimited prop'])} d but burns "
        f"{f0(td[GEO]['CR-H unlimited prop used kg'])} kg - transits are where SEP propellant is least valuable.",
    ])
    story.append(fig("q1_spiral_3d.png", "Figure 4.2 - 3-D view of the CR-S spiral from a perigee-raised GTO: osculating orbits "
                     "coloured light (early) to dark (late), with the Moon's orbit.", 5.8))
    story.append(callout("Answer to Q1", [
        f"For a near-term sail (a<sub>c</sub> ~ 0.12 mm/s<super>2</super>): <b>~{f1(td[GEO][crs]/365.25)} yr from GEO, "
        f"~{f1(td[GTO][crs]/365.25)} yr from a perigee-raised GTO, ~{f1(td[LEO][crs]/365.25)} yr from 1,000 km LEO</b>; "
        f"from TLI, lunar distance in {f1(q1['tli_ballistic_days_to_326000km'])} d plus ~{f0(tli['sail']['median_d'])} d sail capture. "
        "Doubling a<sub>c</sub> halves every number. Cislunar elements should therefore ride to GTO/GEO or TLI and use the sail "
        "for the final leg and for operations, not for the climb out of LEO."]))

    # ------------------------------------------------------------------ Q2
    story += [CondPageBreak(3.3 * inch), H1("5. Q2 - Optimal launch inclination")]
    story.append(P_("Three effects set the best inclination: the lunar orbit plane, whose inclination to Earth's equator swings "
                    "between 18.3 and 28.6 deg with the 18.6-year nodal cycle; sail effectiveness, which depends on the Sun's "
                    "elevation beta above the orbit plane and on eclipses; and the cost of removing any plane mismatch. We swept "
                    "launch inclinations from 0 to 97.6 deg for perigee-raised GTO spirals (six seasons each) and measured "
                    "plane-change rates on the high-apogee arrival orbit."))
    story.append(fig("q2_lunar_plane_cycle.png", "Figure 5.1 - Inclination of the lunar orbit to the equator, 2024-2046, with launch-site "
                     "latitudes. The 2025 major lunar standstill makes 2027-2030 well matched to Cape Canaveral launches."))
    story.append(fig("q2_beta_efficiency.png", "Figure 5.2 - Orbit-averaged useful thrust fraction for energy raising vs Sun elevation "
                     "above the orbit plane (Al/CP1)."))
    bq = q2["beta_efficiency"]
    story.append(P_(f"In LEO the dawn-dusk geometry (beta = 90 deg) is best ({bq['1000']['beta90']:.3f} vs {bq['1000']['beta0']:.3f} "
                    f"of a<sub>c</sub>) because a third of a beta = 0 orbit is in eclipse ({100*bq['1000']['eclipse_beta0']:.0f} %); at GEO "
                    f"the Sun in the plane is best ({bq['35786']['beta0']:.3f}). Over a multi-month spiral the seasons average out, so "
                    "the spiral time itself varies by only +/-3 % with inclination."))
    rows = [["Launch inclination (deg)"] + [f"{i:g}" for i in q2["inclinations"]],
            ["Spiral to lunar distance (d)"] + [f0(x) for x in q2["raise_days_median"]],
            ["Inclination on arrival (deg)"] + [f1(x) for x in q2["final_inclination_deg_median"]],
            ["Total incl. plane match (d)"] + [f0(x) for x in q2["total_days"]]]
    story.append(table(rows, [1.55] + [0.46] * len(q2["inclinations"])))
    story.append(Paragraph(f"Table 5.1 - CR-S from a perigee-raised GTO (launch 2028, arrival ~{q2['arrival_year']:.1f}; lunar plane at "
                           f"arrival {q2['lunar_plane_inclination_at_arrival_deg']:.1f} deg). Plane change near apogee costs "
                           f"~{q2['plane_change']['10']['aligned']:.1f} d/deg with apsides aligned to the node line "
                           f"(~{q2['plane_change']['10']['perpendicular']:.0f} d/deg if perpendicular).", ST["cap"]))
    story.append(fig("q2_time_vs_inclination.png", "Figure 5.3 - Spiral time, residual plane change and total vs launch inclination."))
    story.append(P_("A useful by-product: the out-of-plane part of the sail force drifts the orbit plane toward the ecliptic "
                    "(23.4 deg), which lies within 5.1 deg of the lunar plane - a 28.5 deg launch arrives at ~21 deg. RAAN need not "
                    "be matched at launch: J2 regresses the node of a GTO by ~0.3 deg/day, so the arrival node is set by launch "
                    "date and spiral duration."))
    story.append(callout("Answer to Q2", [
        f"<b>Launch close to the lunar-plane inclination at arrival: ~23-29 deg for 2028-2031.</b> The standard Cape Canaveral "
        f"28.5 deg launch (or a 27 deg GTO rideshare) is within 1 % of the optimum ({f0(min(q2['total_days']))} d total for CR-S). "
        f"Equatorial launches cost ~{f0(q2['total_days'][0]-min(q2['total_days']))} d more and sun-synchronous launches "
        f"~{f0(q2['total_days'][-1]-min(q2['total_days']))} d more. For later constellation launches (2032-2036) the lunar plane drops "
        f"to {q2['lunar_inclination_2034']:.1f} deg, favouring ~20 deg launches. For the LEO demonstrator, choose a dawn-dusk "
        "sun-synchronous orbit."]))

    # ------------------------------------------------------------------ Q3
    story += [CondPageBreak(3.3 * inch), H1("6. Q3 - Transit to and between DRO, LRO-class orbit and EML1/2/4/5")]
    cat = q3["catalog"]
    story.append(P_("<b>Destinations.</b> Periodic orbits were computed by differential correction and continuation in the CR3BP: "
                    "an EML1 northern halo (Az 15,000 km), an EML2 halo (Az 10,000 km), the 9:2 NRHO, a 70,000 km DRO, the "
                    "triangular points L4/L5, and a 100 km polar low lunar orbit representative of the Lunar Reconnaissance "
                    "Orbiter (LRO flew 50 km circular, now ~20 x 165 km)."))
    rows = [["Orbit", "Jacobi C", "Period (d)", "Stability index", "Closest / farthest from Moon (km)"]]
    for k in ("EML1 halo", "EML2 halo", "NRHO 9:2", "DRO 70k", "EML4", "LLO 100 km polar"):
        c = cat[k]
        rows.append([k, f"{c['C']:.4f}", f1(c.get("period_d")) if c.get("period_d") else "-",
                     f1(c.get("stability")) if c.get("stability") else "-",
                     f"{f0(c.get('rmin_moon_km'))} / {f0(c.get('rmax_moon_km'))}" if c.get("rmin_moon_km") else "-"])
    story.append(table(rows, [1.6, 0.9, 0.9, 1.0, 2.2]))
    story.append(Spacer(1, 4))
    story.append(fig("q3_orbit_catalog_2d.png", "Figure 6.1 - Destination orbits seen from above and from the side (Moon-centred, "
                     "rotating frame)."))
    story.append(P_("<b>Method.</b> Transfer time = time to change the Jacobi constant from the origin to the destination value "
                    "under the locally optimal energy law (CR3BP with the Sun line rotating at the synodic rate; median over 12 "
                    "starting phases x 8 Sun phases) + a natural coast between the regions once energies match. Coasts: "
                    f"L1-L2 {f0(q3['l1_l2_manifold_tof']['median_d'])} d (computed along the L1-halo unstable manifold), "
                    "halo/NRHO-DRO 20 d, Moon region-L4/L5 45 d, L4-L5 90 d. Legs to or from the 100 km LLO use a "
                    "Moon-centred averaged spiral to a 20,000 km hand-over orbit (whose energy is close to the L2-halo value) "
                    "plus the remaining energy change."))
    story.append(fig("q3_transfer_matrix.png", "Figure 6.2 - Estimated transfer times (days) between destination orbits for the "
                     "CR-S sail and the CR-H hybrid (row = from, column = to)."))
    rows = [["From \\ to"] + names]
    for a in names:
        rows.append([a] + ["-" if a == b else f"{f0(M(m_s, a, b))} / {f0(M(m_h, a, b))}" for b in names])
    story.append(table(rows, [0.8] + [0.82] * len(names), font=8.2))
    story.append(Paragraph("Table 6.2 - Transfer times in days, sail (CR-S) / hybrid (CR-H).", ST["cap"]))
    et = q3["energy_times"]
    story += bullets([
        f"Halo, NRHO and DRO slots are mutually accessible in {f0(core_s[0])}-{f0(core_s[1])} days: their Jacobi constants differ by "
        f"&lt;= 0.23 and a 0.12 mm/s<super>2</super> sail changes C by {min(rates):.3f}-{max(rates):.3f} per day near these orbits.",
        f"L4/L5 sit only Delta-C ~ 0.16 above the L2 halo energy but ~380,000 km away; the drift dominates "
        f"({f0(M(m_s, 'EML2', 'EML4'))} d sail, {f0(M(m_h, 'EML2', 'EML4'))} d hybrid from the L2 halo).",
        f"Low lunar orbit is the outlier: a 100 km orbit is deep in the lunar well (C = {cat['LLO 100 km polar']['C']:.2f}) and the "
        f"sail spiral to 20,000 km takes {f0(q3['lunar_spiral']['sail']['up_days'])} d with eclipses on every revolution; the hybrid "
        f"needs {f0(q3['lunar_spiral']['hybrid']['up_days'])} d but would spend far more propellant than CR-H carries.",
        f"Departure timing matters: the fastest quarter of Sun and start phases is {100*(1-max(ratios)):.0f}-{100*(1-min(ratios)):.0f} % "
        f"quicker than the median, and {100*(1-max(succ)):.0f}-{100*(1-min(succ)):.0f} % of phases fail within 130 days because the "
        "trajectory escapes or strikes the Moon first (medians are over successful cases). Lowering energy from the NRHO drives "
        "perilune into the Moon, so NRHO-to-halo legs need perilune control; they are estimated from the reverse legs.",
        f"The hybrid shortens halo/NRHO/DRO legs by {100*min(red):.0f}-{100*max(red):.0f} %, L4/L5 legs by {100*min(red45):.0f}-{100*max(red45):.0f} % "
        f"(the long drift is unchanged) and LLO legs by {100*redllo:.0f} % - but the 73-day hybrid lunar spiral needs ~0.6 km/s of SEP, "
        "most of CR-H's 6 kg load.",
    ])
    halo_dro = [M(m_s, a, b) for a, b in (("EML1", "DRO"), ("EML2", "DRO"), ("NRHO", "DRO"), ("DRO", "EML1"), ("DRO", "EML2"), ("DRO", "NRHO"))]
    story.append(callout("Answer to Q3", [
        f"With a near-term sail (CR-S): <b>EML1 &lt;-&gt; EML2 ~{f0(M(m_s,'EML1','EML2'))}-{f0(M(m_s,'EML2','EML1'))} d, halo/NRHO &lt;-&gt; DRO "
        f"{f0(min(halo_dro))}-{f0(max(halo_dro))} d, to L4/L5 {f0(l45_s[0])}-{f0(l45_s[1])} d, and any leg touching a 100 km LLO "
        f"{f0(llo_s[0])}-{f0(llo_s[1])} d</b>. From TLI, sail capture to halo energy takes ~{f0(tli['sail']['median_d'])} d "
        f"({100*tli['sail']['success']:.0f} % of arrival geometries succeed) versus ~{f0(tli['hybrid']['median_d'])} d for the hybrid. "
        f"The hybrid shortens high cislunar legs by {100*min(red):.0f}-{100*max(red):.0f} %. LRO-class orbits should be served by dedicated "
        "SEP or chemical vehicles; the sail constellation belongs in the high cislunar orbits."]))

    # ------------------------------------------------------------------ Q4
    story += [CondPageBreak(3.3 * inch), H1("7. Q4 - What is necessary to achieve a lunar pole-sitter orbit?")]
    story.append(P_("A pole-sitter stays fixed below (or above) a lunar pole in the rotating frame. Its control acceleration must "
                    "cancel gravity plus centrifugal acceleration at every instant. A sail can only produce vectors on its force "
                    "'bubble', which turns with the Sun once per synodic month, so we compute the residual that SEP must supply:"))
    story += eq("eq_hover", 6.0)
    story.append(fig("q4_hover_requirement.png", "Figure 7.1 - Required hover acceleration below the lunar south pole (log colour "
                     "scale; contours in mm/s<super>2</super>) with elevation angles seen from the pole (orange) and candidate stations."))
    rows = [["Station (Moon-centred)", "|a_req| (mm/s<super>2</super>)", "Pure SEP dv/yr (km/s)", "Prop. fraction / yr (Isp 3,000 s)",
             "With sail 0.12", "With sail 1.7", "Sail alone holds hover"]]
    for k, lab in (("below pole 60,000 km", "60,000 km below pole (el. 90 deg)"), ("below pole 100,000 km", "100,000 km below pole"),
                   ("min-demand (el>=45, a_c=0.00)", "best point with el. >= 45 deg")):
        b = q4["budgets"][k]
        rows.append([lab, f2(b["a_req_mm_s2"]), f1(b["by_ac"]["0.000"]["dv_km_s_per_yr"]),
                     f"{100*b['by_ac']['0.000']['prop_frac_1yr_isp3000']:.0f} %",
                     f"{f1(b['by_ac']['0.123']['dv_km_s_per_yr'])} km/s", f"{f1(b['by_ac']['1.700']['dv_km_s_per_yr'])} km/s",
                     f"{100*b['by_ac']['1.700']['frac_month_sail_alone_ok']:.0f} % of month"])
    story.append(table(rows, [1.75, 0.75, 0.8, 0.95, 0.75, 0.75, 0.85]))
    story.append(Paragraph("Table 7.1 - Pole-sitter budgets: SEP delta-v per year still required with sails of 0.12 and 1.7 mm/s<super>2</super>.", ST["cap"]))
    story.append(fig("q4_sail_savings_map.png", "Figure 7.2 - Share of the SEP demand removed by a sail (month-averaged): ~0-10 % at "
                     "0.12 mm/s<super>2</super>, ~10-40 % even at 1.7 mm/s<super>2</super>."))
    story += bullets([
        "The requirement is dominated by lunar gravity along the polar axis; the sail's thrust lies near the Earth-Moon plane "
        "(the Sun is within 5 deg of it), almost perpendicular to what is needed. Hence the small savings in Figure 7.2.",
        "A static hover is therefore an SEP mission: Grebow, Ozimek & Howell needed a 500 kg spacecraft (450 kg propellant, 150 mN) "
        "for 387-554 days of pole-sitting, consistent with the 31-56 km/s per year found here.",
        "Sails make sense only on non-static, synodic-period 'pole-coverage' orbits that let the spacecraft drift with the Sun: "
        "Ozimek et al. found single-sail coverage needs kappa >= 0.58 mm/s<super>2</super> (elevations of only 4-7 deg near L1/L2) and "
        "~1.7 mm/s<super>2</super> for 15-45 deg elevations; Wawrzyniak & Howell require >= 1.5 mm/s<super>2</super> for a 15 deg constraint.",
    ])
    story.append(fig("q4_mass_vs_duration.png", "Figure 7.3 - Initial mass needed for 100 kg dry mass vs pole-sitting duration at "
                     "60,000 km below the pole (Isp 3,000 s).", 6.0))
    story.append(callout("Answer to Q4", [
        f"<b>Necessary:</b> either (a) a sail with a<sub>c</sub> >= ~0.6 mm/s<super>2</super> (low-elevation coverage) to ~1.7 mm/s<super>2</super> "
        "(high elevation) flying synodic-period coverage orbits - a total sail loading of ~5-15 g/m<super>2</super>, i.e. 5-14x "
        "the CR-S performance and beyond the far-term CR-A (0.27 mm/s<super>2</super>); or (b) high-Isp SEP supplying "
        f"{f0(bmin['by_ac']['0.000']['dv_km_s_per_yr'])}-{f0(b60['by_ac']['0.000']['dv_km_s_per_yr'])} km/s per year, which consumes "
        f"{100*bmin['by_ac']['0.000']['prop_frac_1yr_isp3000']:.0f}-{100*b60['by_ac']['0.000']['prop_frac_1yr_isp3000']:.0f} % of the "
        "mass per year at Isp 3,000 s. <b>Recommendation:</b> do not baseline a lunar pole-sitter for Cattle Run; provide polar "
        "coverage with two spacecraft in NRHO/L2-halo orbits (natural dynamics, sail station keeping) and revisit pole-sitting "
        "when sail loading below ~10 g/m<super>2</super> is demonstrated."]))

    # ------------------------------------------------------------------ Q5
    story += [CondPageBreak(3.3 * inch), H1("8. Q5 - The 'no travel' (in irons) region: sail vs hybrid")]
    story.append(P_("A sail cannot push toward the Sun. With a real film part of the momentum is absorbed or diffusely reflected, "
                    "so the force can never tilt more than ~50-56 deg from the sunlight direction: the reachable accelerations form "
                    "a 'bubble' touching the origin, and a cone around the sunward direction is completely unreachable."))
    story.append(fig("q5_force_bubbles.png", "Figure 8.1 - Left: force bubbles of ideal and real films with the Al/CP1 no-go cone. "
                     "Right: maximum useful acceleration (support function) vs direction for the sail and three hybrid variants."))
    rows = [["Configuration", "No thrust at all within (deg of sunward)", "&lt; 5 % a<sub>c</sub> within (deg)",
             "Toward Sun (x a<sub>c</sub>)", "Perpendicular (x a<sub>c</sub>)"]]
    for k in ("Ideal sail", "Al/CP1 sail (CR-S)", "Al/PEN/Cr sail (ACS3)", "Hybrid, fixed SEP (0 deg)", "Hybrid, +/-30 deg gimbal (CR-H)",
              "Hybrid, free SEP pointing", "Hybrid, small SEP (0.25 a_c, +/-30 deg)"):
        c = cfg[k]
        rows.append([k, f1(c["nogo_half_angle_deg_tau0"]), f1(c["nogo_half_angle_deg_tau5pct"]), f2(c["sunward_capability_over_ac"]),
                     f2(c["perp_capability_over_ac"])])
    story.append(table(rows, [2.3, 1.35, 1.05, 0.95, 0.95]))
    story.append(Paragraph("Table 8.1 - In-irons cones and directional capability (SEP sized as CR-H unless noted).", ST["cap"]))
    story.append(fig("q5_in_irons_fraction.png", "Figure 8.2 - Share of time the desired thrust direction is unreachable during "
                     "typical manoeuvres (useful acceleration below 5 % of a<sub>c</sub>)."))
    story.append(fig("q5_envelope_3d.png", "Figure 8.3 - 3-D reachable-acceleration sets: the sail bubble (blue) inside the CR-H "
                     "hybrid's reach surface (orange).", 5.4))
    story.append(callout("Answer to Q5", [
        f"<b>Sail:</b> a cone of {f1(cfg['Al/CP1 sail (CR-S)']['nogo_half_angle_deg_tau0'])} deg half-angle around the sunward direction "
        f"is unreachable for Al/CP1 ({f1(cfg['Al/PEN/Cr sail (ACS3)']['nogo_half_angle_deg_tau0'])} deg for ACS3's Al/PEN/Cr), and thrust is "
        f"below 5 % of a<sub>c</sub> out to {f1(cfg['Al/CP1 sail (CR-S)']['nogo_half_angle_deg_tau5pct'])} deg - "
        f"{100*op['Al/CP1 sail (CR-S)']['isotropic_SK']:.0f} % of all directions. Operationally the sail is in irons "
        f"{100*op['Al/CP1 sail (CR-S)']['orbit_raising']:.0f} % of the time when raising an Earth orbit, "
        f"{100*op['Al/CP1 sail (CR-S)']['DRO_jacobi']:.0f} % in a DRO, {100*op['Al/CP1 sail (CR-S)']['NRHO_jacobi']:.0f} % in an NRHO and "
        f"{100*op['Al/CP1 sail (CR-S)']['isotropic_SK']:.0f} % for arbitrary station-keeping corrections. <b>Hybrid:</b> no in-irons region "
        f"at all. Even a fixed (ungimballed) SEP gives {f2(cfg['Hybrid, fixed SEP (0 deg)']['sunward_capability_over_ac'])} a<sub>c</sub> "
        f"sunward; CR-H's +/-30 deg gimbal gives {f2(cfg['Hybrid, +/-30 deg gimbal (CR-H)']['sunward_capability_over_ac'])} a<sub>c</sub>."]))

    # ------------------------------------------------------------------ Q6
    story += [CondPageBreak(3.3 * inch), H1("9. Q6 - Field of view: fixed camera, antenna and arrays, with and without a gimballed bus")]
    story.append(P_("A sailcraft's attitude belongs to its propulsion: the sail normal follows the steering law. A body-fixed "
                    "instrument therefore points wherever the thrust demand puts it. We simulated four months of operations in a "
                    "70,000 km DRO and the 9:2 NRHO, with sail attitudes from the locally optimal law for (a) random manoeuvre "
                    "demands updated every 12 h and (b) energy-change steering, and counted how often each target is inside the "
                    "instrument field. Free roll about the sail normal is assumed (the sail force does not depend on roll), and "
                    "the membrane blocks +/-5 deg about its plane."))
    story.append(fig("q6_target_angles.png", "Figure 9.1 - Distribution of the angle between targets and the sail normal: "
                     "propulsion-driven attitude spreads Earth, the lunar south pole and SDA targets across the sky."))
    story.append(fig("q6_fov_access.png", "Figure 9.2 - Share of time each target is in view and mean solar-array power for fixed "
                     "and gimballed buses (DRO, manoeuvre demand)."))
    rows = [["Case"] + [c.replace("Fixed, boresight on sail normal", "Fixed").replace("Fixed, best tilt (design-time)", "Fixed, best tilt") for c in
                        ["Fixed, boresight on sail normal", "Fixed, best tilt (design-time)", "Gimbal +/-30 deg", "Gimbal +/-60 deg", "Gimbal +/-90 deg (hemisphere)"]]]
    for case in q6["access"]:
        a = q6["access"][case]
        for tg in ("Earth (HGA, 10 deg beam)", "Lunar south pole (camera, 10 deg)", "SDA field, anti-Sun hemisphere (camera, 15 deg)",
                   "Solar array power (fraction of max)"):
            rows.append([f"{case}: {tg.split(' (')[0]}"] + [f"{100*a[tg][c]:.0f} %" for c in
                        ["Fixed, boresight on sail normal", "Fixed, best tilt (design-time)", "Gimbal +/-30 deg", "Gimbal +/-60 deg", "Gimbal +/-90 deg (hemisphere)"]])
    story.append(table(rows, [2.6, 0.75, 0.8, 0.8, 0.8, 0.85], font=8.2))
    story.append(Paragraph("Table 9.1 - Access fractions for all simulated cases.", ST["cap"]))
    story.append(fig("q6_fov_schematic_3d.png", "Figure 9.3 - Fixed instrument field (violet) vs field of regard of a +/-60 deg two-axis "
                     "gimballed bus (orange).", 4.6))
    story.append(callout("Answer to Q6", [
        f"<b>Fixed bus:</b> a 10 deg antenna or camera on the sail normal sees Earth {100*acc['Earth (HGA, 10 deg beam)']['Fixed, boresight on sail normal']:.0f} % "
        f"and the lunar south pole {100*acc['Lunar south pole (camera, 10 deg)']['Fixed, boresight on sail normal']:.0f} % of the time; the best "
        f"design-time tilt raises this to {100*acc['Earth (HGA, 10 deg beam)']['Fixed, best tilt (design-time)']:.0f} %/"
        f"{100*acc['Lunar south pole (camera, 10 deg)']['Fixed, best tilt (design-time)']:.0f} %. Fixed arrays average "
        f"{100*acc['Solar array power (fraction of max)']['Fixed, boresight on sail normal']:.0f} % of peak power (zero when feathered). "
        f"<b>Gimballed bus:</b> +/-30 deg recovers {100*acc['Solar array power (fraction of max)']['Gimbal +/-30 deg']:.0f} % power; +/-60 deg gives "
        f"{100*acc['Earth (HGA, 10 deg beam)']['Gimbal +/-60 deg']:.0f} %/{100*acc['Lunar south pole (camera, 10 deg)']['Gimbal +/-60 deg']:.0f} % "
        f"access and {100*acc['SDA field, anti-Sun hemisphere (camera, 15 deg)']['Gimbal +/-60 deg']:.0f} % for anti-Sun SDA fields. The sail itself caps "
        "any single-face instrument at ~50 %: carry antennas on both faces, or schedule pointing windows into the steering plan."]))

    # ------------------------------------------------------------------ Q7
    story += [CondPageBreak(3.3 * inch), H1("10. Q7 - Manoeuvrability and acceleration of the hybrid approach")]
    story.append(fig("q7_acceleration_envelope.png", "Figure 10.1 - Maximum acceleration along a commanded direction for CR-S, CR-H "
                     "and the far-term CR-A."))
    rows = [["Design", "Away from Sun", "Perpendicular", "Toward Sun", "Isotropic mean", "dv per year, mean direction (km/s)"]]
    ann = q7["annual_dv_km_s"]
    for k in ("CR-S", "CR-H", "CR-A"):
        e = env[k]
        dvy = e["isotropic_mean"] * 1e-3 * 31557600 / 1e3
        rows.append([k, f3(e["away_from_sun"]), f3(e["perpendicular"]), f3(e["toward_sun"]), f3(e["isotropic_mean"]), f1(dvy)])
    story.append(table(rows, [1.0, 1.0, 1.0, 1.0, 1.0, 1.6]))
    story.append(Paragraph(f"Table 10.1 - Directional acceleration capability (mm/s<super>2</super>). CR-H's SEP is propellant-limited to "
                           f"{f2(ann['CR-H SEP propellant-limited total'])} km/s in total with 6 kg; the sail part is unlimited.", ST["cap"]))
    story.append(fig("q7_reachable_2d.png", "Figure 10.2 - Positions reachable from a 70,000 km DRO after 3 (grey) and 7 days (colour) "
                     "with constant-direction steering commands, relative to the unpowered trajectory."))
    story.append(fig("q7_reachable_3d.png", "Figure 10.3 - 3-D view of the 7-day reachable sets.", 5.4))
    rr = q7["response_days"]
    story += bullets([
        f"<b>Reach:</b> in 3 days the hybrid can displace {f0(rs['CR-H hybrid']['3']['max_disp_km'])} km, including "
        f"{f0(rs['CR-H hybrid']['3']['max_sunward_km'])} km toward the Sun, where the sail manages {f0(rs['CR-S sail']['3']['max_sunward_km'])} km; "
        f"after 7 days {f0(rs['CR-H hybrid']['7']['max_disp_km'])} vs {f0(rs['CR-S sail']['7']['max_disp_km'])} km.",
        f"<b>Response:</b> a 10 m/s manoeuvre takes {f2(rr['CR-S']['10_at_0'])} d (away from Sun) to {f2(rr['CR-S']['10_at_90'])} d "
        f"(perpendicular) with the sail and is impossible toward the Sun; the hybrid needs {f2(rr['CR-H']['10_at_0'])}-{f2(rr['CR-H']['10_at_180'])} d "
        "in any direction.",
        f"<b>Mass:</b> the 1,653 m<super>2</super> sail system weighs ~{f0(q7['mass_trade']['notes']['sail_system_kg'])} kg, so a sail pays "
        f"for itself against SEP-only only after ~{f1(q7['mass_trade']['notes']['sail_beats_sep_above_km_s'])} km/s (sail-only) or "
        f"~{f1(q7['mass_trade']['notes']['hybrid_beats_sep_above_km_s'])} km/s (hybrid) of cumulative manoeuvring - i.e. for long, "
        "manoeuvre-intensive constellation missions, exactly the Cattle Run use case.",
    ])
    story.append(fig("q7_response_time.png", "Figure 10.4 - Days to deliver 10 and 50 m/s vs manoeuvre direction."))
    story.append(fig("q7_mass_trade.png", "Figure 10.5 - Initial mass vs cumulative manoeuvre delta-v for SEP-only, hybrid and sail-only."))
    story.append(callout("Answer to Q7", [
        f"<b>The hybrid is omnidirectional and roughly 2-4x as agile as the sail:</b> {f3(env['CR-H']['toward_sun'])}-{f3(env['CR-H']['away_from_sun'])} "
        f"mm/s<super>2</super> in every direction ({f3(env['CR-H']['isotropic_mean'])} on average vs {f3(env['CR-S']['isotropic_mean'])} for the sail), "
        f"twice the 7-day reach and no stall toward the Sun. The SEP should be used tactically (in-irons gaps, rapid response, "
        "station-keeping precision) while the sail provides the bulk delta-v; with this split the 6 kg propellant load lasts for years."]))

    # ------------------------------------------------------------------ Q8
    story += [CondPageBreak(3.3 * inch), H1("11. Q8 - Lowest acceptable orbit for the below-GEO demonstrator")]
    story.append(P_("The demonstrator must show sufficient acceleration, accurate control and autonomous GNC. Below a certain "
                    "altitude atmospheric drag swamps sunlight pressure, so orbit raising becomes impossible whatever the sail "
                    "size: both forces scale with area/mass, and the criterion depends only on density (Mengali & Quarta):"))
    story += eq("eq_drag", 5.0)
    story.append(fig("q8_drag_vs_srp.png", "Figure 11.1 - Drag-to-sail-thrust ratio vs altitude for solar minimum, moderate and "
                     "maximum activity (NRLMSIS 2.x)."))
    story.append(fig("q8_sma_rate_vs_altitude.png", "Figure 11.2 - Simulated 30-day net semi-major-axis change for CR-S in three orbit "
                     "types (dots: break-even altitude)."))
    envt = {e["alt_km"]: e for e in q8["environment"]}
    rows = [["Criterion", "Solar min (F10.7 70)", "Moderate (150)", "Solar max (230)"],
            ["Max drag = max thrust, orbit mean (km)"] + [f0(q8["f_criterion"][k]["h_mean"]) for k in q8["f_criterion"]],
            ["Max drag = max thrust, day side (km)"] + [f0(q8["f_criterion"][k]["h_dayside"]) for k in q8["f_criterion"]],
            ["Simulated break-even: noon-midnight / dawn-dusk / 28.5 deg (km)"] +
            [f"{f0(be[k]['SSO noon-midnight'])} / {f0(be[k]['SSO dawn-dusk'])} / {f0(be[k]['28.5 deg inclined'])}" for k in be],
            ["Drag &lt;= 25 % of raising rate: noon-midnight / dawn-dusk / 28.5 deg (km)"] +
            [f"{f0(mg[k]['SSO noon-midnight'])} / {f0(mg[k]['SSO dawn-dusk'])} / {f0(mg[k]['28.5 deg inclined'])}" for k in mg]]
    story.append(table(rows, [2.9, 1.25, 1.2, 1.25]))
    story.append(Spacer(1, 6))
    rows = [["Altitude (km)", "Eclipse (beta 0)", "AO fluence /cm<super>2</super>/yr (moderate)", "AO fluence (solar max)",
             "Passive decay, CR-S deployed", "Passive decay, ACS3"]]
    for h in (550, 700, 800, 900, 1000):
        e = envt[h]
        dcy = q8["decay_years"][str(h)]
        rows.append([f"{h}", f"{100*e['eclipse_frac_beta0']:.0f} %", f"{e['AO_fluence_mod']:.1e}", f"{e['AO_fluence_high']:.1e}",
                     f"{365.25*dcy['CR-S deployed (yr)']:.0f} d", f"{365.25*dcy['ACS3 deployed (yr)']:.0f} d"])
    story.append(table(rows, [0.9, 0.9, 1.4, 1.2, 1.15, 1.05]))
    story.append(Paragraph("Table 11.1/11.2 - Altitude criteria; environment and passive decay (sail deployed, 50 % average projected "
                           "area, F10.7 = 150) - a large sail is also an effective drag device for disposal.", ST["cap"]))
    gg = q8["gravity_gradient"]
    story.append(fig("q8_gravity_gradient.png", "Figure 11.3 - Gravity-gradient torque (worst-case attitude) vs the solar-torque trim "
                     "authority of a 10 cm centre-of-mass offset for ACS3 and the 1,653 m<super>2</super> CR-S sail."))
    story += bullets([
        f"Drag sets a hard floor at ~{f0(be['Moderate (F10.7=150)']['SSO dawn-dusk'])}-{f0(be['Moderate (F10.7=150)']['28.5 deg inclined'])} km for "
        f"moderate activity and ~{f0(be['Solar maximum (F10.7=230)']['SSO dawn-dusk'])}-{f0(be['Solar maximum (F10.7=230)']['28.5 deg inclined'])} km at solar "
        "maximum (2028 is the declining phase of Cycle 25; plan for F10.7 ~ 150 with excursions to 200+).",
        f"Atomic oxygen erodes exposed polyimide at ~3e-24 cm<super>3</super>/atom. For a ram-facing surface that is "
        f"~{envt[550]['AO_fluence_mod']*3e-20:.0f} um per year at 550 km (moderate activity) - more than the 2.5 um film - "
        f"{envt[700]['AO_fluence_mod']*3e-20:.1f} um at 700 km and {envt[1000]['AO_fluence_mod']*3e-20:.2f} um at 1,000 km. The aluminised "
        "face protects the front, but defects and the bare back face are attacked; LightSail 2 showed AO damage at ~720 km.",
        f"For a full-scale 1,653 m<super>2</super> sail, gravity-gradient torque exceeds the 10 cm CM-trim authority below "
        f"~{f0(gg['CR-S']['h_gg_equals_amt_km'])} km; a LEO demonstrator therefore needs GG-tolerant steering, magnetorquers and larger "
        f"wheels, or a smaller demonstration sail (ACS3-class sails are never GG-limited).",
        f"From a 550 km rideshare, CR-H can climb to 1,000 km with the sail stowed in {f0(q8['sep_climb_550_to_1000km']['moderate']['days'])} days "
        f"using {f1(q8['sep_climb_550_to_1000km']['moderate']['propellant_kg'])} kg of propellant - a strong argument for the hybrid "
        "(and for a retractable sail).",
    ])
    story.append(callout("Answer to Q8", [
        f"<b>Absolute floor (drag = sail thrust): ~650 km for moderate activity, ~750-800 km at solar maximum.</b> "
        f"<b>Lowest acceptable orbit for a convincing demonstration: ~1,000 km</b> (900 km in a dawn-dusk SSO), where drag costs "
        "less than 25 % of the raising rate even at solar maximum, atomic-oxygen fluence is ~400x lower than at 550 km and a "
        f"CR-S-class sail raises its orbit by ~{f0(q8['sma_sweep_CR-S']['Moderate (F10.7=150)']['SSO dawn-dusk']['rate_km_day'][10]*30)} km per month. "
        "Prefer a dawn-dusk SSO (no eclipses, ~20 % faster). If the demonstrator carries the full 1,653 m<super>2</super> sail, budget "
        "for gravity-gradient torques or fly at several thousand kilometres; otherwise demonstrate with a ~100-500 m<super>2</super> sail."]))

    # ------------------------------------------------------------------ design trades
    story += [CondPageBreak(3.3 * inch), H1("12. Design options and variables")]
    story.append(P_("The outline lists six design options and six variables. The simulator evaluates each; Table 12.1 "
                    "summarises the trades and Figures 12.1-12.3 show the supporting analyses."))
    rf = dt["reefing"]; rc = dt["rcd"]
    rows = [["Option / variable", "Benefit (quantified)", "Cost / risk", "Recommendation"],
            ["Conventional sail (CR-S)", "Propellant-free, unlimited delta-v (~1.5 km/s/yr mean-direction)",
             "In irons 7-28 % of the time; no sunward thrust; attitude slaved to thrust", "Baseline structure"],
            ["Hybrid sail + SEP", "No in-irons region; 2-4x agility; SEP climb from low rideshare",
             "+20 kg (18 %); propellant; plume/sail interaction", "<b>Adopt</b>"],
            ["Gimballed vs fixed SEP", f"Sunward capability {f2(cfg['Hybrid, +/-30 deg gimbal (CR-H)']['sunward_capability_over_ac'])} vs "
             f"{f2(cfg['Hybrid, fixed SEP (0 deg)']['sunward_capability_over_ac'])} a<sub>c</sub>; gimbal also trims CM (4e-3 N m)",
             "Gimbal mass ~30 % of thruster; plume limits ~+/-45 deg", "<b>Adopt +/-30 deg two-axis</b>"],
            ["Retractable / re-deployable sail", f"Throttle: {100*rf['reefable_sail']:.0f} % vs {100*rf['fixed_area_sail']:.0f} % of demands met "
             "exactly; drag avoidance; protection in belts/conjunctions", "+30 % deployer mass; mechanism wear; re-stow risk",
             "Mature on the ground; fly on demo"],
            ["Electrochromic films (RCD)", f"2 % area: {rc['pitch_2pct_at_0']:.1e} N m pitch/yaw, {rc['roll_2pct_at_17']:.1e} N m roll; continuous "
             "dumping; wheel-free roll", "Authority nulls near 60 deg incidence; durability; power", "Adopt for roll + fine trim"],
            ["Double- vs single-sided film", f"Efficiency {dt['efficiency']['Al/CP1/Al double-sided 2.5 um']:.3f} vs {dt['efficiency']['Al/CP1 2.5 um (NEA Scout, Solar Cruiser)']:.3f}; "
             "either face usable (no flip slews)", f"Runs ~{dt['thermal_peak_C']['Al/CP1/Al double-sided 2.5 um']-dt['thermal_peak_C']['Al/CP1 2.5 um (NEA Scout, Solar Cruiser)']:.0f} C hotter "
             f"({dt['thermal_peak_C']['Al/CP1/Al double-sided 2.5 um']:.0f} C)", "Single-sided CP1 (thermal margin)"],
            ["Rigid booms vs spin/yo-yo", f"Spin saves ~{dt['sail_system_mass_rigid']['SC']['total']-dt['sail_system_mass_spin']['SC']['total']:.0f} kg on a 1,653 m<super>2</super> sail",
             "Slow attitude changes (precession) - unsuitable for LEO raising (needs ~0.06 deg/s)", "Rigid booms (agility)"],
            ["Mass / size / material", "a<sub>c</sub> scales with A/m; 1 um film + 45 m booms reach 0.27 mm/s<super>2</super> (CR-A)",
             "Larger sails raise GG torques and inertia", "Grow a<sub>c</sub> for later blocks"],
            ["SEP thrust and Isp", "20 mN at 1,500 s gives 0.15 mm/s<super>2</super>; higher Isp stretches propellant",
             "Power (~350 W) and arrays", "Hall 15-25 mN class"],
            ["Gimbal range", "+/-30 deg: 94 % power; +/-60 deg: 2x instrument access", "Mass, harness, stiffness", "+/-30-60 deg"]]
    story.append(table(rows, [1.45, 2.15, 1.75, 1.25], font=8.4))
    story.append(Paragraph("Table 12.1 - Design option trade summary.", ST["cap"]))
    story.append(fig("dt_momentum_actuators.png", "Figure 12.1 - Propellant-free momentum-management torque for the 1,653 m<super>2</super> "
                     "sail: RCD panels (1/2/5 % of area) vs active mass translator and bus gimbal, against disturbance and Solar "
                     "Cruiser's roll requirement."))
    story.append(P_(f"A 5 cm offset between centre of mass and centre of pressure on CR-S accumulates "
                    f"{rc['momentum_per_day_5cm_Nms']:.0f} N m s per day - far beyond small-satellite wheels - so continuous trim by "
                    "mass shift (AMT or bus gimbal) is mandatory and RCDs are the natural roll actuator (Inness 2023; Heaton 2023)."))
    story.append(fig("dt_thermal_single_double.png", "Figure 12.2 - Membrane temperature vs incidence: a double-sided reflective film "
                     "cannot radiate from its back face and runs ~150 C hotter."))
    story.append(fig("dt_reefing.png", "Figure 12.3 - Share of arbitrary control demands met exactly: fixed-area sail, "
                     "retractable (reefable) sail, hybrid."))

    # ------------------------------------------------------------------ additional questions
    story += [CondPageBreak(3.3 * inch), H1("13. Additional questions that should be addressed")]
    story.append(P_("The outline asks to identify further questions. The analyses surfaced the following, roughly in priority "
                    "order for the proposal:"))
    story.append(table([
        ["#", "Question", "Why it matters / first evidence"],
        ["A", "How long do the film and coatings survive at the demo altitude and through the radiation belts?",
         "AO fluence drops ~400x from 550 to 1,000 km; spiral-out crosses the inner belt for months; LightSail 2 degradation"],
        ["B", "What collision and conjunction risk does a 1,653 m<super>2</super> sail carry at ~1,000 km, and how is it screened?",
         "Large area-to-mass objects; continuous-thrust ephemeris uncertainty (ACS3 provides predictive ephemerides to CARA)"],
        ["C", "How is orbit determination done with continuous, attitude-dependent SRP?",
         "Force/torque model calibration from flight data (Diedrich 2023); GPS in LEO, optical/radiometric in cislunar space"],
        ["D", "What autonomy architecture guarantees safe feathering, momentum management and fault recovery?",
         "Locally optimal laws are cheap on board; certification of autonomous GNC is a DARPA objective"],
        ["E", "Can the attitude system handle LEO gravity-gradient and aerodynamic torques for a large sail?",
         "GG exceeds 10 cm CM-trim authority below ~3,150 km for 1,653 m<super>2</super>"],
        ["F", "How do sail billow, wrinkles and boom thermal deflection change force and torque?",
         "NEA Scout and LightSail 2 boom/sail deformation; RCD authority depends on incidence"],
        ["G", "Can the sail and booms survive lunar and Earth eclipses (thermal snap, contraction loads)?",
         "NEA Scout booms were not designed for lunar-eclipse contraction loads"],
        ["H", "How should a constellation be deployed and phased from one launch?",
         "Sail phasing in DRO/NRHO takes weeks; L4/L5 slots take 2-3 months (Section 6)"],
        ["I", "Where do antennas go when the sail blocks half the sky?", "Single-face instruments are capped near 50 % access (Section 9)"],
        ["J", "Does SEP plume impingement contaminate the film, and what gimbal limits follow?", "Constrains hybrid gimbal range"],
        ["K", "What is the station-keeping cost in the full ephemeris model with solar gravity and eclipses?",
         "CR3BP results here; BCR4BP option is implemented for follow-on runs"],
        ["L", "How is end of life handled?", "Sail as drag device in LEO (decay &lt; 1 yr below 1,000 km); heliocentric escape from cislunar space"],
    ], [0.3, 3.0, 3.3]))

    # ------------------------------------------------------------------ recommendations / next steps
    story += [H1("14. Recommended concept and next steps")]
    story += bullets([
        "<b>Architecture:</b> hybrid sailcraft (CR-H class): Solar Cruiser-heritage 1,653 m<super>2</super> single-sided CP1 sail on rigid "
        "booms, RCD panels for roll, two-axis gimballed bus (+/-30-60 deg) carrying a 15-25 mN Hall thruster, arrays and instruments; "
        "antennas on both faces.",
        "<b>Demonstrator (Phase 1):</b> ~1,000 km dawn-dusk SSO, or a 550 km rideshare plus an 18-day SEP climb with the sail stowed. "
        "Success criteria: measured a<sub>c</sub> within 10 % of prediction, net raising of ~5-7 km/day, autonomous steering and "
        "momentum management without magnetorquers for a defined period, safe feathering demonstrations.",
        "<b>Cislunar operations (Phase 2):</b> launch toward the lunar plane (28.5 deg) to GTO/GEO or TLI; slots in DRO, NRHO and "
        "L1/L2 halos with L4/L5 sentinels; polar coverage by paired NRHO spacecraft instead of a pole-sitter.",
        "<b>Simulator next steps:</b> trajectory optimisation (collocation) for the Q3 legs, full ephemeris and BCR4BP station-keeping "
        "with a sail-aware controller, slew-rate-limited attitude dynamics with RCD/AMT actuators, sail shape uncertainty, and "
        "GPU-scale Monte Carlo of autonomy fault cases.",
    ])

    # ------------------------------------------------------------------ assumptions
    story += [H1("15. Assumptions and limitations")]
    story += bullets([
        "Flat sail with nominal optical properties; no degradation, billow or wrinkle losses (real performance typically 5-15 % lower).",
        "Attitude changes are instantaneous (no slew-rate or momentum limits) in trajectory runs; agility is treated separately.",
        "Orbit-averaged Earth-orbit dynamics omit lunisolar perturbations (0.1 % error after 60 days in raised GTO; larger near lunar distance).",
        "Cislunar dynamics use the circular restricted three-body problem with a rotating Sun line in the Earth-Moon plane; "
        "transfer times are energy-change plus natural-coast estimates, not optimised trajectories (expect +/-30 %).",
        "Drag uses NRLMSIS 2.x equatorial densities with local-time variation, C<sub>D</sub> = 2.2 on projected area and a 1 % "
        "minimum (edge-on) area; latitude and seasonal variations are averaged out.",
        "Mass models are calibrated on ACS3 and Solar Cruiser data; SEP sizing follows Ceriotti & McInnes (25 kg/kW, 70 W/kg arrays).",
        "Field-of-view results assume free roll about the sail normal and simple membrane obstruction.",
    ])

    # ------------------------------------------------------------------ references
    story += [H1("References")]
    refs = [
        "DARPA Special Notice DARPA-SN-27-03, Cattle Run Proposers Day, Amendment 01 (2026).",
        "C. R. McInnes, <i>Solar Sailing: Technology, Dynamics and Mission Applications</i>, Springer-Praxis, 1999.",
        "B. Dachwald et al. / M. Macdonald (ed.), <i>Advances in Solar Sailing</i>, Springer, 2014; G. Vulpetti, <i>Fast Solar Sailing</i>, Springer, 2013.",
        "J. Heiligers, S. Hiddink, R. Noomen, C. R. McInnes, 'Solar sail Lyapunov and halo orbits in the Earth-Moon three-body problem', Acta Astronautica, 2015.",
        "M. T. Ozimek, D. J. Grebow, K. C. Howell, 'Solar sails and lunar south pole coverage', AIAA/AAS, 2008; 'A collocation approach for computing solar sail lunar pole-sitter orbits', Open Aerospace Eng. J., 2010.",
        "D. J. Grebow, M. T. Ozimek, K. C. Howell, 'Design of optimal low-thrust lunar pole-sitter missions', AAS 09-148; 'Advanced modeling of optimal low-thrust lunar pole-sitter trajectories', Acta Astronautica 67, 2010.",
        "G. G. Wawrzyniak, K. C. Howell, 'Accessing the design space for solar sails in the Earth-Moon system', AAS 09-348, 2009.",
        "M. Ceriotti, C. R. McInnes, 'Systems design of a hybrid sail pole-sitter', Adv. Space Res. 48, 2011; Ceriotti & McInnes, 'Hybrid solar sail and SEP for novel Earth observation missions', IAC-10, 2010.",
        "J. Heiligers, M. Ceriotti, C. R. McInnes, J. D. Biggs, 'Mission analysis and systems design of a near-term and far-term pole-sitter mission', Acta Astronautica 94, 2014.",
        "R. M. Ewart, E. Plotke, P. C. Lai, 'Pole-sitter based space domain awareness for cislunar objects', J. Astronaut. Sci. 71, 2024; J. L. West, 'The lunar polesitter', AIAA 2008-2537.",
        "W. K. Wilkie, J. Fernandez, 'Advanced Composite Solar Sail System (ACS3) mission update', ISSS 2023; A. Dono et al., 'ACS3 flight dynamics', ISSS 2023.",
        "L. Johnson et al., 'Near Earth Asteroid Scout - mission update', SSC22-IX-01, 2022; A. Sobey, T. Lockett, NEA Scout deployer, AMS 2016; NASA TechPort project 14656.",
        "B. Betts et al., 'LightSail 2 image-based engineering assessment', ISSS 2023; Gama, 'GAMA-Beta solar sail in-orbit demonstration', ISSS 2023.",
        "Z. McConnel (Redwire), 'Test of a full-scale quadrant for the 1,653 m<super>2</super> Solar Cruiser sail'; K. Maddox (NeXolve), 'Flight-like Solar Cruiser sail quadrant', ISSS 2023.",
        "A. Heaton et al., 'Reflectivity control device roll momentum management for Solar Cruiser'; J. Inness, 'Momentum management strategies for Solar Cruiser'; B. Diedrich, 'Solar sail torque model characterization for NEA Scout'; R. Caverly, 'CABLESSail', ISSS 2023.",
        "P. Seefeldt et al., 'Highly efficient membrane-based photovoltaic array for solar sailing', ISSS 2023; DLR, 'Modular boom deployment mechanism for deployment and retraction of up to four CTMs', ISSS 2023.",
        "G. Mengali, A. A. Quarta, 'Near-optimal solar-sail orbit-raising from low Earth orbit', J. Spacecraft & Rockets 42(5), 2005.",
        "JHU/APL, <i>Cislunar Security National Technical Vision</i>, 2022; M. Holzinger et al., <i>A Primer on Cislunar Space</i>, AFRL 2021-1271; C. Guidi et al., cislunar master planning, 2022; A. Bukley, C. Stover, 'Moonstruck!', Aerospace CSPS, 2024.",
        "NRLMSIS 2.x empirical atmosphere model (pymsis); O. Montenbruck, E. Gill, <i>Satellite Orbits</i>, Springer, 2000 (Harris-Priester table).",
    ]
    for i, r in enumerate(refs, 1):
        story.append(Paragraph(f"[{i}] {r}", ParagraphStyle("ref", parent=ST["small"], leftIndent=16, firstLineIndent=-16, spaceAfter=3)))

    # ------------------------------------------------------------------ appendix
    story += [CondPageBreak(3.3 * inch), H1("Appendix A - Reproducing the results")]
    story.append(P_("All numbers and figures in this report are produced by the code in <font face='Carlito-Bold'>simulator/</font>:"))
    story.append(table([
        ["Command", "Effect"],
        ["pip install numpy scipy matplotlib pymsis  (torch optional)", "Dependencies; torch enables the GPU backend"],
        ["python simulator/run_all.py", "Runs Q1-Q8 and the design trades; writes results/*.json and figures/*.png (~10-15 min on 4 CPU cores)"],
        ["CISLUNAR_BACKEND=torch python simulator/run_all.py", "Same with PyTorch tensors (CUDA when available)"],
        ["python simulator/run_all.py q3_cislunar_transfers", "Re-run a single analysis"],
        ["python reports/build_report.py", "Rebuild this PDF from results and figures"],
        ["node reports/build_deck.js", "Rebuild the companion PowerPoint briefing"],
    ], [2.9, 3.7]))
    story.append(Spacer(1, 8))
    story.append(H2("A.1 Key equations"))
    story += eq("eq_sep", 4.2) + eq("eq_gg", 5.0)
    story.append(P_("SEP power uses efficiency eta = 0.55 (thruster and PPU); the gravity-gradient torque uses the worst-case "
                    "attitude (theta = 45 deg) and the difference between the sail's normal and in-plane moments of inertia from "
                    "the mass model (membrane plus diagonal booms)."))

    doc = Doc(OUT)
    doc.multiBuild(story)
    return OUT


if __name__ == "__main__":
    print(build())
