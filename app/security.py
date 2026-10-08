"""Key checks, rate limits, argon2id hashing, log redaction (Constitution 13)."""
import hmac
import json
import logging
import re
import secrets
import threading
import time
from collections import defaultdict, deque

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Request

from app.config import settings
from app.errors import ApiError

_ph = PasswordHasher(memory_cost=19456, time_cost=2, parallelism=1)  # OWASP minimum, gentle on 512 MB RAM


# ---------------------------------------------------------------- keys
def generate_key() -> str:
    return secrets.token_urlsafe(32)


def hash_key(key: str) -> str:
    return _ph.hash(key)


def verify_key_hash(key_hash: str, key: str) -> bool:
    try:
        return _ph.verify(key_hash, key)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def constant_eq(a: str, b: str) -> bool:
    if not a or not b:
        return False
    return hmac.compare_digest(a.encode(), b.encode())


# ---------------------------------------------------------------- client ip
def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# ---------------------------------------------------------------- rate limiting (single worker, in memory)
class SlidingWindow:
    def __init__(self):
        self._hits: dict = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_s: int = 60) -> int:
        """Records a hit. Returns 0 if allowed, else seconds to wait."""
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > window_s:
                q.popleft()
            if len(q) >= limit:
                return max(1, int(window_s - (now - q[0])) + 1)
            q.append(now)
            return 0


_limiter = SlidingWindow()
_fail_log: dict = defaultdict(deque)
_blocked_until: dict = {}
_fail_lock = threading.Lock()


def rate_limit(bucket: str, ident: str, limit: int) -> None:
    wait = _limiter.hit(f"{bucket}:{ident}", limit)
    if wait:
        raise ApiError(429, "RATE_LIMITED", "too many requests", headers={"Retry-After": str(wait)})


def limit_writes(request: Request) -> None:
    rate_limit("write", client_ip(request), settings.rate_limit_writes_per_min)


def limit_photo(request: Request) -> None:
    rate_limit("photo", client_ip(request), settings.rate_limit_photo_per_min)


def limit_plan(request: Request) -> None:
    rate_limit("plan", client_ip(request), 30)


def check_not_blocked(request: Request) -> None:
    ip = client_ip(request)
    with _fail_lock:
        until = _blocked_until.get(ip)
        if until and until > time.monotonic():
            raise ApiError(429, "RATE_LIMITED", "too many failed attempts",
                           headers={"Retry-After": str(int(until - time.monotonic()) + 1)})
        if until:
            _blocked_until.pop(ip, None)


def record_auth_failure(request: Request) -> None:
    ip, now = client_ip(request), time.monotonic()
    with _fail_lock:
        q = _fail_log[ip]
        while q and now - q[0] > 60:
            q.popleft()
        q.append(now)
        if len(q) >= settings.rate_limit_auth_fail_per_min:
            _blocked_until[ip] = now + 300
            q.clear()


def reset_security_state() -> None:  # used by tests
    _limiter._hits.clear()
    _fail_log.clear()
    _blocked_until.clear()


# ---------------------------------------------------------------- header auth
def unauthorized() -> ApiError:
    return ApiError(401, "UNAUTHORIZED", "missing or invalid key")


def is_admin(request: Request) -> bool:
    """True if a valid admin key is sent. A present-but-wrong key is a 401 and counts as a failure."""
    key = request.headers.get("X-Admin-Key")
    if key is None:
        return False
    check_not_blocked(request)
    if constant_eq(key, settings.admin_api_key):
        return True
    record_auth_failure(request)
    raise unauthorized()


def require_admin(request: Request) -> None:
    check_not_blocked(request)
    key = request.headers.get("X-Admin-Key")
    if key is None or not constant_eq(key, settings.admin_api_key):
        record_auth_failure(request)
        raise unauthorized()


def require_sensor_or_admin(request: Request) -> None:
    check_not_blocked(request)
    sk, ak = request.headers.get("X-Sensor-Key"), request.headers.get("X-Admin-Key")
    if (sk and constant_eq(sk, settings.sensor_api_key)) or (ak and constant_eq(ak, settings.admin_api_key)):
        return
    record_auth_failure(request)
    raise unauthorized()


def is_test_run(request: Request) -> bool:
    """X-Test-Run only honoured with a valid admin key, or outside production."""
    if request.headers.get("X-Test-Run") is None:
        return False
    if settings.app_env != "production":
        return True
    ak = request.headers.get("X-Admin-Key")
    return bool(ak and constant_eq(ak, settings.admin_api_key))


# ---------------------------------------------------------------- logging with redaction
_DB_URL = re.compile(r"postgres(?:ql)?://\S+", re.I)
_JWT = re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")
ALLOWED_FIELDS = ("request_id", "method", "path", "status", "duration_ms", "ip", "event")


def redact(text: str) -> str:
    return _JWT.sub("[redacted-token]", _DB_URL.sub("[redacted-db-url]", text))


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"), "level": record.levelname,
               "msg": redact(record.getMessage())}
        for f in ALLOWED_FIELDS:  # allowlist: nothing else is ever logged
            if hasattr(record, f):
                out[f] = getattr(record, f)
        return json.dumps(out)


def setup_logging() -> logging.Logger:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level.upper())
    for noisy in ("uvicorn.access",):  # access log includes query strings; we log our own line
        logging.getLogger(noisy).disabled = True
    return logging.getLogger("app")
