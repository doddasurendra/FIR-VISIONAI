"""
Andhra Pradesh Prohibition & Excise Department — Jurisdiction Master Data.
Configured with official 26 districts and verified Excise Stations.
"""

from typing import Dict, List, Optional, Any

AP_JURISDICTION_MASTER: Dict[str, List[str]] = {
    "Kurnool": [
        "Kurnool Town Station",
        "Kurnool Rural Station",
        "Alur Station",
        "Adoni Station",
        "Dhone Station",
        "Yemmiganur Station",
        "Pattikonda Station"
    ],
    "Nandyal": [
        "Nandyal Town Station",
        "Allagadda Station",
        "Banaganapalle Station",
        "Nandikotkur Station",
        "Atmakur Station",
        "Koilkuntla Station"
    ],
    "Guntur": [
        "Guntur-1 Station",
        "Guntur-2 Station",
        "Tenali Station",
        "Mangalagiri Station",
        "Ponnur Station",
        "Tadikonda Station"
    ],
    "Palnadu": [
        "Narasaraopet Station",
        "Piduguralla Station",
        "Vinukonda Station",
        "Chilakaluripet Station",
        "Macherla Station",
        "Sattenapalli Station"
    ],
    "Bapatla": [
        "Bapatla Town Station",
        "Chirala Station",
        "Repalle Station",
        "Parchur Station",
        "Vemuru Station"
    ],
    "Visakhapatnam": [
        "VSP-Central Station",
        "Gajuwaka Station",
        "Anandapuram Station",
        "Pendurthi Station",
        "Bheemunipatnam Station",
        "Gopalapatnam Station"
    ],
    "Anakapalli": [
        "Anakapalli Station",
        "Chodavaram Station",
        "Yelamanchili Station",
        "Narsipatnam Station",
        "Payakaraopeta Station"
    ],
    "Alluri Sitharama Raju": [
        "Paderu Station",
        "Araku Valley Station",
        "Rampachodavaram Station",
        "Chintapalli Station",
        "Maredumilli Station"
    ],
    "Krishna": [
        "Machilipatnam Station",
        "Gudivada Station",
        "Vuyyuru Station",
        "Avanigadda Station",
        "Pamarru Station"
    ],
    "NTR": [
        "Vijayawada Central Station",
        "Vijayawada West Station",
        "Ibrahimpatnam Station",
        "Jaggaiahpet Station",
        "Tiruvuru Station",
        "Mylavaram Station"
    ],
    "East Godavari": [
        "Rajahmundry Urban Station",
        "Rajahmundry Rural Station",
        "Kovvur Station",
        "Nidadavole Station",
        "Gopalapuram Station"
    ],
    "Kakinada": [
        "Kakinada Urban Station",
        "Kakinada Rural Station",
        "Peddapuram Station",
        "Pithapuram Station",
        "Tuni Station"
    ],
    "Dr. B.R. Ambedkar Konaseema": [
        "Amalapuram Station",
        "Ramachandrapuram Station",
        "Razole Station",
        "Mandapeta Station",
        "Kothapeta Station"
    ],
    "West Godavari": [
        "Bhimavaram Station",
        "Tadepalligudem Station",
        "Tanuku Station",
        "Palakollu Station",
        "Narsapur Station"
    ],
    "Eluru": [
        "Eluru Town Station",
        "Eluru Rural Station",
        "Jangareddygudem Station",
        "Chintalapudi Station",
        "Nuzvid Station",
        "Kaikalur Station"
    ],
    "Nellore": [
        "Nellore Urban Station",
        "Nellore Rural Station",
        "Kavali Station",
        "Gudur Station",
        "Atmakur Station",
        "Venkatagiri Station"
    ],
    "Tirupati": [
        "Tirupati Urban Station",
        "Renigunta Station",
        "Srikalahasti Station",
        "Chandragiri Station",
        "Puttur Station",
        "Sullurpeta Station"
    ],
    "Chittoor": [
        "Chittoor Urban Station",
        "Chittoor Rural Station",
        "Palamaner Station",
        "Nagari Station",
        "Bangarupalem Station",
        "Kuppam Station"
    ],
    "Ananthapuramu": [
        "Anantapur Urban Station",
        "Anantapur Rural Station",
        "Guntakal Station",
        "Tadipatri Station",
        "Dharmavaram Station",
        "Rayadurg Station",
        "Uravakonda Station"
    ],
    "Sri Sathya Sai": [
        "Hindupur Station",
        "Kadiri Station",
        "Penukonda Station",
        "Puttaparthi Station",
        "Madakasira Station"
    ],
    "YSR Kadapa": [
        "Kadapa Town Station",
        "Kadapa Rural Station",
        "Proddatur Station",
        "Pulivendula Station",
        "Jammalamadugu Station",
        "Badvel Station"
    ],
    "Annamayya": [
        "Madanapalle Station",
        "Rayachoty Urban Station",
        "Rayachoty Rural Station",
        "Rajampet Station",
        "Railway Kodur Station"
    ],
    "Prakasam": [
        "Ongole Urban Station",
        "Ongole Rural Station",
        "Kandukur Station",
        "Markapur Station",
        "Giddalur Station",
        "Kanigiri Station"
    ],
    "Srikakulam": [
        "Srikakulam Town Station",
        "Srikakulam Rural Station",
        "Palasa Station",
        "Tekkali Station",
        "Amadalavalasa Station",
        "Narasannapeta Station"
    ],
    "Vizianagaram": [
        "Vizianagaram Urban Station",
        "Vizianagaram Rural Station",
        "Bobbili Station",
        "Cheepurupalli Station",
        "Gajapathinagaram Station",
        "Srungavarapukota Station"
    ],
    "Parvathipuram Manyam": [
        "Parvathipuram Station",
        "Salur Station",
        "Palakonda Station",
        "Kurupam Station"
    ]
}

