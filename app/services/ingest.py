"""Nikhil's half of fusion: find the neighbour, load children, call core, write the result.
Every number comes from core. Nothing here computes a score."""
import uuid
from datetime import datetime, timezone

from app.errors import ApiError
from app.repositories import geo_sql, potholes as pot, records, refdata
from core.constants import FUSION_RADIUS_M, MAX_PHOTOS_PER_POTHOLE_RETURNED
from core.fusion import recompute_pothole
from core.geo import point_in_polygon
from core.models import POI, Complaint, Crew, Pothole, SensorEvent
from core.priority import rank_queue

FLAGGED = ("mismatch", "duplicate")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ward_for(wards: list, lat: float, lng: float) -> str | None:
    for w in wards:
        if point_in_polygon(lat, lng, w["boundary"]):
            return w["id"]
    return None


def check_service_area(wards: list, lat: float, lng: float, is_test: bool) -> str | None:
    ward = ward_for(wards, lat, lng)
    if ward is None and not is_test:
        raise ApiError(422, "OUTSIDE_SERVICE_AREA", "location is not inside any ward",
                       {"lat": lat, "lng": lng})
    return ward


def refresh_pothole(conn, pothole_id: str, now: datetime) -> dict:
    p_row = pot.get(conn, pothole_id, lock=True)
    c_rows = records.complaints_for(conn, pothole_id)
    s_rows = records.sensors_for(conn, pothole_id)
    pois = [POI(**r) for r in refdata.pois(conn)]
    scores = recompute_pothole(Pothole(**p_row), [Complaint(**r) for r in c_rows],
                               [SensorEvent(**r) for r in s_rows], pois)
    urls = [r["photo_url"] for r in c_rows
            if r["photo_url"] and r["photo_verification"] in ("verified", "unverified")]
    stamps = [r["created_at"] for r in c_rows] + [r["created_at"] for r in s_rows]
    extra = {
        "photo_urls": urls[:MAX_PHOTOS_PER_POTHOLE_RETURNED],
        "needs_review": any(r["photo_verification"] in FLAGGED for r in c_rows),
        "first_reported_at": min(stamps + [p_row["first_reported_at"]]),
        "last_reported_at": max(stamps + [p_row["last_reported_at"] or p_row["first_reported_at"]]),
    }
    return pot.update_scores(conn, pothole_id, scores, extra, now)


def _attach_or_create(conn, lat, lng, ward_id, road_class, source, created_at, now, is_test):
    near = geo_sql.nearest_open_pothole_id(conn, lat, lng, FUSION_RADIUS_M)
    if near:
        return near, False
    return pot.insert_new(conn, lat=lat, lng=lng, ward_id=ward_id, road_class=road_class or "secondary",
                          source=source, created_at=created_at, now=now, is_test=is_test), True


def ingest_complaint(conn, c: dict, now: datetime) -> tuple:
    """c keys: id, client_request_id, text, lat, lng, road_class, gps_accuracy_m, text_score, photo_url,
    photo_score, photo_verification, photo_phash, created_at, ward_id, is_test.
    Returns (complaint_row, pothole_row, is_new_pothole, already_existed)."""
    geo_sql.lock_cells(conn, c["lat"], c["lng"])                      # 9.4 step 1
    existing = records.complaint_by_request_id(conn, c["client_request_id"])
    if existing:
        p = pot.get(conn, existing["pothole_id"])
        return existing, p, p["first_reported_at"] == existing["created_at"], True
    pid, is_new = _attach_or_create(conn, c["lat"], c["lng"], c["ward_id"], c.get("road_class"),
                                    "complaint", c["created_at"], now, c["is_test"])   # step 2 + 3
    row = records.insert_complaint(conn, {**c, "pothole_id": pid})
    return row, refresh_pothole(conn, pid, now), is_new, False        # step 4


def ingest_sensor(conn, e: dict, now: datetime) -> tuple:
    """e keys: id, client_event_id, device_id, lat, lng, peak_z_deviation, duration_ms, speed_kmh,
    recorded_at, sensor_score, created_at, ward_id, is_test."""
    geo_sql.lock_cells(conn, e["lat"], e["lng"])
    existing = records.sensor_by_event_id(conn, e["client_event_id"])
    if existing:
        p = pot.get(conn, existing["pothole_id"])
        return existing, p, p["first_reported_at"] == existing["created_at"], True
    pid, is_new = _attach_or_create(conn, e["lat"], e["lng"], e["ward_id"], None,
                                    "sensor", e["created_at"], now, e["is_test"])
    row = records.insert_sensor(conn, {**e, "pothole_id": pid})
    return row, refresh_pothole(conn, pid, now), is_new, False


def new_id() -> str:
    return str(uuid.uuid4())


def models_for_ranking(conn, ward_id: str | None = None) -> tuple:
    p_rows = pot.list_open(conn, ward_id)
    crews = [Crew(**r) for r in refdata.crews(conn)]
    return [Pothole(**r) for r in p_rows], crews


def queue_rank(conn, pothole_id: str, now: datetime) -> tuple:
    potholes, crews = models_for_ranking(conn)
    items = rank_queue(potholes, crews, now)
    rank = next((i.rank for i in items if i.pothole.id == pothole_id), None)
    return rank, len(items)
