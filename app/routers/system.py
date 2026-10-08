from datetime import datetime, timezone

from fastapi import APIRouter

from app import db
from app.serialization import ok
from core.constants import CONSTANTS

router = APIRouter()
API_VERSION = "1.1.0"


@router.get("/health")
def health(deep: bool = False):
    if deep:
        db.ping()  # raises 503 DB_UNAVAILABLE
    return ok({"status": "ok", "version": API_VERSION, "time": datetime.now(timezone.utc)})


@router.get("/v1/config")
def config():
    return ok(CONSTANTS)
