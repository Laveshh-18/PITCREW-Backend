from .constants import HIGH_SEVERITY_THRESHOLD, SCHOOL_ZONE_RADIUS_M
from .geo import haversine_m
from .models import Comparison, Plan, POI, Pothole


def _metrics(plan: Plan, open_p: list[Pothole], schools: list[POI]) -> dict:
    assigned, finish = set(), {}
    for r in plan.routes:
        for s in r.stops:
            assigned.add(s.pothole_id)
            finish[s.pothole_id] = s.finish_at_minute
    shift = max((r.shift_used_minutes + r.shift_remaining_minutes for r in plan.routes), default=0)
    high = [p for p in open_p if p.severity >= HIGH_SEVERITY_THRESHOLD]
    zone = [p for p in high if any(haversine_m(p.lat, p.lng, s.lat, s.lng) <= SCHOOL_ZONE_RADIUS_M for s in schools)]
    total_sev = sum(p.severity for p in open_p)
    waits = [finish.get(p.id, shift) for p in high]
    return {
        "fixed_total": len(assigned),
        "fixed_high_severity": sum(1 for p in high if p.id in assigned),
        "high_severity_total": len(high),
        "fixed_school_zone_high_severity": sum(1 for p in zone if p.id in assigned),
        "school_zone_high_severity_total": len(zone),
        "severity_weighted_coverage": round(sum(p.severity for p in open_p if p.id in assigned) / total_sev, 3) if total_sev else 0.0,
        "total_travel_minutes": round(sum(r.total_travel_minutes for r in plan.routes), 1),
        "avg_wait_high_severity_minutes": round(sum(waits) / len(waits), 1) if waits else 0.0,
    }


def _pct(fcfs: float, greedy: float) -> float:
    return round((fcfs - greedy) / fcfs * 100, 1) if fcfs else 0.0


def compare(greedy: Plan, fcfs: Plan, potholes: list[Pothole], pois: list[POI]) -> Comparison:
    open_p = [p for p in potholes if p.status == "open"]
    schools = [p for p in pois if p.type == "school"]
    g, f = _metrics(greedy, open_p, schools), _metrics(fcfs, open_p, schools)
    return Comparison(crew_count=greedy.crew_count, greedy=g, fcfs=f, improvement={
        "fixed_high_severity_delta": g["fixed_high_severity"] - f["fixed_high_severity"],
        "fixed_school_zone_high_severity_delta": g["fixed_school_zone_high_severity"] - f["fixed_school_zone_high_severity"],
        "coverage_delta_points": round((g["severity_weighted_coverage"] - f["severity_weighted_coverage"]) * 100, 1),
        "travel_reduction_pct": _pct(f["total_travel_minutes"], g["total_travel_minutes"]),
        "avg_wait_reduction_pct": _pct(f["avg_wait_high_severity_minutes"], g["avg_wait_high_severity_minutes"]),
    })
