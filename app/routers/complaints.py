import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app import db, storage
from app.errors import ApiError
from app.photo import MAX_BYTES, process_photo
from app.repositories import potholes as pot, records, refdata
from app.security import is_test_run, limit_photo, limit_writes
from app.serialization import ok
from app.services import ingest
from app.validation import parse
from core.constants import PHOTO_HASH_LOOKBACK_DAYS
from core.models import KnownPhotoHash
from core.severity import score_text
from core.verification import verify_photo_metadata

router = APIRouter(prefix="/v1")
ALLOWED_FIELDS = {"client_request_id", "text", "lat", "lng", "gps_accuracy_m", "road_class", "photo"}


class ComplaintIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_request_id: uuid.UUID
    text: str = Field(min_length=5, max_length=1000)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    gps_accuracy_m: Optional[float] = Field(None, ge=0, le=5000)
    road_class: Optional[Literal["main", "secondary", "lane"]] = None

    @field_validator("text", mode="before")
    @classmethod
    def _strip(cls, v):  # strip BEFORE the length check so "  ab  " cannot slip past min_length
        return v.strip() if isinstance(v, str) else v


def _too_large() -> ApiError:
    return ApiError(413, "PHOTO_TOO_LARGE", "photo must be 5 MB or smaller")


async def _read_limited(upload) -> bytes:
    """Reads in chunks and aborts as soon as the limit is crossed."""
    buf, total = bytearray(), 0
    while True:
        chunk = await upload.read(65536)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_BYTES:
            raise _too_large()
        buf += chunk
    return bytes(buf)


def _result(row, pothole, is_new, rank, size, status, reasons):
    return {"complaint": records.complaint_public(row), "pothole": pothole, "is_new_pothole": is_new,
            "queue_rank": rank, "queue_size": size,
            "photo_verification": {"status": status, "reasons": reasons}}


def _create(body: ComplaintIn, photo_bytes: bytes | None, test: bool):
    rid = str(body.client_request_id)
    now = ingest.utcnow()
    with db.connection() as conn:                       # fast idempotency path
        existing = records.complaint_by_request_id(conn, rid)
        if existing:
            p = pot.get(conn, existing["pothole_id"])
            rank, size = ingest.queue_rank(conn, p["id"], now)
            return ok(_result(existing, p, p["first_reported_at"] == existing["created_at"], rank, size,
                              existing["photo_verification"], []), 200)
        wards = refdata.wards(conn)
        known = records.known_hashes(conn, now, PHOTO_HASH_LOOKBACK_DAYS) if photo_bytes else []
    ward_id = ingest.check_service_area(wards, body.lat, body.lng, test)

    complaint_id = ingest.new_id()
    text_score = score_text(body.text).score
    photo_url = photo_score = phash = None
    status, reasons = "none", []
    if photo_bytes:
        proc = process_photo(photo_bytes)               # may raise 415 / 422
        ver = verify_photo_metadata(
            has_photo=True, submitted_lat=body.lat, submitted_lng=body.lng,
            gps_accuracy_m=body.gps_accuracy_m, exif_lat=proc.exif_lat, exif_lng=proc.exif_lng,
            taken_at=proc.taken_at, now=now, phash=proc.phash,
            known_hashes=[KnownPhotoHash(**k) for k in known])
        photo_url = storage.upload_jpeg(complaint_id + ".jpg", proc.jpeg)
        if photo_url:                                   # EXIF values are discarded here, never stored
            status, reasons, photo_score, phash = ver.status, ver.reasons, proc.photo_score, proc.phash
        else:                                           # 8.5 step 10: storage down -> text-only complaint
            status, reasons = "none", []

    data = {"id": complaint_id, "client_request_id": rid, "text": body.text, "lat": body.lat, "lng": body.lng,
            "road_class": body.road_class, "gps_accuracy_m": body.gps_accuracy_m, "text_score": text_score,
            "photo_url": photo_url, "photo_score": photo_score, "photo_verification": status,
            "photo_phash": phash, "created_at": now, "ward_id": ward_id, "is_test": test}
    with db.connection() as conn:
        row, pothole, is_new, existed = ingest.ingest_complaint(conn, data, now)
    with db.connection() as conn:
        rank, size = ingest.queue_rank(conn, pothole["id"], now)
    if existed:
        return ok(_result(row, pothole, is_new, rank, size, row["photo_verification"], []), 200)
    return ok(_result(row, pothole, is_new, rank, size, status, reasons), 201)


@router.post("/complaints")
async def create_complaint(request: Request):
    limit_writes(request)
    cl = request.headers.get("content-length", "")
    if cl.isdigit() and int(cl) > MAX_BYTES + 512 * 1024:      # reject oversize bodies up front
        raise _too_large()
    form = await request.form()
    unknown = set(form.keys()) - ALLOWED_FIELDS
    if unknown:
        raise ApiError(422, "VALIDATION_ERROR", "unknown field", {"field": sorted(unknown)[0]})
    fields = {k: v for k, v in form.items() if k != "photo" and isinstance(v, str) and v != ""}
    body = parse(ComplaintIn, fields)

    photo_bytes = None
    upload = form.get("photo")
    if upload is not None and not isinstance(upload, str):
        limit_photo(request)
        photo_bytes = await _read_limited(upload) or None
    return await run_in_threadpool(_create, body, photo_bytes, is_test_run(request))
