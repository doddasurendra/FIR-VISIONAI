"""
FIR VisionAI — Complete Manager Guide PDF Generator
Generates: FIR_VisionAI_Complete_Manager_Guide.pdf
Run from backend/ dir: py docs/generate_manager_guide_pdf.py
"""
import os
import sys
import re

# ─── ReportLab imports ──────────────────────────────────────────────────────
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether, Image
)
from reportlab.platypus.flowables import HRFlowable
from reportlab.lib.colors import HexColor, white, black

# ─── Paths ───────────────────────────────────────────────────────────────────
DOCS_DIR = os.path.dirname(os.path.abspath(__file__))
MD_PATH  = os.path.join(DOCS_DIR, "FIR_VisionAI_Complete_Manager_Guide.md")
PDF_PATH = os.path.join(DOCS_DIR, "FIR_VisionAI_Complete_Manager_Guide.pdf")
DIAGRAM_PNG = os.path.join(DOCS_DIR, "FIR_VisionAI_Architecture_Diagram.png")

# ─── Brand colours ────────────────────────────────────────────────────────────
GOV_GREEN  = HexColor("#0f5132")
GOV_GOLD   = HexColor("#b8960c")
DARK_SLATE = HexColor("#1e293b")
MID_GREY   = HexColor("#64748b")
LIGHT_BG   = HexColor("#f0fdf4")
TABLE_HDR  = HexColor("#1e4d2b")
TABLE_ALT  = HexColor("#f8fafc")
BORDER_CLR = HexColor("#cbd5e1")
NAVY       = HexColor("#0f2744")

# ─── Page dimensions ─────────────────────────────────────────────────────────
PAGE_W, PAGE_H = A4
MARGIN_L = 2.0 * cm
MARGIN_R = 2.0 * cm
MARGIN_T = 2.2 * cm
MARGIN_B = 2.2 * cm
CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R


def make_styles():
    base = getSampleStyleSheet()
    S = {}
    S["title"] = ParagraphStyle("MG_title", fontName="Helvetica-Bold", fontSize=24,
        textColor=GOV_GREEN, alignment=TA_CENTER, spaceAfter=6, leading=30)
    S["subtitle"] = ParagraphStyle("MG_subtitle", fontName="Helvetica", fontSize=11,
        textColor=MID_GREY, alignment=TA_CENTER, spaceAfter=4, leading=15)
    S["dept"] = ParagraphStyle("MG_dept", fontName="Helvetica-Bold", fontSize=11,
        textColor=GOV_GOLD, alignment=TA_CENTER, spaceAfter=3, leading=14)
    S["h1"] = ParagraphStyle("MG_h1", fontName="Helvetica-Bold", fontSize=16,
        textColor=GOV_GREEN, spaceBefore=14, spaceAfter=6, leading=20,
        borderPad=4, leftIndent=0)
    S["h2"] = ParagraphStyle("MG_h2", fontName="Helvetica-Bold", fontSize=13,
        textColor=NAVY, spaceBefore=10, spaceAfter=4, leading=17)
    S["h3"] = ParagraphStyle("MG_h3", fontName="Helvetica-Bold", fontSize=11,
        textColor=DARK_SLATE, spaceBefore=8, spaceAfter=3, leading=15)
    S["body"] = ParagraphStyle("MG_body", fontName="Helvetica", fontSize=9,
        textColor=DARK_SLATE, spaceAfter=5, leading=14, alignment=TA_JUSTIFY)
    S["bullet"] = ParagraphStyle("MG_bullet", fontName="Helvetica", fontSize=9,
        textColor=DARK_SLATE, spaceAfter=3, leading=13, leftIndent=14,
        bulletIndent=4, firstLineIndent=0)
    S["toc_h1"] = ParagraphStyle("MG_toc_h1", fontName="Helvetica-Bold", fontSize=10,
        textColor=GOV_GREEN, spaceAfter=3, leading=14)
    S["toc_h2"] = ParagraphStyle("MG_toc_h2", fontName="Helvetica", fontSize=9,
        textColor=DARK_SLATE, spaceAfter=2, leftIndent=14, leading=13)
    S["note"] = ParagraphStyle("MG_note", fontName="Helvetica-Oblique", fontSize=9,
        textColor=MID_GREY, spaceAfter=5, leading=13, leftIndent=10)
    S["tbl_hdr"] = ParagraphStyle("MG_tbl_hdr", fontName="Helvetica-Bold", fontSize=8,
        textColor=white, alignment=TA_CENTER, leading=11)
    S["tbl_cell"] = ParagraphStyle("MG_tbl_cell", fontName="Helvetica", fontSize=7.5,
        textColor=DARK_SLATE, leading=10, spaceAfter=1)
    S["cover_ver"] = ParagraphStyle("MG_cover_ver", fontName="Helvetica", fontSize=10,
        textColor=white, alignment=TA_CENTER, leading=14)
    return S


