from datetime import datetime, timedelta, timezone
from .constants import (GPS_ACCURACY_CAP_M, PHOTO_DUPLICATE_HAMMING_MAX, PHOTO_MAX_AGE_HOURS,
                        PHOTO_MISMATCH_DISTANCE_M, PHOTO_STALE_DAYS, PHOTO_VERIFY_MAX_DISTANCE_M)
from .geo import haversine_m
from .models import KnownPhotoHash, PhotoVerification


def compute_phash(image_bytes: bytes) -> int:
    """64-bit dHash (grayscale, 9x8, compare neighbours) as a signed int64."""
    import cv2
    import numpy as np
    img = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError("cannot decode image")
    small = cv2.resize(img, (9, 8), interpolation=cv2.INTER_AREA)
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    value = 0
    for b in bits:
        value = (value << 1) | int(b)
    return value - (1 << 64) if value >= (1 << 63) else value


def _hamming(a: int, b: int) -> int:
    return bin((a ^ b) & ((1 << 64) - 1)).count("1")


def verify_photo_metadata(*, has_photo: bool, submitted_lat: float, submitted_lng: float,
                          gps_accuracy_m: float | None, exif_lat: float | None, exif_lng: float | None,
                          taken_at: datetime | None, now: datetime, phash: int | None,
                          known_hashes: list[KnownPhotoHash]) -> PhotoVerification:
    if not has_photo:  # rule 1
        return PhotoVerification(status="none")
    allowed = max(PHOTO_VERIFY_MAX_DISTANCE_M, min(gps_accuracy_m or 0, GPS_ACCURACY_CAP_M))

    # rule 2: same picture reused far from where it was first reported
    if phash is not None:
        for k in known_hashes:
            if _hamming(phash, k.phash) <= PHOTO_DUPLICATE_HAMMING_MAX and \
                    haversine_m(submitted_lat, submitted_lng, k.lat, k.lng) > allowed:
                return PhotoVerification(status="duplicate",
                                         reasons=["photo was already used for a different location"])

    distance = None
    if exif_lat is not None and exif_lng is not None:
        distance = round(haversine_m(submitted_lat, submitted_lng, exif_lat, exif_lng), 1)
    age_hours = None
    if taken_at is not None:
        if taken_at.tzinfo is None:
            taken_at = taken_at.replace(tzinfo=timezone.utc)
        age_hours = round((now - taken_at).total_seconds() / 3600, 3)

    if distance is not None and distance > PHOTO_MISMATCH_DISTANCE_M:  # rule 3
        return PhotoVerification(status="mismatch", distance_m=distance, age_hours=age_hours,
                                 reasons=["photo location does not match report"])
    if taken_at is not None and (now - taken_at > timedelta(days=PHOTO_STALE_DAYS)
                                 or taken_at - now > timedelta(minutes=10)):  # rule 4
        return PhotoVerification(status="mismatch", distance_m=distance, age_hours=age_hours,
                                 reasons=["photo time does not match report"])
    if distance is not None and distance <= allowed and age_hours is not None \
            and age_hours <= PHOTO_MAX_AGE_HOURS:  # rule 5
        return PhotoVerification(status="verified", distance_m=distance, age_hours=age_hours,
                                 reasons=["photo location verified"])
    reasons = []  # rule 6
    if distance is None:
        reasons.append("photo has no location data")
    elif distance > allowed:
        reasons.append("photo location is a bit far from the report")
    if age_hours is None:
        reasons.append("photo has no timestamp")
    elif age_hours > PHOTO_MAX_AGE_HOURS:
        reasons.append("photo is more than a day old")
    return PhotoVerification(status="unverified", distance_m=distance, age_hours=age_hours, reasons=reasons)
