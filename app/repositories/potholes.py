from app.repositories.common import clean, clean_all

COLS = ("id, lat, lng, ward_id, road_class, source, severity, severity_bucket, severity_reasons, exposure, "
        "exposure_reasons, complaint_count, sensor_event_count, confirmation_count, repair_minutes, status, "
        "photo_urls, needs_review, first_reported_at, last_reported_at, fixed_at, updated_at")


def get(conn, pothole_id: str, lock: bool = False) -> dict | None:
    sql = "select " + COLS + " from potholes where id = %s" + (" for update" if lock else "")
    return clean(conn.execute(sql, (pothole_id,)).fetchone())


def list_open(conn, ward_id: str | None = None) -> list:
    if ward_id:
        rows = conn.execute("select " + COLS + " from potholes where status = 'open' and is_test = false "
                            "and ward_id = %s", (ward_id,)).fetchall()
    else:
        rows = conn.execute("select " + COLS + " from potholes where status = 'open' and is_test = false").fetchall()
    return clean_all(rows)


def search(conn, *, ward_id, status, source, min_severity, limit, offset, include_test) -> tuple:
    conds, params = [], {}
    if not include_test:
        conds.append("is_test = false")
    if ward_id:
        conds.append("ward_id = %(ward_id)s"); params["ward_id"] = ward_id
    if status:
        conds.append("status = %(status)s"); params["status"] = status
    if source:
        conds.append("source = %(source)s"); params["source"] = source
    if min_severity is not None:
        conds.append("severity >= %(min_sev)s"); params["min_sev"] = min_severity
    where = (" where " + " and ".join(conds)) if conds else ""
    total = conn.execute("select count(*) as n from potholes" + where, params).fetchone()["n"]
    params.update(limit=limit, offset=offset)
    rows = conn.execute("select " + COLS + " from potholes" + where +
                        " order by severity desc, first_reported_at asc, id asc limit %(limit)s offset %(offset)s",
                        params).fetchall()
    return clean_all(rows), total


def insert_new(conn, *, lat, lng, ward_id, road_class, source, created_at, now, is_test) -> str:
    row = conn.execute(
        "insert into potholes (lat, lng, ward_id, road_class, source, severity, severity_bucket, exposure, "
        "repair_minutes, first_reported_at, last_reported_at, updated_at, is_test) "
        "values (%s, %s, %s, %s, %s, 0, 'low', 0, 15, %s, %s, %s, %s) returning id",
        (lat, lng, ward_id, road_class, source, created_at, created_at, now, is_test)).fetchone()
    return str(row["id"])


def update_scores(conn, pothole_id: str, s, extra: dict, now) -> dict:
    row = conn.execute(
        "update potholes set severity=%s, severity_bucket=%s, severity_reasons=%s, exposure=%s, "
        "exposure_reasons=%s, complaint_count=%s, sensor_event_count=%s, confirmation_count=%s, "
        "repair_minutes=%s, source=%s, photo_urls=%s, needs_review=%s, "
        "first_reported_at=%s, last_reported_at=%s, updated_at=%s where id=%s returning " + COLS,
        (s.severity, s.severity_bucket, s.severity_reasons, s.exposure, s.exposure_reasons,
         s.complaint_count, s.sensor_event_count, s.confirmation_count, s.repair_minutes, s.source,
         extra["photo_urls"], extra["needs_review"], extra["first_reported_at"], extra["last_reported_at"],
         now, pothole_id)).fetchone()
    return clean(row)


def mark_fixed(conn, pothole_id: str, now) -> dict:
    return clean(conn.execute(
        "update potholes set status='fixed', fixed_at=%s, updated_at=%s where id=%s returning " + COLS,
        (now, now, pothole_id)).fetchone())


def stats(conn) -> dict:
    r = conn.execute(
        "select count(*) filter (where status='open') as open_total, "
        "count(*) filter (where status='fixed') as fixed_total, "
        "count(*) filter (where status='open' and severity_bucket='low') as b_low, "
        "count(*) filter (where status='open' and severity_bucket='medium') as b_medium, "
        "count(*) filter (where status='open' and severity_bucket='high') as b_high, "
        "count(*) filter (where status='open' and severity_bucket='critical') as b_critical, "
        "count(*) filter (where status='open' and source='complaint') as s_complaint, "
        "count(*) filter (where status='open' and source='sensor') as s_sensor, "
        "count(*) filter (where status='open' and source='both') as s_both, "
        "count(*) filter (where status='open' and needs_review) as needs_review "
        "from potholes where is_test = false").fetchone()
    return {"open_total": r["open_total"], "fixed_total": r["fixed_total"],
            "by_bucket": {k: r["b_" + k] for k in ("low", "medium", "high", "critical")},
            "by_source": {k: r["s_" + k] for k in ("complaint", "sensor", "both")},
            "auto_detected_unreported": r["s_sensor"], "needs_review": r["needs_review"]}
