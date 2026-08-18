"""HWPX validation and PDF-rendering converter."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from app.documents.common import DocumentFormat
from app.documents.conversion.engines import RhwpEngine
from app.documents.hwpx import HwpxDocument


class HwpxToPdfConverter:
    """Validate HWPX and render it with rhwp."""

    source_format = DocumentFormat.HWPX
    target_format = DocumentFormat.PDF

    def __init__(
        self,
        executable: str | Path = "rhwp",
        *,
        timeout_seconds: int = 120,
        engine: RhwpEngine | None = None,
    ):
        self.engine = engine or RhwpEngine(
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
        HwpxDocument(source)
        return self.engine.export_pdf(source, destination)


__all__ = ["HwpxToPdfConverter"]
