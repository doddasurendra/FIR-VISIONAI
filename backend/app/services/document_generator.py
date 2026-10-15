import os
from datetime import datetime
from typing import Dict, Any, Optional
from jinja2 import Template
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from ..config import settings
from ..models.case import Case
from ..models.legal import CaseLegalSection
from ..models.generation import GeneratedDocument, DocumentApprovalHistory
from ..models.user import User

CASE_DIARY_TEMPLATE = """
ANDHRA PRADESH EXCISE AND PROHIBITION DEPARTMENT
INVESTIGATION CASE DIARY (SECTION 172 CrPC / BNSS)
======================================================
[STATE: DRAFT | AI-GENERATED INVESTIGATION DRAFT]

Case Crime No: {{ case.fir_number }}
Excise Station: {{ case.station }}, {{ case.district }} District
Date of Entry: {{ entry_date }}
Investigating Officer: {{ officer.full_name }} ({{ officer.designation }})

1. CRIME DETAILS:
   - Date & Time of Offence: {{ case.offence_date or 'Under Investigation' }}
   - Occurrence Location: {{ case.village or '' }}, {{ case.mandal or '' }}, {{ case.district }}
   - Specific Location: {{ case.location_description or 'Near check-post' }}
   - Contraband Description: {{ case.contraband_type }} (Quantity: {{ case.seized_quantity }} {{ case.seized_unit }})
   - Conveyance / Vehicle: {{ case.vehicle_details or 'None observed' }}

2. APPLICABLE STATUTORY SECTIONS:
   {% for sec in sections %}
   - {{ sec.act_name }} {{ sec.section_number }}: {{ sec.section_title }} [{{ sec.officer_decision }}]
   {% else %}
   - Sections pending final chemical analysis & legal confirmation.
   {% endfor %}

3. INVESTIGATION PROGRESS & STEPS TAKEN:
   - On credible information, excise patrol team conducted raid and vehicle interception.
   - Accused was found in conscious possession of the seized contraband without permit.
   - Mediators report (panchanama) drawn at scene in presence of independent witnesses.
   - Samples collected, sealed, and marked as per state excise laboratory protocols.
   - Accused produced before the competent jurisdictional Magistrate.

4. NEXT PENDING ACTIONS:
   - Awaiting Government Chemical Examiner Laboratory Analysis Report.
   - Verification of ownership records of the seized vehicle (AP Transport Department).
   - Examination of additional circumstantial witnesses.

DRAFT PREPARED ON: {{ generation_time }}
DISCLAIMER: AI-Generated draft for authorized departmental review. Not a certified final court document.
"""

CHARGESHEET_TEMPLATE = """
IN THE COURT OF THE JUDICIAL MAGISTRATE OF FIRST CLASS
POLICE / EXCISE FINAL REPORT UNDER SECTION 173 CrPC / 193 BNSS
==================================================================
[DEPARTMENTAL WORKING DRAFT - AI-GENERATED]

State of Andhra Pradesh (Through Excise Station {{ case.station }})
Versus
Accused Persons

1. Crime Details:
   - Case Crime No: {{ case.fir_number }}
   - Year: {{ case.year }}
   - Nature of Offence: {{ case.offence_nature }}

2. Charges Framed Under Laws:
   {% for sec in sections %}
   * {{ sec.act_name }} {{ sec.section_number }} ({{ sec.section_title }})
   {% endfor %}

3. Brief Facts of the Prosecution Case:
   {{ case.narrative }}

4. List of Material Objects (Seized Property):
   - M.O. 1: {{ case.seized_quantity }} {{ case.seized_unit }} of {{ case.contraband_type }}
   - M.O. 2: Conveyance {{ case.vehicle_details or 'N/A' }}

5. Witnesses to be Examined (List of Witnesses):
   - L.W. 1: {{ case.seizing_officer_name or 'Seizing Sub-Inspector' }} (Complainant)
   - L.W. 2 & 3: Independent Panch Witnesses (Panchanama witnesses)
   - L.W. 4: Government Chemical Examiner

Prayer: It is humbly prayed that the Hon'ble Court may be pleased to take cognizance of the offence against the accused and process trial in accordance with law.

Prepared by: {{ officer.full_name }}
Date: {{ entry_date }}
"""

class DocumentGeneratorService:
    @staticmethod
    async def generate_draft(
        case_id: str,
        doc_type: str, # CASE_DIARY, CHARGESHEET, CASE_SUMMARY
        user: User,
        db: AsyncSession
    ) -> GeneratedDocument:
        stmt = select(Case).where(Case.id == case_id)
        res = await db.execute(stmt)
        case = res.scalar_one_or_none()
        if not case:
            raise ValueError("Case not found")

        # Fetch sections
        sec_stmt = select(CaseLegalSection).where(CaseLegalSection.case_id == case_id)
        sec_res = await db.execute(sec_stmt)
        sections = sec_res.scalars().all()

        template_str = CASE_DIARY_TEMPLATE if doc_type == "CASE_DIARY" else CHARGESHEET_TEMPLATE
        template = Template(template_str)
        rendered_content = template.render(
            case=case,
            sections=sections,
            officer=user,
            entry_date=datetime.utcnow().strftime("%d-%m-%Y"),
            generation_time=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        )

        doc = GeneratedDocument(
            case_id=case_id,
            doc_type=doc_type,
            title=f"{doc_type.replace('_', ' ').title()} - {case.fir_number}",
            content=rendered_content,
            version=1,
            status="DRAFT",
            created_by=user.id
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        return doc

    @staticmethod
    def export_pdf(doc: GeneratedDocument, output_path: str):
        """Generate PDF using ReportLab with clear DRAFT watermark."""
        c = canvas.Canvas(output_path, pagesize=letter)
        width, height = letter
        
        # Watermark
        c.saveState()
        c.setFont("Helvetica-Bold", 42)
        c.setFillColor(colors.Color(0.85, 0.85, 0.85, alpha=0.35))
        c.translate(width / 2, height / 2)
        c.rotate(45)
        c.drawCentredString(0, 0, f"DRAFT - {doc.status}")
        c.restoreState()

        # Header
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, height - 50, "GOVERNMENT OF ANDHRA PRADESH - EXCISE DEPARTMENT")
        c.setFont("Helvetica-Bold", 11)
        c.drawString(50, height - 70, doc.title)
        c.setFont("Helvetica", 9)
        c.drawString(50, height - 85, f"Document Version: {doc.version} | Status: {doc.status} | Generated: {datetime.utcnow().strftime('%Y-%m-%d')}")
        c.line(50, height - 92, width - 50, height - 92)

        # Body text
        text_obj = c.beginText(50, height - 115)
        text_obj.setFont("Courier", 9)
        text_obj.setLeading(14)
        
        lines = doc.content.split("\n")
        for line in lines[:50]: # First page preview lines
            text_obj.textLine(line)
        c.drawText(text_obj)

        c.showPage()
        c.save()

document_generator = DocumentGeneratorService()
