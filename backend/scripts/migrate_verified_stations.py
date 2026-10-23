"""
Migration & Seeding script: Creates and populates verified_stations in Supabase PostgreSQL & SQLite.
Official Andhra Pradesh Prohibition & Excise Department Station Registry.
"""
import sys
import os
import re
from datetime import datetime, timezone

# Ensure backend root is in python path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.database import SyncSessionLocal, sync_engine
from app.models.station import VerifiedStation
from app.models.base import Base, generate_uuid
from app.services.jurisdiction import AP_JURISDICTION_MASTER, AP_DISTRICT_COORDINATES

# Official station location offsets and details across Andhra Pradesh districts
# Maps district -> dict of station_name -> (lat, lon, mandal, locality, address)
OFFICIAL_STATION_REGISTRY_DATA = {
    "Kurnool": {
        "Kurnool Town Station": (15.8281, 78.0373, "Kurnool Urban", "Budhawarpet", "Beside Collectorate Complex, Nandyal Road, Kurnool - 518002"),
        "Kurnool Rural Station": (15.8050, 78.0550, "Kurnool Rural", "Joharapuram", "Near Joharapuram Ring Road, Kurnool - 518004"),
        "Alur Station": (15.3050, 77.2450, "Alur", "Main Road", "Opp. RTC Bus Stand, Alur, Kurnool Dist - 518395"),
        "Adoni Station": (15.6322, 77.2728, "Adoni", "Arts College Road", "Behind Old Municipal Office, Adoni - 518301"),
        "Dhone Station": (15.4210, 77.8740, "Dhone", "Railway Station Road", "Near RDO Office, Dhone - 518222"),
        "Yemmiganur Station": (15.7330, 77.4810, "Yemmiganur", "Somappa Nagar", "Adoni Road, Yemmiganur - 518360"),
        "Pattikonda Station": (15.4020, 77.5180, "Pattikonda", "Gooty Road", "Near Court Complex, Pattikonda - 518380")
    },
    "Nandyal": {
        "Nandyal Town Station": (15.4886, 78.4836, "Nandyal Urban", "Srinivasa Nagar", "Near Checkpost, Atmakur Road, Nandyal - 518501"),
        "Allagadda Station": (15.1320, 78.5130, "Allagadda", "Bypass Road", "Opp. Civil Court, Allagadda - 518543"),
        "Banaganapalle Station": (15.3180, 78.2250, "Banaganapalle", "Yaganti Road", "Near Nawab Palace, Banaganapalle - 518124"),
        "Nandikotkur Station": (15.8620, 78.2610, "Nandikotkur", "Main Bazaar", "Kurnool Highway, Nandikotkur - 518401"),
        "Atmakur Station": (15.8820, 78.7910, "Atmakur", "Kothapalli Road", "Near Forest Complex, Atmakur - 518422"),
        "Koilkuntla Station": (15.2340, 78.3180, "Koilkuntla", "Old Town", "Banganapalle Road, Koilkuntla - 518134")
    },
    "Guntur": {
        "Guntur-1 Station": (16.3067, 80.4365, "Guntur Urban", "Arundelpet", "2nd Lane Arundelpet, Guntur - 522002"),
        "Guntur-2 Station": (16.2950, 80.4520, "Guntur East", "Kothapet", "Beside Old Mirchi Yard, Guntur - 522001"),
        "Tenali Station": (16.2430, 80.6400, "Tenali", "Chenchupet", "Station Road, Tenali - 522201"),
        "Mangalagiri Station": (16.4310, 80.5680, "Mangalagiri", "Koppuravuru", "Old NH-16, Mangalagiri - 522503"),
        "Ponnur Station": (16.0680, 80.5590, "Ponnur", "RTC Colony", "Bapatla Road, Ponnur - 522124"),
        "Tadikonda Station": (16.4210, 80.4480, "Tadikonda", "Main Road", "Near Tahsildar Office, Tadikonda - 522236")
    },
    "Palnadu": {
        "Narasaraopet Station": (16.2359, 80.0499, "Narasaraopet", "Barkatpura", "Prakash Nagar, Narasaraopet - 522601"),
        "Piduguralla Station": (16.4830, 79.8880, "Piduguralla", "Lime City", "Guntur Highway, Piduguralla - 522413"),
        "Vinukonda Station": (16.0520, 79.7480, "Vinukonda", "Sivapuram", "Guntur Road, Vinukonda - 522647"),
        "Chilakaluripet Station": (16.0890, 80.1670, "Chilakaluripet", "Kalamandir Road", "NH-16 Bypass, Chilakaluripet - 522616"),
        "Macherla Station": (16.4810, 79.2980, "Macherla", "Nagarjuna Sagar Road", "Near Railway Gate, Macherla - 522426"),
        "Sattenapalli Station": (16.3980, 80.1550, "Sattenapalli", "Guntur Road", "Near Taluka Police Station, Sattenapalli - 522403")
    },
    "Bapatla": {
        "Bapatla Town Station": (15.9042, 80.4674, "Bapatla", "College Road", "Agriculture College Road, Bapatla - 522101"),
        "Chirala Station": (15.8250, 80.3540, "Chirala", "Perala", "Guntur Road, Chirala - 523155"),
        "Repalle Station": (16.0220, 80.8510, "Repalle", "Islampet", "Railway Feeder Road, Repalle - 522265"),
        "Parchur Station": (15.9650, 80.2640, "Parchur", "Bazaar Road", "Opposite MDO Office, Parchur - 523169"),
        "Vemuru Station": (16.1820, 80.7510, "Vemuru", "Main Center", "Near Bus Station, Vemuru - 522261")
    },
    "Visakhapatnam": {
        "VSP-Central Station": (17.6868, 83.2185, "Visakhapatnam Urban", "Dwaraka Nagar", "Beside Complex, Dwaraka Nagar, Visakhapatnam - 530016"),
        "Gajuwaka Station": (17.6910, 83.1890, "Gajuwaka", "High School Road", "BHPV Post, Gajuwaka - 530026"),
        "Anandapuram Station": (17.9120, 83.3980, "Anandapuram", "Junction", "Srikakulam Highway, Anandapuram - 530052"),
        "Pendurthi Station": (17.8280, 83.2010, "Pendurthi", "Sarada Colony", "Kothavalasa Road, Pendurthi - 531173"),
        "Bheemunipatnam Station": (17.8920, 83.4520, "Bheemunipatnam", "Beach Road", "Old Dutch Town, Bheemunipatnam - 531163"),
        "Gopalapatnam Station": (17.7540, 83.2280, "Gopalapatnam", "NAD Junction", "Near Simhachalam Railway Gate, Visakhapatnam - 530027")
    },
    "Anakapalli": {
        "Anakapalli Station": (17.6913, 83.0039, "Anakapalli", "Gavarapalem", "Ring Road, Anakapalli - 531001"),
        "Chodavaram Station": (17.8310, 82.9320, "Chodavaram", "RTC Depot Road", "Main Bazaar, Chodavaram - 531036"),
        "Yelamanchili Station": (17.5510, 82.8580, "Yelamanchili", "Somalingapalem", "NH-16 Bypass, Yelamanchili - 531055"),
        "Narsipatnam Station": (17.6690, 82.6120, "Narsipatnam", "Balighattam", "Chintapalli Road, Narsipatnam - 531116"),
        "Payakaraopeta Station": (17.3680, 82.5620, "Payakaraopeta", "Gopalapatnam Road", "Tuni Border, Payakaraopeta - 531126")
    },
    "Alluri Sitharama Raju": {
        "Paderu Station": (18.0697, 82.5317, "Paderu", "ITDA Junction", "Near ITDA Complex, Paderu - 531077"),
        "Araku Valley Station": (18.3280, 82.8790, "Araku", "Padmapuram", "Main Road, Araku Valley - 531149"),
        "Rampachodavaram Station": (17.4480, 81.7760, "Rampachodavaram", "Agency Road", "Sub-Collector Office Road, Rampachodavaram - 533288"),
        "Chintapalli Station": (17.8740, 82.3520, "Chintapalli", "Market Yard", "Lambasingi Road, Chintapalli - 531111"),
        "Maredumilli Station": (17.6010, 81.7120, "Maredumilli", "Forest Road", "Bhadrachalam Highway, Maredumilli - 533295")
    },
    "Krishna": {
        "Machilipatnam Station": (16.1876, 81.1389, "Machilipatnam", "Chilakalapudi", "Court Compound, Machilipatnam - 521001"),
        "Gudivada Station": (16.4350, 80.9980, "Gudivada", "Satyanarayanapuram", "Eluru Road, Gudivada - 521301"),
        "Vuyyuru Station": (16.3680, 80.8450, "Vuyyuru", "Sugar Factory Road", "Near Old Bus Stand, Vuyyuru - 521165"),
        "Avanigadda Station": (16.0210, 80.9180, "Avanigadda", "Diviseema Center", "Main Road, Avanigadda - 521121"),
        "Pamarru Station": (16.3280, 80.9620, "Pamarru", "Bypass", "Gudivada Road, Pamarru - 521157")
    },
    "NTR": {
        "Vijayawada Central Station": (16.5062, 80.6480, "Vijayawada Urban", "Governorpet", "Beside Municipal Corporation, Vijayawada - 520002"),
        "Vijayawada West Station": (16.5220, 80.6180, "Vijayawada West", "Bhavanipuram", "Iron Yard Road, Bhavanipuram - 520012"),
        "Ibrahimpatnam Station": (16.5890, 80.5210, "Ibrahimpatnam", "Ferry Center", "Hyderabad Highway, Ibrahimpatnam - 521456"),
        "Jaggaiahpet Station": (16.8920, 80.0980, "Jaggaiahpet", "Chillakallu Road", "Near RTO Checkpost, Jaggaiahpet - 521175"),
        "Tiruvuru Station": (17.1120, 80.6120, "Tiruvuru", "Madhira Road", "Opp. RTC Depot, Tiruvuru - 521235"),
        "Mylavaram Station": (16.7620, 80.6410, "Mylavaram", "Nuzvid Road", "Near Court Complex, Mylavaram - 521230")
    },
    "East Godavari": {
        "Rajahmundry Urban Station": (17.0005, 81.8040, "Rajahmundry Urban", "Danavaipeta", "Near Sub-Collector Office, Rajahmundry - 533101"),
        "Rajahmundry Rural Station": (16.9820, 81.7650, "Rajahmundry Rural", "Morampudi", "NH-16 Junction, Morampudi - 533107"),
        "Kovvur Station": (17.0120, 81.7320, "Kovvur", "Gosthani Ghat", "Godavari Bund Road, Kovvur - 534350"),
        "Nidadavole Station": (16.9150, 81.6710, "Nidadavole", "Railway Gate", "Main Road, Nidadavole - 534301"),
        "Gopalapuram Station": (17.1080, 81.5420, "Gopalapuram", "Center", "Devarapalli Road, Gopalapuram - 534316")
    },
    "Kakinada": {
        "Kakinada Urban Station": (16.9891, 82.2475, "Kakinada Urban", "Suryaraopeta", "Collectorate Road, Kakinada - 533001"),
        "Kakinada Rural Station": (17.0250, 82.2150, "Kakinada Rural", "Sarpavaram", "Sarpavaram Junction, Kakinada - 533005"),
        "Peddapuram Station": (17.0810, 82.1380, "Peddapuram", "Main Road", "Near Anand Theater, Peddapuram - 533437"),
        "Pithapuram Station": (17.1150, 82.2590, "Pithapuram", "Kukkuteswara Swamy Temple Road", "Samalkota Road, Pithapuram - 533450"),
        "Tuni Station": (17.3550, 82.5480, "Tuni", "Bypass", "Payakaraopeta Road, Tuni - 533401")
    },
    "Dr. B.R. Ambedkar Konaseema": {
        "Amalapuram Station": (16.5787, 82.0061, "Amalapuram", "Clock Tower", "College Road, Amalapuram - 533201"),
        "Ramachandrapuram Station": (16.8420, 82.0250, "Ramachandrapuram", "Draksharamam Road", "Near RDO Office, Ramachandrapuram - 533255"),
        "Razole Station": (16.4780, 81.8350, "Razole", "Tatipaka", "Dindi Road, Razole - 533242"),
        "Mandapeta Station": (16.8650, 81.9320, "Mandapeta", "Alamuru Road", "Near Rice Millers Association, Mandapeta - 533308"),
        "Kothapeta Station": (16.7180, 81.8950, "Kothapeta", "Ravulapalem Road", "Near Bridge Center, Kothapeta - 533223")
    },
    "West Godavari": {
        "Bhimavaram Station": (16.5449, 81.5212, "Bhimavaram", "Somaramam", "PP Road, Bhimavaram - 534201"),
        "Tadepalligudem Station": (16.8120, 81.5280, "Tadepalligudem", "KN Road", "Near Aerodrome, Tadepalligudem - 534101"),
        "Tanuku Station": (16.7580, 81.6820, "Tanuku", "Sajjapuram", "Rashtrapati Road, Tanuku - 534211"),
        "Palakollu Station": (16.5180, 81.7320, "Palakollu", "Ksheerarama", "Bhimavaram Road, Palakollu - 534260"),
        "Narsapur Station": (16.4380, 81.7010, "Narsapur", "Steamer Road", "Godavari Bund, Narsapur - 534275")
    },
    "Eluru": {
        "Eluru Town Station": (16.7107, 81.0952, "Eluru Urban", "Powerpet", "Opposite R.R. Pet Post Office, Eluru - 534002"),
        "Eluru Rural Station": (16.7350, 81.1250, "Eluru Rural", "Sanivarapupeta", "Bypass NH-16, Eluru - 534003"),
        "Jangareddygudem Station": (17.1250, 81.2950, "Jangareddygudem", "Aswaraopeta Road", "Near Old Bus Stand, Jangareddygudem - 534447"),
        "Chintalapudi Station": (17.0650, 80.9850, "Chintalapudi", "Eluru Road", "Near Tahsildar Office, Chintalapudi - 534460"),
        "Nuzvid Station": (16.7850, 80.8480, "Nuzvid", "Hanuman Junction Road", "Near IIIT Campus, Nuzvid - 521201"),
        "Kaikalur Station": (16.5580, 81.2050, "Kaikalur", "Kolleru Road", "Near Railway Station, Kaikalur - 521333")
    },
    "Nellore": {
        "Nellore Urban Station": (14.4426, 79.9865, "Nellore Urban", "Dargamitta", "Collectorate Compound, Nellore - 524003"),
        "Nellore Rural Station": (14.4210, 79.9540, "Nellore Rural", "Podalakur Road", "Near Vedayapalem, Nellore - 524004"),
        "Kavali Station": (14.9120, 79.9920, "Kavali", "Trunk Road", "Near Court Complex, Kavali - 524201"),
        "Gudur Station": (14.1480, 79.8510, "Gudur", "Tower Clock", "East Street, Gudur - 524101"),
        "Atmakur Station": (14.6180, 79.6250, "Atmakur", "Badvel Road", "Near RTC Bus Stand, Atmakur, Nellore Dist - 524322"),
        "Venkatagiri Station": (13.9620, 79.5820, "Venkatagiri", "Raja Veedhi", "Near Raja Palace, Venkatagiri - 524132")
    },
    "Tirupati": {
        "Tirupati Urban Station": (13.6288, 79.4192, "Tirupati Urban", "Bhavani Nagar", "Alipiri Bypass Road, Tirupati - 517501"),
        "Renigunta Station": (13.6480, 79.5120, "Renigunta", "Airport Road", "Near Railway Junction, Renigunta - 517520"),
        "Srikalahasti Station": (13.7510, 79.6980, "Srikalahasti", "Panagal Road", "Near Temple Arch, Srikalahasti - 517644"),
        "Chandragiri Station": (13.5850, 79.3180, "Chandragiri", "Fort Road", "Near Raja Mahal, Chandragiri - 517101"),
        "Puttur Station": (13.4420, 79.5520, "Puttur", "Nagari Road", "Near Bone Specialty Center, Puttur - 517583"),
        "Sullurpeta Station": (13.7020, 80.0210, "Sullurpeta", "SHAR Road", "Near Pulicat View Point, Sullurpeta - 524121")
    },
    "Chittoor": {
        "Chittoor Urban Station": (13.2172, 79.1003, "Chittoor Urban", "Kongareddy Palli", "Beside SP Office, Chittoor - 517001"),
        "Chittoor Rural Station": (13.2450, 79.1280, "Chittoor Rural", "GD Nellore Road", "Near Murukambattu, Chittoor - 517002"),
        "Palamaner Station": (13.2010, 78.7510, "Palamaner", "Bangalore Road", "Near Forest Complex, Palamaner - 517408"),
        "Nagari Station": (13.3280, 79.5850, "Nagari", "Tirupati Road", "Near Municipal Office, Nagari - 517590"),
        "Bangarupalem Station": (13.1950, 78.9180, "Bangarupalem", "Palamaner Highway", "Main Center, Bangarupalem - 517416"),
        "Kuppam Station": (12.7480, 78.3650, "Kuppam", "PES Medical Road", "Near Railway Station, Kuppam - 517425")
    },
    "Ananthapuramu": {
        "Anantapur Urban Station": (14.6819, 77.6006, "Anantapur Urban", "Subash Nagar", "Court Road, Anantapur - 515001"),
        "Anantapur Rural Station": (14.6520, 77.6250, "Anantapur Rural", "Raptadu Road", "Near JNTU Engineering College, Anantapur - 515002"),
        "Guntakal Station": (15.1720, 77.3710, "Guntakal", "Railway Colony", "Near DRM Office, Guntakal - 515801"),
        "Tadipatri Station": (14.9120, 78.0120, "Tadipatri", "Bugga Road", "Near Railway Feeder, Tadipatri - 515411"),
        "Dharmavaram Station": (14.4150, 77.7210, "Dharmavaram", "Silk Colony", "Railway Station Road, Dharmavaram - 515671"),
        "Rayadurg Station": (14.7020, 76.8620, "Rayadurg", "Fort Hill Road", "Bellary Road, Rayadurg - 515865"),
        "Uravakonda Station": (14.9450, 77.2580, "Uravakonda", "Budagavi", "Bellary Highway, Uravakonda - 515812")
    },
    "Sri Sathya Sai": {
        "Hindupur Station": (13.8280, 77.4920, "Hindupur", "Melapuram", "Bangalore Highway, Hindupur - 515201"),
        "Kadiri Station": (14.1120, 78.1620, "Kadiri", "Narasimha Temple Road", "Bypass Road, Kadiri - 515591"),
        "Penukonda Station": (14.0850, 77.5950, "Penukonda", "KIA Motors Zone", "Main Bazaar, Penukonda - 515110"),
        "Puttaparthi Station": (14.1706, 77.8105, "Puttaparthi", "Chitravathi Road", "Near Ashram Complex, Puttaparthi - 515134"),
        "Madakasira Station": (13.9420, 77.2710, "Madakasira", "Pavagada Road", "Near Old Bus Stand, Madakasira - 515301")
    },
    "YSR Kadapa": {
        "Kadapa Town Station": (14.4673, 78.8242, "Kadapa Urban", "Nagarajupeta", "Beside Rims Hospital Road, Kadapa - 516001"),
        "Kadapa Rural Station": (14.4850, 78.8050, "Kadapa Rural", "Chinna Chowk", "Rayachoty Road, Kadapa - 516002"),
        "Proddatur Station": (14.7520, 78.5520, "Proddatur", "Bollavaram", "Jammalamadugu Road, Proddatur - 516360"),
        "Pulivendula Station": (14.4180, 78.2310, "Pulivendula", "Bakrapuram", "Muddanur Road, Pulivendula - 516390"),
        "Jammalamadugu Station": (14.8510, 78.3820, "Jammalamadugu", "Gandikota Road", "Near Bus Station, Jammalamadugu - 516434"),
        "Badvel Station": (14.7420, 79.0580, "Badvel", "Mydukur Road", "Near Market Yard, Badvel - 516227")
    },
    "Annamayya": {
        "Madanapalle Station": (13.5520, 78.5020, "Madanapalle", "Neerugattuvaripalli", "Beside Sub-Collector Office, Madanapalle - 517325"),
        "Rayachoty Urban Station": (14.0104, 78.7516, "Rayachoty Urban", "Market Veedhi", "Collectorate Road, Rayachoty - 516269"),
        "Rayachoty Rural Station": (14.0320, 78.7350, "Rayachoty Rural", "Masapet", "Kadapa Highway, Rayachoty - 516270"),
        "Rajampet Station": (14.1850, 79.1620, "Rajampet", "Old Bus Stand", "Kadapa-Tirupati Highway, Rajampet - 516115"),
        "Railway Kodur Station": (13.9550, 79.3510, "Railway Kodur", "Station Road", "Near Railway Station, Railway Kodur - 516101")
    },
    "Prakasam": {
        "Ongole Urban Station": (15.5057, 80.0499, "Ongole Urban", "Kurnool Road", "Opposite SP Office, Ongole - 523001"),
        "Ongole Rural Station": (15.5250, 80.0210, "Ongole Rural", "Pelluru", "Bypass Road, Ongole - 523002"),
        "Kandukur Station": (15.2150, 79.9050, "Kandukur", "Pamuru Road", "Near Court Complex, Kandukur - 523105"),
        "Markapur Station": (15.7350, 79.2710, "Markapur", "Slate Town", "Giddalur Road, Markapur - 523316"),
        "Giddalur Station": (15.3780, 78.9250, "Giddalur", "Railway Feeder", "Nandyal Highway, Giddalur - 523357"),
        "Kanigiri Station": (15.4020, 79.5120, "Kanigiri", "Beside RTC", "Podili Road, Kanigiri - 523230")
    },
    "Srikakulam": {
        "Srikakulam Town Station": (18.2949, 83.8938, "Srikakulam Urban", "Palakonda Road", "Near Seven Road Junction, Srikakulam - 532001"),
        "Srikakulam Rural Station": (18.2710, 83.9180, "Srikakulam Rural", "Arasavalli", "Near Sun Temple Road, Srikakulam - 532005"),
        "Palasa Station": (18.7710, 84.4150, "Palasa", "Kasibugga", "National Highway 16, Palasa-Kasibugga - 532222"),
        "Tekkali Station": (18.6150, 84.2350, "Tekkali", "Court Road", "Near RDO Office, Tekkali - 532201"),
        "Amadalavalasa Station": (18.4120, 83.9020, "Amadalavalasa", "Sugar Mill Road", "Near Railway Junction, Amadalavalasa - 532185"),
        "Narasannapeta Station": (18.4210, 84.0480, "Narasannapeta", "Main Bazaar", "NH-16 Junction, Narasannapeta - 532421")
    },
    "Vizianagaram": {
        "Vizianagaram Urban Station": (18.1067, 83.3956, "Vizianagaram Urban", "Fort Road", "Near Moti Mahal, Vizianagaram - 535001"),
        "Vizianagaram Rural Station": (18.1280, 83.4210, "Vizianagaram Rural", "Cantonment", "Near Railway Gate, Vizianagaram - 535003"),
        "Bobbili Station": (18.5710, 83.3650, "Bobbili", "Fort Center", "Near Bobbili Palace, Bobbili - 535558"),
        "Cheepurupalli Station": (18.3120, 83.5680, "Cheepurupalli", "Garividi Road", "Main Bazaar, Cheepurupalli - 535128"),
        "Gajapathinagaram Station": (18.2780, 83.3350, "Gajapathinagaram", "Salur Road", "Near Tahsildar Office, Gajapathinagaram - 535270"),
        "Srungavarapukota Station": (18.1180, 83.1510, "Srungavarapukota", "Bowdara Road", "Araku Ghat Road, S.Kota - 535145")
    },
    "Parvathipuram Manyam": {
        "Parvathipuram Station": (18.7796, 83.4278, "Parvathipuram", "Belagam", "Beside ITDA Office, Parvathipuram - 535501"),
        "Salur Station": (18.5280, 83.2150, "Salur", "Pachipenta Road", "Near Old Bus Stand, Salur - 535591"),
        "Palakonda Station": (18.6020, 83.7580, "Palakonda", "RTC Complex Road", "Main Bazaar, Palakonda - 535440"),
        "Kurupam Station": (18.8710, 83.5510, "Kurupam", "Agency Road", "Near Palace Center, Kurupam - 535524")
    }
}


