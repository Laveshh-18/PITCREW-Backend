from datetime import datetime, timezone
from .constants import (AGING_BONUS_CAP, AGING_BONUS_PER_DAY, FACTOR_FLOOR, PROXIMITY_HORIZON_MIN)
from .geo import travel_minutes
from .models import Crew, Pothole, QueueItem


def proximity_for(travel_min: float) -> float:
    return max(FACTOR_FLOOR, 1 - travel_min / PROXIMITY_HORIZON_MIN)


def aging_multiplier(pothole: Pothole, now: datetime) -> float:
    first = pothole.first_reported_at
    if first.tzinfo is None:
        first = first.replace(tzinfo=timezone.utc)
    days = max(0.0, (now - first).total_seconds() / 86400)
    return 1 + min(AGING_BONUS_CAP, AGING_BONUS_PER_DAY * days)


def priority_value(severity: float, exposure: float, proximity: float, aging: float) -> float:
    return max(severity, FACTOR_FLOOR) * max(exposure, FACTOR_FLOOR) * max(proximity, FACTOR_FLOOR) * aging


def rank_queue(potholes: list[Pothole], crews: list[Crew], now: datetime) -> list[QueueItem]:
    rows = []
    for p in potholes:
        if p.status != "open":
            continue
        best_t, best_crew = None, None
        for c in crews:
            t = travel_minutes(c.current_lat, c.current_lng, p.lat, p.lng)
            if best_t is None or t < best_t:
                best_t, best_crew = t, c.id
        prox = proximity_for(best_t if best_t is not None else PROXIMITY_HORIZON_MIN)
        age = aging_multiplier(p, now)
        rows.append((priority_value(p.severity, p.exposure, prox, age), prox, age, best_crew, p))
    rows.sort(key=lambda r: (-r[0], -r[4].severity, r[4].first_reported_at, r[4].id))
    return [QueueItem(rank=i + 1, pothole=p, severity=p.severity, exposure=p.exposure,
                      proximity=round(prox, 3), aging_multiplier=round(age, 3),
                      priority=round(pr, 3), nearest_crew_id=cid)
            for i, (pr, prox, age, cid, p) in enumerate(rows)]
