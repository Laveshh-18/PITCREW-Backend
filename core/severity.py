from .constants import BUCKET_LOWER, GRAVITY_MS2
from . import config as cfg
from .models import SignalScore


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def score_text(text: str) -> SignalScore:
    t = " " + (text or "").lower() + " "
    total, reasons = 0.0, []
    for reason, weight, patterns in cfg.KEYWORDS:
        if any(p in t for p in patterns):
            total += weight
            reasons.append(reason)
    return SignalScore(score=round(min(1.0, max(0.0, cfg.TEXT_BASE + total)), 3), reasons=reasons)


def score_photo(image_bytes: bytes | None) -> SignalScore | None:
    if not image_bytes:
        return None
    try:
        import cv2
        import numpy as np
        img = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        if img is None:
            return None
        h, w = img.shape
        centre = img[h // 4: 3 * h // 4, w // 4: 3 * w // 4]
        if centre.size == 0:
            return None
        dark_ratio = float((centre < cfg.PHOTO_DARK_THRESHOLD).mean())
        score = round(_clamp(dark_ratio / cfg.PHOTO_DARK_DIVISOR, 0, 1), 3)
        return SignalScore(score=score, reasons=["large dark area in photo"] if score >= 0.6 else [])
    except Exception:
        return None


def score_sensor(peak_z_deviation: float, duration_ms: int, speed_kmh: float) -> SignalScore:
    speed_factor = _clamp(30 / max(speed_kmh, 10), 0.5, 2.0)
    score = round(_clamp(peak_z_deviation / cfg.SENSOR_Z_DIVISOR * speed_factor, 0, 1), 3)
    reasons = ["strong jolt detected by sensor"] if score >= 0.6 else ["jolt detected by sensor"]
    return SignalScore(score=score, reasons=reasons)


def bucket_for(severity: float) -> str:
    if severity >= BUCKET_LOWER["critical"]:
        return "critical"
    if severity >= BUCKET_LOWER["high"]:
        return "high"
    if severity >= BUCKET_LOWER["medium"]:
        return "medium"
    return "low"