# ─── Canvas callbacks ─────────────────────────────────────────────────────────
def first_page(canvas, doc):
    """Full-bleed cover page."""
    W, H = PAGE_W, PAGE_H
    canvas.saveState()
    # Dark green background
    canvas.setFillColor(GOV_GREEN)
    canvas.rect(0, 0, W, H, fill=1, stroke=0)
    # Gold accent band
    canvas.setFillColor(GOV_GOLD)
    canvas.rect(0, H * 0.55, W, 6, fill=1, stroke=0)
    canvas.rect(0, H * 0.14, W, 6, fill=1, stroke=0)
    # Organisation
    canvas.setFillColor(GOV_GOLD)
    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawCentredString(W / 2, H * 0.91, "ANDHRA PRADESH PROHIBITION & EXCISE DEPARTMENT")
    canvas.setFont("Helvetica", 10)
    canvas.setFillColor(white)
    canvas.drawCentredString(W / 2, H * 0.88, "Government of Andhra Pradesh — Law Enforcement Technology Division")
    # Main title
    canvas.setFillColor(white)
    canvas.setFont("Helvetica-Bold", 32)
    canvas.drawCentredString(W / 2, H * 0.76, "FIR VisionAI")
    canvas.setFont("Helvetica-Bold", 18)
    canvas.drawCentredString(W / 2, H * 0.71, "u-FIR v2.0")
    canvas.setFont("Helvetica", 13)
    canvas.setFillColor(GOV_GOLD)
    canvas.drawCentredString(W / 2, H * 0.665,
        "Complete System Architecture, Operations Guide")
    canvas.drawCentredString(W / 2, H * 0.635,
        "& Button-by-Button Manager Reference")
    # Divider
    canvas.setStrokeColor(GOV_GOLD)
    canvas.setLineWidth(1.5)
    canvas.line(W * 0.2, H * 0.615, W * 0.8, H * 0.615)
    # Meta block
    canvas.setFillColor(white)
    canvas.setFont("Helvetica", 9)
    meta = [
        "Document Classification: OFFICIAL — For Law Enforcement Review Only",
        "Release Version: 2.0.4-PROD (Enterprise Build)",
        "Date of Publication: October 2026",
        "Repository: github.com/doddasurendra/fir-sahayak",
    ]
    y = H * 0.57
    for m in meta:
        canvas.drawCentredString(W / 2, y, m)
        y -= 14
    # Chapters list
    canvas.setFillColor(HexColor("#d1fae5"))
    canvas.setFont("Helvetica", 8)
    chapters = [
        "21 Chapters  •  19-Step User Guide  •  37+ UI Button Reference",
        "Complete API Endpoints  •  Database Schema  •  OCR Pipeline",
        "RAG Chatbot  •  Geolocation  •  Multilingual Document Generation",
        "Security, RBAC & Audit Ledger  •  Testing Matrix  •  Glossary",
    ]
    y = H * 0.42
    for c in chapters:
        canvas.drawCentredString(W / 2, y, c)
        y -= 13
    # Footer
    canvas.setFillColor(white)
    canvas.setFont("Helvetica", 8)
    canvas.drawCentredString(W / 2, H * 0.09,
        "CONFIDENTIAL — AI Suggests, Officers Decide — No Fabricated Data")
    canvas.drawCentredString(W / 2, H * 0.065,
        "Powered by React 18 · FastAPI · Supabase PostgreSQL · Google Gemini 1.5 · pgvector")
    canvas.restoreState()


