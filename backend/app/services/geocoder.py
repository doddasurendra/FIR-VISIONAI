import logging
import re
from typing import Dict, Any, Optional, Tuple
import httpx

logger = logging.getLogger(__name__)

# Curated high-precision centroid table for Andhra Pradesh districts and key mandals
AP_DISTRICT_COORDINATES: Dict[str, Tuple[float, float]] = {
    "alluri sitharama raju": (18.0645, 82.5284),
    "anakapalli": (17.6913, 83.0039),
    "ananthapuramu": (14.6819, 77.6006),
    "anantapur": (14.6819, 77.6006),
    "annamayya": (14.0416, 78.9619),
    "bapatla": (15.9042, 80.4674),
    "chittoor": (13.2172, 79.1003),
    "dr. b.r. ambedkar konaseema": (16.5816, 81.9961),
    "konaseema": (16.5816, 81.9961),
    "east godavari": (17.0005, 81.8040),
    "eluru": (16.7107, 81.0952),
    "guntur": (16.3067, 80.4365),
    "kakinada": (16.9891, 82.2475),
    "krishna": (16.1809, 81.1303),
    "kurnool": (15.8281, 78.0373),
    "nandyal": (15.4886, 78.4836),
    "ntr": (16.5062, 80.6480),
    "vijayawada": (16.5062, 80.6480),
    "palnadu": (16.2349, 80.0435),
    "parvathipuram manyam": (18.7756, 83.4277),
    "prakasam": (15.5057, 80.0499),
    "ongole": (15.5057, 80.0499),
    "sri potti sriramulu nellore": (14.4426, 79.9865),
    "nellore": (14.4426, 79.9865),
    "sri sathya sai": (14.1670, 77.8115),
    "srikakulam": (18.2969, 83.8968),
    "tirupati": (13.6288, 79.4192),
    "visakhapatnam": (17.6868, 83.2185),
    "vizag": (17.6868, 83.2185),
    "vizianagaram": (18.1067, 83.3956),
    "west godavari": (16.5449, 81.5212),
    "bhimavaram": (16.5449, 81.5212),
    "ysr": (14.4673, 78.8242),
    "kadapa": (14.4673, 78.8242),
    "ysr kadapa": (14.4673, 78.8242)
}

AP_MANDAL_COORDINATES: Dict[str, Tuple[float, float]] = {
    "piduguralla": (16.4833, 79.8833),
    "mangalagiri": (16.4320, 80.5600),
    "tenali": (16.2435, 80.6400),
    "narasaraopet": (16.2349, 80.0435),
    "sattenapalle": (16.3980, 80.1448),
    "tadepalle": (16.4800, 80.6000),
    "gannavaram": (16.5367, 80.8033),
    "gudivada": (16.4410, 80.9926),
    "machilipatnam": (16.1875, 81.1389),
    "nuzvid": (16.7865, 80.8465),
    "rajamahendravaram": (17.0005, 81.8040),
    "amalapuram": (16.5787, 82.0061),
    "ramachandrapuram": (16.8500, 82.0200),
    "adoni": (15.6322, 77.2728),
    "yemmiganur": (15.7333, 77.4833),
    "dhone": (15.4200, 77.8700),
    "proddatur": (14.7500, 78.5500),
    "pulivendula": (14.4200, 78.2300),
    "hindupur": (13.8300, 77.4900),
    "dharmavaram": (14.4100, 77.7200),
    "kandukur": (15.2167, 79.9000),
    "chirala": (15.8200, 80.3500),
    "srikalahasti": (13.7500, 79.7000),
    "nagari": (13.3300, 79.5800),
    "madnapalle": (13.5500, 78.5000),
    "madanapalle": (13.5500, 78.5000),
    "tadepalligudem": (16.8100, 81.5300),
    "tanuku": (16.7500, 81.6800),
    "palakollu": (16.5200, 81.7300),
    "bobbili": (18.5700, 83.3700),
    "salur": (18.5300, 83.2100),
    "tekkali": (18.6100, 84.2300),
    "palasa": (18.7700, 84.4100)
}

