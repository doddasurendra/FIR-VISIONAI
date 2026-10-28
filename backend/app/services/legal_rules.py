"""
Offence rules for legal section suggestions.

Each rule says which provisions apply to a kind of offence under each regime (IPC for incidents before
1 July 2024, BNS on or after; special Acts regardless of date), what triggers it in the case facts, and
its essential ingredients with the words in an FIR that evidence each one. The recommender reports, for
every provision, which ingredients the recorded facts establish and which are still missing.

These are review aids for the officer, not legal determinations. Provision text comes from the legal
corpus; a rule only names the provision.
"""
import re
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

BNS = "Bharatiya Nyaya Sanhita, 2023"
IPC = "Indian Penal Code, 1860"
EXCISE = "Andhra Pradesh Excise Act, 1968"
PROHIBITION = "Andhra Pradesh Prohibition Act, 1995"
NDPS = "Narcotic Drugs and Psychotropic Substances Act, 1985"
BNS_COMMENCEMENT = date(2024, 7, 1)

LIQUOR = ["liquor", "arrack", "distill", "wash", "hooch", "toddy", "spirit", "gudumba", "non-duty paid", "ndpl",
          "spurious", "iml", "jaggery"]
VEHICLE = ["vehicle", "auto", "lorry", "truck", "car ", "bike", "two wheeler", "two-wheeler", "motorcycle", "scooter",
           "conveyance", "tractor", "van"]
TRANSPORT_OR_POSSESSION = ["transport", "possession", "possess", "carrying", "carried", "manufactur", "distill",
                           "sale", "selling", "sold", "stor", "conceal"]

# IPC provisions and their BNS counterparts (for FIRs that cite the IPC for a post-1 July 2024 incident)
IPC_TO_BNS = {"Section 379": "Section 303(2)", "Section 411": "Section 317(2)", "Section 279": "Section 281",
              "Section 304A": "Section 106(1)", "Section 420": "Section 318(4)", "Section 302": "Section 103(1)",
              "Section 34": "Section 3(5)", "Section 120B": "Section 61(2)"}


def _ganja_subsection(case) -> Tuple[str, Optional[str]]:
    kg = None
    unit = (case.seized_unit or "").lower()
    if case.seized_quantity is not None:
        if unit.startswith("kg") or "kilo" in unit:
            kg = case.seized_quantity
        elif unit.startswith("g") or "gram" in unit:
            kg = case.seized_quantity / 1000
    if kg is None:
        return "Section 20(b)(ii)(B)", "Weighed quantity of ganja (decides small / intermediate / commercial quantity)"
    if kg <= 1:
        return "Section 20(b)(ii)(A)", None
    if kg < 20:
        return "Section 20(b)(ii)(B)", None
    return "Section 20(b)(ii)(C)", None


