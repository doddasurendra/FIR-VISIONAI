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
ANDHRA PRADESH LAW ENFORCEMENT & PROHIBITION EXCISE
INVESTIGATION CASE DIARY (SECTION 172 CrPC / BNSS)
======================================================
[STATE: DRAFT | EVIDENCE-GROUNDED INVESTIGATION DRAFT]

Case Crime No: {{ case.fir_number or 'UNASSIGNED — OFFICER ENTRY REQUIRED' }}
Jurisdiction Station: {{ case.station or 'Station Pending Verification' }}, {{ case.district }} District
Date of Entry: {{ entry_date }}
Investigating Officer: {{ officer.full_name }} ({{ officer.designation or 'Officer' }})

1. RECORDED CASE PARTICULARS:
   - Nature of Offence: {{ case.offence_nature or 'Not specified — verification required' }}
   - Date & Time of Offence: {{ case.offence_date or 'Under investigation' }}
   - Occurrence Location: {{ case.location_description or (case.village ~ ', ' ~ case.mandal if case.village else 'Location details under investigation') }}
   {% if case.contraband_type %}
   - Seized Property / Contraband: {{ case.contraband_type }}{% if case.seized_quantity %} (Quantity: {{ case.seized_quantity }} {{ case.seized_unit or 'units' }}){% endif %}
   {% else %}
   - Seized Property / Contraband: None recorded in primary FIR
   {% endif %}
   - Conveyance / Vehicle Details: {{ case.vehicle_details or 'None recorded' }}

2. APPLICABLE STATUTORY PROVISIONS:
   {% for sec in sections %}
   - {{ sec.act_name }} {{ sec.section_number }}: {{ sec.section_title }} [{{ sec.officer_decision }}]
   {% else %}
   - Statutory provisions subject to ongoing investigation and officer confirmation.
   {% endfor %}

3. INVESTIGATION RECORD & PRELIMINARY FACTS:
   {% if case.narrative %}
   {{ case.narrative }}
   {% else %}
   - Initial FIR registered based on incident report. Detailed investigative steps pending recording.
   {% endif %}

4. VERIFICATION STATUS & PENDING ACTIONS:
   {% if not case.witnesses_summary %}
   - [ACTION NEEDED] Examination of eyewitnesses and recording of Section 161 CrPC / BNSS statements.
   {% endif %}
   {% if case.contraband_type and not case.seized_quantity %}
   - [ACTION NEEDED] Exact quantification and chemical/forensic examination report.
   {% endif %}
   {% if case.vehicle_details %}
   - [ACTION NEEDED] Verification of conveyance ownership records from Transport Department.
   {% endif %}
   - Production of case diary before jurisdictional magistrate as per statutory timeline.

DRAFT PREPARED ON: {{ generation_time }}
DISCLAIMER: AI-Assisted evidence draft prepared from recorded case facts. Requires official signature and review.
"""

CHARGESHEET_TEMPLATE = """
{% if is_incomplete %}
================================================================================
DRAFT CANNOT BE COMPLETED — ADDITIONAL VERIFIED INFORMATION REQUIRED
================================================================================
Case Crime No: {{ case.fir_number or 'MISSING' }}
Station: {{ case.station or 'MISSING' }}, {{ case.district or 'MISSING' }} District

The formal chargesheet / final report under Section 173 CrPC / 193 BNSS cannot
be compiled because mandatory verified case information is missing:
{% for field in missing_fields %}
  * {{ field }}
{% endfor %}

Please verify and complete the missing case details before generating the court chargesheet.
{% else %}
IN THE COURT OF THE JUDICIAL MAGISTRATE OF FIRST CLASS
FINAL POLICE / DEPARTMENTAL REPORT UNDER SECTION 173 CrPC / 193 BNSS
==================================================================
[DEPARTMENTAL WORKING DRAFT — REVIEWS AND APPROVALS REQUIRED]

State of Andhra Pradesh (Through Station: {{ case.station }})
Versus
Accused Persons

1. Crime Details:
   - Case Crime No: {{ case.fir_number }}
   - Year: {{ case.year }}
   - Nature of Offence: {{ case.offence_nature }}
   - Occurrence Location: {{ case.location_description or (case.village ~ ', ' ~ case.mandal if case.village else 'Jurisdiction area') }}

2. Statutory Charges:
   {% for sec in sections %}
   * {{ sec.act_name }} {{ sec.section_number }} ({{ sec.section_title }})
   {% else %}
   * Applicable penal sections subject to judicial submission.
   {% endfor %}

3. Prosecution Facts (Grounded in Verified Case Record):
   {{ case.narrative or 'Facts as recorded in initial First Information Report.' }}

4. Seized Material Objects / Evidence:
   {% if case.contraband_type %}
   - M.O. 1: {{ case.contraband_type }}{% if case.seized_quantity %} ({{ case.seized_quantity }} {{ case.seized_unit or 'units' }}){% endif %}
   {% else %}
   - M.O. 1: No physical contraband / property seized in this case.
   {% endif %}
   {% if case.vehicle_details %}
   - M.O. 2: Conveyance {{ case.vehicle_details }}
   {% endif %}

5. Witnesses for Prosecution:
   - L.W. 1: {{ case.seizing_officer_name or officer.full_name }} (Complainant / Investigating Officer)
   {% if case.witnesses_summary %}
   - Additional Witnesses: {{ case.witnesses_summary }}
   {% else %}
   - Independent witnesses: Subject to Section 161 statements during trial.
   {% endif %}

PRAYER: It is humbly prayed that the Hon'ble Court may be pleased to take cognizance of the offence against the accused and conduct trial in accordance with law.

Prepared by: {{ officer.full_name }} ({{ officer.designation or 'Investigating Officer' }})
Date of Draft: {{ entry_date }}
{% endif %}
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

        # Evaluate completeness for court chargesheet
        missing_fields = []
        if not case.fir_number or case.fir_number.strip().upper() in ("UNKNOWN", "PENDING", ""):
            missing_fields.append("FIR Crime Number (MANDATORY)")
        if not case.district or case.district.strip().upper() in ("UNKNOWN", ""):
            missing_fields.append("District Jurisdiction (MANDATORY)")
        if not case.station or case.station.strip().upper() in ("UNKNOWN", ""):
            missing_fields.append("Police / Excise Station Jurisdiction (MANDATORY)")
        if not case.offence_nature or len(case.offence_nature.strip()) < 5:
            missing_fields.append("Specific Offence Description & Act Ingredients (MANDATORY)")
        if not sections or not any(s.officer_decision == "ACCEPTED" for s in sections):
            missing_fields.append("Verified Legal Penal Sections (Officer Acceptance Required)")

        is_incomplete = (len(missing_fields) > 0 and doc_type == "CHARGESHEET")

        template_str = CASE_DIARY_TEMPLATE if doc_type == "CASE_DIARY" else CHARGESHEET_TEMPLATE
        template = Template(template_str)
        rendered_content = template.render(
            case=case,
            sections=sections,
            officer=user,
            entry_date=datetime.utcnow().strftime("%d-%m-%Y"),
            generation_time=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            is_incomplete=is_incomplete,
            missing_fields=missing_fields
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