def header_footer(canvas, doc):
    """Header and footer for all non-cover pages."""
    W, H = PAGE_W, PAGE_H
    canvas.saveState()
    # Header bar
    canvas.setFillColor(GOV_GREEN)
    canvas.rect(0, H - 1.2 * cm, W, 1.2 * cm, fill=1, stroke=0)
    canvas.setFillColor(white)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(MARGIN_L, H - 0.75 * cm, "FIR VisionAI — Complete Manager Guide")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(W - MARGIN_R, H - 0.75 * cm,
        "AP Prohibition & Excise Department — OFFICIAL")
    # Gold accent line
    canvas.setFillColor(GOV_GOLD)
    canvas.rect(0, H - 1.25 * cm, W, 2, fill=1, stroke=0)
    # Footer
    canvas.setFillColor(LIGHT_BG)
    canvas.rect(0, 0, W, 1.0 * cm, fill=1, stroke=0)
    canvas.setFillColor(GOV_GREEN)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(MARGIN_L, 0.38 * cm, "u-FIR v2.0 — Confidential")
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawCentredString(W / 2, 0.38 * cm, f"Page {doc.page}")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(W - MARGIN_R, 0.38 * cm, "October 2026")
    canvas.restoreState()


# ─── Cover page flowables ─────────────────────────────────────────────────────
def build_cover_page(styles):
    """Return a single PageBreak (cover is drawn entirely by first_page callback)."""
    return [PageBreak()]


# ─── TOC ──────────────────────────────────────────────────────────────────────
TOC_ENTRIES = [
    ("1", "Executive Summary", 1),
    ("2", "Project Objectives & Core Purpose", 1),
    ("3", "System Architecture Overview (4 Tiers)", 1),
    ("4", "Actual System Architecture Diagram", 1),
    ("5", "End-to-End Six-Stage Workflow", 1),
    ("6", "Step-by-Step User Operational Guide (Steps 1–19)", 1),
    ("6.1", "Step 1: Open the Application and Sign In", 2),
    ("6.2", "Step 2: Understand the Dashboard", 2),
    ("6.3", "Step 3: Explain the Navigation Menu", 2),
    ("6.4", "Step 4–5: Create a New Case & Upload Evidence", 2),
    ("6.5", "Step 6–7: OCR Extraction & Officer Review", 2),
    ("6.6", "Step 8: Incident Location & Map Navigation", 2),
    ("6.7", "Step 9–10: AI Legal Intelligence & Knowledge Base", 2),
    ("6.8", "Step 11: AI FIR RAG Assistant", 2),
    ("6.9", "Step 12–14: Investigation Tools & Document Generators", 2),
    ("6.10", "Step 15–19: Administration, Search & Export", 2),
    ("7", "Complete Button-by-Button UI Reference Table", 1),
    ("8", "Frontend Architecture & Components (React 18)", 1),
    ("9", "Backend Architecture & Complete API Reference", 1),
    ("10", "Database Schema & Supabase Architecture", 1),
    ("11", "OCR & Multilingual Text Extraction Pipeline", 1),
    ("12", "Knowledge Base & 8-Category RAG Pipeline", 1),
    ("13", "Exact Incident Geolocation, Map & Navigation", 1),
    ("14", "Multilingual Case Diary & Chargesheet Generators", 1),
    ("15", "Security, RBAC & Cryptographic Audit Ledger", 1),
    ("16", "Error Handling & Troubleshooting Guide", 1),
    ("17", "Testing Matrix & Implementation Status", 1),
    ("18", "Technical & Legal Glossary", 1),
    ("19", "Manager Presentation Summary", 1),
    ("20", "Appendix A — Verified Routes Inventory", 1),
    ("21", "Appendix B — Database Objects & Configuration", 1),
]


def build_toc(styles):
    story = []
    story.append(Paragraph("TABLE OF CONTENTS", styles["h1"]))
    story.append(HRFlowable(width=CONTENT_W, thickness=2, color=GOV_GREEN, spaceAfter=8))
    for num, title, level in TOC_ENTRIES:
        text = f"<b>{num}.</b>&nbsp;&nbsp;{title}"
        s = styles["toc_h1"] if level == 1 else styles["toc_h2"]
        story.append(Paragraph(text, s))
    story.append(PageBreak())
    return story


