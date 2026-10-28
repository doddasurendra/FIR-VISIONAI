"""
Crime hotspots from each case's own geocoded incident location.

Cases inside the user's jurisdiction are grouped by district and station/mandal, then split by
distance (DBSCAN-style: a case joins a cluster when it lies within CLUSTER_RADIUS_KM of any case
already in it). Clusters are scored with the department's levels:
  HIGH   - 5 or more cases, or 50 litres or more seized
  MEDIUM - 2 or more cases
  LOW    - a single case
Quantities are summed per unit (litres, kg, bottles, rupees are never added together).
Locations follow case_location.case_location (the case page uses the same rule): approximate ones are
on the map, marked approximate; cases with no usable place are returned separately as "location not
yet verified", never dropped.
"""
import math
from collections import Counter, defaultdict
from datetime import date, datetime, time
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.case import Case
from ..models.user import User
from .auth import apply_case_scope_filter
from .case_location import case_location

CLUSTER_RADIUS_KM = 5.0
HIGH_CASES, HIGH_LITRES, MEDIUM_CASES = 5, 50.0, 2


def haversine_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def normalise_unit(unit: Optional[str]) -> str:
    u = (unit or "").strip().lower().rstrip(".")
    if u in ("l", "ltr", "ltrs", "litre", "litres", "liter", "liters"):
        return "Litres"
    if u in ("kg", "kgs", "kilogram", "kilograms"):
        return "Kg"
    if u in ("bottle", "bottles"):
        return "Bottles"
    if u in ("inr", "rs", "rupees", "₹"):
        return "INR"
    return unit.strip() if unit and unit.strip() else "Unspecified"


def intensity(case_count: int, litres: float) -> str:
    if case_count >= HIGH_CASES or litres >= HIGH_LITRES:
        return "HIGH"
    if case_count >= MEDIUM_CASES:
        return "MEDIUM"
    return "LOW"


def cluster_by_distance(points: List[Dict[str, Any]], radius_km: float = CLUSTER_RADIUS_KM) -> List[List[Dict[str, Any]]]:
    """Single-linkage (DBSCAN with min_samples=1) grouping of points carrying latitude/longitude."""
    clusters: List[List[Dict[str, Any]]] = []
    unassigned = list(points)
    while unassigned:
        seed = unassigned.pop(0)
        members, frontier = [seed], [seed]
        while frontier:
            p = frontier.pop()
            near = [q for q in unassigned
                    if haversine_km(p["latitude"], p["longitude"], q["latitude"], q["longitude"]) <= radius_km]
            for q in near:
                unassigned.remove(q)
            members += near
            frontier += near
        clusters.append(members)
    return clusters


