"""
Deterministic reading of the standard AP FIR form (Form IF-1 / u/s 154 Cr.P.C.) and of seizure
report lines ("Contraband Seized: ...", "Vehicle: ... | Accused: ...").

Every value is copied from the text, with the passage it came from, so it can be checked against
the document. The model-based extraction fills only what this parser cannot read; the extraction
quality check compares stored case fields with what this parser reads.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .field_validation import canonical_contraband

_DATE = r"(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})"
_TIME = r"(\d{1,2})[.:](\d{2})\s*(?:hrs|hours|h)?"
_SUB_ITEM = re.compile(r"\s\(\s*[a-e]\s*\)\s")
_NOT_A_PLACE = re.compile(r"^(direction|distance|beat|if outside|-|nil|not applicable)", re.I)
# Parts of an address that are not the town or village (roads, landmarks, district names)
_NOT_A_TOWN = re.compile(r"district|dist\.|near|beat|\d|road|street|bazaa?r|main|colony|nagar|bus|stand|stop|"
                         r"branch|bank|market|junction|circle|cross|lane|toll|plaza|station|opp|behind", re.I)
VEHICLE_REG = re.compile(r"\b([A-Z]{2})\s*-?\s*(\d{1,2})\s*-?\s*([A-Z]{1,3})\s*-?\s*(\d{3,4})\b")

# Acts as written in FIRs -> short name used in case fields and legal suggestions
_ACT_NAMES = [
    (re.compile(r"\bI\.?\s*P\.?\s*C\b|Indian Penal Code", re.I), "IPC"),
    (re.compile(r"\bB\.?\s*N\.?\s*S\.?\s*S\b|Nagarik Suraksha", re.I), "BNSS"),
    (re.compile(r"\bB\.?\s*N\.?\s*S\b|Nyaya Sanhita", re.I), "BNS"),
    (re.compile(r"\bI\.?\s*T\.?\s*Act\b|Information Technology Act", re.I), "IT Act"),
    (re.compile(r"\bN\.?\s*D\.?\s*P\.?\s*S\b|Narcotic Drugs", re.I), "NDPS Act"),
    (re.compile(r"Arms Act", re.I), "Arms Act"),
    (re.compile(r"\bM\.?\s*V\.?\s*Act\b|Motor Vehicles Act", re.I), "MV Act"),
    (re.compile(r"Excise Act", re.I), "AP Excise Act"),
    (re.compile(r"Prevention of Corruption Act|\bP\.?\s*C\.?\s*Act\b", re.I), "PC Act"),
]
# Offence words for sections that commonly appear, used to name the offence when the FIR does not
OFFENCE_BY_SECTION = {
    ("IPC", "420"): "cheating", ("IPC", "468"): "forgery for the purpose of cheating",
    ("IPC", "471"): "using a forged document as genuine", ("IPC", "379"): "theft", ("IPC", "380"): "theft in a dwelling",
    ("IPC", "302"): "murder", ("IPC", "307"): "attempt to murder", ("IPC", "323"): "voluntarily causing hurt",
    ("IPC", "354"): "assault on a woman", ("IPC", "363"): "kidnapping", ("IPC", "365"): "abduction",
    ("IPC", "392"): "robbery", ("IPC", "406"): "criminal breach of trust", ("IPC", "457"): "house-breaking by night",
    ("IPC", "279"): "rash driving", ("IPC", "304A"): "causing death by negligence",
    ("IT Act", "66C"): "identity theft", ("IT Act", "66D"): "cheating by personation using a computer resource",
    ("BNS", "318"): "cheating", ("BNS", "336"): "forgery", ("BNS", "340"): "using a forged document as genuine",
    ("BNS", "303"): "theft", ("BNS", "281"): "rash driving",
}


@dataclass
class ParsedFIR:
    offence_date: Optional[datetime] = None
    time_from: Optional[str] = None
    time_to: Optional[str] = None
    place: Optional[str] = None
    address: Optional[str] = None
    town: Optional[str] = None
    district: Optional[str] = None
    complainant: Optional[str] = None
    accused: List[str] = field(default_factory=list)
    sections: List[Tuple[str, str]] = field(default_factory=list)    # (act, section)
    contraband_raw: Optional[str] = None
    contraband_type: Optional[str] = None
    seized_quantity: Optional[float] = None
    seized_unit: Optional[str] = None
    vehicle_details: Optional[str] = None
    vehicle_registration: Optional[str] = None
    particulars: Optional[str] = None
    occurrence: Optional[str] = None
    officer: Optional[str] = None
    evidence: Dict[str, str] = field(default_factory=dict)            # field -> passage it was read from

    def section_labels(self) -> List[str]:
        return [f"{act} {sec}" for act, sec in self.sections]

    def offence_label(self) -> Optional[str]:
        names = []
        for key in self.sections:
            name = OFFENCE_BY_SECTION.get((key[0], re.sub(r"\(.*", "", key[1])))
            if name and name not in names:
                names.append(name)
        return ", ".join(names) if names else None


def normalise_registration(text: Optional[str]) -> Optional[str]:
    """'AP 21 TY 4567' / 'AP-21-TY-4567' -> 'AP21TY4567'; None when no Indian registration is present."""
    m = VEHICLE_REG.search((text or "").upper())
    return "".join(m.groups()) if m else None


def _date(d: str, m: str, y: str) -> Optional[datetime]:
    year = int(y) + (2000 if len(y) == 2 else 0)
    try:
        return datetime(year, int(m), int(d))
    except ValueError:
        return None


def _line_value(text: str, label: str) -> Optional[Tuple[str, str]]:
    m = re.search(label + r"\s*[:\-]\s*(.+)", text, re.I)
    if not m:
        return None
    value = m.group(1).strip().strip("|").strip()
    return (value, m.group(0).strip()) if value and not re.fullmatch(r"[-–—\s]*|nil|n/?a", value, re.I) else None


def _clean_name(value: str) -> str:
    value = re.split(r"\s+\(?[a-h]\)\s|\s{2,}|\||;|,\s*(?:s/o|d/o|w/o|aged|age)\b", value, flags=re.I)[0]
    value = re.sub(r"\((?:A|W|LW)-?\d+\)", "", value)
    return value.strip(" .,:-")


def _sections(text: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    # "Act, Indian Penal Code : Sections 420, 468, 471 IPC." / "Section 66C, 66D of IT Act, 2000"
    for m in re.finditer(r"(?:u/s|sections?|secs?\.?)\s*((?:\d{1,3}[A-Z]{0,2}(?:\(\w{1,3}\))*(?:\s*(?:,|and|&|/|r/w)\s*)?)+)"
                         r"([^\n]{0,60})", text, re.I):
        nums = re.findall(r"\d{1,3}[A-Z]{0,2}(?:\(\w{1,3}\))*", m.group(1))
        context = m.group(2) + " " + text[max(0, m.start() - 60):m.start()]
        act = None
        # The act named right after the numbers wins over one named before them
        for rx, name in _ACT_NAMES:
            if rx.search(m.group(2)):
                act = name
                break
        if not act:
            for rx, name in _ACT_NAMES:
                if rx.search(context):
                    act = name
                    break
        if not act:
            continue
        for n in nums:
            if (act, n) not in out and n not in ("154", "157", "173") :
                out.append((act, n))
    return out


def parse_fir_text(text: str) -> ParsedFIR:
    """Fields read verbatim from FIR / seizure-report text. Missing fields stay None."""
    p = ParsedFIR()
    t = text or ""

    m = re.search(r"Occurrence of Offence[^\n]*?(?:Day|Date)\s*:\s*" + _DATE, t, re.I) or \
        re.search(r"(?:Date of (?:Occurrence|Offence)|Occurrence Date|Date & Time of Occurrence)\s*[:\-]?\s*" + _DATE, t, re.I)
    if m:
        p.offence_date = _date(*m.groups()[-3:])
        p.evidence["offence_date"] = m.group(0).strip()
    m = re.search(r"Between\s+" + _TIME + r"\s*(?:and|to|-)\s*" + _TIME, t, re.I) or \
        re.search(r"Time from\s*:\s*" + _TIME + r".*?Time to\s*:\s*" + _TIME, t, re.I)
    if m:
        p.time_from, p.time_to = f"{int(m.group(1)):02d}:{m.group(2)}", f"{int(m.group(3)):02d}:{m.group(4)}"
        p.evidence["offence_time"] = m.group(0).strip()

    v = _line_value(t, r"Place of (?:occurrence|offence)")
    if v:
        # One-line forms run the sub-items on: "... Guntur Dist. (a) Direction and Distance ... (b) Address ..."
        place = _SUB_ITEM.split(v[0])[0].strip().rstrip(".").strip()
        if len(place) >= 4 and not _NOT_A_PLACE.match(place):
            p.place = place
        p.evidence["place"] = v[1]
    v = _line_value(t, r"\(b\)\s*Address")
    if v and "place" in p.evidence:
        address = _SUB_ITEM.split(v[0])[0].strip().rstrip(".").strip()
        if len(address) >= 4 and not _NOT_A_PLACE.match(address):
            p.address = address
            p.evidence["place"] += " / " + v[1]
            p.place = p.place or address
    if not p.place:
        p.evidence.pop("place", None)
    if p.place:
        dm = re.search(r"([A-Z][a-z]+)\s+(?:District|Dist\.?)", p.place + " " + (p.address or ""))
        p.district = dm.group(1) if dm else None
        for source in (p.place, p.address or ""):
            parts = [x.strip() for x in source.split(",") if x.strip()]
            towns = [x for x in parts if not _NOT_A_TOWN.search(x)]
            if towns:
                p.town = towns[0]
                break

    v = _line_value(t, r"Complainant\s*/?\s*Informant\s*:?\s*\(a\)\s*Name") or _line_value(t, r"Complainant(?:'s)? Name") \
        or _line_value(t, r"Complainant")
    if v:
        name = _clean_name(re.sub(r"^\(a\)\s*Name\s*:\s*", "", v[0], flags=re.I))
        if name and len(name) <= 80:
            p.complainant, p.evidence["complainant"] = name, v[1]

    # Accused: the "(a) Name :" entries of the accused-particulars item, or "Accused: X (A-1)" lines
    am = re.search(r"Details of known\s*/\s*suspected\s*/\s*unknown accused.*?(?=\n\s*\d{1,2}\.\s|\Z)", t, re.I | re.S)
    if am:
        for n in re.finditer(r"\(a\)\s*Name\s*:\s*([^\n]+)", am.group(0)):
            name = _clean_name(n.group(1))
            if name and name not in p.accused:
                p.accused.append(name)
        p.evidence["accused"] = " ".join(am.group(0).split())[:300]
        pm = re.search(r"Particulars\s*:\s*([^\n]+)", am.group(0))
        if pm:
            p.particulars = pm.group(1).strip()
    for n in re.finditer(r"Accused(?:\s*Person)?\s*(?:\(s\))?\s*:\s*([^\n|]+)", t, re.I):
        for part in re.split(r",|\band\b", n.group(1)):
            name = _clean_name(part)
            if name and len(name) <= 60 and name not in p.accused and not re.search(r"\d{3,}|unknown", name, re.I):
                p.accused.append(name)
                p.evidence.setdefault("accused", n.group(0).strip())

    p.sections = _sections(t)
    if p.sections:
        p.evidence["sections"] = ", ".join(p.section_labels())

    m = re.search(r"Contraband(?:\s*Seized)?\s*:\s*(\d+(?:\.\d+)?)\s*(Litres?|Ltrs?|L|Kgs?|Kilograms?|Grams?|g|Bottles?|Packets?)\s+"
                  r"([^/\n.|]+)", t, re.I)
    if m:
        p.seized_quantity = float(m.group(1))
        unit = m.group(2).lower()
        p.seized_unit = ("Litres" if unit.startswith("l") else "Kgs" if unit.startswith("k") else
                         "Grams" if unit.startswith("g") else "Bottles" if unit.startswith("b") else "Packets")
        p.contraband_raw = m.group(3).strip()
        p.contraband_type = canonical_contraband(p.contraband_raw)
        p.evidence["contraband"] = m.group(0).strip()
    v = _line_value(t, r"Vehicle(?:\s*(?:No|Number|Details))?")
    if v:
        p.vehicle_details = v[0].split("|")[0].strip().rstrip(".")
        p.vehicle_registration = normalise_registration(p.vehicle_details)
        p.evidence["vehicle"] = v[1]
    v = _line_value(t, r"Occurrence")
    if v and not re.match(r"of Offence", v[0], re.I):
        p.occurrence = v[0].rstrip(".")
    v = _line_value(t, r"(?:Investigating|Seizing) Officer(?:'s)?(?: Name)?")
    if v:
        p.officer = _clean_name(v[0])
    return p
