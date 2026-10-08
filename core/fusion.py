from .constants import (POI_INFLUENCE_RADIUS_M, REPAIR_MINUTES, UNVERIFIED_PHOTO_WEIGHT_FACTOR)
from . import config as cfg
from .geo import haversine_m
from .models import Complaint, POI, Pothole, PotholeScores, SensorEvent
from .severity import bucket_for, score_text

ROAD_SCORE = {"main": 1.0, "secondary": 0.6, "lane": 0.3}
FLAGGED = ("mismatch", "duplicate")


def recompute_pothole(pothole: Pothole, complaints: list[Complaint], sensor_events: list[SensorEvent],
                      pois: list[POI]) -> PotholeScores:
    reasons: list[str] = []

    # ---- text signal (every complaint's text counts, even with a flagged photo)
    text_best = None
    for c in complaints:
        ts = score_text(c.text)
        value = c.text_score if c.text_score is not None else ts.score
        text_best = value if text_best is None else max(text_best, value)
        for r in ts.reasons:
            if r not in reasons:
                reasons.append(r)

    # ---- photo signal: verified preferred, else unverified at reduced weight
    photo_best, photo_weight = None, 0.0
    for status, w in (("verified", cfg.BLEND_WEIGHTS["photo"]),
                      ("unverified", cfg.BLEND_WEIGHTS["photo"] * UNVERIFIED_PHOTO_WEIGHT_FACTOR)):
        scores = [c.photo_score for c in complaints if c.photo_verification == status and c.photo_score is not None]
        if scores:
            photo_best, photo_weight = max(scores), w
            break

    # ---- sensor signal
    sensor_best = max((e.sensor_score for e in sensor_events), default=None)
    if sensor_best is not None:
        reasons.append("strong jolt detected by sensor" if sensor_best >= 0.6 else "jolt detected by sensor")

    parts = []  # (value, weight)
    if text_best is not None:
        parts.append((text_best, cfg.BLEND_WEIGHTS["text"]))
    if photo_best is not None:
        parts.append((photo_best, photo_weight))
    if sensor_best is not None:
        parts.append((sensor_best, cfg.BLEND_WEIGHTS["sensor"]))
    wsum = sum(w for _, w in parts)
    severity = round(sum(v * w for v, w in parts) / wsum, 3) if wsum else 0.0

    if any(c.photo_verification == "verified" for c in complaints):
        reasons.append("photo location verified")
    if any(c.photo_verification in FLAGGED for c in complaints):
        reasons.append("photo location does not match report")

    # ---- counts
    complaint_count = len(complaints)
    sensor_count = len(sensor_events)
    devices = {e.device_id for e in sensor_events}
    confirmation = sum(1 for c in complaints if c.photo_verification not in FLAGGED) + len(devices)

    # ---- exposure
    ex_reasons = []
    poi_score, nearest = 0.0, None
    for p in pois:
        d = haversine_m(pothole.lat, pothole.lng, p.lat, p.lng)
        s = max(0.0, 1 - d / POI_INFLUENCE_RADIUS_M)
        if s > poi_score:
            poi_score, nearest = s, (p, d)
    if nearest and poi_score > 0:
        ex_reasons.append(f"{nearest[0].type} within {int(round(nearest[1]))} m")
    road_score = ROAD_SCORE.get(pothole.road_class, 0.6)
    if pothole.road_class == "main":
        ex_reasons.append("main road")
    elif pothole.road_class == "lane":
        ex_reasons.append("lane (low traffic)")
    conf_score = min(1.0, confirmation / 5)
    if confirmation >= 2:
        ex_reasons.append(f"{confirmation} confirmations")
    exposure = round(0.4 * poi_score + 0.3 * road_score + 0.3 * conf_score, 3)

    bucket = bucket_for(severity)
    source = "both" if complaint_count and sensor_count else ("sensor" if sensor_count else "complaint")
    return PotholeScores(severity=severity, severity_bucket=bucket, severity_reasons=reasons,
                         exposure=exposure, exposure_reasons=ex_reasons, complaint_count=complaint_count,
                         sensor_event_count=sensor_count, confirmation_count=confirmation,
                         repair_minutes=REPAIR_MINUTES[bucket], source=source)
