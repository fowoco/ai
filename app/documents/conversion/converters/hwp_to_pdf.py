"""HWP 5.x validation and direct PDF rendering."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from app.documents.common import DocumentFormat
from app.documents.conversion.engines import LibreOfficeEngine
from app.documents.conversion.errors import DocumentConversionError
from app.documents.hwp5 import Hwp5BinaryDocument
from app.documents.hwp5.editor import Hwp5Error


class HwpToPdfConverter:
    """Validate binary HWP and render it directly with LibreOffice."""

    source_format = DocumentFormat.HWP
    target_format = DocumentFormat.PDF

    def __init__(
        self,
        executable: str | Path = "soffice",
        *,
        timeout_seconds: int = 120,
        engine: LibreOfficeEngine | None = None,
    ):
        self.engine = engine or LibreOfficeEngine(
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
        return self.engine.export_pdf(
            source,
            destination,
            input_filter="Hwp2002_File",
        )


__all__ = ["HwpToPdfConverter"]
