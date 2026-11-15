"""Image validation and normalisation for uploaded photos.

- The file type is decided by decoding the image, never by the filename or the
  browser-supplied content type.
- Orientation from EXIF is applied, then all metadata (including GPS location) is
  dropped by re-encoding.
- Images are resized to at most MAX_EDGE pixels and stored as JPEG, with a thumbnail.
"""

import hashlib
import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.errors import AppError

MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MAX_EDGE = 1920
THUMB_EDGE = 400
# MPO: multi-picture JPEG produced by some phone cameras.
ALLOWED_FORMATS = frozenset({"JPEG", "PNG", "WEBP", "MPO"})
# Decompression-bomb guard: ~50 megapixels is far above any phone camera output.
Image.MAX_IMAGE_PIXELS = 50_000_000


class InvalidUploadError(AppError):
    status_code = 422
    code = "invalid_upload"


class UploadTooLargeError(AppError):
    status_code = 413
    code = "upload_too_large"


@dataclass(frozen=True)
class ProcessedImage:
    data: bytes
    thumbnail: bytes
    width: int
    height: int
    sha256: str
    content_type: str = "image/jpeg"


def _encode(image: Image.Image, edge: int, quality: int) -> tuple[bytes, int, int]:
    copy = image.copy()
    copy.thumbnail((edge, edge), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    copy.save(buffer, format="JPEG", quality=quality, optimize=True, progressive=True)
    return buffer.getvalue(), copy.width, copy.height


def process_photo(raw: bytes) -> ProcessedImage:
    if len(raw) > MAX_UPLOAD_BYTES:
        raise UploadTooLargeError(f"Photos must be under {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    if not raw:
        raise InvalidUploadError("The file is empty.")
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            fmt = probe.format
            probe.verify()
        if fmt not in ALLOWED_FORMATS:
            raise InvalidUploadError("Upload a JPEG, PNG or WebP photo.")
        with Image.open(io.BytesIO(raw)) as img:
            img.load()
            upright = ImageOps.exif_transpose(img)
            rgb = upright.convert("RGB")
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError) as exc:
        raise InvalidUploadError("This file is not a valid photo.") from exc

    data, width, height = _encode(rgb, MAX_EDGE, 82)
    thumb, _, _ = _encode(rgb, THUMB_EDGE, 75)
    return ProcessedImage(
        data=data,
        thumbnail=thumb,
        width=width,
        height=height,
        sha256=hashlib.sha256(data).hexdigest(),
    )