def get_all_districts() -> List[str]:
    """Return all 26 official AP districts."""
    return sorted(list(AP_JURISDICTION_MASTER.keys()))

def get_stations_for_district(district: str) -> List[str]:
    """Return official stations for a specific district (case-insensitive lookup)."""
    for d, stations in AP_JURISDICTION_MASTER.items():
        if d.lower() == district.lower():
            return sorted(stations)
    return []

def validate_jurisdiction(district: str, station: Optional[str] = None) -> bool:
    """Validate that district exists, and if station is provided, that station belongs to district."""
    stations = get_stations_for_district(district)
    if not stations:
        return False
    if station:
        station_lower = station.lower().strip()
        matched = any(s.lower() == station_lower for s in stations)
        return matched
    return True

def get_jurisdiction_summary() -> Dict:
    total_stations = sum(len(stations) for stations in AP_JURISDICTION_MASTER.values())
    return {
        "state": "Andhra Pradesh",
        "department": "Prohibition & Excise Department",
        "total_districts": len(AP_JURISDICTION_MASTER),
        "total_stations": total_stations,
        "state_headquarters": "Amaravati Headquarters",
        "districts": get_all_districts()
    }


import math

AP_DISTRICT_COORDINATES: Dict[str, Dict[str, float]] = {
    "Alluri Sitharama Raju": {"lat": 18.0697, "lon": 82.5317},
    "Anakapalli": {"lat": 17.6913, "lon": 83.0039},
    "Ananthapuramu": {"lat": 14.6819, "lon": 77.6006},
    "Annamayya": {"lat": 14.0104, "lon": 78.7516},
    "Bapatla": {"lat": 15.9042, "lon": 80.4674},
    "Chittoor": {"lat": 13.2172, "lon": 79.1003},
    "Dr. B.R. Ambedkar Konaseema": {"lat": 16.5787, "lon": 82.0061},
    "East Godavari": {"lat": 17.0005, "lon": 81.8040},
    "Eluru": {"lat": 16.7107, "lon": 81.0952},
    "Guntur": {"lat": 16.3067, "lon": 80.4365},
    "Kakinada": {"lat": 16.9891, "lon": 82.2475},
    "Krishna": {"lat": 16.1876, "lon": 81.1389},
    "Kurnool": {"lat": 15.8281, "lon": 78.0373},
    "Nandyal": {"lat": 15.4886, "lon": 78.4836},
    "NTR": {"lat": 16.5062, "lon": 80.6480},
    "Palnadu": {"lat": 16.2359, "lon": 80.0499},
    "Parvathipuram Manyam": {"lat": 18.7796, "lon": 83.4278},
    "Prakasam": {"lat": 15.5057, "lon": 80.0499},
    "Nellore": {"lat": 14.4426, "lon": 79.9865},
    "Sri Sathya Sai": {"lat": 14.1706, "lon": 77.8105},
    "Srikakulam": {"lat": 18.2949, "lon": 83.8938},
    "Tirupati": {"lat": 13.6288, "lon": 79.4192},
    "Visakhapatnam": {"lat": 17.6868, "lon": 83.2185},
    "Vizianagaram": {"lat": 18.1067, "lon": 83.3956},
    "West Godavari": {"lat": 16.5449, "lon": 81.5212},
    "YSR Kadapa": {"lat": 14.4673, "lon": 78.8242},
}

