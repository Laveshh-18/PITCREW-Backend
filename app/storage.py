"""Supabase Storage upload through the REST API (service role key, backend only)."""
import logging

import httpx

from app.config import settings

log = logging.getLogger("app")


def public_url(name: str) -> str:
    return f"{settings.supabase_url}/storage/v1/object/public/{settings.supabase_bucket}/{name}"


def upload_jpeg(name: str, data: bytes) -> str | None:
    """name is server generated ({complaint_id}.jpg). Returns the public URL or None on failure."""
    if not (settings.supabase_url and settings.supabase_service_role_key):
        return None
    try:
        r = httpx.post(
            f"{settings.supabase_url}/storage/v1/object/{settings.supabase_bucket}/{name}",
            content=data, timeout=15,
            headers={"Authorization": f"Bearer {settings.supabase_service_role_key}",
                     "apikey": settings.supabase_service_role_key,
                     "Content-Type": "image/jpeg", "x-upsert": "false"})
        if r.status_code in (200, 201):
            return public_url(name)
        log.warning("storage upload failed", extra={"event": "storage_error", "status": r.status_code})
    except Exception:
        log.warning("storage upload error", extra={"event": "storage_error"})
    return None
