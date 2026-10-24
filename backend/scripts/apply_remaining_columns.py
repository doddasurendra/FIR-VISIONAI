import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SyncSessionLocal
from sqlalchemy import text

db = SyncSessionLocal()

columns_to_add = [
    ("incident_place_raw", "TEXT"),
    ("incident_location_normalized", "TEXT"),
    ("incident_village", "VARCHAR(255)"),
    ("incident_mandal", "VARCHAR(255)"),
    ("incident_district", "VARCHAR(255)"),
    ("incident_state", "VARCHAR(100) DEFAULT 'Andhra Pradesh'"),
    ("incident_pincode", "VARCHAR(20)"),
    ("incident_landmark", "VARCHAR(255)"),
    ("incident_latitude", "DOUBLE PRECISION"),
    ("incident_longitude", "DOUBLE PRECISION"),
    ("incident_location_confidence", "DOUBLE PRECISION DEFAULT 0.0"),
    ("incident_location_source_doc_id", "VARCHAR(36)"),
    ("incident_location_source_page", "INTEGER"),
    ("incident_location_evidence_passage", "TEXT"),
    ("incident_location_geocoder_status", "VARCHAR(50) DEFAULT 'UNRESOLVED'"),
    ("incident_location_verified", "BOOLEAN DEFAULT FALSE"),
    ("incident_location_verified_by", "VARCHAR(255)"),
    ("incident_location_verified_at", "TIMESTAMP WITH TIME ZONE"),
]

for col_name, col_type in columns_to_add:
    try:
        sql = f"ALTER TABLE cases ADD COLUMN IF NOT EXISTS {col_name} {col_type};"
        db.execute(text(sql))
        db.commit()
        print(f"Added or verified column: {col_name}")
    except Exception as e:
        db.rollback()
        print(f"Error adding {col_name}: {e}")

print("\nVerifying all columns on cases table:")
res = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'cases' ORDER BY ordinal_position")).fetchall()
col_names = [r[0] for r in res]
for col_name, _ in columns_to_add:
    print(f" - {col_name}: {'PRESENT' if col_name in col_names else 'MISSING'}")
