import logging
import re
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import db
from app.config import settings
from app.errors import ApiError
from app.routers import admin, complaints, planning, potholes, refdata, sensors, system
from app.security import client_ip, setup_logging

API_VERSION = system.API_VERSION
prod = settings.app_env == "production"
log = logging.getLogger("app")
_RID = re.compile(r"^[A-Za-z0-9._\-]{1,64}$")


def _check_production_config() -> None:
    if not prod:
        return
    for name, val in (("ADMIN_API_KEY", settings.admin_api_key), ("SENSOR_API_KEY", settings.sensor_api_key)):
        if len(val) < 32:
            raise RuntimeError(f"{name} must be at least 32 characters in production")


@asynccontextmanager
async def lifespan(_: FastAPI):
    global log
    log = setup_logging()
    _check_production_config()
    db.open_pool()
    yield
    db.close_pool()


app = FastAPI(
    title="Road-Repair Prioritizer", version=API_VERSION, lifespan=lifespan,
    docs_url=None if prod else "/docs", redoc_url=None if prod else "/redoc",
    openapi_url=None if prod else "/openapi.json",
)


def err(request: Request, status: int, code: str, message: str, details=None, headers=None) -> JSONResponse:
    return JSONResponse(status_code=status, headers=headers or {}, content={"error": {
        "code": code, "message": message, "details": details or {},
        "request_id": getattr(request.state, "request_id", None)}})


@app.middleware("http")
async def request_context(request: Request, call_next):
    incoming = request.headers.get("X-Request-ID", "")
    rid = incoming if _RID.match(incoming) else str(uuid.uuid4())
    request.state.request_id = rid
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:  # never leak stack traces
        log.exception("unhandled error", extra={"request_id": rid, "event": "unhandled"})
        response = err(request, 500, "INTERNAL_ERROR", "unexpected error")
    response.headers["X-Request-ID"] = rid
    response.headers["X-API-Version"] = API_VERSION
    log.info("request", extra={"request_id": rid, "method": request.method, "path": request.url.path,
                               "status": response.status_code, "ip": client_ip(request),
                               "duration_ms": round((time.perf_counter() - start) * 1000)})
    return response


# CORS is added last so it is the outermost layer (also answers preflight and covers error responses)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins, allow_origin_regex=settings.allowed_origin_regex,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-ID", "X-Sensor-Key", "X-Admin-Key", "X-Crew-Key", "X-Test-Run"],
    expose_headers=["X-Request-ID", "X-API-Version", "Retry-After"],
    allow_credentials=False,
)


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    return err(request, exc.status, exc.code, exc.message, exc.details, exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    loc = [str(p) for p in first.get("loc", []) if p not in ("body", "query", "path")]
    return err(request, 422, "VALIDATION_ERROR", first.get("msg", "invalid request"), {"field": ".".join(loc)})


@app.exception_handler(StarletteHTTPException)
async def http_handler(request: Request, exc: StarletteHTTPException):
    codes = {400: "BAD_REQUEST", 401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND"}
    return err(request, exc.status_code, codes.get(exc.status_code, "BAD_REQUEST"), str(exc.detail))


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    return err(request, 500, "INTERNAL_ERROR", "unexpected error")


for r in (system.router, refdata.router, potholes.router, complaints.router, sensors.router,
          planning.router, admin.router):
    app.include_router(r)
