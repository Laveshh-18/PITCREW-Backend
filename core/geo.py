import math
from .constants import DETOUR_FACTOR, TRAVEL_SPEED_KMH


def haversine_m(a_lat, a_lng, b_lat, b_lng) -> float:
    r = 6371000.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lng - a_lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def travel_minutes(a_lat, a_lng, b_lat, b_lng) -> float:
    return haversine_m(a_lat, a_lng, b_lat, b_lng) * DETOUR_FACTOR / (TRAVEL_SPEED_KMH * 1000 / 60)


def point_in_polygon(lat: float, lng: float, boundary: list) -> bool:
    """Ray casting. boundary = [{"lat":..,"lng":..}, ...]"""
    inside = False
    j = len(boundary) - 1
    for i in range(len(boundary)):
        yi, xi = boundary[i]["lat"], boundary[i]["lng"]
        yj, xj = boundary[j]["lat"], boundary[j]["lng"]
        if (yi > lat) != (yj > lat) and lng < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside
