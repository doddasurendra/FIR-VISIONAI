"""
FIR VisionAI — Comprehensive Case Export Service.
Generates authenticated, case-scoped export documents in:
- Excel (.xlsx) with readable multi-sheet structure
- JSON (.json) with valid structured hierarchy
- CSV (.csv) with RFC 4180 escaping and UTF-8-sig encoding for Indic text
- Word (.docx) with official AP Government / Law Enforcement styling
- PDF (.pdf) with ReportLab, Nirmala Indic font, and official statutory header
"""
from __future__ import annotations
import io
import csv
import json
import os
from datetime import datetime, timezone
from typing import Dict, Any, List

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Register Nirmala font for Telugu & Hindi support if available
FONT_NAME = "Helvetica"
BOLD_FONT_NAME = "Helvetica-Bold"

try:
    nirmala_path = "C:/Windows/Fonts/Nirmala.ttf"
    nirmala_bold_path = "C:/Windows/Fonts/NirmalaB.ttf"
    if os.path.exists(nirmala_path):
        pdfmetrics.registerFont(TTFont("Nirmala", nirmala_path))
        FONT_NAME = "Nirmala"
        if os.path.exists(nirmala_bold_path):
            pdfmetrics.registerFont(TTFont("Nirmala-Bold", nirmala_bold_path))
            BOLD_FONT_NAME = "Nirmala-Bold"
        else:
            BOLD_FONT_NAME = "Nirmala"
except Exception:
    FONT_NAME = "Helvetica"
    BOLD_FONT_NAME = "Helvetica-Bold"


# ─────────────────────────────────────────────────────────────────────────────
# 1. EXCEL (.XLSX) GENERATOR
# ─────────────────────────────────────────────────────────────────────────────
def generate_case_xlsx(data: Dict[str, Any]) -> bytes:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # remove default sheet

    case = data.get("case", {})
    fields = data.get("fields", [])
    entities = data.get("entities", [])
    documents = data.get("documents", [])
    workflow = data.get("workflow", [])

    navy_fill = PatternFill(start_color="112D4E", end_color="112D4E", fill_type="solid")
    gold_fill = PatternFill(start_color="B45309", end_color="B45309", fill_type="solid")
    alt_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    white_bold = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    thin_border = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1"),
    )

    # Sheet 1: Case Summary
    ws1 = wb.create_sheet(title="Case Summary")
    ws1.views.sheetView[0].showGridLines = True
    ws1.merge_cells("A1:D1")
    ws1["A1"] = "GOVERNMENT OF ANDHRA PRADESH — PROHIBITION & EXCISE DEPARTMENT"
    ws1["A1"].font = Font(name="Calibri", size=13, bold=True, color="112D4E")
    ws1["A1"].alignment = Alignment(horizontal="center", vertical="center")

    ws1.merge_cells("A2:D2")
    ws1["A2"] = f"Official Unified FIR Record: {case.get('fir_number', 'N/A')} ({case.get('year', '')})"
    ws1["A2"].font = Font(name="Calibri", size=11, bold=True, color="B45309")
    ws1["A2"].alignment = Alignment(horizontal="center", vertical="center")

    summary_rows = [
        ("FIR / Case Number", str(case.get("fir_number", ""))),
        ("Year", str(case.get("year", ""))),
        ("District", str(case.get("district", ""))),
        ("Station", str(case.get("station", ""))),
        ("Status", str(case.get("status", "DRAFT"))),
        ("Classification Status", str(case.get("classification_status", "PENDING"))),
        ("Offence Category", str(case.get("offence_category", ""))),
        ("Offence Nature", str(case.get("offence_nature", ""))),
        ("Contraband Type", str(case.get("contraband_type", ""))),
        ("Seized Quantity", f"{case.get('seized_quantity', 0)} {case.get('seized_unit', '')}"),
        ("Vehicle Details", str(case.get("vehicle_details", "None reported"))),
        ("Seizing Officer", f"{case.get('seizing_officer_name', '')} ({case.get('seizing_officer_rank', '')})"),
        ("Registration Date", str(case.get("registration_date", ""))),
        ("Narrative Summary", str(case.get("narrative", "")[:300])),
        ("Export Timestamp (UTC)", datetime.now(timezone.utc).isoformat()),
    ]

    ws1.cell(row=4, column=1, value="Property / Attribute").fill = navy_fill
    ws1.cell(row=4, column=1).font = white_bold
    ws1.cell(row=4, column=2, value="Official Value").fill = navy_fill
    ws1.cell(row=4, column=2).font = white_bold

    for idx, (prop, val) in enumerate(summary_rows, 5):
        c1 = ws1.cell(row=idx, column=1, value=prop)
        c2 = ws1.cell(row=idx, column=2, value=val)
        c1.font = Font(name="Calibri", size=10, bold=True, color="1E293B")
        c2.font = Font(name="Calibri", size=10, color="0F172A")
        c1.border = thin_border
        c2.border = thin_border
        if idx % 2 == 0:
            c1.fill = alt_fill
            c2.fill = alt_fill

    # Sheet 2: Verified Case Fields
    ws2 = wb.create_sheet(title="Case Fields")
    ws2.views.sheetView[0].showGridLines = True
    f_headers = ["Field Name", "Extracted Value", "Verified / Override Value", "Verification Status", "Page #", "Confidence"]
    for col_idx, h in enumerate(f_headers, 1):
        c = ws2.cell(row=1, column=col_idx, value=h)
        c.fill = navy_fill
        c.font = white_bold
        c.alignment = Alignment(horizontal="center")

    for row_idx, f in enumerate(fields, 2):
        vals = [
            f.get("field_name", ""),
            str(f.get("original_value", "") or ""),
            str(f.get("human_override_value") or f.get("normalized_value") or ""),
            f.get("verification_status", "UNVERIFIED"),
            f.get("page_number", 1),
            f.get("confidence_score", 1.0)
        ]
        for col_idx, val in enumerate(vals, 1):
            cell = ws2.cell(row=row_idx, column=col_idx, value=val)
            cell.font = Font(name="Calibri", size=10)
            cell.border = thin_border
            if row_idx % 2 == 0:
                cell.fill = alt_fill

    # Sheet 3: Extracted Entities
    ws3 = wb.create_sheet(title="Entities & Suspects")
    ws3.views.sheetView[0].showGridLines = True
    e_headers = ["Entity Name", "Type", "Role in Case", "Verification Status", "Risk Score"]
    for col_idx, h in enumerate(e_headers, 1):
        c = ws3.cell(row=1, column=col_idx, value=h)
        c.fill = gold_fill
        c.font = white_bold
        c.alignment = Alignment(horizontal="center")

    for row_idx, e in enumerate(entities, 2):
        ent = e.get("entity", {}) if "entity" in e else e
        mention = e.get("mention", {}) if "mention" in e else {}
        vals = [
            ent.get("canonical_name", ""),
            ent.get("entity_type", ""),
            mention.get("role_in_case", "ACCUSED"),
            ent.get("verification_status", "CONFIRMED"),
            ent.get("risk_score", 0.0)
        ]
        for col_idx, val in enumerate(vals, 1):
            cell = ws3.cell(row=row_idx, column=col_idx, value=val)
            cell.font = Font(name="Calibri", size=10)
            cell.border = thin_border

    # Sheet 4: Workflow Pipeline
    ws4 = wb.create_sheet(title="Workflow Status")
    ws4.views.sheetView[0].showGridLines = True
    w_headers = ["Stage", "Status", "Started At", "Completed At", "Summary / Notes"]
    for col_idx, h in enumerate(w_headers, 1):
        c = ws4.cell(row=1, column=col_idx, value=h)
        c.fill = navy_fill
        c.font = white_bold

    for row_idx, w in enumerate(workflow, 2):
        vals = [
            w.get("stage", ""),
            w.get("status", ""),
            str(w.get("started_at", "") or ""),
            str(w.get("completed_at", "") or ""),
            str(w.get("result_summary") or w.get("error_message") or "")
        ]
        for col_idx, val in enumerate(vals, 1):
            cell = ws4.cell(row=row_idx, column=col_idx, value=val)
            cell.font = Font(name="Calibri", size=10)
            cell.border = thin_border

    # Auto-adjust column widths
    for sheet in wb.worksheets:
        for col in sheet.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = get_column_letter(col[0].column)
            sheet.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 60)

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# 2. JSON GENERATOR
# ─────────────────────────────────────────────────────────────────────────────
def generate_case_json(data: Dict[str, Any]) -> bytes:
    export_payload = {
        "metadata": {
            "department": "Andhra Pradesh Prohibition & Excise Department / AP Police",
            "system": "FIR VisionAI (u-FIR Intelligence Platform)",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "export_version": "2.0"
        },
        "case": data.get("case", {}),
        "fields": data.get("fields", []),
        "entities": data.get("entities", []),
        "documents": data.get("documents", []),
        "workflow": data.get("workflow", [])
    }
    return json.dumps(export_payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# 3. CSV GENERATOR
# ─────────────────────────────────────────────────────────────────────────────
def generate_case_csv(data: Dict[str, Any]) -> bytes:
    """Generate CSV with UTF-8 BOM for full Telugu and Hindi character preservation."""
    out = io.StringIO()
    writer = csv.writer(out, quoting=csv.QUOTE_MINIMAL)

    case = data.get("case", {})
    fields = data.get("fields", [])
    entities = data.get("entities", [])

    # Case Summary Header
    writer.writerow(["SECTION: CASE SUMMARY"])
    writer.writerow(["FIR Number", case.get("fir_number", "")])
    writer.writerow(["Year", case.get("year", "")])
    writer.writerow(["District", case.get("district", "")])
    writer.writerow(["Station", case.get("station", "")])
    writer.writerow(["Status", case.get("status", "DRAFT")])
    writer.writerow(["Offence Nature", case.get("offence_nature", "")])
    writer.writerow(["Contraband Type", case.get("contraband_type", "")])
    writer.writerow(["Seized Quantity", f"{case.get('seized_quantity', 0)} {case.get('seized_unit', '')}"])
    writer.writerow(["Vehicle Details", case.get("vehicle_details", "")])
    writer.writerow(["Registration Date", str(case.get("registration_date", ""))])
    writer.writerow([])

    # Fields
    writer.writerow(["SECTION: VERIFIED CASE FIELDS"])
    writer.writerow(["Field Name", "Original Value", "Verified Value", "Status", "Confidence", "Page #"])
    for f in fields:
        writer.writerow([
            f.get("field_name", ""),
            f.get("original_value", "") or "",
            f.get("human_override_value") or f.get("normalized_value") or "",
            f.get("verification_status", "UNVERIFIED"),
            f.get("confidence_score", 1.0),
            f.get("page_number", 1)
        ])
    writer.writerow([])

    # Entities
    writer.writerow(["SECTION: EXTRACTED ENTITIES"])
    writer.writerow(["Entity Name", "Type", "Role", "Verification", "Risk Score"])
    for e in entities:
        ent = e.get("entity", {}) if "entity" in e else e
        mention = e.get("mention", {}) if "mention" in e else {}
        writer.writerow([
            ent.get("canonical_name", ""),
            ent.get("entity_type", ""),
            mention.get("role_in_case", "ACCUSED"),
            ent.get("verification_status", "CONFIRMED"),
            ent.get("risk_score", 0.0)
        ])

    return ("\ufeff" + out.getvalue()).encode("utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# 4. WORD (.DOCX) GENERATOR
# ─────────────────────────────────────────────────────────────────────────────
def generate_case_docx(data: Dict[str, Any]) -> bytes:
    doc = docx.Document()

    # Page Margins
    for section in doc.sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.8)
        section.right_margin = Inches(0.8)

    case = data.get("case", {})
    fields = data.get("fields", [])
    entities = data.get("entities", [])
    workflow = data.get("workflow", [])

    # Official Header
    p_header = doc.add_paragraph()
    p_header.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r1 = p_header.add_run("GOVERNMENT OF ANDHRA PRADESH\nPROHIBITION & EXCISE DEPARTMENT\n")
    r1.bold = True
    r1.font.size = Pt(13)
    r1.font.color.rgb = RGBColor(0x11, 0x2D, 0x4E)

    r2 = p_header.add_run(f"UNIFIED FIRST INFORMATION REPORT — {case.get('fir_number', 'N/A')}\n")
    r2.bold = True
    r2.font.size = Pt(12)
    r2.font.color.rgb = RGBColor(0xB4, 0x53, 0x09)

    # Status Banner
    is_draft = case.get("status", "DRAFT") != "APPROVED"
    p_status = doc.add_paragraph()
    p_status.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_status = p_status.add_run(
        "*** ADVISORY COPY — PENDING FORMAL SIGN-OFF ***" if is_draft else "OFFICIAL VERIFIED RECORD"
    )
    r_status.bold = True
    r_status.font.size = Pt(10)
    r_status.font.color.rgb = RGBColor(0xC0, 0x26, 0x26) if is_draft else RGBColor(0x0F, 0x51, 0x32)

    # Core Case Details Table
    doc.add_heading("1. Case Metadata & Identification", level=2)
    meta_table = doc.add_table(rows=0, cols=2)
    meta_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    meta_table.autofit = True

    meta_items = [
        ("FIR / Case Number", str(case.get("fir_number", ""))),
        ("Registration Year", str(case.get("year", ""))),
        ("District", str(case.get("district", ""))),
        ("Police / Excise Station", str(case.get("station", ""))),
        ("Classification Status", str(case.get("classification_status", "PENDING"))),
        ("Offence Category", str(case.get("offence_category", "EXCISE"))),
        ("Offence Nature", str(case.get("offence_nature", ""))),
        ("Contraband Seized", f"{case.get('seized_quantity', 0)} {case.get('seized_unit', '')} ({case.get('contraband_type', '')})"),
        ("Vehicle Involved", str(case.get("vehicle_details", "None reported"))),
        ("Seizing Officer", f"{case.get('seizing_officer_name', '')} - {case.get('seizing_officer_rank', '')}"),
        ("Registration Date", str(case.get("registration_date", ""))),
    ]
    for prop, val in meta_items:
        row = meta_table.add_row()
        c0, c1 = row.cells[0], row.cells[1]
        c0.text = prop
        c1.text = val
        c0.paragraphs[0].runs[0].font.bold = True
        c0.paragraphs[0].runs[0].font.size = Pt(9.5)
        c1.paragraphs[0].runs[0].font.size = Pt(9.5)

    # Verified Fields Table
    doc.add_heading("2. Extracted & Human-Verified FIR Fields", level=2)
    if fields:
        f_table = doc.add_table(rows=1, cols=4)
        f_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        headers = ["Field Name", "Extracted Value", "Verified / Override Value", "Status"]
        for idx, h in enumerate(headers):
            cell = f_table.rows[0].cells[idx]
            cell.text = h
            cell.paragraphs[0].runs[0].font.bold = True
            cell.paragraphs[0].runs[0].font.size = Pt(9)

        for f in fields:
            row = f_table.add_row()
            row.cells[0].text = f.get("field_name", "")
            row.cells[1].text = str(f.get("original_value", "") or "")
            row.cells[2].text = str(f.get("human_override_value") or f.get("normalized_value") or "")
            row.cells[3].text = f.get("verification_status", "UNVERIFIED")
            for cell in row.cells:
                if cell.paragraphs[0].runs:
                    cell.paragraphs[0].runs[0].font.size = Pt(8.5)
    else:
        doc.add_paragraph("No structured fields recorded for this case.")

    # Entities Section
    doc.add_heading("3. Associated Suspects, Entities & Vehicles", level=2)
    if entities:
        e_table = doc.add_table(rows=1, cols=4)
        e_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        e_headers = ["Name / Identifier", "Type", "Role", "Verification"]
        for idx, h in enumerate(e_headers):
            cell = e_table.rows[0].cells[idx]
            cell.text = h
            cell.paragraphs[0].runs[0].font.bold = True
            cell.paragraphs[0].runs[0].font.size = Pt(9)

        for e in entities:
            ent = e.get("entity", {}) if "entity" in e else e
            mention = e.get("mention", {}) if "mention" in e else {}
            row = e_table.add_row()
            row.cells[0].text = ent.get("canonical_name", "")
            row.cells[1].text = ent.get("entity_type", "")
            row.cells[2].text = mention.get("role_in_case", "ACCUSED")
            row.cells[3].text = ent.get("verification_status", "CONFIRMED")
            for cell in row.cells:
                if cell.paragraphs[0].runs:
                    cell.paragraphs[0].runs[0].font.size = Pt(8.5)
    else:
        doc.add_paragraph("No entities linked to this case record.")

    # Narrative
    doc.add_heading("4. Recorded FIR Narrative", level=2)
    doc.add_paragraph(case.get("narrative", "No narrative recorded."))

    # Legal Disclaimer Footer
    p_disc = doc.add_paragraph()
    p_disc.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_disc = p_disc.add_run(
        f"\nGenerated by FIR VisionAI on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}.\n"
        "Official Government of Andhra Pradesh intelligence system. Unauthorized duplication prohibited."
    )
    r_disc.font.size = Pt(8)
    r_disc.font.italic = True
    r_disc.font.color.rgb = RGBColor(0x64, 0x74, 0x8B)

    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# 5. PDF (.PDF) GENERATOR WITH INDIC FONT SUPPORT
# ─────────────────────────────────────────────────────────────────────────────
def generate_case_pdf(data: Dict[str, Any]) -> bytes:
    out = io.BytesIO()
    c = canvas.Canvas(out, pagesize=letter)
    width, height = letter

    case = data.get("case", {})
    fields = data.get("fields", [])
    entities = data.get("entities", [])
    is_draft = case.get("status", "DRAFT") != "APPROVED"

    def draw_header_banner(page_num: int):
        # Top banner
        c.setFillColor(colors.HexColor("#112D4E"))
        c.rect(0, height - 60, width, 60, fill=1, stroke=0)

        c.setFillColor(colors.white)
        c.setFont(BOLD_FONT_NAME, 11)
        c.drawCentredString(width / 2.0, height - 25, "GOVERNMENT OF ANDHRA PRADESH — PROHIBITION & EXCISE DEPARTMENT")

        c.setFont(FONT_NAME, 9)
        c.drawCentredString(width / 2.0, height - 42, f"OFFICIAL FIRST INFORMATION REPORT RECORD (u-FIR) — PAGE {page_num}")

        # Gold bar
        c.setFillColor(colors.HexColor("#B45309"))
        c.rect(0, height - 64, width, 4, fill=1, stroke=0)

    def draw_footer(page_num: int):
        c.setFillColor(colors.HexColor("#64748B"))
        c.setFont(FONT_NAME, 7.5)
        c.drawString(36, 25, f"FIR VisionAI Law Enforcement Export | Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        c.drawRightString(width - 36, 25, f"Case: {case.get('fir_number', '')} | Page {page_num}")

    # PAGE 1
    page = 1
    draw_header_banner(page)
    draw_footer(page)

    y = height - 90

    # Status Watermark / Indicator
    if is_draft:
        c.setFillColor(colors.HexColor("#DC2626"))
        c.setFont(BOLD_FONT_NAME, 10)
        c.drawString(36, y, "STATUS: DRAFT / IN-REVIEW (ADVISORY RECORD)")
    else:
        c.setFillColor(colors.HexColor("#0F5132"))
        c.setFont(BOLD_FONT_NAME, 10)
        c.drawString(36, y, "STATUS: OFFICIAL APPROVED FIR RECORD")

    y -= 25

    # Case Details Box
    c.setFillColor(colors.HexColor("#1E293B"))
    c.setFont(BOLD_FONT_NAME, 13)
    c.drawString(36, y, f"FIR Number: {case.get('fir_number', 'N/A')}")
    y -= 16

    c.setFont(FONT_NAME, 9.5)
    c.drawString(36, y, f"District: {case.get('district', '')}   |   Station: {case.get('station', '')}   |   Year: {case.get('year', '')}")
    y -= 15
    c.drawString(36, y, f"Offence Nature: {case.get('offence_nature', 'N/A')}")
    y -= 15
    c.drawString(36, y, f"Contraband Seized: {case.get('seized_quantity', 0)} {case.get('seized_unit', '')} ({case.get('contraband_type', '')})")
    y -= 15
    c.drawString(36, y, f"Vehicle: {case.get('vehicle_details', 'None')}   |   Seizing Officer: {case.get('seizing_officer_name', '')}")
    y -= 25

    # Verified Fields Section
    c.setFillColor(colors.HexColor("#112D4E"))
    c.setFont(BOLD_FONT_NAME, 11)
    c.drawString(36, y, "Verified FIR Fields & Structured Data:")
    y -= 15

    # Table Header
    c.setFillColor(colors.HexColor("#F1F5F9"))
    c.rect(36, y - 4, width - 72, 16, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#1E293B"))
    c.setFont(BOLD_FONT_NAME, 8.5)
    c.drawString(42, y, "FIELD")
    c.drawString(170, y, "EXTRACTED VALUE")
    c.drawString(350, y, "VERIFIED VALUE")
    c.drawString(500, y, "STATUS")
    y -= 16

    c.setFont(FONT_NAME, 8)
    for f in fields[:12]:
        val1 = str(f.get("original_value", "") or "")[:30]
        val2 = str(f.get("human_override_value") or f.get("normalized_value") or "")[:30]
        st = f.get("verification_status", "UNVERIFIED")

        c.setFillColor(colors.HexColor("#334155"))
        c.drawString(42, y, str(f.get("field_name", ""))[:22])
        c.drawString(170, y, val1)
        c.drawString(350, y, val2)
        c.drawString(500, y, st)

        c.setStrokeColor(colors.HexColor("#E2E8F0"))
        c.line(36, y - 2, width - 36, y - 2)
        y -= 14

    y -= 15

    # Entities Section
    c.setFillColor(colors.HexColor("#112D4E"))
    c.setFont(BOLD_FONT_NAME, 11)
    c.drawString(36, y, "Associated Entities (Persons, Vehicles, Phone Numbers):")
    y -= 15

    c.setFillColor(colors.HexColor("#F1F5F9"))
    c.rect(36, y - 4, width - 72, 16, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#1E293B"))
    c.setFont(BOLD_FONT_NAME, 8.5)
    c.drawString(42, y, "ENTITY NAME")
    c.drawString(240, y, "TYPE")
    c.drawString(380, y, "ROLE")
    c.drawString(480, y, "VERIFICATION")
    y -= 16

    c.setFont(FONT_NAME, 8)
    for e in entities[:8]:
        ent = e.get("entity", {}) if "entity" in e else e
        mention = e.get("mention", {}) if "mention" in e else {}

        c.setFillColor(colors.HexColor("#334155"))
        c.drawString(42, y, str(ent.get("canonical_name", ""))[:32])
        c.drawString(240, y, str(ent.get("entity_type", "")))
        c.drawString(380, y, str(mention.get("role_in_case", "ACCUSED")))
        c.drawString(480, y, str(ent.get("verification_status", "CONFIRMED")))

        c.setStrokeColor(colors.HexColor("#E2E8F0"))
        c.line(36, y - 2, width - 36, y - 2)
        y -= 14

    y -= 15

    # Narrative Excerpt
    if y > 100:
        c.setFillColor(colors.HexColor("#112D4E"))
        c.setFont(BOLD_FONT_NAME, 10)
        c.drawString(36, y, "Recorded FIR Narrative Excerpt:")
        y -= 12

        c.setFillColor(colors.HexColor("#475569"))
        c.setFont(FONT_NAME, 7.5)
        narrative_txt = str(case.get("narrative", "None recorded"))[:400]
        # Draw wrapped lines
        for line in narrative_txt.split("\n")[:4]:
            c.drawString(36, y, line[:105])
            y -= 10

    c.showPage()
    c.save()
    return out.getvalue()
