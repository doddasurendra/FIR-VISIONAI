"""
FIR VisionAI — PDF Guide Generator
Uses ReportLab 5.x to convert the Markdown architecture guide into a professional PDF.
Run: python docs/generate_guide_pdf.py
Output: docs/FIR_VisionAI_Complete_Architecture_and_Step_by_Step_Guide.pdf
"""
import os
import re
import sys

# ─── ReportLab imports ──────────────────────────────────────────────────────
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether
)
from reportlab.platypus.flowables import HRFlowable
from reportlab.lib.colors import HexColor, white, black

# ─── Paths ───────────────────────────────────────────────────────────────────
DOCS_DIR = os.path.dirname(os.path.abspath(__file__))
MD_PATH = os.path.join(DOCS_DIR, "FIR_VisionAI_Architecture_Guide.md")
PDF_PATH = os.path.join(DOCS_DIR, "FIR_VisionAI_Complete_Architecture_and_Step_by_Step_Guide.pdf")

# ─── Brand colours ────────────────────────────────────────────────────────────
GOV_GREEN = HexColor("#0f5132")   # AP Excise department green
GOV_GOLD  = HexColor("#b8960c")   # Government gold accent
DARK_SLATE = HexColor("#1e293b")  # Text primary
MID_GREY  = HexColor("#64748b")   # Text secondary
LIGHT_BG  = HexColor("#f0fdf4")   # Light green background
TABLE_HDR = HexColor("#1e4d2b")   # Table header dark green
TABLE_ALT = HexColor("#f8fafc")   # Alternating table row
BORDER_CLR = HexColor("#cbd5e1")  # Border colour
CODE_BG   = HexColor("#1e293b")   # Code block background
CODE_TEXT = HexColor("#e2e8f0")   # Code block text

# ─── Page dimensions ─────────────────────────────────────────────────────────
PAGE_W, PAGE_H = A4
MARGIN_L = 2.0 * cm
MARGIN_R = 2.0 * cm
MARGIN_T = 2.2 * cm
MARGIN_B = 2.2 * cm
CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R