def build_clusters(located: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group located incidents by district and station/mandal, split by distance, then score."""
    groups: Dict[tuple, List[Dict[str, Any]]] = defaultdict(list)
    for inc in located:
        area = inc.get("station") or inc.get("mandal") or "Unassigned area"
        groups[((inc.get("district") or "Unknown").strip().lower(), area.strip().lower())].append(inc)

    out = []
    for members_all in groups.values():
        for members in cluster_by_distance(members_all):
            lat = sum(m["latitude"] for m in members) / len(members)
            lon = sum(m["longitude"] for m in members) / len(members)
            radius_m = max([haversine_km(lat, lon, m["latitude"], m["longitude"]) * 1000 for m in members] + [400.0])
            by_unit: Dict[str, float] = defaultdict(float)
            for m in members:
                if m.get("seized_quantity"):
                    by_unit[m["unit"]] += float(m["seized_quantity"])
            litres = by_unit.get("Litres", 0.0)
            first = members[0]
            mandals = Counter(m["mandal"] for m in members if m.get("mandal"))
            out.append({
                "cluster_id": f"{first['district']}|{first.get('station') or first.get('mandal')}|{first['case_id'][:8]}",
                "district": first.get("district") or "Unknown",
                "station": first.get("station") or "Station not recorded",
                "location_name": (mandals.most_common(1)[0][0] if mandals else first.get("station")) or "Unassigned area",
                "latitude": round(lat, 6),
                "longitude": round(lon, 6),
                "radius_m": round(radius_m),
                "incident_count": len(members),
                "seized_by_unit": {u: round(q, 2) for u, q in sorted(by_unit.items())},
                # Kept for older clients: litres only, the unit the HIGH threshold is defined in
                "total_seized_quantity": round(litres, 2),
                "contraband_breakdown": dict(Counter(m.get("contraband_type") or "Unknown" for m in members)),
                "risk_intensity": intensity(len(members), litres),
                "approximate_locations": sum(1 for m in members if m.get("is_approximate",
                                             m.get("geocoder_status") not in ("EXACT", "MANUAL_CONFIRMED"))),
                "cases": sorted(members, key=lambda m: m.get("incident_date") or "", reverse=True),
            })
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    out.sort(key=lambda c: (order[c["risk_intensity"]], -c["incident_count"]))
    return out


def _as_iso(value) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


async def get_crime_hotspots(
    user: User,
    db: AsyncSession,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    offence_type: Optional[str] = None,
    contraband_type: Optional[str] = None,
) -> Dict[str, Any]:
    incident_date = func.coalesce(Case.offence_date, Case.registration_date)
    stmt = select(Case).where(Case.is_archived == False)  # noqa: E712
    stmt = apply_case_scope_filter(stmt, user, Case)  # STATION / DISTRICT / STATE jurisdiction
    if date_from:
        stmt = stmt.where(incident_date >= datetime.combine(date_from, time.min))
    if date_to:
        stmt = stmt.where(incident_date <= datetime.combine(date_to, time.max))
    if offence_type:
        stmt = stmt.where(func.lower(Case.offence_nature) == offence_type.strip().lower())
    if contraband_type:
        stmt = stmt.where(func.lower(Case.contraband_type) == contraband_type.strip().lower())
    cases = (await db.execute(stmt)).scalars().all()

    # Filter choices come from the whole jurisdiction, not the filtered result
    options_stmt = apply_case_scope_filter(
        select(Case.offence_nature, Case.contraband_type).where(Case.is_archived == False), user, Case)  # noqa: E712
    opts = (await db.execute(options_stmt)).all()

    located, unlocated = [], []
    for c in cases:
        item = {
            "case_id": c.id,
            "fir_number": c.fir_number,
            "status": c.status,
            "district": c.district,
            "station": c.station,
            "mandal": c.incident_mandal or c.mandal,
            "offence_nature": c.offence_nature,
            "contraband_type": c.contraband_type,
            "seized_quantity": c.seized_quantity,
            "seized_unit": c.seized_unit,
            "unit": normalise_unit(c.seized_unit),
            "incident_date": _as_iso(c.offence_date or c.registration_date),
            "geocoder_status": c.incident_location_geocoder_status,
            "location_text": c.incident_location_normalized or c.incident_place_raw or c.location_description,
        }
        loc = case_location(c)  # the same rule as the case page
        item.update(location_precision=loc["precision"], is_approximate=loc["is_approximate"])
        if loc["latitude"] is not None:
            located.append({**item, "latitude": loc["latitude"], "longitude": loc["longitude"]})
        else:
            unlocated.append({**item, "location_status": "LOCATION_NOT_YET_VERIFIED"})

    clusters = build_clusters(located)
    return {
        "hotspots": clusters,
        "total_hotspots": len(clusters),
        "incidents": located,
        "unlocated_cases": unlocated,
        "totals": {"cases": len(cases), "located": len(located), "unlocated": len(unlocated)},
        "filters": {
            "offence_types": sorted({o for o, _ in opts if o}),
            "contraband_types": sorted({c for _, c in opts if c}),
            "applied": {"date_from": _as_iso(date_from), "date_to": _as_iso(date_to),
                        "offence_type": offence_type, "contraband_type": contraband_type},
        },
        "levels": {"HIGH": f"{HIGH_CASES}+ cases or {HIGH_LITRES:g}+ litres", "MEDIUM": f"{MEDIUM_CASES}+ cases",
                   "LOW": "1 case"},
        "scope": {"role": user.role, "district": user.district, "station": user.station},
        "disclaimer": "Hotspots use each case's recorded incident location. Locations marked approximate were "
                      "geocoded from the place description and should be confirmed.",
    }
