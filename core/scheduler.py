from datetime import datetime
from typing import Callable
from .geo import travel_minutes
from .models import Crew, Plan, Point, Pothole, Route, Stop
from .priority import aging_multiplier, priority_value, proximity_for


def _run(potholes: list[Pothole], crews: list[Crew], now: datetime, algorithm: str,
         choose: Callable) -> Plan:
    open_p = [p for p in potholes if p.status == "open"]
    state = [{"crew": c, "lat": c.current_lat, "lng": c.current_lng,
              "clock": float(c.minutes_used), "done": False,
              "stops": [], "path": [Point(lat=c.current_lat, lng=c.current_lng)],
              "travel": 0.0, "repair": 0.0} for c in crews]
    assigned: set[str] = set()
    while True:
        active = [s for s in state if not s["done"]]
        if not active:
            break
        s = min(active, key=lambda x: (x["clock"], x["crew"].id))
        cands = []
        for p in open_p:
            if p.id in assigned:
                continue
            t = travel_minutes(s["lat"], s["lng"], p.lat, p.lng)
            if s["clock"] + t + p.repair_minutes <= s["crew"].shift_minutes:
                prox = proximity_for(t)
                age = aging_multiplier(p, now)
                cands.append((p, t, prox, age, priority_value(p.severity, p.exposure, prox, age)))
        if not cands:
            s["done"] = True
            continue
        p, t, prox, age, pr = choose(cands)
        arrive = s["clock"] + t
        finish = arrive + p.repair_minutes
        s["stops"].append(Stop(sequence=len(s["stops"]) + 1, pothole_id=p.id, lat=p.lat, lng=p.lng,
                               travel_minutes=round(t, 1), repair_minutes=p.repair_minutes,
                               arrive_at_minute=round(arrive, 1), finish_at_minute=round(finish, 1),
                               severity=p.severity, exposure=p.exposure, proximity=round(prox, 3),
                               aging_multiplier=round(age, 3), priority=round(pr, 3)))
        s["path"].append(Point(lat=p.lat, lng=p.lng))
        s["travel"] += t
        s["repair"] += p.repair_minutes
        s["clock"] = finish
        s["lat"], s["lng"] = p.lat, p.lng
        assigned.add(p.id)
    routes = [Route(crew_id=s["crew"].id, crew_name=s["crew"].name, color_index=s["crew"].color_index,
                    stops=s["stops"], path=s["path"], total_travel_minutes=round(s["travel"], 1),
                    total_repair_minutes=round(s["repair"], 1), shift_used_minutes=round(s["clock"], 1),
                    shift_remaining_minutes=round(s["crew"].shift_minutes - s["clock"], 1))
              for s in state]
    return Plan(algorithm=algorithm, generated_at=now, crew_count=len(crews), routes=routes,
                unassigned_pothole_ids=[p.id for p in open_p if p.id not in assigned])


def _greedy_choose(cands):
    # max priority; tie: higher severity, earlier first_reported_at, smaller id
    return min(cands, key=lambda c: (-c[4], -c[0].severity, c[0].first_reported_at, c[0].id))


def plan_day(potholes: list[Pothole], crews: list[Crew], now: datetime) -> Plan:
    return _run(potholes, crews, now, "greedy", _greedy_choose)


def fcfs_plan(potholes: list[Pothole], crews: list[Crew], now: datetime) -> Plan:
    return _run(potholes, crews, now, "fcfs", lambda cands: min(cands, key=lambda c: (c[0].first_reported_at, c[0].id)))
