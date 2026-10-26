"""
Pre-write checks and database-error translation for case registration.

SQLite (local and tests) does not enforce VARCHAR lengths, PostgreSQL does: a value that fits
locally can fail on Supabase with "value too long". Checking lengths against the model before
writing turns that into a field-level correction the officer can act on.
"""
import logging
import re
from typing import Dict, List, Optional, Tuple

from sqlalchemy.exc import DataError, IntegrityError, InterfaceError, OperationalError, SQLAlchemyError

logger = logging.getLogger(__name__)

FIELD_LABELS = {
    "fir_number": "FIR / Crime Number",
    "district": "District",
    "station": "Police / Excise Station",
    "offence_nature": "Offence Nature / Allegation",
    "contraband_type": "Contraband / Seized Property",
    "seized_unit": "Seized Quantity Unit",
    "vehicle_details": "Vehicle Details",
    "seizing_officer_name": "Seizing / Investigating Officer",
    "seizing_officer_rank": "Officer Rank",
    "mandal": "Mandal",
    "village": "Village",
}

FIELD_SECTIONS = {
    "fir_number": "FIR & Jurisdiction", "district": "FIR & Jurisdiction", "station": "FIR & Jurisdiction",
    "offence_nature": "FIR & Jurisdiction", "contraband_type": "Seizure & Evidence",
    "seized_unit": "Seizure & Evidence", "vehicle_details": "Seizure & Evidence",
}


def column_length_issues(model, values: Dict[str, object]) -> List[Dict]:
    """Validation-report entries for string values longer than their column allows."""
    issues = []
    for name, value in values.items():
        if value is None or name not in model.__table__.c:
            continue
        limit = getattr(model.__table__.c[name].type, "length", None)
        text = str(value)
        if limit and len(text) > limit:
            issues.append({
                "field": name,
                "label": FIELD_LABELS.get(name, name.replace("_", " ").title()),
                "issue": "TOO_LONG",
                "reason": f"This field allows at most {limit} characters; the reviewed value has {len(text)}. "
                          f"Shorten it before confirming.",
                "correction_section": FIELD_SECTIONS.get(name, "Case Details"),
                "candidate_value": None,
                "max_length": limit,
            })
    return issues


def describe_db_error(exc: SQLAlchemyError) -> Tuple[int, Dict]:
    """
    HTTP status and response body for a database failure during registration. Never includes
    SQL text, parameters or record contents.
    """
    msg = str(getattr(exc, "orig", exc))
    if isinstance(exc, IntegrityError):
        if "fir_number" in msg:
            return 409, {"code": "DUPLICATE_FIR_NUMBER",
                         "detail": "This FIR number is already registered. Open the existing case or correct the FIR number."}
        return 409, {"code": "CONFLICTING_RECORD",
                     "detail": "The case conflicts with an existing record. Refresh the page and try again."}
    if isinstance(exc, DataError) or "value too long" in msg:
        m = re.search(r"character varying\((\d+)\)", msg)
        limit = f" (limit {m.group(1)} characters)" if m else ""
        return 422, {"code": "FIELD_VALUE_INVALID",
                     "detail": f"A reviewed field is too long or has an invalid format{limit}. Shorten long fields and try again."}
    if isinstance(exc, (OperationalError, InterfaceError)) or "timeout" in msg.lower() or "connection" in msg.lower():
        return 503, {"code": "DATABASE_UNAVAILABLE",
                     "detail": "The case database could not be reached. Nothing was saved; check the connection and confirm again."}
    return 500, {"code": "CASE_SAVE_FAILED",
                 "detail": "The case could not be saved because of a database error. Nothing was saved; try again or contact the administrator."}


def jurisdiction_issue(user, district: Optional[str], station: Optional[str]) -> Optional[Dict]:
    """A validation-report entry when the reviewed station/district is outside the officer's scope."""
    from .auth import enforce_data_scope
    if enforce_data_scope(user, district, station):
        return None
    field = "station" if user.role == "STATION" and (district or "").lower() == (user.district or "").lower() else "district"
    expected = user.station if field == "station" else user.district
    return {
        "field": field,
        "label": FIELD_LABELS[field],
        "issue": "OUT_OF_JURISDICTION",
        "reason": f"You can register cases only for your own jurisdiction ({user.district}"
                  f"{' / ' + user.station if user.role == 'STATION' and user.station else ''}). "
                  f"Correct the {FIELD_LABELS[field].lower()} or ask an officer of that jurisdiction to register it.",
        "correction_section": "FIR & Jurisdiction",
        "candidate_value": expected,
    }
