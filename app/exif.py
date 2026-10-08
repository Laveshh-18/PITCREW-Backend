"""EXIF extraction from the ORIGINAL upload (before re-encoding). Values are never stored or logged."""
from datetime import datetime, timedelta, timezone

from PIL import Image

IST = timezone(timedelta(hours=5, minutes=30))
_GPS_IFD, _EXIF_IFD = 0x8825, 0x8769
_DTO, _OFFSET_DTO = 36867, 36881


def _deg(dms, ref) -> float | None:
    try:
        d, m, s = (float(x) for x in dms)
        val = d + m / 60 + s / 3600
        return -val if ref in ("S", "W") else val
    except Exception:
        return None


def _parse_offset(v) -> timezone | None:
    try:
        sign = -1 if v.startswith("-") else 1
        hh, mm = v.lstrip("+-").split(":")
        return timezone(sign * timedelta(hours=int(hh), minutes=int(mm)))
    except Exception:
        return None


def extract_exif(img: Image.Image) -> tuple:
    """Returns (exif_lat, exif_lng, taken_at_utc). Any of them may be None; that is normal."""
    lat = lng = taken = None
    try:
        exif = img.getexif()
        if not exif:
            return None, None, None
        try:
            gps = exif.get_ifd(_GPS_IFD)
        except Exception:
            gps = {}
        if gps and 2 in gps and 4 in gps:
            lat, lng = _deg(gps[2], gps.get(1)), _deg(gps[4], gps.get(3))
            if lat is None or lng is None or not (-90 <= lat <= 90 and -180 <= lng <= 180) \
                    or (lat == 0 and lng == 0):
                lat = lng = None
        try:
            sub = exif.get_ifd(_EXIF_IFD)
        except Exception:
            sub = {}
        raw = sub.get(_DTO) or exif.get(306)
        if raw:
            naive = datetime.strptime(str(raw).strip(), "%Y:%m:%d %H:%M:%S")
            tz = _parse_offset(str(sub.get(_OFFSET_DTO, ""))) or IST  # no tz info -> India time
            taken = naive.replace(tzinfo=tz).astimezone(timezone.utc)
    except Exception:
        pass
    return lat, lng, taken
