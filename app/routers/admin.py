from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app import db, seed
from app.errors import ApiError
from app.repositories import refdata
from app.security import generate_key, hash_key, require_admin
from app.serialization import ok
from app.services import ingest

router = APIRouter(prefix="/v1/admin", dependencies=[Depends(require_admin)])


@router.post("/seed")
def seed_data(reset: bool = False):
    return ok(seed.run_seed(reset))


@router.post("/crews/{crew_id}/rotate-key")
def rotate_key(crew_id: str):
    with db.connection() as conn:
        if not refdata.crew(conn, crew_id):
            raise ApiError(404, "NOT_FOUND", "crew not found")
        key = generate_key()
        refdata.set_crew_secret(conn, crew_id, hash_key(key))   # old key is invalid immediately
    return ok({"crew_id": crew_id, "crew_key": key})


@router.post("/reset-day")
def reset_day():
    now = datetime.now(timezone.utc)
    with db.connection() as conn:
        crews = conn.execute("update crews set current_lat = depot_lat, current_lng = depot_lng, "
                             "minutes_used = 0, updated_at = %s", (now,)).rowcount
        fixed = conn.execute("update potholes set status = 'open', fixed_at = null, updated_at = %s "
                             "where status = 'fixed'", (now,)).rowcount
    return ok({"crews_reset": crews, "potholes_reopened": fixed})


@router.delete("/test-data")
def delete_test_data():
    now = ingest.utcnow()
    with db.connection() as conn:
        touched = {str(r["pothole_id"]) for r in conn.execute(
            "select pothole_id from complaints where is_test union select pothole_id from sensor_events "
            "where is_test").fetchall()}
        c = conn.execute("delete from complaints where is_test").rowcount
        s = conn.execute("delete from sensor_events where is_test").rowcount
        p = conn.execute("delete from potholes where is_test").rowcount
        for pid in touched:                       # real potholes that lost test records get re-scored
            exists = conn.execute("select 1 from potholes where id = %s", (pid,)).fetchone()
            if exists:
                ingest.refresh_pothole(conn, pid, now)
    return ok({"complaints_deleted": c, "sensor_events_deleted": s, "potholes_deleted": p})
