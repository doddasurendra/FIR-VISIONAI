import csv
import json
import os
import hashlib
from typing import Dict, Any, List
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..models.bulk import BulkJob
from ..models.case import Case, CaseField
from ..models.entity import Entity, EntityMention
from ..models.user import User

class BulkIngestionService:
    @staticmethod
    async def process_csv_or_json(
        job_id: str,
        file_path: str,
        user: User,
        db: AsyncSession
    ):
        stmt = select(BulkJob).where(BulkJob.id == job_id)
        res = await db.execute(stmt)
        job = res.scalar_one_or_none()
        if not job:
            return

        job.status = "RUNNING"
        await db.commit()

        records = []
        errors = []

        try:
            if job.file_type == "CSV":
                with open(file_path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    records = list(reader)
            elif job.file_type == "JSON":
                with open(file_path, "r", encoding="utf-8") as f:
                    records = json.load(f)
                    if not isinstance(records, list):
                        records = [records]

            job.total_records = len(records)
            await db.commit()

            success_cnt = 0
            fail_cnt = 0

            for idx, r in enumerate(records):
                try:
                    fir_no = r.get("fir_number") or f"FIR-{datetime.utcnow().year}-BULK-{idx+1:04d}"
                    
                    # Duplicate check
                    dup_stmt = select(Case).where(Case.fir_number == fir_no)
                    dup_res = await db.execute(dup_stmt)
                    if dup_res.scalar_one_or_none():
                        errors.append({"record_index": idx, "fir_number": fir_no, "error": "Duplicate FIR number already exists."})
                        fail_cnt += 1
                        continue

                    # Create case
                    new_case = Case(
                        fir_number=fir_no,
                        year=int(r.get("year", 2024)),
                        district=r.get("district", user.district),
                        station=r.get("station", user.station or "Town Station"),
                        mandal=r.get("mandal", "General Mandal"),
                        village=r.get("village", "Town"),
                        offence_nature=r.get("offence_nature", "Unlawful Liquor Transport"),
                        contraband_type=r.get("contraband_type", "ID Liquor"),
                        seized_quantity=float(r.get("seized_quantity", 10.0)),
                        seized_unit=r.get("seized_unit", "Litres"),
                        vehicle_details=r.get("vehicle_details", "Auto AP21TY4567"),
                        narrative=r.get("narrative", "Historical bulk imported record."),
                        status="IN_REVIEW",
                        created_by=user.id
                    )
                    db.add(new_case)
                    await db.flush()

                    # Create Accused Entity Mention if provided
                    accused_name = r.get("accused_name")
                    if accused_name:
                        # Check existing canonical entity
                        e_stmt = select(Entity).where(Entity.canonical_name.ilike(accused_name.strip()))
                        e_res = await db.execute(e_stmt)
                        ent = e_res.scalar_one_or_none()
                        if not ent:
                            ent = Entity(
                                canonical_name=accused_name.strip(),
                                entity_type="PERSON",
                                aliases_json="[]",
                                attributes_json=json.dumps({"address": r.get("village", "")}),
                                risk_score=0.25
                            )
                            db.add(ent)
                            await db.flush()

                        mention = EntityMention(
                            entity_id=ent.id,
                            case_id=new_case.id,
                            mention_text=accused_name.strip(),
                            role_in_case="ACCUSED"
                        )
                        db.add(mention)

                    success_cnt += 1
                except Exception as ex:
                    errors.append({"record_index": idx, "error": str(ex)})
                    fail_cnt += 1

                job.processed_records = idx + 1
                job.success_count = success_cnt
                job.failure_count = fail_cnt

            job.status = "COMPLETED"
            job.errors_json = json.dumps(errors)
            await db.commit()

        except Exception as e:
            job.status = "FAILED"
            job.errors_json = json.dumps([{"error": str(e)}])
            await db.commit()

bulk_service = BulkIngestionService()
