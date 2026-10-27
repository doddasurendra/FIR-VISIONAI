import os
import sys
import json
from datetime import datetime, timedelta

# Add backend to sys.path
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, backend_path)

from app.database import setup_database_sync, SyncSessionLocal
from app.models.user import User
from app.models.case import Case, CaseField
from app.models.entity import Entity, EntityMention, GraphEdge
from app.models.legal import LegalCorpus, CaseLegalSection
from app.models.document import Document, DocumentPage, DocumentChunk
from app.services.auth import hash_password
from app.services.text_processing import split_text
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import sqlite3

def generate_synthetic_demo_pdf(output_path: str):
    """Generate a realistic 3-page synthetic Andhra Pradesh Excise FIR PDF for grounded RAG tests."""
    c = canvas.Canvas(output_path, pagesize=letter)
    width, height = letter

    # Page 1: General Crime Registration & Location Details
    c.setFont("Helvetica-Bold", 14)
    c.drawString(60, height - 60, "GOVERNMENT OF ANDHRA PRADESH - EXCISE DEPARTMENT")
    c.setFont("Helvetica-Bold", 11)
    c.drawString(60, height - 80, "FIRST INFORMATION REPORT (u/s 154 CrPC / 173 BNSS)")
    c.drawString(60, height - 95, "Crime No: FIR-2024-KNL-0042 | Year: 2024 | Station: Kurnool Town Station")
    c.line(60, height - 105, width - 60, height - 105)

    c.setFont("Helvetica-Bold", 10)
    c.drawString(60, height - 130, "1. OCCURRENCE OF OFFENCE:")
    c.setFont("Helvetica", 9)
    c.drawString(80, height - 148, "Date of Offence: 14th August 2024 at 21:30 Hours")
    c.drawString(80, height - 164, "Place of Occurrence: Kallur Toll Plaza, NH-44 Highway, Kurnool District")
    c.drawString(80, height - 180, "Direction and distance from Station: 6 KM South-West")

    c.setFont("Helvetica-Bold", 10)
    c.drawString(60, height - 210, "2. COMPLAINANT / INFORMANT DETAILS:")
    c.setFont("Helvetica", 9)
    c.drawString(80, height - 228, "Name: K. Venkateshwarlu, Sub-Inspector of Prohibition & Excise")
    c.drawString(80, height - 244, "Badge No: EXC-KNL-104, Station: Kurnool Town Station")

    c.setFont("Helvetica-Bold", 10)
    c.drawString(60, height - 275, "3. ACCUSED PERSON PARTICULARS IDENTIFIED AT SCENE:")
    c.setFont("Helvetica", 9)
    c.drawString(80, height - 293, "A-1: Ramu Naidu, Male, Age 38 years, Residing at Kallur Village, Kurnool District.")
    c.drawString(80, height - 309, "A-2: Someshwar Rao, Male, Age 32 years, Residing at Joharapuram, Kurnool District.")
    
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(60, 40, "Physical PDF Page 1 of 3 - FIR-2024-KNL-0042")
    c.showPage()

    # Page 2: Contraband Seizure and Vehicle Details
    c.setFont("Helvetica-Bold", 12)
    c.drawString(60, height - 60, "PROPERTY SEIZURE & CONTRABAND PARTICULARS (PAGE 2)")
    c.line(60, height - 70, width - 60, height - 70)

    c.setFont("Helvetica-Bold", 10)
    c.drawString(60, height - 100, "4. DETAILS OF SEIZED CONTRABAND LIQUOR:")
    c.setFont("Helvetica", 9)
    c.drawString(80, height - 120, "Contraband Category: Illicit Distilled (ID) Arrack / Spurious Liquor.")
    c.drawString(80, height - 138, "Total Quantity Seized: 45.0 Litres packed in 9 black polythene sachets of 5 Litres each.")
    c.drawString(80, height - 156, "Estimated Market Value: Rs. 22,500/- (Rupees Twenty Two Thousand Five Hundred only).")
    c.drawString(80, height - 174, "Chemical Smell: Strong pungent smell of fermented jaggery wash and toxic heads.")

    c.setFont("Helvetica-Bold", 10)
    c.drawString(60, height - 210, "5. CONVEYANCE / VEHICLE USED IN COMMISSION:")
    c.setFont("Helvetica", 9)
    c.drawString(80, height - 230, "Vehicle Type: Three-Wheeler Passenger Auto Rickshaw (Yellow/Black).")
    c.drawString(80, height - 248, "Vehicle Registration Number: AP21TY4567.")
    c.drawString(80, height - 266, "Chassis Number: MA1ER5678X90123.")
    c.drawString(80, height - 284, "Registered Owner: Ramu Naidu (Accused No. 1).")

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(60, 40, "Physical PDF Page 2 of 3 - FIR-2024-KNL-0042")
    c.showPage()

    # Page 3: Witness Statements and Recorded Legal Sections
    c.setFont("Helvetica-Bold", 12)
    c.drawString(60, height - 60, "PANCHANAMA WITNESSES & STATUTORY SECTIONS (PAGE 3)")
    c.line(60, height - 70, width - 60, height - 70)

    c.setFont("Helvetica-Bold", 10)
    c.drawString(60, height - 100, "6. INDEPENDENT MEDIATOR WITNESSES:")
    c.setFont("Helvetica", 9)
    c.drawString(80, height - 120, "Witness 1: V. Krishnaiah, Son of Narayana, Age 44, Shopkeeper, Kallur.")
    c.drawString(80, height - 138, "Witness 2: M. Subba Rao, Son of Venkataram, Age 40, Agriculturist, Kallur.")

    c.setFont("Helvetica-Bold", 10)
    c.drawString(60, height - 170, "7. RECORDED SECTIONS OF LAW:")
    c.setFont("Helvetica", 9)
    c.drawString(80, height - 190, "Recorded Statutory Provision: Andhra Pradesh Excise Act, 1968 - Section 34(a).")
    c.drawString(80, height - 208, "Penal Section for Vehicle Forfeiture: Andhra Pradesh Excise Act, 1968 - Section 45.")

    c.setFont("Helvetica-Bold", 10)
    c.drawString(60, height - 240, "8. INVESTIGATING OFFICER REMARKS:")
    c.setFont("Helvetica", 9)
    c.drawString(80, height - 260, "Accused failed to produce any transport permit or valid government authorization.")
    c.drawString(80, height - 276, "Sample bottles marked 'S1' and 'S2' drawn for chemical analysis.")

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(60, 40, "Physical PDF Page 3 of 3 - FIR-2024-KNL-0042")
    c.showPage()

    c.save()
    print("Synthetic demonstration PDF generated at", output_path)