RULES: List[Dict] = [
    {
        "key": "theft", "offence": "Theft",
        "triggers": ["theft", "stole", "stolen", "snatch", "pickpocket", "burglar", "robbed"],
        "provisions": {"BNS": [(BNS, ["Section 303(2)", "Section 303"])], "IPC": [(IPC, ["Section 379"])]},
        "ingredients": [
            ("Movable property involved", VEHICLE + ["property", "phone", "gold", "cash", "jewel", "activa", "laptop"]),
            ("Property was in another person's possession", ["complainant", "owner", "belonging", "parked", "his ", "her "]),
            ("Taken without that person's consent", ["without consent", "stole", "stolen", "theft", "snatch"]),
            ("Dishonest intention", ["dishonest", "stole", "stolen", "theft"]),
            ("Property moved in order to take it", ["fled", "took", "taken", "drove away", "stole", "removed", "lifted"]),
        ],
    },
    {
        "key": "stolen_property", "offence": "Receiving / retaining stolen property",
        "triggers": ["stolen property", "received stolen", "receiving stolen", "retained stolen", "recovered from the accused",
                     "found in possession of stolen"],
        "provisions": {"BNS": [(BNS, ["Section 317(2)", "Section 317"])], "IPC": [(IPC, ["Section 411"])]},
        "ingredients": [
            ("The property is stolen property", ["stolen", "stole"]),
            # Phrases, not "received" alone: every FIR says "information received at the police station"
            ("The accused received or retained it", ["received the stolen", "received stolen", "receiving stolen",
                                                     "retained the stolen", "retained stolen", "recovered from the accused",
                                                     "recovered from him", "recovered from her", "found in possession",
                                                     "found in his possession", "found in her possession"]),
            ("Knowing or having reason to believe it was stolen", ["knowing", "reason to believe", "knowingly"]),
        ],
    },
    {
        "key": "excise_liquor", "offence": "Illicit liquor (AP Excise Act)",
        "triggers": LIQUOR,
        "provisions": {"ANY": [(EXCISE, ["Section 34(a)"])]},
        "ingredients": [
            ("An intoxicant (liquor, arrack, wash) is involved", LIQUOR),
            ("Import, export, transport, manufacture, possession or sale", TRANSPORT_OR_POSSESSION),
            ("Without a licence or permit", ["without permit", "without licence", "without license", "no permit",
                                             "failed to produce", "without valid", "without any"]),
        ],
    },
    {
        "key": "arrack", "offence": "Arrack / country liquor (AP Prohibition Act)",
        "triggers": ["arrack", "country liquor", "id liquor", "illicit distilled"],
        "provisions": {"ANY": [(PROHIBITION, ["Section 8(b)"])]},
        "ingredients": [
            ("The substance is arrack or country liquor", ["arrack", "country liquor", "id liquor", "illicit distilled"]),
            ("Manufacture, transport, sale or possession in Andhra Pradesh", TRANSPORT_OR_POSSESSION),
        ],
    },
    {
        "key": "ndpl", "offence": "Non-duty-paid liquor (AP Prohibition Act)",
        "triggers": ["non-duty paid", "non duty paid", "ndpl", "duty not paid", "without excise duty", "karnataka liquor",
                     "telangana liquor", "other state liquor"],
        "provisions": {"ANY": [(PROHIBITION, ["Section 8(c)"])]},
        "ingredients": [
            ("Liquor on which AP excise duty was not paid", ["non-duty paid", "non duty paid", "ndpl", "duty", "other state"]),
            ("No transit permit or invoice", ["without permit", "no permit", "without valid", "failed to produce"]),
        ],
    },
    {
        "key": "excise_vehicle", "offence": "Confiscation of the conveyance (AP Excise Act)",
        "triggers": LIQUOR, "requires_vehicle": True,
        "provisions": {"ANY": [(EXCISE, ["Section 45"])]},
        "ingredients": [
            ("An offence under the AP Excise Act", LIQUOR),
            ("The vehicle was used to transport or conceal the contraband", VEHICLE),
        ],
    },
    {
        "key": "ganja", "offence": "Ganja / cannabis (NDPS Act)",
        "triggers": ["ganja", "cannabis", "marijuana", "hemp"],
        "provisions": {"ANY": [(NDPS, ["Section 8(c)"]), (NDPS, ["@ganja_quantity"])]},
        "ingredients": [
            ("The substance is ganja / cannabis", ["ganja", "cannabis", "marijuana", "hemp"]),
            ("Production, possession, transport or sale", TRANSPORT_OR_POSSESSION),
            ("Quantity weighed and recorded", ["kg", "kilogram", "gram"]),
        ],
    },
    {
        "key": "ndps_vehicle", "offence": "Conveyance used for an NDPS offence",
        "triggers": ["ganja", "cannabis", "marijuana"], "requires_vehicle": True,
        "provisions": {"ANY": [(NDPS, ["Section 25"])]},
        "ingredients": [
            ("Owner or person in control of the conveyance", ["owner", "driver", "driving", "registered"]),
            ("Conveyance used for the NDPS offence", VEHICLE),
            ("Knowledge or permission of that person", ["knowing", "knowledge", "permitted", "allowed"]),
        ],
    },
    {
        "key": "rash_driving", "offence": "Rash or negligent driving",
        "triggers": ["rash", "negligent", "accident", "collided", "hit and run", "overspeed", "over speed", "high speed"],
        "provisions": {"BNS": [(BNS, ["Section 281"])], "IPC": [(IPC, ["Section 279"])]},
        "ingredients": [
            ("A vehicle driven on a public way", ["road", "highway", "public way", "street", "junction"]),
            ("Driven in a rash or negligent manner", ["rash", "negligent", "speed"]),
            ("Endangering human life or likely to cause hurt", ["injur", "hurt", "died", "death", "endanger"]),
        ],
    },
    {
        "key": "death_negligence", "offence": "Death by negligence",
        "triggers": ["died", "death", "deceased", "fatal"], "also_needs": ["rash", "negligent", "accident", "collided"],
        "provisions": {"BNS": [(BNS, ["Section 106(1)", "Section 106"])], "IPC": [(IPC, ["Section 304A"])]},
        "ingredients": [
            ("A death was caused", ["died", "death", "deceased", "fatal"]),
            ("By a rash or negligent act", ["rash", "negligent", "accident"]),
            ("Not amounting to culpable homicide", ["accident", "negligent"]),
        ],
    },
    {
        "key": "adulteration", "offence": "Adulterated liquor causing hurt or death",
        "triggers": ["methanol", "poison", "adulterat", "noxious"], "also_needs": ["death", "died", "hurt", "blind", "hospital"],
        "provisions": {"ANY": [(EXCISE, ["Section 37A"])]},
        "ingredients": [
            ("A noxious substance mixed into liquor", ["methanol", "poison", "adulterat", "noxious"]),
            ("Consumption caused grievous hurt or death", ["death", "died", "blind", "grievous", "hospital"]),
        ],
    },
]

