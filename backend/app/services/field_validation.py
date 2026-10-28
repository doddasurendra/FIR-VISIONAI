"""
Format and consistency checks for extracted / overridden case fields.

Each field must match its expected form (FIR number pattern, contraband type from a fixed list,
quantity as a number, a real date) and agree with the case header. Problems are either
  BLOCK - the value cannot be saved (e.g. a quantity typed into the contraband type field), or
  FLAG  - saved but shown for officer review (e.g. FIR number differs from the case header).
"""
import re
from typing import Any, Dict, List, Optional

from .retrieval import normalise_id

CONTRABAND_TYPES = [
    "ID Liquor", "ID Liquor (Arrack)", "IML Liquor", "Non-Duty Paid Liquor", "Spurious Liquor",
    "Spurious Toddy Adulterated", "Toddy", "Fermented Jaggery Wash", "Beer", "Ganja (Cannabis)",
    "Narcotic Drugs", "Other", "Unknown",
]
_CONTRABAND_ALIASES = [
    (re.compile(r"arrack|gudumba|country liquor", re.I), "ID Liquor (Arrack)"),
    (re.compile(r"\bid\b|illicit(ly)? distill", re.I), "ID Liquor"),
    (re.compile(r"non[- ]?duty|ndpl|duty not paid|other state", re.I), "Non-Duty Paid Liquor"),
    (re.compile(r"spurious toddy|adulterated toddy", re.I), "Spurious Toddy Adulterated"),
    (re.compile(r"spurious", re.I), "Spurious Liquor"),
    (re.compile(r"\btoddy\b", re.I), "Toddy"),
    (re.compile(r"jaggery|\bwash\b", re.I), "Fermented Jaggery Wash"),
    (re.compile(r"\biml\b|indian made", re.I), "IML Liquor"),
    (re.compile(r"\bbeer\b", re.I), "Beer"),
    (re.compile(r"ganja|cannabis|marijuana", re.I), "Ganja (Cannabis)"),
    (re.compile(r"narcotic|heroin|opium|ndps", re.I), "Narcotic Drugs"),
]
_QUANTITY_IN_TEXT = re.compile(r"\d+(?:\.\d+)?\s*(?:l|ltr|ltrs|litre|litres|liter|liters|kg|kgs|g|grams?|bottles?|packets?|ml)\b", re.I)
FIR_NUMBER_RE = re.compile(
    r"^(?:FIR[-/ ]?\d{4}[-/ ]?[A-Z]{2,6}(?:[-/ ][A-Z0-9]{1,10})*[-/ ]?\d{1,6}"     # FIR-2024-KNL-0042, FIR-2024-EXC-IMAGE-01
    r"|(?:Cr\.?\s*No\.?\s*|Crime\s*No\.?\s*)?\d{1,5}/\d{4})$", re.I)                # 89/2024, Cr. No. 999/2026


def canonical_contraband(value: Optional[str]) -> Optional[str]:
    """The fixed-list name for a contraband value, or None if it is not a contraband type."""
    v = (value or "").strip()
    if not v:
        return None
    for name in CONTRABAND_TYPES:
        if v.lower() == name.lower():
            return name
    for rx, name in _CONTRABAND_ALIASES:
        if rx.search(v):
            return name
    return None


