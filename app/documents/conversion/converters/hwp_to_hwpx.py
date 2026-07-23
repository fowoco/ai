"""HWP 5.x to HWPX conversion."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from app.documents.common import DocumentFormat
from app.documents.conversion.engines import JavaHwp2HwpxEngine
from app.documents.conversion.errors import DocumentConversionError
from app.documents.hwp5 import Hwp5BinaryDocument
from app.documents.hwp5.editor import Hwp5Error


class HwpToHwpxConverter:
    """Delegate binary HWP conversion to the Java hwp2hwpx engine."""

    source_format = DocumentFormat.HWP
    target_format = DocumentFormat.HWPX

    def __init__(
        self,
        executable: str | Path = "java",
        *,
        timeout_seconds: int = 120,
        engine: JavaHwp2HwpxEngine | None = None,
    ):
        self.engine = engine or JavaHwp2HwpxEngine(
            str(executable),
            timeout_seconds,
        )

    def require_available(self) -> Path:
        return self.engine.require_available()

    def convert(
        self,
        source: Path,
        destination: Path,
        *,
        options: Mapping[str, object] | None = None,
    ) -> Path:
        del options
        try:
            Hwp5BinaryDocument(source)
        except (Hwp5Error, OSError) as exc:
            raise DocumentConversionError("invalid HWP 5.x input") from exc
        return self.engine.convert(source, destination)


__all__ = ["HwpToHwpxConverter"]