def make_styles():
    """Return a dict of ReportLab ParagraphStyles."""
    base = getSampleStyleSheet()

    styles = {}

    styles["title"] = ParagraphStyle(
        "title",
        fontName="Helvetica-Bold",
        fontSize=26,
        textColor=GOV_GREEN,
        alignment=TA_CENTER,
        spaceAfter=6,
        leading=32,
    )
    styles["subtitle"] = ParagraphStyle(
        "subtitle",
        fontName="Helvetica",
        fontSize=12,
        textColor=MID_GREY,
        alignment=TA_CENTER,
        spaceAfter=4,
        leading=16,
    )
    styles["dept"] = ParagraphStyle(
        "dept",
        fontName="Helvetica-Bold",
        fontSize=11,
        textColor=GOV_GOLD,
        alignment=TA_CENTER,
        spaceAfter=3,
    )
    styles["h1"] = ParagraphStyle(
        "h1",
        fontName="Helvetica-Bold",
        fontSize=15,
        textColor=white,
        alignment=TA_LEFT,
        spaceBefore=14,
        spaceAfter=6,
        leading=20,
        backColor=GOV_GREEN,
        leftIndent=-0.3*cm,
        rightIndent=-0.3*cm,
        borderPad=5,
    )
    styles["h2"] = ParagraphStyle(
        "h2",
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=GOV_GREEN,
        alignment=TA_LEFT,
        spaceBefore=10,
        spaceAfter=4,
        leading=16,
        borderPad=2,
    )
    styles["h3"] = ParagraphStyle(
        "h3",
        fontName="Helvetica-Bold",
        fontSize=10.5,
        textColor=DARK_SLATE,
        alignment=TA_LEFT,
        spaceBefore=8,
        spaceAfter=3,
        leading=14,
    )
    styles["h4"] = ParagraphStyle(
        "h4",
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=MID_GREY,
        alignment=TA_LEFT,
        spaceBefore=6,
        spaceAfter=2,
        leading=13,
    )
    styles["body"] = ParagraphStyle(
        "body",
        fontName="Helvetica",
        fontSize=9.5,
        textColor=DARK_SLATE,
        alignment=TA_JUSTIFY,
        spaceBefore=2,
        spaceAfter=3,
        leading=14,
    )
    styles["bullet"] = ParagraphStyle(
        "bullet",
        fontName="Helvetica",
        fontSize=9,
        textColor=DARK_SLATE,
        alignment=TA_LEFT,
        spaceBefore=1,
        spaceAfter=1,
        leading=13,
        leftIndent=12,
        bulletIndent=0,
        bulletText="•",
    )
    styles["code"] = ParagraphStyle(
        "code",
        fontName="Courier",
        fontSize=7.5,
        textColor=CODE_TEXT,
        alignment=TA_LEFT,
        spaceBefore=2,
        spaceAfter=2,
        leading=11,
        backColor=CODE_BG,
        leftIndent=5,
        rightIndent=5,
        borderPad=4,
    )
    styles["caption"] = ParagraphStyle(
        "caption",
        fontName="Helvetica-Oblique",
        fontSize=8,
        textColor=MID_GREY,
        alignment=TA_CENTER,
        spaceBefore=1,
        spaceAfter=5,
    )
    styles["toc_title"] = ParagraphStyle(
        "toc_title",
        fontName="Helvetica-Bold",
        fontSize=14,
        textColor=GOV_GREEN,
        alignment=TA_CENTER,
        spaceBefore=8,
        spaceAfter=10,
    )
    styles["toc_entry"] = ParagraphStyle(
        "toc_entry",
        fontName="Helvetica",
        fontSize=10,
        textColor=DARK_SLATE,
        spaceBefore=3,
        spaceAfter=3,
        leading=14,
    )
    styles["warning"] = ParagraphStyle(
        "warning",
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=HexColor("#7c2d12"),
        alignment=TA_LEFT,
        spaceBefore=3,
        spaceAfter=3,
        leading=13,
        backColor=HexColor("#fef3c7"),
        leftIndent=5,
        borderPad=4,
    )
    styles["note"] = ParagraphStyle(
        "note",
        fontName="Helvetica-Oblique",
        fontSize=8.5,
        textColor=HexColor("#1e3a5f"),
        alignment=TA_LEFT,
        spaceBefore=2,
        spaceAfter=2,
        leading=13,
        backColor=HexColor("#eff6ff"),
        leftIndent=5,
        borderPad=4,
    )
    return styles


def header_footer(canvas, doc):
    """Draw running header and footer on every page."""
    canvas.saveState()

    # Header bar
    canvas.setFillColor(GOV_GREEN)
    canvas.rect(0, PAGE_H - 1.5*cm, PAGE_W, 1.5*cm, fill=1, stroke=0)

    canvas.setFont("Helvetica-Bold", 9)
    canvas.setFillColor(white)
    canvas.drawString(MARGIN_L, PAGE_H - 1.0*cm, "FIR VisionAI — Complete Architecture & User Guide")
    canvas.drawRightString(PAGE_W - MARGIN_R, PAGE_H - 1.0*cm,
                           "AP Prohibition & Excise Department | OFFICIAL")

    # Footer bar
    canvas.setFillColor(GOV_GREEN)
    canvas.rect(0, 0, PAGE_W, 1.2*cm, fill=1, stroke=0)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(white)
    canvas.drawString(MARGIN_L, 0.45*cm, "CONFIDENTIAL — For Authorised Officers Only")
    canvas.drawCentredString(PAGE_W / 2, 0.45*cm, f"Page {doc.page}")
    canvas.drawRightString(PAGE_W - MARGIN_R, 0.45*cm, "FIR Sahayak u-FIR v2.0")

    canvas.restoreState()


