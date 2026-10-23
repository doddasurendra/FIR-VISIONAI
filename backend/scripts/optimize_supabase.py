import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import engine
from sqlalchemy import text

async def main():
    async with engine.connect() as conn:
        print("1. Checking pg_trgm extension...")
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
            await conn.commit()
            print("   pg_trgm extension enabled successfully.")
        except Exception as e:
            print(f"   Note on pg_trgm: {e}")

        print("\n2. Creating performance indexes in Supabase...")
        indexes = [
            # Deduplication composite index
            ("idx_docs_hash_status", "CREATE INDEX IF NOT EXISTS idx_docs_hash_status ON documents (file_hash, ingestion_status);"),
            # Jurisdiction + archive composite index for cases
            ("idx_cases_dist_stn_arch", "CREATE INDEX IF NOT EXISTS idx_cases_dist_stn_arch ON cases (district, station, is_archived);"),
            # Case status + jurisdiction composite
            ("idx_cases_dist_status", "CREATE INDEX IF NOT EXISTS idx_cases_dist_status ON cases (district, status);"),
            # Extraction runs document lookup
            ("idx_ext_runs_doc_status", "CREATE INDEX IF NOT EXISTS idx_ext_runs_doc_status ON extraction_runs (document_id, status);"),
            # GIN trigram indexes for fast keyword search in RAG
            ("idx_legal_corpus_trgm_act", "CREATE INDEX IF NOT EXISTS idx_legal_corpus_trgm_act ON legal_corpus USING gin (act_name gin_trgm_ops);"),
            ("idx_legal_corpus_trgm_sec", "CREATE INDEX IF NOT EXISTS idx_legal_corpus_trgm_sec ON legal_corpus USING gin (section_title gin_trgm_ops);"),
            ("idx_doc_chunks_trgm", "CREATE INDEX IF NOT EXISTS idx_doc_chunks_trgm ON document_chunks USING gin (chunk_text gin_trgm_ops);"),
        ]

        for name, sql in indexes:
            try:
                await conn.execute(text(sql))
                await conn.commit()
                print(f"   [CREATED/VERIFIED] {name}")
            except Exception as e:
                print(f"   [ERROR] {name}: {e}")

        print("\n3. Verifying updated indexes on core tables...")
        res = await conn.execute(text("""
            SELECT tablename, indexname 
            FROM pg_indexes 
            WHERE schemaname = 'public' AND indexname LIKE 'idx_%'
            ORDER BY tablename, indexname;
        """))
        for row in res.fetchall():
            print(f"   {row[0]} -> {row[1]}")

if __name__ == "__main__":
    asyncio.run(main())
