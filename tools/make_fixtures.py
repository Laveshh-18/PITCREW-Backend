"""Generates deterministic demo fixtures into backend/fixtures/ (SYNTHETIC DATA).
Lavesh can replace these files with his own; the seed loader only needs the same JSON shape.
Usage: python tools/make_fixtures.py"""
import json
import os
import random
import uuid

NS = uuid.UUID("0b7a1f3e-5c1d-4f6a-9b0e-2f7c1d9a3e44")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")
rng = random.Random(42)

LAT0, LNG0, DLAT, DLNG = 26.905, 75.780, 0.0135, 0.0151  # three adjacent ~1.5 km wards, Jaipur


def box(r, c, n):
    la0, ln0 = LAT0 + r * DLAT, LNG0 + c * DLNG
    la1, ln1 = la0 + DLAT, ln0 + DLNG
    return {"id": f"ward-{n}", "name": f"Ward {n}", "center_lat": round((la0 + la1) / 2, 6),
            "center_lng": round((ln0 + ln1) / 2, 6),
            "boundary": [{"lat": la0, "lng": ln0}, {"lat": la1, "lng": ln0},
                         {"lat": la1, "lng": ln1}, {"lat": la0, "lng": ln1}],
            "_box": (la0, la1, ln0, ln1)}


wards = [box(0, 0, 1), box(0, 1, 2), box(1, 0, 3)]


def rand_in(w, margin=0.0008):
    la0, la1, ln0, ln1 = w["_box"]
    return (round(rng.uniform(la0 + margin, la1 - margin), 6), round(rng.uniform(ln0 + margin, ln1 - margin), 6))


def offset(lat, lng, metres):  # small offset used to place a pothole near a POI
    return round(lat + metres / 111000, 6), round(lng + metres / 99000, 6)


pois = []
for i, (t, nm) in enumerate([("school", "Govt Sr. Sec. School"), ("school", "Adarsh Vidya Mandir"),
                             ("school", "St. Xavier's Public School"), ("school", "Saraswati Shishu Mandir"),
                             ("hospital", "City Care Hospital"), ("hospital", "Community Health Centre")]):
    w = wards[i % 3]
    la, ln = rand_in(w, 0.003)
    pois.append({"id": str(uuid.uuid5(NS, f"poi{i}")), "type": t, "name": nm, "lat": la, "lng": ln, "ward_id": w["id"]})

crews = [{"id": f"crew-{x}", "name": f"Crew {x.upper()}", "color_index": i, "shift_minutes": 480,
          "depot_lat": wards[i]["center_lat"], "depot_lng": wards[i]["center_lng"]}
         for i, x in enumerate("abc")]

HIGH = ["Huge deep crater near school gate, a bike skidded and rider injured", "Very dangerous big pothole, accident at night",
        "Deep waterlogged pothole, tyre burst, dangerous for children", "gehra gadda, bada khatarnak, accident ho gaya",
        "Large crater on main road, scooter fell, very dangerous"]
MED = ["Big pothole on the road, vehicles slow down", "Deep pothole after rain, water collects here",
       "pothole bada hai, raat me dikhta nahi", "Road damaged, large hole near the turn"]
LOW = ["Small crack on the road surface", "Minor pothole near the shop", "chota gaddha sadak par",
       "Some road damage near the lane entrance"]

status_plan = (["verified"] * 10 + ["unverified"] * 5 + ["mismatch"] * 2 + ["duplicate"])
rng.shuffle(status_plan)
complaints = []
n_high_target = 13  # about 25% high/critical near POIs
for i in range(50):
    if i < n_high_target:
        p = pois[i % len(pois)]
        la, ln = offset(p["lat"], p["lng"], rng.uniform(15, 140) * rng.choice([-1, 1]))
        text, road = rng.choice(HIGH), rng.choice(["main", "secondary"])
    else:
        w = rng.choice(wards)
        la, ln = rand_in(w)
        text = rng.choice(MED + LOW + LOW)
        road = rng.choice(["main", "secondary", "secondary", "lane"])
    if i in (20, 21, 22):  # three complaints pile up at one spot -> fused into 1 pothole
        la, ln = complaints[19]["lat"] + 0.00005 * (i - 19), complaints[19]["lng"]
    st = status_plan.pop() if ((i % 3 == 0 or i == 49) and status_plan) else "none"
    complaints.append({
        "client_request_id": str(uuid.uuid5(NS, f"complaint{i}")), "text": text, "lat": la, "lng": ln,
        "road_class": road, "hours_ago": round(rng.uniform(1, 14 * 24), 1),
        "photo_verification": st, "photo_score": round(rng.uniform(0.2, 0.9), 3) if st != "none" else None})

sensors = []
for i in range(6):
    if i < 2:  # fused with an existing complaint (within 20 m)
        c = complaints[5 + i * 7]
        la, ln = offset(c["lat"], c["lng"], 6)
    else:      # sensor-only: nobody reported these
        la, ln = rand_in(rng.choice(wards))
    sensors.append({"client_event_id": str(uuid.uuid5(NS, f"sensor{i}")), "device_id": str(uuid.uuid5(NS, f"device{i % 3}")),
                    "lat": la, "lng": ln, "peak_z_deviation": round(rng.uniform(4.0, 9.0), 2),
                    "duration_ms": rng.randint(80, 400), "speed_kmh": round(rng.uniform(15, 45), 1),
                    "hours_ago": round(rng.uniform(1, 72), 1)})

for w in wards:
    w.pop("_box")
os.makedirs(OUT, exist_ok=True)
for name, data in (("wards.json", wards), ("pois.json", pois), ("crews.json", crews),
                   ("complaints_seed_50.json", complaints), ("sensor_events_seed.json", sensors)):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
print("wrote fixtures to", OUT)