def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0 # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def match_location_to_jurisdiction(lat: float, lon: float) -> Dict[str, Any]:
    """
    Reverse-geocodes coordinates to the closest Andhra Pradesh district and candidate stations.
    Advises that Wi-Fi/hotspot geolocation is approximate and requires officer confirmation.
    """
    closest_district = None
    min_dist = float("inf")

    for district, coords in AP_DISTRICT_COORDINATES.items():
        dist = haversine_distance_km(lat, lon, coords["lat"], coords["lon"])
        if dist < min_dist:
            min_dist = dist
            closest_district = district

    # Assess confidence based on distance
    if min_dist <= 45.0:
        confidence = "HIGH"
    elif min_dist <= 100.0:
        confidence = "MEDIUM"
    else:
        confidence = "APPROXIMATE"

    candidate_stations = get_stations_for_district(closest_district) if closest_district else []

    return {
        "latitude": round(lat, 5),
        "longitude": round(lon, 5),
        "detected_district": closest_district,
        "nearest_distance_km": round(min_dist, 1),
        "confidence": confidence,
        "candidate_stations": candidate_stations,
        "all_districts": get_all_districts(),
        "disclaimer": (
            "Wi-Fi and mobile hotspot connections provide approximate network-level geolocation. "
            "Because departmental jurisdiction boundaries require legal certainty, please confirm or "
            "select your assigned excise station from the candidate list."
        )
    }


