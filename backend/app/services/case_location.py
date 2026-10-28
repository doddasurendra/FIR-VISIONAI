"""
One location rule for a case, used by the case page and by Hotspots so both always agree.

  VERIFIED     - an officer confirmed the point on the map (MANUAL_CONFIRMED / verified flag)
  EXACT        - the geocoder matched a street, building or similar point
  APPROXIMATE  - stored coordinates from an area match, or the case's mandal / district centroid
                 when nothing is stored; shown on the map, marked "approximate"
  NONE         - no usable place at all; listed as "location not yet verified"

Coordinates a failed geocode stored as a placeholder (status UNRESOLVED / FAILED) are never used.
"""
from typing import Any, Dict, Optional

from .geocoder import AP_DISTRICT_COORDINATES, AP_MANDAL_COORDINATES

UNUSABLE_STATUSES = ("UNRESOLVED", "FAILED")


def _centroid(case) -> Optional[Dict[str, Any]]:
    mandal = (getattr(case, "incident_mandal", None) or getattr(case, "mandal", None) or "").strip().lower()
    if mandal in AP_MANDAL_COORDINATES:
        lat, lon = AP_MANDAL_COORDINATES[mandal]
        return {"latitude": lat, "longitude": lon, "label": f"{mandal.title()} mandal (approximate)"}
    for district in (getattr(case, "incident_district", None), getattr(case, "district", None)):
        key = (district or "").lower().replace("district", "").strip()
        if key in AP_DISTRICT_COORDINATES:
            lat, lon = AP_DISTRICT_COORDINATES[key]
            return {"latitude": lat, "longitude": lon, "label": f"{key.title()} district (approximate)"}
    return None


def case_location(case) -> Dict[str, Any]:
    """{latitude, longitude, precision, is_approximate, source} for a case (see module docstring)."""
    status = (case.incident_location_geocoder_status or "").upper()
    lat, lon = case.incident_latitude, case.incident_longitude
    if lat is not None and lon is not None and status not in UNUSABLE_STATUSES:
        if case.incident_location_verified or status == "MANUAL_CONFIRMED":
            precision = "VERIFIED"
        elif status == "EXACT":
            precision = "EXACT"
        else:
            precision = "APPROXIMATE"
        return {"latitude": float(lat), "longitude": float(lon), "precision": precision,
                "is_approximate": precision == "APPROXIMATE", "source": "stored"}
    centroid = _centroid(case)
    if centroid:
        return {"latitude": centroid["latitude"], "longitude": centroid["longitude"], "precision": "APPROXIMATE",
                "is_approximate": True, "source": "centroid", "label": centroid["label"]}
    return {"latitude": None, "longitude": None, "precision": "NONE", "is_approximate": False, "source": None}
