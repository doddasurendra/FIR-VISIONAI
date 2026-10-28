"""
One-off, approved repair of two case_fields rows of FIR-2024-KNL-0042 that did not match its FIR
(values most likely written by automated tests that ran against the live database before tests were
isolated):
  - fir_number      "Cr. No. 999/2026"            -> "FIR-2024-KNL-0042" (case header; FIR page 1 "Crime No")
  - contraband_type override "Verified 50.0 Litres" -> override cleared ("ID Liquor"; quantity stays 45.0)

original_value (the raw extraction) is kept as it was; the value the application uses
(human_override_value, else normalized_value) is corrected. Each change is audited (FIELD_REPAIRED)
with the old and new values, after a JSON backup of both rows is written to BACKUPS_DIR.

  python scripts/repair_knl0042_fields.py           # dry run
  python scripts/repair_knl0042_fields.py --apply
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import AsyncSessionLocal  # noqa: E402
from app.models.case import Case, CaseField  # noqa: E402
from app.services.audit import log_audit_event  # noqa: E402

FIR = "FIR-2024-KNL-0042"
COLUMNS = ("original_value", "normalized_value", "human_override_value", "verification_status")
REPAIRS = {
    "fir_number": {"expect": "Cr. No. 999/2026",
                   "set": {"normalized_value": FIR, "human_override_value": FIR, "verification_status": "VERIFIED"}},
    "contraband_type": {"expect": "Verified 50.0 Litres",
                        "set": {"human_override_value": None, "verification_status": "VERIFIED"}},
}


async def main(apply: bool) -> int:
    async with AsyncSessionLocal() as db:
        case = (await db.execute(select(Case).where(Case.fir_number == FIR))).scalar_one()
        rows = (await db.execute(select(CaseField).where(CaseField.case_id == case.id,
                                                         CaseField.field_name.in_(list(REPAIRS))))).scalars().all()
        plan = []
        for row in rows:
            r = REPAIRS[row.field_name]
            current = row.human_override_value or row.normalized_value or row.original_value
            if current != r["expect"]:
                print(f"{row.field_name}: current value {current!r} is not the expected {r['expect']!r}; left unchanged.")
                continue
            before = {c: getattr(row, c) for c in COLUMNS}
            after = {**before, **r["set"]}
            plan.append((row, before, after))
            print(f"{row.field_name} (row {row.id}): {before} -> {after}")
        if not plan:
            print("Nothing to repair.")
            return 0
        if not apply:
            print("Dry run only. Re-run with --apply.")
            return 0

        os.makedirs(settings.BACKUPS_DIR, exist_ok=True)
        stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        backup = os.path.join(settings.BACKUPS_DIR, f"case_fields_{FIR}_before_repair_{stamp}.json")
        with open(backup, "w", encoding="utf-8") as f:
            json.dump([{"id": row.id, "case_id": row.case_id, "field_name": row.field_name, **before}
                       for row, before, _ in plan], f, indent=1, default=str)
        print(f"Backup written: {backup}")
        for row, before, after in plan:
            for c, v in after.items():
                setattr(row, c, v)
        await db.commit()
        for row, before, after in plan:
            await log_audit_event(db, actor_id="system", actor_username="system_data_repair",
                                  action_type="FIELD_REPAIRED", object_type="CASE_FIELD", object_id=row.id,
                                  before_state={"case": FIR, "field": row.field_name, **before},
                                  after_state={"case": FIR, "field": row.field_name, **after,
                                               "reason": "Value did not match the FIR; approved data repair",
                                               "backup_file": os.path.basename(backup)},
                                  refresh=False)
        print(f"Repaired {len(plan)} field(s); audited as FIELD_REPAIRED.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    sys.exit(asyncio.run(main(ap.parse_args().apply)))