def run_migration():
    print("================================================================")
    print("MIGRATING & SEEDING VERIFIED EXCISE STATIONS (SUPABASE & SQLITE)")
    print("================================================================")
    
    # Ensure table is created
    VerifiedStation.__table__.create(bind=sync_engine, checkfirst=True)
    print("  ✓ Verified 'verified_stations' table exists or was created.")

    session = SyncSessionLocal()
    try:
        existing_count = session.query(VerifiedStation).count()
        print(f"  Existing verified stations in database: {existing_count}")

        inserted_count = 0
        updated_count = 0

        # Loop through all 26 districts and 146 verified stations
        for district, stations_dict in OFFICIAL_STATION_REGISTRY_DATA.items():
            for station_name, details in stations_dict.items():
                lat, lon, mandal, locality, address = details
                # Derive deterministic station code
                code_prefix = district[:3].upper()
                clean_name = re.sub(r'[^A-Z0-9]', '', station_name.replace("Station", "").upper())
                station_code = f"AP-EXC-{code_prefix}-{clean_name[:15]}"

                stn = session.query(VerifiedStation).filter(
                    VerifiedStation.district == district,
                    VerifiedStation.station_name == station_name
                ).first()

                if not stn:
                    stn = VerifiedStation(
                        id=generate_uuid(),
                        station_code=station_code,
                        station_name=station_name,
                        district=district,
                        mandal=mandal,
                        locality=locality,
                        address=address,
                        state="Andhra Pradesh",
                        latitude=lat,
                        longitude=lon,
                        is_active=True,
                        verification_source="AP_EXCISE_OFFICIAL_REGISTRY_2024"
                    )
                    session.add(stn)
                    inserted_count += 1
                else:
                    stn.latitude = lat
                    stn.longitude = lon
                    stn.mandal = mandal
                    stn.locality = locality
                    stn.address = address
                    stn.station_code = station_code
                    updated_count += 1

        session.commit()
        total_now = session.query(VerifiedStation).count()
        print(f"  ✓ Inserted: {inserted_count}, Updated: {updated_count}")
        print(f"  ✓ Total verified stations in database now: {total_now}")
        print("MIGRATION COMPLETED SUCCESSFULLY.")
    except Exception as e:
        session.rollback()
        print(f"  ✗ Error during migration: {e}")
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    run_migration()