def first_page(canvas, doc):
    """Cover page — no header/footer."""
    canvas.saveState()

    # Full-page background
    canvas.setFillColor(GOV_GREEN)
    canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

    # White content area
    canvas.setFillColor(white)
    canvas.roundRect(MARGIN_L * 0.8, MARGIN_B * 0.8,
                     PAGE_W - MARGIN_L * 1.6, PAGE_H - MARGIN_B * 1.6,
                     radius=10, fill=1, stroke=0)

    # Gold accent strip at top of white area
    canvas.setFillColor(GOV_GOLD)
    canvas.rect(MARGIN_L * 0.8, PAGE_H - MARGIN_T * 0.8 - 0.8*cm,
                PAGE_W - MARGIN_L * 1.6, 0.8*cm, fill=1, stroke=0)

    # AP Emblem placeholder circle
    canvas.setFillColor(GOV_GREEN)
    canvas.circle(PAGE_W / 2, PAGE_H * 0.72, 1.4*cm, fill=1, stroke=0)
    canvas.setFillColor(GOV_GOLD)
    canvas.circle(PAGE_W / 2, PAGE_H * 0.72, 1.1*cm, fill=0, stroke=1)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.setFillColor(white)
    canvas.drawCentredString(PAGE_W / 2, PAGE_H * 0.72 - 0.12*cm, "AP")

    # Title
    canvas.setFont("Helvetica-Bold", 22)
    canvas.setFillColor(GOV_GREEN)
    canvas.drawCentredString(PAGE_W / 2, PAGE_H * 0.62, "FIR VisionAI")
    canvas.setFont("Helvetica-Bold", 15)
    canvas.drawCentredString(PAGE_W / 2, PAGE_H * 0.57, "Complete System Architecture")
    canvas.drawCentredString(PAGE_W / 2, PAGE_H * 0.53, "& Step-by-Step User Guide")

    # Divider line
    canvas.setStrokeColor(GOV_GOLD)
    canvas.setLineWidth(1.5)
    canvas.line(MARGIN_L * 2, PAGE_H * 0.50, PAGE_W - MARGIN_L * 2, PAGE_H * 0.50)

    # Subtitle
    canvas.setFont("Helvetica", 10)
    canvas.setFillColor(MID_GREY)
    canvas.drawCentredString(PAGE_W / 2, PAGE_H * 0.46,
                             "Andhra Pradesh Prohibition & Excise Department")
    canvas.drawCentredString(PAGE_W / 2, PAGE_H * 0.43, "FIR Sahayak u-FIR v2.0")

    # Metadata box
    canvas.setFillColor(LIGHT_BG)
    canvas.roundRect(MARGIN_L * 2, PAGE_H * 0.24, PAGE_W - MARGIN_L * 4,
                     0.16 * PAGE_H, radius=5, fill=1, stroke=0)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.setFillColor(DARK_SLATE)
    canvas.drawCentredString(PAGE_W / 2, PAGE_H * 0.37, "Document Version: 2.0   |   October 2026")
    canvas.setFont("Helvetica", 8.5)
    canvas.setFillColor(MID_GREY)
    canvas.drawCentredString(PAGE_W / 2, PAGE_H * 0.34,
                             "Classification: OFFICIAL — For Authorised Officers Only")
    canvas.drawCentredString(PAGE_W / 2, PAGE_H * 0.31,
                             "Repository: github.com/doddasurendra/fir-sahayak")
    canvas.drawCentredString(PAGE_W / 2, PAGE_H * 0.28,
                             "Generated from verified source code inspection")

    # Bottom warning
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(HexColor("#7c2d12"))
    canvas.drawCentredString(PAGE_W / 2, PAGE_H * 0.18,
                             "WARNING: This document contains operational system information.")
    canvas.drawCentredString(PAGE_W / 2, PAGE_H * 0.15,
                             "Handle in accordance with departmental data security protocols.")

    canvas.restoreState()


def build_table(data, col_widths=None, header_row=True):
    """Build a styled ReportLab Table from a list-of-lists."""
    if not data:
        return None

    if col_widths is None:
        cols = len(data[0])
        col_widths = [CONTENT_W / cols] * cols

    tbl = Table(data, colWidths=col_widths, repeatRows=1 if header_row else 0)

    style_cmds = [
        # Header
        ("BACKGROUND", (0, 0), (-1, 0), TABLE_HDR),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8.5),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        # Body rows
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("ALIGN", (0, 1), (-1, -1), "LEFT"),
        ("TOPPADDING", (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        # Borders
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER_CLR),
        ("BOX", (0, 0), (-1, -1), 1, GOV_GREEN),
        # Alternating rows
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, TABLE_ALT]),
    ]
    tbl.setStyle(TableStyle(style_cmds))
    return tbl


