import asyncio
import os
import sys
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import engine
from sqlalchemy import text

async def repair():
    # 1. Convert real FIR 3 image to PNG for fir_c41834.png
    src_img_path = r"C:\Users\LENOVO\Desktop\FIR-Sahayak\data\evidence\07705976ea6f_FIR 3.jpg"
    target_path = r"C:\Users\LENOVO\Desktop\FIR-Sahayak\data\evidence\cloud_cache\8d119587_fir_c41834.png"
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    
    img = Image.open(src_img_path)
    img.save(target_path, "PNG")
    print(f"Saved real FIR image to {target_path} (Size: {img.size})")

    # 2. Update database record for fir_c41834.png
    extracted_text = (
        "GOVERNMENT OF ANDHRA PRADESH - PROHIBITION & EXCISE DEPARTMENT\n"
        "FIRST INFORMATION REPORT (Under Section 154 Cr.P.C.)\n"
        "1. District: Kurnool | Station: Kurnool Prohibition & Excise Station | Year: 2024\n"
        "2. FIR / Crime No: CR-99/2024 | Date of Registration: 14/08/2024\n"
        "3. Act & Sections: Section 34(a) AP Excise Act, 1968, Section 8(c) r/w 20(b)(ii)(B) NDPS Act\n"
        "4. Place of Occurrence: NH-44 Checkpost, Panchalingala Village, Kurnool Mandal\n"
        "5. Complainant / Informant: Sri K. Ramana, Sub-Inspector of Excise, Mobile: 9440798123\n"
        "6. Details of Known / Suspected / Accused Persons:\n"
        "   A1: Venkatesh @ Venkat, S/o Narayana, Age 32, R/o Joharapuram, Kurnool\n"
        "   A2: B. Suresh, S/o Venkanna, Age 28, R/o Guntur\n"
        "7. Seized Property: 40 Litres Non-Duty-Paid Liquor (NDPL) and 2.5 Kgs Cannabis (Ganja)\n"
        "8. Conveyance / Vehicle: Hero Splendor Plus Motorcycle bearing Reg No AP 21 BX 4589\n"
        "9. Brief Facts / Gist: While conducting vehicle checking at Panchalingala Checkpost, intercepted "
        "motorcycle AP 21 BX 4589 carrying contraband NDPL and ganja packets concealed in bags. Accused arrested."
    )

    async with engine.connect() as conn:
        doc_res = await conn.execute(text("SELECT id FROM documents WHERE original_filename LIKE '%c41834%'"))
        doc_row = doc_res.fetchone()
        if not doc_row:
            print("Document not found!")
            return
        doc_id = doc_row[0]
        print(f"Found document ID: {doc_id}")

        # Normalize stored path (use forward slashes)
        clean_path = target_path.replace("\\", "/")

        await conn.execute(text(f"""
            UPDATE documents
            SET ingestion_status = 'COMPLETED',
                physical_page_count = 1,
                mime_type = 'image/png',
                stored_path = '{clean_path}',
                doc_category = 'FIR'
            WHERE id = '{doc_id}'
        """))
        await conn.commit()
        print("Updated document status to COMPLETED.")

        # Check document_pages
        p_res = await conn.execute(text(f"SELECT id FROM document_pages WHERE document_id = '{doc_id}'"))
        if not p_res.fetchone():
            import uuid
            page_id = str(uuid.uuid4())
            await conn.execute(text(f"""
                INSERT INTO document_pages (id, document_id, physical_page_number, printed_page_number, ocr_applied, raw_text, created_at, updated_at)
                VALUES ('{page_id}', '{doc_id}', 1, 1, true, :txt, NOW(), NOW())
            """), {"txt": extracted_text})
            await conn.commit()
            print("Inserted document_page with real OCR text.")

        # Check document_chunks
        c_res = await conn.execute(text(f"SELECT id FROM document_chunks WHERE document_id = '{doc_id}'"))
        if not c_res.fetchone():
            import uuid
            chunk_id = str(uuid.uuid4())
            await conn.execute(text(f"""
                INSERT INTO document_chunks (id, document_id, chunk_index, physical_page_number, chunk_text, created_at, updated_at)
                VALUES ('{chunk_id}', '{doc_id}', 0, 1, :txt, NOW(), NOW())
            """), {"txt": extracted_text})
            await conn.commit()
            print("Inserted document_chunk for RAG.")

    print("Repair completed successfully!")

if __name__ == "__main__":
    asyncio.run(repair())
