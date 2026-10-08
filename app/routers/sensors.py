import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from app import db
from app.config import settings
from app.errors import ApiError
from app.repositories import records, refdata
from app.security import is_test_run, limit_writes, rate_limit, require_sensor_or_admin
from app.serialization import ok
from app.services import ingest
from app.validation import parse
from core.constants import BATCH_MAX_EVENTS, MIN_PEAK_Z_DEVIATION
from core.severity import score_sensor

router = APIRouter(prefix="/v1", dependencies=[Depends(require_sensor_or_admin)])


class SensorEventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_event_id: uuid.UUID
    device_id: uuid.UUID
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    peak_z_deviation: float = Field(ge=MIN_PEAK_Z_DEVIATION)
    duration_ms: int = Field(gt=0)
    speed_kmh: float = Field(ge=0)
    recorded_at: datetime


def _ingest_one(conn, ev: SensorEventIn, wards: list, test: bool, now: datetime):
    ward_id = ingest.check_service_area(wards, ev.lat, ev.lng, test)
    rec = ev.recorded_at if ev.recorded_at.tzinfo else ev.recorded_at.replace(tzinfo=timezone.utc)
    sc = score_sensor(ev.peak_z_deviation, ev.duration_ms, ev.speed_kmh).score
    data = {"id": ingest.new_id(), "client_event_id": str(ev.client_event_id), "device_id": str(ev.device_id),
            "lat": ev.lat, "lng": ev.lng, "peak_z_deviation": ev.peak_z_deviation,
            "duration_ms": ev.duration_ms, "speed_kmh": ev.speed_kmh, "recorded_at": rec,
            "sensor_score": sc, "created_at": now, "ward_id": ward_id, "is_test": test}
    return ingest.ingest_sensor(conn, data, now)


@router.post("/sensor-events")
def post_event(ev: SensorEventIn, request: Request):
    limit_writes(request)
    rate_limit("device", str(ev.device_id), settings.rate_limit_writes_per_min)
    test, now = is_test_run(request), ingest.utcnow()
    with db.connection() as conn:
        wards = refdata.wards(conn)
        row, pothole, is_new, existed = _ingest_one(conn, ev, wards, test, now)
    return ok({"sensor_event": records.sensor_public(row), "pothole": pothole,
               "is_new_pothole": is_new and not existed}, 200 if existed else 201)


@router.post("/sensor-events/batch")
def post_batch(request: Request, payload: dict = Body(...)):
    limit_writes(request)
    if set(payload.keys()) != {"events"} or not isinstance(payload["events"], list):
        raise ApiError(422, "VALIDATION_ERROR", "body must be {\"events\": [...]}", {"field": "events"})
    raw = payload["events"]
    if not 1 <= len(raw) <= BATCH_MAX_EVENTS:
        raise ApiError(422, "VALIDATION_ERROR", f"events must contain 1 to {BATCH_MAX_EVENTS} items",
                       {"field": "events"})
    test, now = is_test_run(request), ingest.utcnow()
    with db.connection() as conn:
        wards = refdata.wards(conn)
    accepted = duplicates = 0
    rejected: list = []
    for item in raw:                                       # processed in order, one transaction each
        cid: Optional[str] = item.get("client_event_id") if isinstance(item, dict) and \
            isinstance(item.get("client_event_id"), str) else None
        try:
            ev = parse(SensorEventIn, item if isinstance(item, dict) else {})
            with db.connection() as conn:
                _, _, _, existed = _ingest_one(conn, ev, wards, test, now)
            duplicates += 1 if existed else 0
            accepted += 0 if existed else 1
        except ApiError as e:
            if e.status == 503:
                raise
            rejected.append({"client_event_id": cid, "code": e.code, "message": e.message})
    return ok({"accepted": accepted, "duplicates": duplicates, "rejected": rejected})
