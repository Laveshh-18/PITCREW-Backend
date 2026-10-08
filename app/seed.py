"""Loads fixtures (wards, POIs, crews, complaints, sensor events) idempotently. Admin only."""
import json
import os
import uuid
from datetime import timedelta

import psycopg.types.json as pgjson

from app import db, storage
from app.config import settings
from app.errors import ApiError
from app.repositories import refdata
from app.security import generate_key, hash_key
from app.services import ingest
from core.severity import score_sensor, score_text

NS = uuid.UUID("6f1c2a52-8f3e-4a53-9a55-0d1c8b5e7a10")


def _load(name: str):
    path = os.path.join(settings.fixtures_dir, name)
    if not os.path.exists(path):
        raise ApiError(400, "BAD_REQUEST", f"fixture file missing: {name}. "
                       "Run `python tools/make_fixtures.py` or sync contracts/fixtures into backend/fixtures")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run_seed(reset: bool) -> dict:
    wards, pois, crews = _load("wards.json"), _load("pois.json"), _load("crews.json")
    complaints, sensors = _load("complaints_seed_50.json"), _load("sensor_events_seed.json")
    now = ingest.utcnow()
    keys: dict = {}
    with db.connection() as conn:
        if reset:
            conn.execute("truncate sensor_events, complaints, potholes, crew_secrets, crews, pois, wards cascade")
        for w in wards:
            conn.execute("insert into wards (id, name, center_lat, center_lng, boundary) values (%s,%s,%s,%s,%s) "
                         "on conflict (id) do update set name=excluded.name, center_lat=excluded.center_lat, "
                         "center_lng=excluded.center_lng, boundary=excluded.boundary",
                         (w["id"], w["name"], w["center_lat"], w["center_lng"], pgjson.Jsonb(w["boundary"])))
        for p in pois:
            conn.execute("insert into pois (id, type, name, lat, lng, ward_id) values (%s,%s,%s,%s,%s,%s) "
                         "on conflict (id) do update set type=excluded.type, name=excluded.name, lat=excluded.lat, "
                         "lng=excluded.lng, ward_id=excluded.ward_id",
                         (p["id"], p["type"], p["name"], p["lat"], p["lng"], p["ward_id"]))
        for c in crews:
            conn.execute("insert into crews (id, name, color_index, depot_lat, depot_lng, shift_minutes, "
                         "current_lat, current_lng, minutes_used) values (%s,%s,%s,%s,%s,%s,%s,%s,0) "
                         "on conflict (id) do nothing",
                         (c["id"], c["name"], c["color_index"], c["depot_lat"], c["depot_lng"],
                          c.get("shift_minutes", 480), c["depot_lat"], c["depot_lng"]))
            has = conn.execute("select 1 from crew_secrets where crew_id=%s", (c["id"],)).fetchone()
            if not has:                                    # keys are shown once, only the hash is stored
                key = generate_key()
                refdata.set_crew_secret(conn, c["id"], hash_key(key))
                keys[c["id"]] = key
        ward_rows = refdata.wards(conn)
        for i, c in enumerate(complaints):
            created = now - timedelta(hours=c["hours_ago"])
            has_photo = bool(c.get("photo_verification", "none") != "none")
            url = storage.public_url(f"sample-{i % 8 + 1}.jpg") if has_photo and settings.supabase_url else None
            ingest.ingest_complaint(conn, {
                "id": str(uuid.uuid5(NS, "c" + c["client_request_id"])),
                "client_request_id": c["client_request_id"], "text": c["text"], "lat": c["lat"], "lng": c["lng"],
                "road_class": c.get("road_class"), "gps_accuracy_m": None,
                "text_score": score_text(c["text"]).score, "photo_url": url, "photo_score": c.get("photo_score") if has_photo else None,
                "photo_verification": c.get("photo_verification", "none"), "photo_phash": None,
                "created_at": created, "ward_id": ingest.ward_for(ward_rows, c["lat"], c["lng"]),
                "is_test": False}, now)
        for e in sensors:
            created = now - timedelta(hours=e["hours_ago"])
            ingest.ingest_sensor(conn, {
                "id": str(uuid.uuid5(NS, "s" + e["client_event_id"])),
                "client_event_id": e["client_event_id"], "device_id": e["device_id"], "lat": e["lat"],
                "lng": e["lng"], "peak_z_deviation": e["peak_z_deviation"], "duration_ms": e["duration_ms"],
                "speed_kmh": e["speed_kmh"], "recorded_at": created,
                "sensor_score": score_sensor(e["peak_z_deviation"], e["duration_ms"], e["speed_kmh"]).score,
                "created_at": created, "ward_id": ingest.ward_for(ward_rows, e["lat"], e["lng"]),
                "is_test": False}, now)
    return {"seeded": {"wards": len(wards), "pois": len(pois), "crews": len(crews),
                       "complaints": len(complaints), "sensor_events": len(sensors)},
            "crew_keys": keys}
