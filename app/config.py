"""The ONLY place environment variables are read."""
import os
from dataclasses import dataclass

try:  # local development convenience; harmless on Render
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # pragma: no cover
    pass


def _list(v: str) -> list:
    return [x.strip().rstrip("/") for x in v.split(",") if x.strip()]


@dataclass(frozen=True)
class Settings:
    app_env: str
    database_url: str
    supabase_url: str
    supabase_service_role_key: str
    supabase_bucket: str
    admin_api_key: str
    sensor_api_key: str
    allowed_origins: list
    allowed_origin_regex: str | None
    rate_limit_writes_per_min: int
    rate_limit_photo_per_min: int
    rate_limit_auth_fail_per_min: int
    log_level: str
    port: int
    fixtures_dir: str


def load_settings() -> Settings:
    g = os.environ.get
    return Settings(
        app_env=g("APP_ENV", "development"),
        database_url=g("DATABASE_URL", ""),
        supabase_url=g("SUPABASE_URL", "").rstrip("/"),
        supabase_service_role_key=g("SUPABASE_SERVICE_ROLE_KEY", ""),
        supabase_bucket=g("SUPABASE_STORAGE_BUCKET", "complaint-photos"),
        admin_api_key=g("ADMIN_API_KEY", ""),
        sensor_api_key=g("SENSOR_API_KEY", ""),
        allowed_origins=_list(g("ALLOWED_ORIGINS", "")),
        allowed_origin_regex=g("ALLOWED_ORIGIN_REGEX") or None,
        rate_limit_writes_per_min=int(g("RATE_LIMIT_WRITES_PER_MIN", "60")),
        rate_limit_photo_per_min=int(g("RATE_LIMIT_PHOTO_PER_MIN", "10")),
        rate_limit_auth_fail_per_min=int(g("RATE_LIMIT_AUTH_FAIL_PER_MIN", "10")),
        log_level=g("LOG_LEVEL", "INFO"),
        port=int(g("PORT", "8000")),
        fixtures_dir=g("FIXTURES_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures")),
    )


settings = load_settings()