# ─── Pipe-delimited table parser ─────────────────────────────────────────────
def build_table(lines, styles):
    """Parse GitHub-style pipe table lines into a ReportLab Table flowable."""
    rows = []
    for line in lines:
        if re.match(r"\s*\|[-:| ]+\|\s*$", line):
            continue  # separator row
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(cells)

    if not rows:
        return []

    n_cols = max(len(r) for r in rows)
    # Pad short rows
    for r in rows:
        while len(r) < n_cols:
            r.append("")

    # Convert to Paragraphs
    tbl_data = []
    for ri, row in enumerate(rows):
        para_row = []
        for ci, cell in enumerate(row):
            s = styles["tbl_hdr"] if ri == 0 else styles["tbl_cell"]
            text = cell.replace("**", "").replace("`", "").replace("*", "")
            para_row.append(Paragraph(text, s))
        tbl_data.append(para_row)

    # Column widths — distribute evenly
    col_w = CONTENT_W / n_cols

    tbl = Table(tbl_data, colWidths=[col_w] * n_cols, repeatRows=1)
    ts = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), TABLE_HDR),
        ("TEXTCOLOR",  (0, 0), (-1, 0), white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, 0), 8),
        ("ALIGN",      (0, 0), (-1, 0), "CENTER"),
        ("VALIGN",     (0, 0), (-1, -1), "TOP"),
        ("FONTNAME",   (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",   (0, 1), (-1, -1), 7.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, TABLE_ALT]),
        ("GRID",       (0, 0), (-1, -1), 0.4, BORDER_CLR),
        ("LEFTPADDING",  (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
    ])
    tbl.setStyle(ts)
    return [tbl, Spacer(1, 8)]


# ─── Markdown → ReportLab ─────────────────────────────────────────────────────
def parse_and_build(md_text, styles):
    """
    Convert markdown to ReportLab flowables.
    Handles: # ## ### headings, - bullets, | tables, > blockquotes, plain paragraphs.
    Inserts architecture diagram PNG when ![...](FIR_VisionAI_Architecture_Diagram.png) found.
    """
    story = []
    lines = md_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]

        # ── Architecture diagram image ──────────────────────────────────────
        if "FIR_VisionAI_Architecture_Diagram.png" in line and os.path.exists(DIAGRAM_PNG):
            story.append(Spacer(1, 6))
            try:
                img = Image(DIAGRAM_PNG, width=CONTENT_W, height=CONTENT_W * 0.625)
                story.append(img)
                story.append(Paragraph(
                    "<i>Figure 1 — FIR VisionAI System Architecture (All 6 Tiers)</i>",
                    styles["note"]))
            except Exception as e:
                story.append(Paragraph(f"[Architecture diagram: {e}]", styles["note"]))
            i += 1
            continue

        # ── H1 ──────────────────────────────────────────────────────────────
        if line.startswith("# ") and not line.startswith("## "):
            text = line[2:].strip()
            story.append(PageBreak())
            story.append(Paragraph(text, styles["h1"]))
            story.append(HRFlowable(width=CONTENT_W, thickness=1.5,
                                     color=GOV_GREEN, spaceAfter=6))
            i += 1
            continue

        # ── H2 ──────────────────────────────────────────────────────────────
        if line.startswith("## ") and not line.startswith("### "):
            text = line[3:].strip()
            story.append(Spacer(1, 6))
            story.append(Paragraph(text, styles["h2"]))
            story.append(HRFlowable(width=CONTENT_W * 0.6, thickness=1,
                                     color=GOV_GOLD, spaceAfter=4))
            i += 1
            continue

        # ── H3 ──────────────────────────────────────────────────────────────
        if line.startswith("### "):
            text = line[4:].strip()
            story.append(Paragraph(text, styles["h3"]))
            i += 1
            continue

        # ── HR ──────────────────────────────────────────────────────────────
        if re.match(r"^---+\s*$", line):
            story.append(HRFlowable(width=CONTENT_W, thickness=0.5,
                                     color=BORDER_CLR, spaceAfter=4))
            i += 1
            continue

        # ── Pipe table ──────────────────────────────────────────────────────
        if line.strip().startswith("|"):
            tbl_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                tbl_lines.append(lines[i])
                i += 1
            story.extend(build_table(tbl_lines, styles))
            continue

        # ── Bullet list ─────────────────────────────────────────────────────
        if re.match(r"^\s*[-*]\s+", line):
            text = re.sub(r"^\s*[-*]\s+", "", line)
            text = sanitize(text)
            story.append(Paragraph(f"• {text}", styles["bullet"]))
            i += 1
            continue

        # ── Numbered list ───────────────────────────────────────────────────
        if re.match(r"^\s*\d+\.\s+", line):
            text = re.sub(r"^\s*\d+\.\s+", "", line)
            num = re.match(r"^\s*(\d+)\.", line).group(1)
            text = sanitize(text)
            story.append(Paragraph(f"{num}. {text}", styles["bullet"]))
            i += 1
            continue

        # ── Blockquote / note ────────────────────────────────────────────────
        if line.startswith(">"):
            text = line.lstrip("> ").strip()
            text = sanitize(text)
            story.append(Paragraph(f"<i>{text}</i>", styles["note"]))
            i += 1
            continue

        # ── Empty line ───────────────────────────────────────────────────────
        if not line.strip():
            story.append(Spacer(1, 4))
            i += 1
            continue

        # ── Plain paragraph ──────────────────────────────────────────────────
        text = sanitize(line)
        if text:
            story.append(Paragraph(text, styles["body"]))
        i += 1

    return story


def sanitize(text):
    """Escape XML special chars and convert markdown bold/code to ReportLab tags."""
    # Remove markdown image syntax
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    # Escape XML entities
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Bold: **text** → <b>text</b>
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    # Code: `text` → code face
    text = re.sub(r"`([^`]+)`", r"<font name='Courier'>\1</font>", text)
    # Italics: *text* → <i>text</i>
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    return text.strip()


# ─── Main ─────────────────────────────────────────────────────────────────────
def generate_pdf():
    print(f"Reading Markdown from: {MD_PATH}")
    with open(MD_PATH, encoding="utf-8") as f:
        md_text = f.read()
    print(f"  Markdown length: {len(md_text):,} characters")

    styles = make_styles()

    doc = SimpleDocTemplate(
        PDF_PATH,
        pagesize=A4,
        leftMargin=MARGIN_L,
        rightMargin=MARGIN_R,
        topMargin=MARGIN_T + 0.5 * cm,
        bottomMargin=MARGIN_B + 0.5 * cm,
        title="FIR VisionAI — Complete Manager Guide",
        author="AP Prohibition & Excise Department",
        subject="System Architecture, Operations Guide & Button Reference",
        creator="FIR VisionAI Documentation Generator v2",
    )

    story = []
    story.extend(build_cover_page(styles))   # Cover page (canvas callback)
    story.extend(build_toc(styles))           # Table of Contents
    story.extend(parse_and_build(md_text, styles))  # 21 chapters

    print("Building PDF (this may take a moment) ...")
    doc.build(
        story,
        onFirstPage=first_page,
        onLaterPages=header_footer,
    )

    if os.path.exists(PDF_PATH):
        size_kb = os.path.getsize(PDF_PATH) // 1024
        import subprocess
        # Count pages using pypdfium2
        try:
            import pypdfium2 as pdfium
            pdfdoc = pdfium.PdfDocument(PDF_PATH)
            pages = len(pdfdoc)
            print(f"\nPDF generated successfully!")
            print(f"  Path  : {PDF_PATH}")
            print(f"  Size  : {size_kb} KB")
            print(f"  Pages : {pages}")
        except Exception:
            print(f"\nPDF generated successfully!")
            print(f"  Path  : {PDF_PATH}")
            print(f"  Size  : {size_kb} KB")
    else:
        print("FAILED — PDF not found after build.")
        sys.exit(1)


if __name__ == "__main__":
    generate_pdf()
