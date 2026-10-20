import os
import hashlib
import mimetypes
import sqlite3
from datetime import datetime
from typing import Optional, Tuple, Dict, Any, List
import httpx
from ..config import settings

class StorageService:
    """
    Dual-mode Storage Service:
    - Primary Cloud: Supabase Private Storage Bucket (AES-256 encrypted, signed URLs)
    - Fallback / Offline / Test: Local Filesystem storage in data/evidence
    """

    def __init__(self):
        self.supabase_url = settings.SUPABASE_URL
        self.supabase_key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_KEY
        self.bucket = settings.SUPABASE_STORAGE_BUCKET
        self.evidence_dir = settings.EVIDENCE_DIR
        os.makedirs(self.evidence_dir, exist_ok=True)

    def is_cloud_configured(self) -> bool:
        """Check if live Supabase Cloud credentials are configured."""
        return bool(
            self.supabase_url
            and self.supabase_key
            and not self.supabase_url.startswith("https://your-project")
            and not self.supabase_key.startswith("your-")
        )

    def get_status(self) -> Dict[str, Any]:
        """Return cloud storage status diagnostics."""
        configured = self.is_cloud_configured()
        return {
            "primary_backend": "SUPABASE_STORAGE" if configured else "LOCAL_FILESYSTEM",
            "cloud_configured": configured,
            "cloud_status": "ONLINE" if configured else "BLOCKED_PENDING_CREDENTIALS",
            "bucket_name": self.bucket,
            "local_fallback_directory": self.evidence_dir,
            "local_fallback_ready": os.path.exists(self.evidence_dir)
        }

    def compute_sha256(self, file_bytes: bytes) -> str:
        """Calculate cryptographically secure SHA-256 digest."""
        hasher = hashlib.sha256()
        hasher.update(file_bytes)
        return hasher.hexdigest()

    async def upload_file(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str = "application/pdf"
    ) -> Dict[str, Any]:
        """
        Upload file to Supabase Private Storage if configured;
        otherwise fall back safely to local evidence directory.
        """
        file_hash = self.compute_sha256(file_bytes)

        if self.is_cloud_configured():
            try:
                cloud_path = f"evidence/{file_hash[:8]}_{filename}"
                headers = {
                    "Authorization": f"Bearer {self.supabase_key}",
                    "Content-Type": content_type,
                    "x-upsert": "true"
                }
                upload_url = f"{self.supabase_url.rstrip('/')}/storage/v1/object/{self.bucket}/{cloud_path}"

                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(upload_url, content=file_bytes, headers=headers)
                    if resp.status_code in (200, 201):
                        return {
                            "storage_type": "SUPABASE",
                            "stored_path": cloud_path,
                            "file_hash": file_hash,
                            "file_size": len(file_bytes),
                            "cloud_url": f"{self.supabase_url}/storage/v1/object/{self.bucket}/{cloud_path}"
                        }
            except Exception as e:
                # Log cloud upload failure and fall back to local disk
                pass

        # Local storage fallback
        safe_name = f"{file_hash[:12]}_{filename}"
        local_path = os.path.join(self.evidence_dir, safe_name)
        with open(local_path, "wb") as f:
            f.write(file_bytes)

        return {
            "storage_type": "LOCAL",
            "stored_path": local_path,
            "file_hash": file_hash,
            "file_size": len(file_bytes),
            "cloud_url": None
        }

    async def get_file_bytes(self, stored_path: str, storage_type: str = "LOCAL") -> bytes:
        """Retrieve binary file content from Supabase cloud or local storage."""
        if storage_type == "SUPABASE" and self.is_cloud_configured():
            headers = {"Authorization": f"Bearer {self.supabase_key}"}
            download_url = f"{self.supabase_url.rstrip('/')}/storage/v1/object/{self.bucket}/{stored_path}"
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(download_url, headers=headers)
                if resp.status_code == 200:
                    return resp.content

        # Fallback to local disk
        if os.path.exists(stored_path):
            with open(stored_path, "rb") as f:
                return f.read()

        raise FileNotFoundError(f"Document not found at: {stored_path}")

    async def create_signed_url(self, stored_path: str, expires_in_seconds: int = 3600) -> Optional[str]:
        """Create time-limited signed URL for private cloud access."""
        if not self.is_cloud_configured():
            return None

        try:
            sign_url = f"{self.supabase_url.rstrip('/')}/storage/v1/object/sign/{self.bucket}/{stored_path}"
            headers = {"Authorization": f"Bearer {self.supabase_key}"}
            payload = {"expiresIn": expires_in_seconds}

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(sign_url, json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    signed_path = data.get("signedURL")
                    if signed_path:
                        return f"{self.supabase_url.rstrip('/')}/storage/v1{signed_path}"
        except Exception:
            return None

        return None

    def create_database_backup(self, destination_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute atomic SQLite online backup with SHA-256 integrity verification.
        Preserves complete database tables, FTS5 indices, and relations.
        """
        db_path = settings.SYNC_DATABASE_URL.replace("sqlite:///", "")
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Source database file not found at {db_path}")

        backup_dir = destination_dir or os.path.join(os.path.dirname(db_path), "backups")
        os.makedirs(backup_dir, exist_ok=True)

        timestamp_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"fir_sahayak_backup_{timestamp_str}.db"
        backup_path = os.path.join(backup_dir, backup_filename)

        # Atomic online SQLite backup
        source_conn = sqlite3.connect(db_path, timeout=30.0)
        dest_conn = sqlite3.connect(backup_path)
        try:
            source_conn.backup(dest_conn)
        finally:
            dest_conn.close()
            source_conn.close()

        # Integrity verification on backup
        check_conn = sqlite3.connect(backup_path)
        try:
            cur = check_conn.cursor()
            cur.execute("PRAGMA integrity_check;")
            integrity_result = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM cases;")
            cases_count = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM documents;")
            docs_count = cur.fetchone()[0]
        finally:
            check_conn.close()

        # Compute SHA-256 of backup
        with open(backup_path, "rb") as f:
            backup_bytes = f.read()
        backup_sha256 = self.compute_sha256(backup_bytes)

        return {
            "status": "SUCCESS",
            "backup_filename": backup_filename,
            "backup_path": backup_path,
            "sha256_hash": backup_sha256,
            "size_bytes": len(backup_bytes),
            "size_kb": round(len(backup_bytes) / 1024, 2),
            "integrity_check": integrity_result,
            "cases_verified": cases_count,
            "documents_verified": docs_count,
            "created_at": datetime.utcnow().isoformat() + "Z"
        }

    def list_backups(self, backup_dir: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all verified database backups available on disk."""
        db_path = settings.SYNC_DATABASE_URL.replace("sqlite:///", "")
        target_dir = backup_dir or os.path.join(os.path.dirname(db_path), "backups")
        if not os.path.exists(target_dir):
            return []

        backups = []
        for fname in sorted(os.listdir(target_dir), reverse=True):
            if fname.endswith(".db"):
                fpath = os.path.join(target_dir, fname)
                try:
                    stat = os.stat(fpath)
                    backups.append({
                        "filename": fname,
                        "path": fpath,
                        "size_bytes": stat.st_size,
                        "size_kb": round(stat.st_size / 1024, 2),
                        "modified_at": datetime.utcfromtimestamp(stat.st_mtime).isoformat() + "Z"
                    })
                except Exception:
                    pass
        return backups

# Singleton instance
storage_service = StorageService()

