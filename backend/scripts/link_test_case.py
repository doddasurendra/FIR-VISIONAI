import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import engine
from sqlalchemy import text

async def link_case():
    async with engine.connect() as conn:
        c_res = await conn.execute(text("SELECT id, fir_number, district, station FROM cases WHERE fir_number = 'CR-99/2024' LIMIT 1"))
        c_row = c_res.fetchone()
        if not c_row:
            # fallback to any case
            c_res = await conn.execute(text("SELECT id, fir_number, district, station FROM cases LIMIT 1"))
            c_row = c_res.fetchone()
            
        case_id = c_row[0]
        fir_no = c_row[1]
        dist = c_row[2]
        stn = c_row[3]
        print(f"Linking fir_c41834.png to Case {fir_no} ({dist}) [ID: {case_id}]")
        
        await conn.execute(text(f"""
            UPDATE documents 
            SET case_id = '{case_id}',
                district = :dist,
                station = :stn,
                document_title = 'FIR Evidence Photograph - {fir_no}',
                doc_category = 'FIR'
            WHERE original_filename LIKE '%c41834%'
        """), {"dist": dist, "stn": stn})
        await conn.commit()
        print("Updated fir_c41834.png with case_id and jurisdiction!")

if __name__ == "__main__":
    asyncio.run(link_case())