# ── Facts ────────────────────────────────────────────────────────────────────

_MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                        "september", "october", "november", "december"], start=1)}
_DATE_NUMERIC = re.compile(r"(?:occurrence of offence|date of offence|date of occurrence|offence)[^0-9]{0,40}?"
                           r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", re.I)
_DATE_WORDS = re.compile(r"(?:occurrence of offence|date of offence|date of occurrence)[^0-9]{0,40}?"
                         r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+),?\s+(\d{4})", re.I)


def incident_date_from_text(text: str) -> Optional[date]:
    """The date of offence written in an FIR ('Occurrence of Offence: Day : 14.08.2024', 'Date of Offence: 14th August 2024')."""
    for rx in (_DATE_NUMERIC, _DATE_WORDS):
        m = rx.search(text or "")
        if not m:
            continue
        try:
            d, mo, y = m.group(1), m.group(2), m.group(3)
            month = int(mo) if mo.isdigit() else _MONTHS.get(mo.lower())
            if month:
                return date(int(y), month, int(d))
        except ValueError:
            continue
    return None


def parse_date_value(value) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    for candidate in (s, s[:10], s[:19]):
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%d %B %Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
    return incident_date_from_text(f"date of offence {s}")


_ACT_HINTS = [
    (re.compile(r"\b(?:ipc|i\.p\.c\.?|indian penal code)\b", re.I), IPC),
    (re.compile(r"\b(?:bns|bharatiya nyaya sanhita)\b", re.I), BNS),
    (re.compile(r"\b(?:ndps|narcotic drugs)", re.I), NDPS),
    (re.compile(r"prohibition act", re.I), PROHIBITION),
    (re.compile(r"excise act", re.I), EXCISE),
]
_SECTION_LIST = r"((?:\d{1,3}[A-Z]?(?:\([0-9a-zA-Z]+\))*\s*(?:,|and|&|/)?\s*)+)"
_RECORDED_BEFORE = re.compile(r"\bsec(?:tion)?s?\.?\s*" + _SECTION_LIST +
                              r"\s*(?:of\s+(?:the\s+)?)?(ipc|i\.p\.c\.?|indian penal code|bns|bharatiya nyaya sanhita|"
                              r"ndps(?: act)?|narcotic drugs[^,.;]*act|(?:a\.?p\.?\s*)?prohibition act|(?:a\.?p\.?\s*|andhra pradesh\s+)?excise act)", re.I)
_RECORDED_AFTER = re.compile(r"(indian penal code|bharatiya nyaya sanhita|ndps act|narcotic drugs[^,.;]*act|prohibition act[^-–:]{0,10}|"
                             r"excise act[^-–:]{0,10})\s*[-–:]\s*sec(?:tion)?s?\.?\s*" + _SECTION_LIST, re.I)


def _act_for(hint: str) -> Optional[str]:
    for rx, act in _ACT_HINTS:
        if rx.search(hint):
            return act
    return None


def recorded_sections(texts: List[str]) -> List[Tuple[str, str]]:
    """(act, 'Section N') pairs an FIR records: 'Sections 379, 411 IPC', 'AP Excise Act, 1968 - Section 34(a)'."""
    found: List[Tuple[str, str]] = []
    for t in texts:
        for m in _RECORDED_BEFORE.finditer(t or ""):
            act = _act_for(m.group(2))
            for num in re.findall(r"\d{1,3}[A-Z]?(?:\([0-9a-zA-Z]+\))*", m.group(1)):
                pair = (act, f"Section {num}")
                if act and pair not in found:
                    found.append(pair)
        for m in _RECORDED_AFTER.finditer(t or ""):
            act = _act_for(m.group(1))
            for num in re.findall(r"\d{1,3}[A-Z]?(?:\([0-9a-zA-Z]+\))*", m.group(2)):
                pair = (act, f"Section {num}")
                if act and pair not in found:
                    found.append(pair)
    return found


def regime_for(incident: Optional[date]) -> str:
    if incident is None:
        return "UNKNOWN"
    return "BNS" if incident >= BNS_COMMENCEMENT else "IPC"


def _cue_present(cue: str, facts: str) -> bool:
    if len(cue) <= 3 and cue.isalpha():
        return re.search(rf"\b{re.escape(cue)}\b", facts) is not None
    return cue in facts


def evaluate_ingredients(rule: Dict, facts: str) -> Tuple[List[str], List[str]]:
    matched, missing = [], []
    for label, cues in rule["ingredients"]:
        (matched if any(_cue_present(c, facts) for c in cues) else missing).append(label)
    return matched, missing


def triggered(rule: Dict, facts: str, has_vehicle: bool) -> bool:
    if not any(_cue_present(t, facts) for t in rule["triggers"]):
        return False
    if rule.get("also_needs") and not any(_cue_present(t, facts) for t in rule["also_needs"]):
        return False
    if rule.get("requires_vehicle") and not has_vehicle:
        return False
    return True


def provisions_for(rule: Dict, regime: str, case) -> List[Tuple[str, List[str], Optional[str]]]:
    """[(act, [section numbers in preference order], extra missing ingredient)] for the regime ('UNKNOWN' -> both)."""
    keys = ["ANY"] + (["BNS", "IPC"] if regime == "UNKNOWN" else [regime])
    out = []
    for k in keys:
        for act, numbers in rule["provisions"].get(k, []):
            extra = None
            if numbers == ["@ganja_quantity"]:
                number, extra = _ganja_subsection(case)
                numbers = [number]
            out.append((act, numbers, extra))
    return out


def rule_for_provision(act: str, number: str) -> Optional[Dict]:
    """The offence rule naming this provision (used to evaluate ingredients of sections the FIR records)."""
    base = re.sub(r"\(.*$", "", number)
    for rule in RULES:
        for plist in rule["provisions"].values():
            for a, numbers in plist:
                if a == act and any(n == number or re.sub(r"\(.*$", "", n) == base for n in numbers):
                    return rule
    return None
