"""Pydantic models = shared data shapes (Constitution Section 5)."""
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class _M(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Pothole(_M):
    id: str
    lat: float
    lng: float
    ward_id: str | None = None
    road_class: str = "secondary"
    source: str = "complaint"
    severity: float = 0.0
    severity_bucket: str = "low"
    severity_reasons: list[str] = []
    exposure: float = 0.0
    exposure_reasons: list[str] = []
    complaint_count: int = 0
    sensor_event_count: int = 0
    confirmation_count: int = 1
    repair_minutes: int = 15
    status: str = "open"
    photo_urls: list[str] = []
    needs_review: bool = False
    first_reported_at: datetime
    last_reported_at: datetime | None = None
    fixed_at: datetime | None = None
    updated_at: datetime | None = None


class Complaint(_M):
    id: str
    pothole_id: str | None = None
    text: str
    lat: float
    lng: float
    photo_url: str | None = None
    text_score: float | None = None
    photo_score: float | None = None
    photo_verification: str = "none"
    road_class: str | None = None
    gps_accuracy_m: float | None = None
    created_at: datetime | None = None


class SensorEvent(_M):
    id: str
    pothole_id: str | None = None
    device_id: str
    lat: float
    lng: float
    peak_z_deviation: float
    duration_ms: int
    speed_kmh: float
    recorded_at: datetime
    sensor_score: float = 0.0
    created_at: datetime | None = None


class POI(_M):
    id: str
    type: str
    name: str = ""
    lat: float
    lng: float
    ward_id: str | None = None


class Crew(_M):
    id: str
    name: str = ""
    color_index: int = 0
    depot_lat: float
    depot_lng: float
    shift_minutes: int = 480
    current_lat: float
    current_lng: float
    minutes_used: float = 0.0


class SignalScore(_M):
    score: float
    reasons: list[str] = []


class PotholeScores(_M):
    severity: float
    severity_bucket: str
    severity_reasons: list[str]
    exposure: float
    exposure_reasons: list[str]
    complaint_count: int
    sensor_event_count: int
    confirmation_count: int
    repair_minutes: int
    source: str


class KnownPhotoHash(_M):
    phash: int
    lat: float
    lng: float


class PhotoVerification(_M):
    status: str
    distance_m: float | None = None
    age_hours: float | None = None
    reasons: list[str] = []


class QueueItem(_M):
    rank: int
    pothole: Pothole
    severity: float
    exposure: float
    proximity: float
    aging_multiplier: float
    priority: float
    nearest_crew_id: str | None = None


class Point(_M):
    lat: float
    lng: float


class Stop(_M):
    sequence: int
    pothole_id: str
    lat: float
    lng: float
    travel_minutes: float
    repair_minutes: int
    arrive_at_minute: float
    finish_at_minute: float
    severity: float
    exposure: float
    proximity: float
    aging_multiplier: float
    priority: float


class Route(_M):
    crew_id: str
    crew_name: str
    color_index: int
    stops: list[Stop]
    path: list[Point]
    total_travel_minutes: float
    total_repair_minutes: float
    shift_used_minutes: float
    shift_remaining_minutes: float


class Plan(_M):
    algorithm: str
    generated_at: datetime
    crew_count: int
    routes: list[Route]
    unassigned_pothole_ids: list[str]


class Comparison(_M):
    crew_count: int
    greedy: dict
    fcfs: dict
    improvement: dict
