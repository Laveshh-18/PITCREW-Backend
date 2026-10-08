from app.repositories.common import clean, clean_all

CREW_COLS = ("id, name, color_index, depot_lat, depot_lng, shift_minutes, current_lat, current_lng, "
             "minutes_used, updated_at")


def wards(conn) -> list:
    return clean_all(conn.execute("select id, name, center_lat, center_lng, boundary from wards order by id").fetchall())


def pois(conn) -> list:
    return clean_all(conn.execute("select id, type, name, lat, lng, ward_id from pois order by name, id").fetchall())


def crews(conn) -> list:
    return clean_all(conn.execute("select " + CREW_COLS + " from crews order by id").fetchall())


def crew(conn, crew_id: str, lock: bool = False) -> dict | None:
    sql = "select " + CREW_COLS + " from crews where id = %s" + (" for update" if lock else "")
    return clean(conn.execute(sql, (crew_id,)).fetchone())


def crew_secret_hashes(conn) -> list:
    return conn.execute("select crew_id, key_hash from crew_secrets").fetchall()


def set_crew_secret(conn, crew_id: str, key_hash: str) -> None:
    conn.execute(
        "insert into crew_secrets (crew_id, key_hash, rotated_at) values (%s, %s, now()) "
        "on conflict (crew_id) do update set key_hash = excluded.key_hash, rotated_at = now()",
        (crew_id, key_hash))
