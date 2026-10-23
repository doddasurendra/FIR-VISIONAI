import asyncio
import time
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import AsyncSessionLocal
from app.services.analytics import analytics_service
from app.services.rag_engine import rag_engine
from app.models.user import User
from app.models.document import Document
from sqlalchemy import select

async def measure():
    print("=" * 60)
    print("FIR Sahayak Performance Benchmark")
    print("=" * 60)

    async with AsyncSessionLocal() as session:
        mock_user = User(
            id="bench-user-1",
            username="admin",
            role="STATE",
            district=None,
            station=None
        )

        # 1. Measure Analytics KPI Query time (Parallel vs Cached)
        print("\n[1] Testing Dashboard Analytics KPIs:")
        start = time.perf_counter()
        kpis_1 = await analytics_service.get_dashboard_kpis(user=mock_user, db=session)
        dur_1 = (time.perf_counter() - start) * 1000
        print(f"   First call (DB query execution): {dur_1:.2f} ms")
        print(f"   Total cases: {kpis_1.get('total_cases')}")

        start = time.perf_counter()
        kpis_2 = await analytics_service.get_dashboard_kpis(user=mock_user, db=session)
        dur_2 = (time.perf_counter() - start) * 1000
        print(f"   Second call (Cache HIT): {dur_2:.2f} ms")

        # 2. Get a sample document
        doc_res = await session.execute(select(Document).limit(1))
        sample_doc = doc_res.scalars().first()
        doc_id = sample_doc.id if sample_doc else "no-doc"

        # 3. Test RAG Legal Corpus retrieval time
        print(f"\n[2] Testing RAG Legal Corpus Retrieval (Targeted DB filter, doc_id={doc_id[:8]}...):")
        start = time.perf_counter()
        try:
            resp = await rag_engine.answer_fir_plus_legal(
                document_id=doc_id,
                query="What are the bail provisions and penalties under NDPS Act?",
                user=mock_user,
                db=session,
                language="en"
            )
            dur_rag = (time.perf_counter() - start)
            print(f"   Mode C RAG (FIR + Legal Corpus): {dur_rag:.2f} seconds")
            print(f"   Answer length: {len(resp.get('answer', ''))} chars")
        except Exception as e:
            print(f"   RAG test note: {e}")

        # 4. Test RAG second call (with caching/circuit breaker)
        print("\n[3] Testing RAG Legal Corpus Subsequent Call:")
        start = time.perf_counter()
        try:
            resp2 = await rag_engine.answer_fir_plus_legal(
                document_id=doc_id,
                query="What are the bail provisions and penalties under NDPS Act?",
                user=mock_user,
                db=session,
                language="en"
            )
            dur_rag2 = (time.perf_counter() - start)
            print(f"   Mode C RAG second call: {dur_rag2:.2f} seconds")
        except Exception as e:
            print(f"   RAG test note: {e}")

    print("\n" + "=" * 60)
    print("Benchmark complete!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(measure())
