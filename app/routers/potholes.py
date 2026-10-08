import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict

from app import db
from app.config import settings
from app.errors import ApiError
from app.repositories import potholes as pot, records, refdata
from app.security import (check_not_blocked, constant_eq, is_admin, record_auth_failure,
                          unauthorized, verify_key_hash)
from app.serialization import ok
from core.geo import travel_minutes

router = APIRouter(prefix="/v1")


def _can_see_test(request: Request) -> bool:
    return settings.app_env != "production" or is_admin(request)


@router.get("/potholes")
def list_potholes(request: Request, ward_id: Optional[str] = None,
                  status: Optional[Literal["open", "fixed"]] = None,
                  source: Optional[Literal["complaint", "sensor", "both"]] = None,
                  min_severity: Optional[float] = Query(None, ge=0, le=1),
                  limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
                  include_test: bool = False):
    include = include_test and _can_see_test(request)
    with db.connection() as conn:
        items, total = pot.search(conn, ward_id=ward_id, status=status, source=source,
                                  min_severity=min_severity, limit=limit, offset=offset, include_test=include)
    return ok({"items": items, "total": total})


@router.get("/potholes/{pothole_id}")
def get_pothole(pothole_id: uuid.UUID, request: Request):
    admin = is_admin(request)
    with db.connection() as conn:
        p = pot.get(conn, str(pothole_id))
        if not p:
            raise ApiError(404, "NOT_FOUND", "pothole not found")
        c_rows, s_rows = records.complaints_for(conn, p["id"]), records.sensors_for(conn, p["id"])
    cv = records.complaint_admin if admin else records.complaint_public
    sv = records.sensor_admin if admin else records.sensor_public
    return ok({**p, "complaints": [cv(r) for r in c_rows], "sensor_events": [sv(r) for r in s_rows]})


@router.get("/stats")
def stats():
    with db.connection() as conn:
        return ok(pot.stats(conn))


class FixIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    crew_id: str


@router.post("/potholes/{pothole_id}/fix")
def fix_pothole(pothole_id: uuid.UUID, body: FixIn, request: Request):
    check_not_blocked(request)
    admin = is_admin(request)                         # wrong admin key -> 401
    with db.connection() as conn:
        if not admin:
            key = request.headers.get("X-Crew-Key")
            if not key:
                raise unauthorized()
            owner = next((r["crew_id"] for r in refdata.crew_secret_hashes(conn)
                          if verify_key_hash(r["key_hash"], key)), None)
            if owner is None:
                record_auth_failure(request)
                raise unauthorized()
            if owner != body.crew_id:                 # valid key, wrong crew
                raise ApiError(403, "FORBIDDEN", "this key cannot act for that crew")
        crew = refdata.crew(conn, body.crew_id, lock=True)
        if not crew:
            raise ApiError(404, "NOT_FOUND", "crew not found")
        p = pot.get(conn, str(pothole_id), lock=True)
        if not p:
            raise ApiError(404, "NOT_FOUND", "pothole not found")
        if p["status"] == "fixed":
            raise ApiError(409, "ALREADY_FIXED", "pothole is already fixed")
        now = datetime.now(timezone.utc)
        travel = travel_minutes(crew["current_lat"], crew["current_lng"], p["lat"], p["lng"])
        used = round(crew["minutes_used"] + travel + p["repair_minutes"], 1)
        conn.execute("update crews set current_lat=%s, current_lng=%s, minutes_used=%s, updated_at=%s where id=%s",
                     (p["lat"], p["lng"], used, now, crew["id"]))
        fixed = pot.mark_fixed(conn, p["id"], now)
        return ok({"pothole": fixed, "crew": refdata.crew(conn, crew["id"])})
