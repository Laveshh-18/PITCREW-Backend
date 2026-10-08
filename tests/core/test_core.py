from datetime import datetime, timedelta, timezone

from core.compare import compare
from core.fusion import recompute_pothole
from core.models import POI, Complaint, Crew, KnownPhotoHash, Pothole, SensorEvent
from core.priority import rank_queue
from core.scheduler import fcfs_plan, plan_day
from core.severity import bucket_for, score_sensor, score_text
from core.verification import verify_photo_metadata

NOW = datetime(2026, 10, 8, 9, 30, tzinfo=timezone.utc)
LAT, LNG = 26.9124, 75.7873


def _verify(**kw):
    base = dict(has_photo=True, submitted_lat=LAT, submitted_lng=LNG, gps_accuracy_m=None, exif_lat=LAT,
                exif_lng=LNG, taken_at=NOW - timedelta(minutes=5), now=NOW, phash=None, known_hashes=[])
    base.update(kw)
    return verify_photo_metadata(**base)


def test_buckets():
    assert [bucket_for(x) for x in (0.1, 0.35, 0.6, 0.8, 1.0)] == ["low", "medium", "high", "critical", "critical"]


def test_text_score_and_reasons():
    s = score_text("Huge deep crater, bike skidded")
    assert s.score >= 0.8 and "deep" in s.reasons and "crater" in s.reasons
    assert score_text("small crack").score == 0.1
    assert 0 <= score_text("x" * 5).score <= 1


def test_sensor_speed_factor():
    slow = score_sensor(5, 100, 10).score
    fast = score_sensor(5, 100, 60).score
    assert slow > fast


def test_verification_statuses():
    assert _verify(has_photo=False).status == "none"
    assert _verify().status == "verified"
    assert _verify(exif_lat=None, exif_lng=None, taken_at=None).status == "unverified"
    assert _verify(exif_lat=LAT + 0.01).status == "mismatch"                      # ~1.1 km away
    assert _verify(taken_at=NOW - timedelta(days=10)).status == "mismatch"        # stale
    assert _verify(taken_at=NOW + timedelta(hours=1)).status == "mismatch"        # future
    assert _verify(exif_lat=LAT + 0.0018).status == "unverified"                  # ~200 m, between limits
    assert _verify(taken_at=NOW - timedelta(days=2)).status == "unverified"       # 24 h .. 7 d


def test_gps_accuracy_widens_allowed_distance():
    far = LAT + 0.0018  # ~200 m
    assert _verify(exif_lat=far).status == "unverified"
    assert _verify(exif_lat=far, gps_accuracy_m=250).status == "verified"


def test_duplicate_far_vs_near():
    known = [KnownPhotoHash(phash=12345, lat=LAT + 0.05, lng=LNG)]
    assert _verify(phash=12345, known_hashes=known).status == "duplicate"
    near = [KnownPhotoHash(phash=12345, lat=LAT, lng=LNG)]
    assert _verify(phash=12345, known_hashes=near).status == "verified"           # same spot is legitimate


def _pothole(i, lat, lng, sev, hours_old=1, status="open", repair=25):
    return Pothole(id=f"p{i:03d}", lat=lat, lng=lng, severity=sev, exposure=0.5, repair_minutes=repair,
                   status=status, first_reported_at=NOW - timedelta(hours=hours_old))


def _crews(n=2):
    return [Crew(id=f"crew-{c}", name=f"Crew {c}", color_index=i, depot_lat=LAT, depot_lng=LNG + i * 0.01,
                 current_lat=LAT, current_lng=LNG + i * 0.01) for i, c in enumerate("abc"[:n])]


def _field(n=60):
    return [_pothole(i, LAT + (i % 8) * 0.004, LNG + (i // 8) * 0.004, round(0.2 + (i * 7 % 10) / 12, 3),
                     hours_old=i * 3 + 1) for i in range(n)]


def test_scheduler_no_double_assignment_and_capacity():
    plan = plan_day(_field(), _crews(2), NOW)
    ids = [s.pothole_id for r in plan.routes for s in r.stops]
    assert len(ids) == len(set(ids))
    for r in plan.routes:
        assert r.shift_used_minutes <= 480
    assert len(ids) < 60 and len(plan.unassigned_pothole_ids) == 60 - len(ids)


def test_deterministic():
    a = plan_day(_field(), _crews(2), NOW).model_dump()
    b = plan_day(_field(), _crews(2), NOW).model_dump()
    assert a == b


def test_fcfs_orders_by_age_and_compare_runs():
    field, crews = _field(), _crews(2)
    f = fcfs_plan(field, crews, NOW)
    first = f.routes[0].stops[0].pothole_id
    assert first in {p.id for p in sorted(field, key=lambda p: p.first_reported_at)[:3]}
    cmp = compare(plan_day(field, crews, NOW), f, field, [POI(id="s", type="school", lat=LAT, lng=LNG)])
    assert cmp.greedy["fixed_total"] > 0 and "avg_wait_reduction_pct" in cmp.improvement


def test_queue_sorted_desc():
    q = rank_queue(_field(), _crews(2), NOW)
    assert [i.priority for i in q] == sorted((i.priority for i in q), reverse=True)
    assert q[0].rank == 1 and q[0].nearest_crew_id


def test_fusion_confirmations_and_flagged_photos():
    p = _pothole(1, LAT, LNG, 0)
    cs = [Complaint(id="c1", text="deep crater", lat=LAT, lng=LNG, text_score=0.9, photo_score=0.8,
                    photo_verification="verified"),
          Complaint(id="c2", text="big hole", lat=LAT, lng=LNG, text_score=0.5, photo_score=0.9,
                    photo_verification="mismatch")]
    ss = [SensorEvent(id=f"s{i}", device_id=f"d{i % 2}", lat=LAT, lng=LNG, peak_z_deviation=6, duration_ms=100,
                      speed_kmh=30, recorded_at=NOW, sensor_score=0.5) for i in range(3)]
    out = recompute_pothole(p, cs, ss, [POI(id="h", type="hospital", lat=LAT, lng=LNG)])
    assert out.confirmation_count == 1 + 2          # one unflagged complaint + two distinct devices
    assert out.source == "both" and out.sensor_event_count == 3
    assert "photo location does not match report" in out.severity_reasons
    assert 0 <= out.severity <= 1 and 0 <= out.exposure <= 1