def parse_and_build(md_text, styles):
    """
    Parse Markdown text into a list of ReportLab flowables.
    Handles: H1-H4, bullet lists, code blocks, horizontal rules,
    table pipes, blockquotes, bold/italic inline, normal paragraphs.
    """
    flowables = []
    lines = md_text.split("\n")
    i = 0
    in_code_block = False
    code_lines = []
    table_rows = []
    in_table = False

    def flush_table():
        nonlocal table_rows, in_table
        if not table_rows:
            in_table = False
            return
        # Filter out separator rows (---|---) and blank rows
        data_rows = []
        for row in table_rows:
            cells = [c.strip() for c in row.strip("|").split("|")]
            if all(re.match(r"^[-: ]+$", c) for c in cells if c):
                continue
            data_rows.append(cells)
        if not data_rows:
            table_rows = []
            in_table = False
            return
        # Normalise column count
        n_cols = max(len(r) for r in data_rows)
        normalised = []
        for row in data_rows:
            padded = row + [""] * (n_cols - len(row))
            normalised.append([safe_para(c, styles["body"]) for c in padded])
        col_w = CONTENT_W / n_cols
        tbl = build_table(normalised, [col_w] * n_cols, header_row=True)
        if tbl:
            flowables.append(Spacer(1, 4))
            flowables.append(tbl)
            flowables.append(Spacer(1, 6))
        table_rows = []
        in_table = False

    def safe_para(text, style):
        """Convert markdown inline formatting to ReportLab XML and return Paragraph."""
        # Escape XML special chars
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        # Bold-italic
        text = re.sub(r"\*\*\*(.*?)\*\*\*", r"<b><i>\1</i></b>", text)
        # Bold
        text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
        # Italic
        text = re.sub(r"\*(.*?)\*", r"<i>\1</i>", text)
        # Inline code
        text = re.sub(r"`([^`]+)`", r"<font name='Courier' size='8'>\1</font>", text)
        try:
            return Paragraph(text or "&nbsp;", style)
        except Exception:
            return Paragraph(text[:200] if text else "&nbsp;", style)

    while i < len(lines):
        line = lines[i]

        # ── Code block ──────────────────────────────────────────────────────
        if line.strip().startswith("```"):
            if in_code_block:
                # End code block
                code_text = "\n".join(code_lines)
                # Wrap into a table for background colour
                code_para = Paragraph(
                    code_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                             .replace("\n", "<br/>"),
                    styles["code"]
                )
                code_tbl = Table([[code_para]], colWidths=[CONTENT_W])
                code_tbl.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), CODE_BG),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("ROUNDEDCORNERS", [4, 4, 4, 4]),
                ]))
                flowables.append(Spacer(1, 4))
                flowables.append(code_tbl)
                flowables.append(Spacer(1, 6))
                in_code_block = False
                code_lines = []
            else:
                if in_table:
                    flush_table()
                in_code_block = True
                code_lines = []
            i += 1
            continue

        if in_code_block:
            code_lines.append(line)
            i += 1
            continue

        # ── Pipe table ──────────────────────────────────────────────────────
        if line.strip().startswith("|"):
            if not in_table:
                in_table = True
            table_rows.append(line)
            i += 1
            continue
        else:
            if in_table:
                flush_table()

        # ── Horizontal rule ─────────────────────────────────────────────────
        if re.match(r"^-{3,}$", line.strip()) or re.match(r"^={3,}$", line.strip()):
            flowables.append(Spacer(1, 4))
            flowables.append(HRFlowable(width=CONTENT_W, thickness=1,
                                        color=GOV_GREEN, spaceAfter=4))
            i += 1
            continue

        # ── Headings ────────────────────────────────────────────────────────
        h4 = re.match(r"^####\s+(.*)", line)
        h3 = re.match(r"^###\s+(.*)", line)
        h2 = re.match(r"^##\s+(.*)", line)
        h1 = re.match(r"^#\s+(.*)", line)

        if h1:
            flowables.append(PageBreak())
            flowables.append(Spacer(1, 6))
            # H1 with green background box
            h1_text = h1.group(1).strip()
            h1_tbl = Table(
                [[Paragraph(h1_text, styles["h1"])]],
                colWidths=[CONTENT_W]
            )
            h1_tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), GOV_GREEN),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ]))
            flowables.append(h1_tbl)
            flowables.append(Spacer(1, 8))
            i += 1
            continue

        if h2:
            flowables.append(Spacer(1, 8))
            txt = h2.group(1).strip()
            flowables.append(safe_para(f"<b>{txt}</b>", styles["h2"]))
            flowables.append(HRFlowable(width=CONTENT_W * 0.4, thickness=2,
                                        color=GOV_GOLD, spaceAfter=4))
            i += 1
            continue

        if h3:
            flowables.append(Spacer(1, 6))
            flowables.append(safe_para(h3.group(1).strip(), styles["h3"]))
            i += 1
            continue

        if h4:
            flowables.append(safe_para(h4.group(1).strip(), styles["h4"]))
            i += 1
            continue

        # ── Bullet / numbered list ───────────────────────────────────────────
        bullet_m = re.match(r"^(\s*)([-*+]|\d+\.)\s+(.*)", line)
        if bullet_m:
            indent = len(bullet_m.group(1))
            content = bullet_m.group(3)
            bstyle = ParagraphStyle(
                "dyn_bullet",
                parent=styles["bullet"],
                leftIndent=12 + indent * 8,
            )
            flowables.append(safe_para(f"• {content}", bstyle))
            i += 1
            continue

        # ── Blockquote / note ────────────────────────────────────────────────
        if line.strip().startswith(">"):
            content = line.strip().lstrip(">").strip()
            if content.upper().startswith("IMPORTANT") or content.upper().startswith("WARNING") or content.upper().startswith("CAUTION"):
                flowables.append(safe_para(f"⚠ {content}", styles["warning"]))
            else:
                flowables.append(safe_para(content, styles["note"]))
            i += 1
            continue

        # ── Empty line ───────────────────────────────────────────────────────
        if not line.strip():
            flowables.append(Spacer(1, 4))
            i += 1
            continue

        # ── Normal paragraph ─────────────────────────────────────────────────
        flowables.append(safe_para(line.strip(), styles["body"]))
        i += 1

    # Flush any remaining table
    if in_table:
        flush_table()

    return flowables


