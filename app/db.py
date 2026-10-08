"""Connection pool (Supabase transaction pooler, port 6543)."""
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout

from app.config import settings
from app.errors import ApiError

_pool: ConnectionPool | None = None


def open_pool() -> None:
    global _pool
    if not settings.database_url:
        return
    # prepare_threshold=None: required by pgbouncer in transaction mode
    _pool = ConnectionPool(settings.database_url, min_size=1, max_size=5, open=False, timeout=10,
                           kwargs={"row_factory": dict_row, "prepare_threshold": None, "connect_timeout": 10})
    _pool.open(wait=False)


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def _unavailable() -> ApiError:
    return ApiError(503, "DB_UNAVAILABLE", "database unavailable")


@contextmanager
def connection():
    """One transaction: commits on success, rolls back on any exception."""
    if _pool is None:
        raise _unavailable()
    try:
        with _pool.connection() as conn:
            yield conn
    except (psycopg.OperationalError, PoolTimeout):
        raise _unavailable()


def ping() -> None:
    with connection() as conn:
        conn.execute("select 1")