def parse_quantity(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = re.search(r"\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(m.group(0)) if m else None


def _issue(level: str, code: str, message: str) -> Dict[str, str]:
    return {"level": level, "code": code, "message": message}


def validate_field(name: str, value: Any, case=None) -> List[Dict[str, str]]:
    """Problems with one field value (empty list when it is fine)."""
    name = (name or "").lower()
    text = "" if value is None else str(value).strip()
    issues: List[Dict[str, str]] = []
    if not text:
        return issues
    if name == "fir_number":
        if not FIR_NUMBER_RE.match(text):
            issues.append(_issue("FLAG", "FORMAT", f"'{text}' is not an FIR number (e.g. FIR-2024-KNL-0042 or 89/2024)."))
        if case is not None and case.fir_number and normalise_id(text) != normalise_id(case.fir_number):
            issues.append(_issue("FLAG", "MISMATCH_WITH_CASE",
                                 f"Differs from the case header FIR number '{case.fir_number}'."))
    elif name in ("contraband_type", "contraband"):
        if _QUANTITY_IN_TEXT.search(text) or re.fullmatch(r"[\d.\s]+", text):
            issues.append(_issue("BLOCK", "QUANTITY_IN_TYPE_FIELD",
                                 f"'{text}' contains a quantity. Enter the type here (e.g. ID Liquor) and the quantity in "
                                 f"the seized quantity field."))
        elif canonical_contraband(text) is None:
            issues.append(_issue("FLAG", "NOT_IN_LIST", f"'{text}' is not a contraband type. Use one of: "
                                 + ", ".join(CONTRABAND_TYPES) + "."))
        if case is not None and case.contraband_type and canonical_contraband(text) and \
                canonical_contraband(case.contraband_type) and canonical_contraband(text) != canonical_contraband(case.contraband_type):
            issues.append(_issue("FLAG", "MISMATCH_WITH_CASE", f"Differs from the case header contraband '{case.contraband_type}'."))
    elif name in ("seized_quantity", "quantity"):
        q = parse_quantity(text)
        if q is None:
            issues.append(_issue("BLOCK", "NOT_A_NUMBER", f"'{text}' is not a quantity; enter a number (e.g. 45.0)."))
        elif q < 0:
            issues.append(_issue("BLOCK", "NEGATIVE", "A quantity cannot be negative."))
        elif case is not None and case.seized_quantity is not None and abs(q - float(case.seized_quantity)) > 1e-6:
            issues.append(_issue("FLAG", "MISMATCH_WITH_CASE", f"Differs from the case header quantity {case.seized_quantity:g}."))
    elif name in ("district", "station"):
        header = getattr(case, name, None) if case is not None else None
        if header and text.lower() != header.strip().lower():
            issues.append(_issue("FLAG", "MISMATCH_WITH_CASE", f"Differs from the case header {name} '{header}'."))
    elif name in ("offence_date", "incident_date", "date_of_offence"):
        from .legal_rules import parse_date_value
        if parse_date_value(text) is None:
            issues.append(_issue("FLAG", "FORMAT", f"'{text}' is not a date."))
    elif name in ("offence_nature", "crime_type", "offence_category"):
        if re.match(r"^\d{1,2}(st|nd|rd|th)?\s+[A-Za-z]+\s+\d{4}", text) or re.match(r"^\d{1,2}[./-]\d{1,2}[./-]\d{4}", text):
            issues.append(_issue("FLAG", "DATE_IN_TEXT_FIELD", f"'{text}' is a date, not an offence."))
        elif len(text) > 120:
            issues.append(_issue("FLAG", "NOT_A_CATEGORY", "This holds a whole sentence; it should be a short offence category."))
    return issues


def effective_value(field) -> Optional[str]:
    return field.human_override_value or field.normalized_value or field.original_value


def validate_case_fields(case, fields) -> Dict[str, Any]:
    """Every stored field checked against its format and the case header."""
    results = []
    for f in fields:
        value = effective_value(f)
        issues = validate_field(f.field_name, value, case)
        # The raw extraction is kept for history; report it too when it is in the wrong field
        raw_issues = [i for i in validate_field(f.field_name, f.original_value, None)
                      if i["code"] in ("DATE_IN_TEXT_FIELD", "QUANTITY_IN_TYPE_FIELD")] if f.original_value != value else []
        results.append({"field_id": f.id, "field_name": f.field_name, "value": value,
                        "issues": issues, "raw_value_issues": raw_issues,
                        "needs_review": bool(issues)})
    return {"case_id": case.id, "fir_number": case.fir_number,
            "fields_needing_review": sum(1 for r in results if r["needs_review"]), "fields": results}
