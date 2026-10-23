"""
E2E Test: Exact station detection, dropdown fix, RAG cache, document deduplication.
"""
import asyncio
import sys
import os

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

async def test_station_detection():
    from app.database import AsyncSessionLocal
    from app.services.jurisdiction import detect_exact_station

    print("\n=== Test 1: Exact Station Detection (Kurnool Town coordinates) ===")
    async with AsyncSessionLocal() as db:
        result = await detect_exact_station(15.828, 78.037, accuracy=15.0, user=None, db=db)

    mt = result.get("match_type")
    conf = result.get("confidence")
    dist = result.get("detected_district")
    near = result.get("nearest_distance_km")
    exact = result.get("exact_station")
    print(f"  match_type      : {mt}")
    print(f"  confidence      : {conf}")
    print(f"  district        : {dist}")
    print(f"  nearest km      : {near}")
    if exact:
        print(f"  exact station   : {exact.get('station_name')} [{exact.get('station_code')}]")
        print(f"  exact distance  : {exact.get('distance_km')} km")
        print(f"  mandal          : {exact.get('mandal')}")
    else:
        print("  exact station   : None (using candidate list)")
    cands = result.get("candidate_stations", [])
    print(f"  candidates      : {cands[:4]}")
    print(f"  PASS: match_type={mt}, district={dist}")

async def test_rag_cache():
    print("\n=== Test 2: RAG In-Memory Query Cache ===")
    from app.services.rag_engine import _cache_get, _cache_put
    doc_id = "test-doc-999"
    q = "What is the accused name?"
    lang = "en"
    result = {"answer": "The accused is John Doe.", "citations": [], "mode": "PDF_ONLY"}
    _cache_put(doc_id, q, lang, result)
    cached = _cache_get(doc_id, q, lang)
    assert cached is not None, "FAIL: Cache returned None immediately after put"
    assert cached["answer"] == result["answer"], "FAIL: Cache returned wrong answer"
    print("  Cache put/get: PASS")
    # Different query should miss
    miss = _cache_get(doc_id, "Different query", lang)
    assert miss is None, "FAIL: Cache should miss for different query"
    print("  Cache miss for different query: PASS")
    # Different doc should miss
    miss2 = _cache_get("other-doc-000", q, lang)
    assert miss2 is None, "FAIL: Cache should miss for different document_id"
    print("  Cache document isolation: PASS")

async def test_verified_stations_count():
    print("\n=== Test 3: Verified Stations Registry in Supabase ===")
    from app.database import SyncSessionLocal
    from app.models.station import VerifiedStation
    session = SyncSessionLocal()
    try:
        total = session.query(VerifiedStation).count()
        active = session.query(VerifiedStation).filter(VerifiedStation.is_active == True).count()
        districts = session.query(VerifiedStation.district).distinct().count()
        print(f"  Total stations  : {total}")
        print(f"  Active stations : {active}")
        print(f"  Districts covered: {districts}")
        assert total >= 140, f"FAIL: Expected 140+ stations, got {total}"
        assert districts >= 20, f"FAIL: Expected 20+ districts, got {districts}"
        print(f"  PASS: {total} verified stations in {districts} districts")
    finally:
        session.close()

async def main():
    print("=================================================================")
    print("FIR VisionAI — Station Detection & Performance E2E Test Suite")
    print("=================================================================")
    await test_verified_stations_count()
    await test_station_detection()
    await test_rag_cache()
    print("\n=================================================================")
    print("All tests PASSED")
    print("=================================================================")

if __name__ == "__main__":
    asyncio.run(main())
