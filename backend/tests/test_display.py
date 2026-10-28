"""
Dashboard: contraband seized is totalled per unit (litres, kg and bottles are never added together)
and every count stays within the user's jurisdiction; the FIR summary listing reads only summary status.
"""
from app.services.analytics import contraband_by_unit
from tests.test_knowledge_base_rag import auth, station_headers, state_headers  # noqa: F401


def test_contraband_is_totalled_per_unit():
    stats = contraband_by_unit([
        ("ID Liquor", "Litres", 2, 45.0), ("ID Liquor", "ltrs", 1, 5.0), ("Ganja", "kg", 1, 2.5),
        ("Ganja", "Litres", 1, 1.0), (None, None, 3, None),
    ])
    by = {s["contraband"]: s for s in stats}
    assert by["ID Liquor"]["quantities"] == [{"unit": "Litres", "total": 50.0}] and by["ID Liquor"]["cases"] == 3
    assert {q["unit"] for q in by["Ganja"]["quantities"]} == {"Kg", "Litres"}
    assert by["Ganja"]["total_quantity"] is None                       # mixed units are never summed
    assert by["Unknown"]["quantities"] == [] and stats[-1]["contraband"] == "Unknown"


def test_dashboard_counts_stay_within_jurisdiction(client, station_headers, state_headers):
    station = client.get("/api/v1/analytics/dashboard", headers=station_headers).json()
    state = client.get("/api/v1/analytics/dashboard", headers=state_headers).json()
    assert station["pending_drafts"] <= state["pending_drafts"]
    assert station["pending_verifications"] <= state["pending_verifications"]
    for s in station["contraband_stats"]:
        assert all(set(q) == {"unit", "total"} for q in s["quantities"])


def test_one_record_is_read_the_same_as_in_the_full_listing():
    import asyncio
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models.user import User
    from app.services import fir_summaries as fs

    async def check():
        async with AsyncSessionLocal() as db:
            user = (await db.execute(select(User).where(User.role == "STATE"))).scalars().first()
            everything = await fs.list_records(db, user)
            assert everything
            for kind in ("doc:", "case:"):
                rec = next((r for r in everything if r["record_key"].startswith(kind)), None)
                if rec:
                    assert await fs.list_records(db, user, only=rec["record_key"]) == [rec]
                    assert await fs.authorized_record(db, user, rec["record_key"]) == rec
    asyncio.run(check())


def test_summary_listing_returns_states(client, state_headers):
    res = client.get("/api/v1/summaries/records", headers=state_headers, params={"language": "en"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["coverage"]["total_records"] >= len(body["items"])
    for item in body["items"]:
        assert set(item["summary_state"]) == {"en", "te", "hi"}