def build_cover_page(styles):
    """Return flowables for the cover page (used after first_page canvas callback)."""
    # The cover is drawn by the first_page canvas callback.
    # We return a PageBreak so the first real content starts on page 2.
    return [PageBreak()]


def build_toc(styles):
    """Return a simple Table of Contents page."""
    flowables = []
    flowables.append(Spacer(1, 0.5*cm))
    flowables.append(Paragraph("TABLE OF CONTENTS", styles["toc_title"]))
    flowables.append(HRFlowable(width=CONTENT_W, thickness=1.5, color=GOV_GREEN, spaceAfter=12))

    toc_entries = [
        ("1", "Executive Summary", "3"),
        ("2", "System Architecture Overview", "3"),
        ("3", "Technology Stack", "4"),
        ("4", "Frontend Architecture — All Pages & Features", "5"),
        ("4.1", "Login Page", "5"),
        ("4.2", "Dashboard", "5"),
        ("4.3", "Case Management", "6"),
        ("4.4", "FIR Folders", "6"),
        ("4.5", "Case Detail", "7"),
        ("4.6", "New Case Intake", "7"),
        ("4.7", "FIR Application Form", "8"),
        ("4.8", "Document Extraction Workspace", "8"),
        ("4.9", "AI & Legal Intelligence", "8"),
        ("4.10", "AI Case Summaries", "9"),
        ("4.11", "AI FIR Chatbot", "9"),
        ("4.12", "Knowledge Base", "10"),
        ("4.13", "Entity Network", "10"),
        ("4.14", "Entity Review Queue", "10"),
        ("4.15", "Case Diary Generator", "11"),
        ("4.16", "Chargesheet Generator", "11"),
        ("4.17", "Bulk Ingestion", "11"),
        ("4.18", "Employee Management", "11"),
        ("4.19", "Audit Trail", "12"),
        ("4.20", "Reports & Analytics", "12"),
        ("4.21", "Settings & Health", "12"),
        ("4.22", "Persons View", "12"),
        ("5", "Backend Architecture — All API Endpoints", "13"),
        ("6", "Database Schema & Relationships", "17"),
        ("7", "OCR & Extraction Pipeline", "19"),
        ("8", "AI FIR Chatbot & RAG Pipeline", "20"),
        ("9", "Knowledge Base & Legal Corpus", "21"),
        ("10", "Investigation Tools", "22"),
        ("11", "End-to-End Six-Stage Workflow", "22"),
        ("12", "Security, Roles & Audit", "24"),
        ("13", "Troubleshooting Guide", "25"),
        ("14", "Testing & Deployment", "26"),
        ("15", "Glossary", "26"),
    ]

    for num, title, page in toc_entries:
        is_main = len(num) <= 1 or (len(num) == 1 and num.isdigit())
        is_main_section = "." not in num
        dot_count = int(CONTENT_W / 5.5)
        dots = "." * dot_count

        if is_main_section:
            entry_style = ParagraphStyle(
                "toc_main",
                fontName="Helvetica-Bold",
                fontSize=10,
                textColor=GOV_GREEN,
                spaceBefore=5,
                spaceAfter=2,
                leading=14,
            )
        else:
            entry_style = ParagraphStyle(
                "toc_sub",
                fontName="Helvetica",
                fontSize=9,
                textColor=DARK_SLATE,
                spaceBefore=1,
                spaceAfter=1,
                leading=13,
                leftIndent=16,
            )

        entry_data = [
            [
                Paragraph(f"{num}. {title}", entry_style),
                Paragraph(page, entry_style),
            ]
        ]
        entry_tbl = Table(entry_data, colWidths=[CONTENT_W - 1.5*cm, 1.5*cm])
        entry_tbl.setStyle(TableStyle([
            ("ALIGN", (0, 0), (0, 0), "LEFT"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ("LINEBELOW", (0, 0), (-1, -1), 0.3, BORDER_CLR),
        ]))
        flowables.append(entry_tbl)

    flowables.append(PageBreak())
    return flowables


def generate_pdf():
    """Main function: read Markdown, parse, and write PDF."""
    print(f"Reading: {MD_PATH}")
    with open(MD_PATH, "r", encoding="utf-8") as f:
        md_text = f.read()

    styles = make_styles()

    # Build document
    doc = SimpleDocTemplate(
        PDF_PATH,
        pagesize=A4,
        leftMargin=MARGIN_L,
        rightMargin=MARGIN_R,
        topMargin=MARGIN_T + 0.5*cm,  # leave room for header bar
        bottomMargin=MARGIN_B + 0.5*cm,  # leave room for footer bar
        title="FIR VisionAI — Complete Architecture & User Guide",
        author="AP Prohibition & Excise Department",
        subject="System Architecture and Step-by-Step User Guide",
        creator="FIR VisionAI Documentation Generator",
    )

    story = []

    # Cover page (drawn by canvas callback, just add PageBreak)
    story.extend(build_cover_page(styles))

    # TOC page (uses header/footer)
    story.extend(build_toc(styles))

    # Main content parsed from Markdown
    story.extend(parse_and_build(md_text, styles))

    # Build with appropriate callbacks
    doc.build(
        story,
        onFirstPage=first_page,    # Cover page — no header/footer
        onLaterPages=header_footer, # All subsequent pages get header/footer
    )

    # Verify output
    if os.path.exists(PDF_PATH):
        size_kb = os.path.getsize(PDF_PATH) // 1024
        print(f"\nPDF generated successfully!")
        print(f"  Path: {PDF_PATH}")
        print(f"  Size: {size_kb} KB")
    else:
        print("PDF generation FAILED - file not found after build.")
        sys.exit(1)


if __name__ == "__main__":
    generate_pdf()