class GeocoderService:
    @staticmethod
    def _clean_str(s: Optional[str]) -> str:
        if not s:
            return ""
        return re.sub(r'[\r\n\t]+', ' ', s).strip()

    @classmethod
    async def geocode_incident_location(
        cls,
        raw_place: Optional[str],
        village: Optional[str] = None,
        mandal: Optional[str] = None,
        district: Optional[str] = None,
        state: str = "Andhra Pradesh"
    ) -> Dict[str, Any]:
        """
        Geocode an incident location strictly within Andhra Pradesh.
        Resolves to coordinates via OpenStreetMap Nominatim or curated AP regional centroid fallback.
        Never presents an approximate match as an exact incident point.
        """
        raw_clean = cls._clean_str(raw_place)
        vil_clean = cls._clean_str(village)
        man_clean = cls._clean_str(mandal)
        dist_clean = cls._clean_str(district)

        # Build search query string
        parts = []
        if raw_clean:
            # Strip common police prefixes
            clean_addr = re.sub(r'^(?:at about|near|in front of|opposite to|beside|at)\s+', '', raw_clean, flags=re.I)
            parts.append(clean_addr)
        elif vil_clean:
            parts.append(vil_clean)

        if man_clean and man_clean.lower() not in " ".join(parts).lower():
            parts.append(f"{man_clean} Mandal")
        if dist_clean and dist_clean.lower() not in " ".join(parts).lower():
            parts.append(f"{dist_clean} District")
        parts.append(state)

        query_str = ", ".join(parts)

        # 1. Try Live Geocoding via Nominatim (with timeout and error handling)
        try:
            headers = {"User-Agent": "FIR-VisionAI-Excise-Platform/2.0 (ap-excise@ap.gov.in)"}
            async with httpx.AsyncClient(timeout=3.5) as client:
                resp = await client.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={
                        "q": query_str,
                        "format": "json",
                        "limit": 1,
                        "countrycodes": "in"
                    },
                    headers=headers
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data and len(data) > 0:
                        hit = data[0]
                        lat = float(hit.get("lat"))
                        lon = float(hit.get("lon"))
                        # Validate bounding box of Andhra Pradesh (approx 12.5 - 19.5 N, 76.5 - 84.8 E)
                        if 12.0 <= lat <= 20.0 and 76.0 <= lon <= 85.5:
                            hit_type = hit.get("type", "").lower()
                            is_exact = hit_type in ("house", "building", "road", "residential", "highway", "amenity")
                            return {
                                "latitude": lat,
                                "longitude": lon,
                                "status": "EXACT" if is_exact else "APPROXIMATE",
                                "display_name": hit.get("display_name", query_str),
                                "provider": "OpenStreetMap Nominatim",
                                "confidence": 0.92 if is_exact else 0.78,
                                "is_approximate": not is_exact,
                                "notes": "Resolved via OpenStreetMap live geocoding" if is_exact else "Resolved to area centroid (approximate). Field verification recommended."
                            }
        except Exception as e:
            logger.info(f"Live geocoding network pass through: {e}")

        # 2. Try Mandal centroid lookup
        if man_clean and man_clean.lower() in AP_MANDAL_COORDINATES:
            lat, lon = AP_MANDAL_COORDINATES[man_clean.lower()]
            return {
                "latitude": lat,
                "longitude": lon,
                "status": "APPROXIMATE",
                "display_name": f"{man_clean.title()} Mandal, {dist_clean.title() if dist_clean else ''}, Andhra Pradesh",
                "provider": "AP Regional Centroid Directory",
                "confidence": 0.70,
                "is_approximate": True,
                "notes": f"Approximate coordinates for {man_clean.title()} Mandal. Officer field verification required."
            }

        # 3. Try District centroid lookup
        if dist_clean:
            dist_key = dist_clean.lower().replace("district", "").strip()
            if dist_key in AP_DISTRICT_COORDINATES:
                lat, lon = AP_DISTRICT_COORDINATES[dist_key]
                return {
                    "latitude": lat,
                    "longitude": lon,
                    "status": "APPROXIMATE",
                    "display_name": f"{dist_clean.title()} District, Andhra Pradesh",
                    "provider": "AP Regional Centroid Directory",
                    "confidence": 0.55,
                    "is_approximate": True,
                    "notes": f"Broad location matched to {dist_clean.title()} District centroid. Please confirm exact incident point on map."
                }

        # 4. Default fallback: Guntur (Central Andhra Pradesh hub) as pending resolution
        default_lat, default_lon = (16.3067, 80.4365)
        return {
            "latitude": default_lat,
            "longitude": default_lon,
            "status": "UNRESOLVED",
            "display_name": raw_clean or "Unresolved Incident Location",
            "provider": "Manual Entry Required",
            "confidence": 0.20,
            "is_approximate": True,
            "notes": "Could not automatically resolve address. Please drag or click marker on map to confirm exact spot."
        }

    @staticmethod
    def get_directions_url(lat: float, lon: float, destination_name: Optional[str] = None) -> str:
        """Generate Google Maps / OpenStreetMap turn-by-turn navigation link."""
        return f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}"

geocoder_service = GeocoderService()
