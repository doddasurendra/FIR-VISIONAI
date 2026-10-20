import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from ...database import get_db
from ...models.user import User
from ...services.auth import get_current_user
from ...services.storage import storage_service
from ...services.audit import log_audit_event

router = APIRouter(prefix="/system", tags=["System Administration & Diagnostics"])

@router.post("/backup")
async def create_backup(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create atomic online database snapshot with SHA-256 verification."""
    if current_user.role not in ("STATE", "DISTRICT"):
        raise HTTPException(status_code=403, detail="Insufficient role to trigger system backup")

    try:
        result = storage_service.create_database_backup()
        await log_audit_event(
            db=db,
            actor_id=current_user.id,
            actor_username=current_user.username,
            action_type="DATABASE_BACKUP_CREATED",
            object_type="SYSTEM_BACKUP",
            object_id=result["backup_filename"],
            after_state=result
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backup failed: {str(e)}")

@router.get("/backups")
async def list_backups(
    current_user: User = Depends(get_current_user)
):
    """List all available database snapshots."""
    return storage_service.list_backups()

@router.get("/backups/download/{filename}")
async def download_backup(
    filename: str,
    current_user: User = Depends(get_current_user)
):
    """Download verified database snapshot (authorized admin only)."""
    if current_user.role not in ("STATE", "DISTRICT"):
        raise HTTPException(status_code=403, detail="Insufficient role to download backup")

    safe_name = os.path.basename(filename)
    backups = storage_service.list_backups()
    target = next((b for b in backups if b["filename"] == safe_name), None)
    if not target or not os.path.exists(target["path"]):
        raise HTTPException(status_code=404, detail="Backup snapshot not found")

    return FileResponse(
        path=target["path"],
        filename=safe_name,
        media_type="application/x-sqlite3"
    )