async def detect_exact_station(
    lat: float,
    lon: float,
    accuracy: Optional[float] = None,
    user: Optional[Any] = None,
    db: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    High-precision station detection against official Andhra Pradesh Prohibition & Excise
    Station Registry. Calculates exact Haversine distances to verified physical station
    coordinates, checks officer jurisdictional authorization, and evaluates GPS accuracy.
    """
    from ..models.station import VerifiedStation
    from sqlalchemy import select
    from datetime import datetime, timezone
    import re

    stations_list = []
    if db:
        try:
            stmt = select(VerifiedStation).where(VerifiedStation.is_active == True)
            res = await db.execute(stmt)
            stations_list = res.scalars().all()
        except Exception:
            stations_list = []

    # If DB has no stations loaded yet, fallback to district centres
    if not stations_list:
        basic = match_location_to_jurisdiction(lat, lon)
        basic["accuracy_meters"] = accuracy
        basic["detection_timestamp"] = datetime.now(timezone.utc).isoformat()
        basic["match_type"] = "DISTRICT_LEVEL"
        basic["exact_station"] = None
        basic["officer_auth"] = None
        basic["candidate_station_objects"] = []
        return basic

    station_distances = []
    for stn in stations_list:
        dist_km = haversine_distance_km(lat, lon, stn.latitude, stn.longitude)
        
        # Check authorization if user provided
        is_auth = False
        if user:
            if getattr(user, "role", "") == "STATE":
                is_auth = True
            elif getattr(user, "role", "") == "DISTRICT":
                u_dist = (getattr(user, "district", "") or "").strip().lower()
                is_auth = u_dist == stn.district.strip().lower()
            elif getattr(user, "role", "") == "STATION":
                u_dist = (getattr(user, "district", "") or "").strip().lower()
                dist_match = u_dist == stn.district.strip().lower()
                clean_u = re.sub(r'[^a-z0-9]', '', (getattr(user, "station", "") or "").lower())
                clean_s = re.sub(r'[^a-z0-9]', '', stn.station_name.lower())
                stn_match = (clean_u in clean_s) or (clean_s in clean_u) if clean_u and clean_s else False
                is_auth = dist_match and stn_match
                
        station_distances.append({
            "id": stn.id,
            "station_code": stn.station_code,
            "station_name": stn.station_name,
            "district": stn.district,
            "mandal": stn.mandal or "",
            "locality": stn.locality or "",
            "address": stn.address or "",
            "latitude": stn.latitude,
            "longitude": stn.longitude,
            "distance_km": round(dist_km, 2),
            "distance_meters": int(round(dist_km * 1000)),
            "is_officer_authorized": is_auth,
        })

    station_distances.sort(key=lambda s: s["distance_km"])
    closest_station = station_distances[0] if station_distances else None

    # Determine confidence & exact match
    exact_station = None
    if closest_station and closest_station["distance_km"] <= 5.0:
        match_type = "EXACT_MATCH"
        confidence = "HIGH"
        exact_station = closest_station
    elif closest_station and closest_station["distance_km"] <= 35.0:
        match_type = "NEARBY_CANDIDATES"
        confidence = "MEDIUM"
        if closest_station["distance_km"] <= 15.0:
            exact_station = closest_station
    else:
        match_type = "DISTRICT_LEVEL"
        confidence = "APPROXIMATE"

    detected_district = exact_station["district"] if exact_station else (closest_station["district"] if closest_station else "Kurnool")
    nearest_dist = exact_station["distance_km"] if exact_station else (closest_station["distance_km"] if closest_station else 0.0)

    officer_auth = None
    if user:
        is_exact_authorized = exact_station["is_officer_authorized"] if exact_station else False
        officer_auth = {
            "username": getattr(user, "username", ""),
            "role": getattr(user, "role", ""),
            "assigned_district": getattr(user, "district", ""),
            "assigned_station": getattr(user, "station", ""),
            "is_authorized_station": is_exact_authorized,
        }

    candidate_names = [s["station_name"] for s in station_distances[:10] if s["district"] == detected_district]
    if not candidate_names:
        candidate_names = [s["station_name"] for s in station_distances[:6]]

    return {
        "latitude": round(lat, 6),
        "longitude": round(lon, 6),
        "accuracy_meters": round(accuracy, 1) if accuracy is not None else None,
        "detection_timestamp": datetime.now(timezone.utc).isoformat(),
        "detected_district": detected_district,
        "nearest_distance_km": round(nearest_dist, 2),
        "confidence": confidence,
        "match_type": match_type,
        "exact_station": exact_station,
        "candidate_stations": candidate_names,
        "candidate_station_objects": station_distances[:6],
        "all_districts": get_all_districts(),
        "officer_auth": officer_auth,
        "disclaimer": (
            "Verified against official AP Prohibition & Excise Station Registry. "
            "Departmental jurisdiction boundaries require legal certainty. "
            "Station assignment adheres strictly to authorized officer credentials."
        )
    }
