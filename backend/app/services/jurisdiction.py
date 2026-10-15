"""
Andhra Pradesh Prohibition & Excise Department — Jurisdiction Master Data.
Configured with official 26 districts and verified Excise Stations.
"""

from typing import Dict, List, Optional

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
