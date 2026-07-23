"""Safe raster preparation for embedded HWP images."""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover
    Image = None
    ImageOps = None


MAX_SOURCE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000


@dataclass(frozen=True)
class PreparedImage:
    data: bytes
    extension: str
    width: int
    height: int


def prepare_image(
    source_path: str | Path,
    *,
    kind: str = "image",
    target_width_mm: float,
    target_height_mm: float,
    dpi: int = 200,
    extension: str | None = None,
) -> PreparedImage:
    """Validate, orient, resize and encode a signature/photo/image."""

    if Image is None or ImageOps is None:
        raise ImportError("Pillow is required for image fields")
    source = Path(source_path)
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError(f"image exceeds {MAX_SOURCE_BYTES} bytes")
    if target_width_mm <= 0 or target_height_mm <= 0:
        raise ValueError("target image dimensions must be positive")
    if kind not in {"image", "photo", "signature"}:
        raise ValueError(f"unsupported image kind: {kind}")

    target_size = (
        max(1, round(target_width_mm / 25.4 * dpi)),
        max(1, round(target_height_mm / 25.4 * dpi)),
    )
    if target_size[0] * target_size[1] > MAX_IMAGE_PIXELS:
        raise ValueError(f"target image exceeds {MAX_IMAGE_PIXELS} pixels")
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    with Image.open(source) as opened:
        if opened.width * opened.height > MAX_IMAGE_PIXELS:
            raise ValueError(f"image exceeds {MAX_IMAGE_PIXELS} pixels")
        opened.verify()
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened)
        image.load()
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise ValueError(f"image exceeds {MAX_IMAGE_PIXELS} pixels")

        if kind == "photo":
            prepared = ImageOps.fit(
                image.convert("RGB"), target_size, method=Image.Resampling.LANCZOS
            )
            output_extension = extension or "jpg"
        else:
            rgba = image.convert("RGBA")
            rgba.thumbnail(target_size, Image.Resampling.LANCZOS)
            prepared = Image.new("RGBA", target_size, (255, 255, 255, 0))
            offset = (
                (target_size[0] - rgba.width) // 2,
                (target_size[1] - rgba.height) // 2,
            )
            prepared.alpha_composite(rgba, offset)
            output_extension = extension or "png"

        output_extension = output_extension.casefold().lstrip(".")
        output = io.BytesIO()
        if output_extension in {"jpg", "jpeg"}:
            prepared.convert("RGB").save(
                output, format="JPEG", quality=92, optimize=True, progressive=False
            )
            output_extension = "jpg"
        elif output_extension == "bmp":
            prepared.convert("RGB").save(output, format="BMP")
        elif output_extension == "png":
            prepared.save(output, format="PNG", optimize=True)
        else:
            raise ValueError(f"unsupported embedded image extension: {output_extension}")

    return PreparedImage(output.getvalue(), output_extension, *target_size)


__all__ = ["PreparedImage", "prepare_image"]
