"""
Migration: Widen legal_corpus column sizes for version, jurisdiction, effective_date, repeal_date, source_gazette.
Also count current document categories.
"""
import asyncio
import sys
sys.path.insert(0, ".")
from app.database import AsyncSessionLocal
from sqlalchemy import text

async def main():
    async with AsyncSessionLocal() as s:
        # Check column sizes
        res = await s.execute(text("""
            SELECT column_name, character_maximum_length, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'legal_corpus' 
            AND column_name IN ('version', 'jurisdiction', 'effective_date', 'repeal_date', 'source_gazette', 'verification_status', 'section_number', 'act_name')
            ORDER BY column_name
        """))
        print('legal_corpus column sizes:')
        for r in res.all():
            print(f'  {r[0]}: {r[2]}({r[1]})')
        
        # Document counts
        res2 = await s.execute(text("SELECT doc_category, COUNT(*) FROM documents WHERE is_archived = false GROUP BY doc_category ORDER BY doc_category"))
        print('\nDocument counts by category:')
        for r in res2.all():
            print(f'  {r[0]}: {r[1]}')
        
        # Legal corpus sections
        res3 = await s.execute(text('SELECT COUNT(*) FROM legal_corpus'))
        print(f'\nLegal corpus total sections: {res3.scalar()}')
        
        # Widen columns 
        print('\nRunning ALTER TABLE migrations...')
        migrations = [
            "ALTER TABLE legal_corpus ALTER COLUMN version TYPE VARCHAR(100)",
            "ALTER TABLE legal_corpus ALTER COLUMN jurisdiction TYPE VARCHAR(100)",
            "ALTER TABLE legal_corpus ALTER COLUMN effective_date TYPE VARCHAR(50)",
            "ALTER TABLE legal_corpus ALTER COLUMN repeal_date TYPE VARCHAR(50)",
            "ALTER TABLE legal_corpus ALTER COLUMN verification_status TYPE VARCHAR(30)",
            "ALTER TABLE legal_corpus ALTER COLUMN source_gazette TYPE VARCHAR(500)",
        ]
        for sql in migrations:
            try:
                await s.execute(text(sql))
                print(f'  OK: {sql}')
            except Exception as e:
                print(f'  SKIP (already done?): {e}')
        await s.commit()
        print('\nMigration complete.')

asyncio.run(main())
