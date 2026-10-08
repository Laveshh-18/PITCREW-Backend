"""Turns models/rows into JSON-safe data. Timestamps become ISO 8601 UTC with Z (Section 4.1)."""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi.responses import JSONResponse
from pydantic import BaseModel


def iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_json(obj):
    if isinstance(obj, BaseModel):
        return to_json(obj.model_dump(mode="python"))
    if isinstance(obj, dict):
        return {k: to_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_json(v) for v in obj]
    if isinstance(obj, datetime):
        return iso(obj)
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, Decimal):
        return float(obj)
    return obj


def ok(data, status: int = 200) -> JSONResponse:
    return JSONResponse(status_code=status, content=to_json(data))
