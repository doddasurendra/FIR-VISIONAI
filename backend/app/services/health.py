"""
Readiness checks for /api/v1/health/ready: they actually touch the database and Supabase Storage,
unlike /api/v1/health, which only proves the process is up. Every check has a hard timeout and
reports errors without connection strings, keys or other secrets.
"""
import asyncio
import re
import time
from typing import Any, Dict

import httpx
from sqlalchemy import text

from ..config import settings
from ..database import sync_engine, is_postgres
from .storage import storage_service

DB_TIMEOUT_SECONDS = 10.0
STORAGE_TIMEOUT_SECONDS = 8.0

# scheme://user:password@host  ->  scheme://***@host ; also bearer tokens / JWT-looking strings
_CREDENTIALS_IN_URL = re.compile(r"(\w+://)[^/\s@]+@")
_JWT_LIKE = re.compile(r"eyJ[\w-]+\.[\w-]+\.[\w-]+")


def safe_error(exc: BaseException) -> str:
    """One-line, secret-free description of an exception, suitable for API responses and logs."""
    message = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
    message = _CREDENTIALS_IN_URL.sub(r"\1***@", message)
    message = _JWT_LIKE.sub("***", message)
    if settings.SUPABASE_SERVICE_ROLE_KEY:
        message = message.replace(settings.SUPABASE_SERVICE_ROLE_KEY, "***")
    if settings.SUPABASE_KEY:
        message = message.replace(settings.SUPABASE_KEY, "***")
    return f"{type(exc).__name__}: {message[:300]}" if message else type(exc).__name__


def _select_one() -> None:
    with sync_engine.connect() as conn:
        conn.execute(text("SELECT 1"))


async def check_database() -> Dict[str, Any]:
    started = time.perf_counter()
    result: Dict[str, Any] = {"engine": "SUPABASE_POSTGRESQL" if is_postgres else "SQLITE_LOCAL"}
    try:
        await asyncio.wait_for(asyncio.to_thread(_select_one), timeout=DB_TIMEOUT_SECONDS)
        result["ok"] = True
    except asyncio.TimeoutError:
        result["ok"] = False
        result["error"] = f"Database did not answer SELECT 1 within {DB_TIMEOUT_SECONDS:.0f}s"
    except Exception as exc:
        result["ok"] = False
        result["error"] = safe_error(exc)
    result["latency_ms"] = round((time.perf_counter() - started) * 1000)
    return result


async def check_storage() -> Dict[str, Any]:
    if not storage_service.is_cloud_configured():
        # Local filesystem mode is a supported configuration, not a failure
        return {"backend": "LOCAL_FILESYSTEM", "ok": storage_service.get_status()["local_fallback_ready"]}
    started = time.perf_counter()
    result: Dict[str, Any] = {"backend": "SUPABASE_STORAGE", "bucket": storage_service.bucket}
    url = f"{storage_service.supabase_url.rstrip('/')}/storage/v1/bucket/{storage_service.bucket}"
    try:
        async with httpx.AsyncClient(timeout=STORAGE_TIMEOUT_SECONDS) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {storage_service.supabase_key}"})
        result["ok"] = resp.status_code == 200
        if not result["ok"]:
            result["error"] = f"Supabase Storage answered HTTP {resp.status_code} for bucket '{storage_service.bucket}'"
    except Exception as exc:
        result["ok"] = False
        result["error"] = safe_error(exc)
    result["latency_ms"] = round((time.perf_counter() - started) * 1000)
    return result


async def readiness() -> Dict[str, Any]:
    database, storage = await asyncio.gather(check_database(), check_storage())
    ready = database["ok"] and storage["ok"]
    return {
        "app": "fir-visionai",
        "status": "ready" if ready else "degraded",
        "checks": {"database": database, "storage": storage},
    }
