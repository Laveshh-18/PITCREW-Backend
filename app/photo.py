"""Photo pipeline (Constitution 8.5). CPU work: call through run_in_threadpool."""
import io
from dataclasses import dataclass
from datetime import datetime

from PIL import Image, ImageOps

from app.errors import ApiError
from app.exif import extract_exif
from core.constants import MAX_IMAGE_PIXELS, MAX_PHOTO_MB
from core.severity import score_photo
from core.verification import compute_phash

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
MAX_BYTES = MAX_PHOTO_MB * 1024 * 1024


@dataclass
class ProcessedPhoto:
    jpeg: bytes
    exif_lat: float | None
    exif_lng: float | None
    taken_at: datetime | None
    phash: int | None
    photo_score: float | None


def detect_type(data: bytes) -> str | None:
    """Magic bytes, never the file extension or Content-Type."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def process_photo(data: bytes) -> ProcessedPhoto:
    kind = detect_type(data)
    if kind is None:
        raise ApiError(415, "UNSUPPORTED_MEDIA_TYPE", "only jpeg, png and webp images are accepted")
    try:
        img = Image.open(io.BytesIO(data))
        if img.width * img.height > MAX_IMAGE_PIXELS:
            raise ApiError(422, "INVALID_IMAGE", "image is too large in pixels")
        img.load()
        exif_lat, exif_lng, taken_at = extract_exif(img)          # step 4: from the original
        img = ImageOps.exif_transpose(img)                         # step 5: orientation
        img = img.convert("RGB")
        img.thumbnail((1024, 1024))                                # step 6: resize ...
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)                   # ... and fresh JPEG: no EXIF, no hidden payload
        jpeg = buf.getvalue()
    except ApiError:
        raise
    except Exception:  # corrupt file, decompression bomb, re-encode failure
        raise ApiError(422, "INVALID_IMAGE", "image could not be processed")
    # dHash and photo score on the oriented, resized JPEG (a 9x8 hash is size-invariant)
    try:
        phash = compute_phash(jpeg)
    except Exception:
        phash = None
    sc = score_photo(jpeg)
    return ProcessedPhoto(jpeg, exif_lat, exif_lng, taken_at, phash, sc.score if sc else None)
