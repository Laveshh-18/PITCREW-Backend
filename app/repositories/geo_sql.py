"""The ONLY place lat/lng are converted to PostGIS order (x = lng first). Constitution 4.2."""

POINT_SQL = "st_setsrid(st_makepoint(%(lng)s, %(lat)s), 4326)::geography"


def cell_keys(lat: float, lng: float) -> list:
    """Grid cell (0.001 deg, ~110 m) of the point plus its 8 neighbours, sorted to avoid deadlocks."""
    ilat, ilng = round(lat * 1000), round(lng * 1000)
    keys = {f"{(ilat + di) / 1000:.3f}:{(ilng + dj) / 1000:.3f}" for di in (-1, 0, 1) for dj in (-1, 0, 1)}
    return sorted(keys)


def lock_cells(conn, lat: float, lng: float) -> None:
    """Transaction-scoped advisory locks: concurrent writes at one spot are serialised (9.4 step 1)."""
    for key in cell_keys(lat, lng):
        conn.execute("select pg_advisory_xact_lock(hashtext(%s))", (key,))


def nearest_open_pothole_id(conn, lat: float, lng: float, radius_m: float):
    row = conn.execute(
        "select id from potholes where status = 'open' "
        "and st_dwithin(location, " + POINT_SQL + ", %(r)s) "
        "order by st_distance(location, " + POINT_SQL + ") limit 1",
        {"lat": lat, "lng": lng, "r": radius_m}).fetchone()
    return str(row["id"]) if row else None
