from app.repositories.common import clean, clean_all

COMPLAINT_COLS = ("id, client_request_id, pothole_id, text, photo_url, lat, lng, road_class, text_score, "
                  "photo_score, gps_accuracy_m, photo_verification, created_at")
SENSOR_COLS = ("id, client_event_id, pothole_id, device_id, lat, lng, peak_z_deviation, duration_ms, "
               "speed_kmh, recorded_at, sensor_score, created_at")


# ---------- public / admin views (Constitution 5.4.1)
def complaint_public(r: dict) -> dict:
    flagged = r["photo_verification"] in ("mismatch", "duplicate")
    return {"id": r["id"], "pothole_id": r["pothole_id"], "text": r["text"],
            "photo_url": None if flagged else r["photo_url"], "photo_verification": r["photo_verification"],
            "lat": r["lat"], "lng": r["lng"], "road_class": r["road_class"], "created_at": r["created_at"]}


def complaint_admin(r: dict) -> dict:
    return {**complaint_public(r), "photo_url": r["photo_url"], "client_request_id": r["client_request_id"],
            "text_score": r["text_score"], "photo_score": r["photo_score"], "gps_accuracy_m": r["gps_accuracy_m"]}


def sensor_public(r: dict) -> dict:
    return {k: r[k] for k in ("id", "pothole_id", "lat", "lng", "peak_z_deviation", "duration_ms",
                              "speed_kmh", "recorded_at", "sensor_score", "created_at")}


def sensor_admin(r: dict) -> dict:
    return {**sensor_public(r), "device_id": r["device_id"], "client_event_id": r["client_event_id"]}


# ---------- complaints
def complaint_by_request_id(conn, rid: str):
    return clean(conn.execute("select " + COMPLAINT_COLS + " from complaints where client_request_id = %s",
                              (rid,)).fetchone())


def complaints_for(conn, pothole_id: str) -> list:
    return clean_all(conn.execute("select " + COMPLAINT_COLS + " from complaints where pothole_id = %s "
                                  "order by created_at desc, id", (pothole_id,)).fetchall())


def insert_complaint(conn, c: dict) -> dict:
    return clean(conn.execute(
        "insert into complaints (id, client_request_id, pothole_id, text, photo_url, lat, lng, road_class, "
        "text_score, photo_score, gps_accuracy_m, photo_verification, photo_phash, created_at, is_test) "
        "values (%(id)s, %(client_request_id)s, %(pothole_id)s, %(text)s, %(photo_url)s, %(lat)s, %(lng)s, "
        "%(road_class)s, %(text_score)s, %(photo_score)s, %(gps_accuracy_m)s, %(photo_verification)s, "
        "%(photo_phash)s, %(created_at)s, %(is_test)s) returning " + COMPLAINT_COLS, c).fetchone())


def known_hashes(conn, now, days: int, limit: int = 5000) -> list:
    return conn.execute(
        "select photo_phash as phash, lat, lng from complaints where photo_phash is not null "
        "and created_at > %s - make_interval(days => %s) order by created_at desc limit %s",
        (now, days, limit)).fetchall()


# ---------- sensor events
def sensor_by_event_id(conn, eid: str):
    return clean(conn.execute("select " + SENSOR_COLS + " from sensor_events where client_event_id = %s",
                              (eid,)).fetchone())


def sensors_for(conn, pothole_id: str) -> list:
    return clean_all(conn.execute("select " + SENSOR_COLS + " from sensor_events where pothole_id = %s "
                                  "order by recorded_at desc, id", (pothole_id,)).fetchall())


def insert_sensor(conn, e: dict) -> dict:
    return clean(conn.execute(
        "insert into sensor_events (id, client_event_id, pothole_id, device_id, lat, lng, peak_z_deviation, "
        "duration_ms, speed_kmh, recorded_at, sensor_score, created_at, is_test) "
        "values (%(id)s, %(client_event_id)s, %(pothole_id)s, %(device_id)s, %(lat)s, %(lng)s, "
        "%(peak_z_deviation)s, %(duration_ms)s, %(speed_kmh)s, %(recorded_at)s, %(sensor_score)s, "
        "%(created_at)s, %(is_test)s) returning " + SENSOR_COLS, e).fetchone())
