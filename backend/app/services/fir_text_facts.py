"""
Facts read directly from FIR text, used to fill what the AI extraction left empty.

- People: accused, complainant / informant, witnesses, from the standard FIR form wording
  ("6. Complainant / Informant : (a) Name : ...", "A-1: ...", "Witness 1: ...").
- Identifiers: vehicle registration numbers and phone numbers.
- Crime category: a short category for an offence description or section list
  ("cheated the complainant by using forged documents ..." -> "Cheating / Forgery").
Placeholder names ("Unknown person(s)", "Not known", "N/A") are never returned as people.
"""
import re
from typing import Dict, List, Optional

from .retrieval import id_tokens

PLACEHOLDERS = {"unknown", "unknown suspect", "unknown person", "unknown person(s)", "unknown persons", "not known",
                "n/a", "na", "nil", "none", "-", "—", "unidentified", "unknown accused"}
_NAME = r"([A-Z][A-Za-z.]*(?:\s+[A-Z][A-Za-z.]*){0,4})"
_STOP_AFTER = r"(?=\s*(?:\(\w\)|,|;|\.\s|\n|S/o|D/o|W/o|Son of|Daughter of|Wife of|Father|Male|Female|Age|$))"

_COMPLAINANT = [
    re.compile(r"Complainant\s*/\s*Informant[^:]{0,40}:\s*(?:\(a\)\s*)?Name\s*:\s*\**\s*" + _NAME + _STOP_AFTER),
    re.compile(r"Complainant(?:\s*/\s*Informant)?\s*:\s*" + _NAME + _STOP_AFTER),
    re.compile(r"COMPLAINANT\s*/\s*INFORMANT DETAILS\s*:\s*Name\s*:\s*" + _NAME + _STOP_AFTER),
]
_ACCUSED = [
    re.compile(r"(?:known\s*/\s*suspected\s*/\s*unknown\s*accused|ACCUSED PERSON PARTICULARS)[^:]{0,80}:\s*(?:\(a\)\s*)?Name\s*:\s*\**\s*"
               + _NAME + _STOP_AFTER, re.I),
    re.compile(r"\bA-\d{1,2}\s*:\s*" + _NAME + _STOP_AFTER),
    re.compile(r"\bAccused(?:\s+No\.?\s*\d+)?\s*:\s*" + _NAME + _STOP_AFTER),
]
_WITNESS = [
    re.compile(r"\bWitness\s*\d{0,2}\s*:\s*" + _NAME + _STOP_AFTER),
    re.compile(r"\bPanch(?:a)?\s+witness(?:es)?\s*\d{0,2}\s*:\s*" + _NAME + _STOP_AFTER, re.I),
]

CRIME_CATEGORIES = [
    ("Cheating / Forgery", [r"cheat", r"forg", r"fraud", r"\b420\b", r"\b468\b", r"\b471\b", r"\b318\b", r"\b336\b"]),
    ("Cyber crime", [r"\b66[cd]\b", r"\bit act\b", r"online", r"cyber", r"otp", r"phishing"]),
    ("Theft", [r"\btheft\b", r"\bstole", r"\bstolen\b", r"\b379\b", r"\b303\b"]),
    ("Robbery / Dacoity", [r"robber", r"dacoit", r"\b392\b", r"\b395\b", r"\b309\b"]),
    ("Illicit liquor (Excise)", [r"liquor", r"arrack", r"distill", r"toddy", r"jaggery wash", r"excise act", r"prohibition act"]),
    ("Narcotics (NDPS)", [r"ganja", r"cannabis", r"ndps", r"narcotic", r"heroin"]),
    ("Road accident / Rash driving", [r"rash", r"accident", r"collid", r"\b279\b", r"\b304a\b", r"\b281\b", r"\b106\b"]),
    ("Murder", [r"murder", r"\b302\b", r"\b103\b"]),
    ("Hurt / Assault", [r"assault", r"\bhurt\b", r"\b323\b", r"\b324\b", r"\b115\b", r"\b118\b"]),
    ("Crimes against women", [r"dowry", r"\b498a\b", r"outrag", r"\b354\b", r"molest"]),
]


def crime_category(*texts: Optional[str]) -> Optional[str]:
    """A short category for offence wording, or None when nothing recognisable is present."""
    low = " ".join(t for t in texts if t).lower()
    if not low.strip():
        return None
    for name, patterns in CRIME_CATEGORIES:
        if any(re.search(p, low) for p in patterns):
            return name
    return "Other"


def _clean(name: str) -> Optional[str]:
    name = re.sub(r"\s+", " ", (name or "").strip(" .*:-")).strip()
    if not name or name.lower() in PLACEHOLDERS or name.lower().startswith(("unknown", "not ")):
        return None
    if len(name) < 3 or not re.search(r"[A-Za-z]{2}", name):
        return None
    return name


def _collect(patterns, text: str) -> List[str]:
    out: List[str] = []
    for rx in patterns:
        for m in rx.finditer(text):
            name = _clean(m.group(1))
            if name and name.lower() not in {n.lower() for n in out}:
                out.append(name)
    return out


def find_people_and_identifiers(text: str) -> Dict[str, List[str]]:
    text = re.sub(r"\*\*", "", text or "")  # OCR markdown bold
    complainants = _collect(_COMPLAINANT, text)
    return {
        "accused": _collect(_ACCUSED, text),
        "complainant": complainants[:1],
        "witnesses": _collect(_WITNESS, text),
        "vehicles": [t["raw"] for t in id_tokens(text) if t["kind"] == "VEHICLE"],
        "phones": [t["raw"] for t in id_tokens(text) if t["kind"] == "PHONE"],
    }