def seed_demo_database():
    setup_database_sync()
    session = SyncSessionLocal()
    
    try:
        # Check if cases already exist
        if session.query(Case).count() > 0:
            print("Database already contains cases. Skipping case seed.")
            return

        # 1. Create Synthetic Demo Cases
        c1 = Case(
            fir_number="FIR-2024-KNL-0042",
            year=2024,
            district="Kurnool",
            station="Kurnool Town Station",
            mandal="Kurnool Urban",
            village="Kallur",
            location_description="Near Kallur Toll Plaza, NH-44",
            offence_date=datetime(2024, 8, 14, 21, 30),
            detection_date=datetime(2024, 8, 14, 21, 45),
            registration_date=datetime(2024, 8, 15, 9, 0),
            offence_nature="Illicit Distillation & Transport of ID Liquor",
            contraband_type="ID Liquor",
            seized_quantity=45.0,
            seized_unit="Litres",
            vehicle_details="Auto AP21TY4567",
            seizing_officer_name="K. Venkateshwarlu",
            seizing_officer_rank="Excise Sub-Inspector",
            narrative="Raid conducted at Kallur Toll Plaza. Intercepted passenger auto transporting 45 litres of illicit distilled liquor without permit. Accused Ramu Naidu and Someshwar Rao arrested.",
            status="IN_REVIEW",
            created_by="system_demo"
        )

        c2 = Case(
            fir_number="FIR-2024-KNL-0019",
            year=2024,
            district="Kurnool",
            station="Kurnool Town Station",
            mandal="Alur",
            village="Halaharvi",
            location_description="Border Check Post, Karnataka Border",
            offence_date=datetime(2024, 5, 10, 18, 0),
            detection_date=datetime(2024, 5, 10, 18, 30),
            registration_date=datetime(2024, 5, 11, 10, 0),
            offence_nature="Smuggling of Non-Duty Paid Liquor (NDPL)",
            contraband_type="Non-Duty Paid Liquor",
            seized_quantity=120.0,
            seized_unit="Bottles",
            vehicle_details="Hero Splendor AP21AB9876",
            seizing_officer_name="K. Venkateshwarlu",
            seizing_officer_rank="Excise Sub-Inspector",
            narrative="Border interception of 120 bottles of Karnataka liquor transported illegally into Andhra Pradesh without excise duty stamp. Accused Ramu Naidu was driving the two-wheeler.",
            status="APPROVED",
            created_by="system_demo"
        )

        c3 = Case(
            fir_number="FIR-2024-GNT-0088",
            year=2024,
            district="Guntur",
            station="Guntur East Station",
            mandal="Tenali",
            village="Tenali Rural",
            location_description="Tenali Railway Feeder Road",
            offence_date=datetime(2024, 9, 2, 14, 15),
            detection_date=datetime(2024, 9, 2, 14, 30),
            registration_date=datetime(2024, 9, 2, 17, 0),
            offence_nature="Commercial Transport of Ganja (Cannabis)",
            contraband_type="Ganja (Cannabis)",
            seized_quantity=18.5,
            seized_unit="Kgs",
            vehicle_details="Maruti Swift AP07CK5521",
            seizing_officer_name="P. Sambasiva Rao",
            seizing_officer_rank="Excise Inspector",
            narrative="Seizure of 18.5 kilograms of dry ganja in vehicle boot space during joint highway surveillance. Accused Sheikh Basha apprehended.",
            status="IN_REVIEW",
            created_by="system_demo"
        )

        c4 = Case(
            fir_number="FIR-2023-VSP-0112",
            year=2023,
            district="Visakhapatnam",
            station="Anakapalle Station",
            mandal="Kasimkota",
            village="Bayyavaram",
            location_description="Highway dhaba junction",
            offence_date=datetime(2023, 11, 20, 22, 0), # Incident occurred in 2023 (Pre-BNS era -> Historical IPC applies!)
            detection_date=datetime(2023, 11, 20, 22, 30),
            registration_date=datetime(2023, 11, 21, 8, 30),
            offence_nature="Rash driving and Spurious Liquor Transport",
            contraband_type="Spurious Toddy Adulterated",
            seized_quantity=60.0,
            seized_unit="Litres",
            vehicle_details="Tata Ace AP31TC1122",
            seizing_officer_name="M. Appalaraju",
            seizing_officer_rank="Sub-Inspector",
            narrative="Vehicle collision during high speed evasion carrying 60 litres of chemical adulterated toddy. Incident occurred prior to BNS enforcement; historical IPC 279 and AP Excise Act 34(a) apply.",
            status="APPROVED",
            created_by="system_demo"
        )

        session.add_all([c1, c2, c3, c4])
        session.flush()

        # 2. Create Entities & Mentions
        # Canonical Person 1: Ramu Naidu (Repeat Offender in c1 & c2)
        e1 = Entity(
            canonical_name="Ramu Naidu",
            entity_type="PERSON",
            aliases_json=json.dumps(["R. Naidu", "Kallur Ramu"]),
            attributes_json=json.dumps({"age": 38, "village": "Kallur", "district": "Kurnool", "phone": "9848012345"}),
            risk_score=0.82,
            risk_factors_json=json.dumps(["2 recorded excise offences in 2024", "Transport of commercial volume ID liquor", "Vehicle owner AP21TY4567"]),
            verification_status="CONFIRMED"
        )
        # Duplicate candidate entity for review queue: Rama Naidu
        e1_dup = Entity(
            canonical_name="Rama Naidu",
            entity_type="PERSON",
            aliases_json="[]",
            attributes_json=json.dumps({"age": 39, "village": "Kallur", "district": "Kurnool", "phone": "9848012345"}),
            risk_score=0.45,
            verification_status="REVIEW_PENDING"
        )
        # Person 2: Someshwar Rao (Co-accused with Ramu Naidu)
        e2 = Entity(
            canonical_name="Someshwar Rao",
            entity_type="PERSON",
            aliases_json="[]",
            attributes_json=json.dumps({"age": 32, "village": "Joharapuram", "district": "Kurnool"}),
            risk_score=0.35,
            verification_status="CONFIRMED"
        )
        # Person 3: Sheikh Basha (Guntur case)
        e3 = Entity(
            canonical_name="Sheikh Basha",
            entity_type="PERSON",
            aliases_json="[]",
            attributes_json=json.dumps({"age": 29, "district": "Guntur"}),
            risk_score=0.40,
            verification_status="CONFIRMED"
        )
        # Vehicle 1: Auto AP21TY4567
        v1 = Entity(
            canonical_name="Auto AP21TY4567",
            entity_type="VEHICLE",
            aliases_json="[]",
            attributes_json=json.dumps({"registration_number": "AP21TY4567", "vehicle_type": "Auto Rickshaw"}),
            risk_score=0.75,
            verification_status="CONFIRMED"
        )

        session.add_all([e1, e1_dup, e2, e3, v1])
        session.flush()

        # Mentions
        m1 = EntityMention(entity_id=e1.id, case_id=c1.id, mention_text="Ramu Naidu", role_in_case="ACCUSED")
        m2 = EntityMention(entity_id=e2.id, case_id=c1.id, mention_text="Someshwar Rao", role_in_case="ACCUSED")
        m3 = EntityMention(entity_id=v1.id, case_id=c1.id, mention_text="Auto AP21TY4567", role_in_case="VEHICLE_USED")
        m4 = EntityMention(entity_id=e1.id, case_id=c2.id, mention_text="Ramu Naidu", role_in_case="ACCUSED")
        m5 = EntityMention(entity_id=e3.id, case_id=c3.id, mention_text="Sheikh Basha", role_in_case="ACCUSED")

        session.add_all([m1, m2, m3, m4, m5])

        # Graph Edges
        edge1 = GraphEdge(source_entity_id=e1.id, target_entity_id=e2.id, edge_type="CO_ACCUSED", case_id=c1.id, weight=1.0)
        edge2 = GraphEdge(source_entity_id=e1.id, target_entity_id=v1.id, edge_type="VEHICLE_OWNED", case_id=c1.id, weight=1.0)
        edge3 = GraphEdge(source_entity_id=e2.id, target_entity_id=v1.id, edge_type="VEHICLE_USED", case_id=c1.id, weight=0.8)

        session.add_all([edge1, edge2, edge3])

        # 3. Create Case Fields
        f1 = CaseField(case_id=c1.id, field_name="contraband_type", original_value="ID Liquor", normalized_value="ID Liquor", confidence_score=0.98, verification_status="VERIFIED")
        f2 = CaseField(case_id=c1.id, field_name="seized_quantity", original_value="45.0 Litres", normalized_value="45.0", confidence_score=0.95, verification_status="VERIFIED")
        f3 = CaseField(case_id=c1.id, field_name="vehicle_details", original_value="Auto AP21TY4567", normalized_value="Auto AP21TY4567", confidence_score=0.99, verification_status="VERIFIED")

        session.add_all([f1, f2, f3])
        session.commit()
        print("Synthetic demo cases and entity relationships committed.")

        # 4. Generate & Ingest 3-page FIR PDF for c1
        evidence_dir = os.path.join(os.path.dirname(__file__), "..", "data", "evidence")
        pdf_path = os.path.join(evidence_dir, "FIR-2024-KNL-0042_Official.pdf")
        generate_synthetic_demo_pdf(pdf_path)

        # Ingest PDF into database tables and FTS5
        from app.services.pdf_pipeline import compute_sha256
        file_hash = compute_sha256(pdf_path)
        doc = Document(
            case_id=c1.id,
            original_filename="FIR-2024-KNL-0042_Official.pdf",
            stored_path=pdf_path,
            file_hash=file_hash,
            mime_type="application/pdf",
            physical_page_count=3,
            ingestion_status="COMPLETED",
            created_by="system_demo"
        )
        session.add(doc)
        session.commit()

        # Insert 3 physical pages and chunks
        db_path = session.bind.url.database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        p1_text = (
            "GOVERNMENT OF ANDHRA PRADESH - EXCISE DEPARTMENT. FIRST INFORMATION REPORT Crime No: FIR-2024-KNL-0042. "
            "Station: Kurnool Town Station. Date of Offence: 14th August 2024 at 21:30 Hours. "
            "Place of Occurrence: Kallur Toll Plaza, NH-44 Highway, Kurnool District. "
            "Complainant: K. Venkateshwarlu, Sub-Inspector. "
            "Accused A-1: Ramu Naidu, Male, Age 38 years, Residing at Kallur Village, Kurnool District. "
            "Accused A-2: Someshwar Rao, Male, Age 32 years, Residing at Joharapuram, Kurnool District."
        )
        p2_text = (
            "PROPERTY SEIZURE & CONTRABAND PARTICULARS (PAGE 2). "
            "Contraband Category: Illicit Distilled (ID) Arrack / Spurious Liquor. "
            "Total Quantity Seized: 45.0 Litres packed in 9 black polythene sachets of 5 Litres each. "
            "Estimated Market Value: Rs. 22,500/-. Strong pungent smell of fermented jaggery wash. "
            "Conveyance Vehicle Used: Three-Wheeler Passenger Auto Rickshaw AP21TY4567. "
            "Chassis Number: MA1ER5678X90123. Registered Owner: Ramu Naidu."
        )
        p3_text = (
            "PANCHANAMA WITNESSES & STATUTORY SECTIONS (PAGE 3). "
            "Witness 1: V. Krishnaiah, Son of Narayana, Age 44, Shopkeeper, Kallur. "
            "Witness 2: M. Subba Rao, Son of Venkataram, Age 40, Agriculturist, Kallur. "
            "Recorded Statutory Provision: Andhra Pradesh Excise Act, 1968 - Section 34(a). "
            "Penal Section for Vehicle Forfeiture: Andhra Pradesh Excise Act, 1968 - Section 45. "
            "Sample bottles marked S1 and S2 drawn for chemical analysis."
        )

        for p_num, p_text in [(1, p1_text), (2, p2_text), (3, p3_text)]:
            dp = DocumentPage(
                document_id=doc.id,
                physical_page_number=p_num,
                printed_page_number=p_num,
                raw_text=p_text,
                ocr_applied=False,
                ocr_confidence=1.0
            )
            session.add(dp)

            chunks, search_from = [], 0
            for idx, piece in enumerate(split_text(p_text, max_chars=300, overlap=50)):
                start = p_text.find(piece, search_from)
                start = start if start >= 0 else search_from
                chunks.append({"chunk_index": idx, "chunk_text": piece, "char_start": start, "char_end": start + len(piece)})
                search_from = start + 1
            for c in chunks:
                dc = DocumentChunk(
                    document_id=doc.id,
                    physical_page_number=p_num,
                    chunk_index=c["chunk_index"],
                    chunk_text=c["chunk_text"],
                    char_start=c["char_start"],
                    char_end=c["char_end"]
                )
                session.add(dc)
                cursor.execute(
                    "INSERT INTO document_chunks_fts (chunk_id, document_id, physical_page_number, chunk_text) VALUES (?, ?, ?, ?)",
                    (dc.id, doc.id, p_num, c["chunk_text"])
                )

        conn.commit()
        conn.close()
        session.commit()
        print("Demo multi-page FIR PDF indexed into FTS5 with physical pages 1, 2, and 3.")

    finally:
        session.close()

if __name__ == "__main__":
    seed_demo_database()
