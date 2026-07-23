"""HWPX validation and PDF-rendering converter."""

from __future__ import annotations

import tempfile
from collections.abc import Mapping
from pathlib import Path

from app.documents.common import DocumentFormat
from app.documents.conversion.engines import LibreOfficeEngine
from app.documents.conversion.errors import DocumentConversionError
from app.documents.conversion.protocol import DocumentConverter
from app.documents.hwpx import HwpxDocument


class HwpxToPdfConverter:
    """Validate HWPX and delegate rendering to an external engine."""

    source_format = DocumentFormat.HWPX
    target_format = DocumentFormat.PDF

    def __init__(
        self,
        executable: str | Path = "soffice",
        *,
        timeout_seconds: int = 120,
        engine: LibreOfficeEngine | None = None,
        fallback_converters: tuple[DocumentConverter, DocumentConverter] | None = None,
    ):
        self.engine = engine or LibreOfficeEngine(
            str(executable),
            timeout_seconds,
        )
        self.fallback_converters = fallback_converters
        if fallback_converters is not None:
            hwpx_to_hwp, hwp_to_pdf = fallback_converters
            if (
                hwpx_to_hwp.source_format is not DocumentFormat.HWPX
                or hwpx_to_hwp.target_format is not DocumentFormat.HWP
                or hwp_to_pdf.source_format is not DocumentFormat.HWP
                or hwp_to_pdf.target_format is not DocumentFormat.PDF
            ):
                raise ValueError(
                    "HWPX PDF fallback must contain HWPX -> HWP and HWP -> PDF converters"
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
        HwpxDocument(source)
        try:
            return self.engine.export_pdf(
                source,
                destination,
                input_filter="Hwp2002_File",
            )
        except DocumentConversionError as direct_error:
            if self.fallback_converters is None:
                raise
            return self._convert_via_hwp(
                source,
                destination,
                options=options,
                direct_error=direct_error,
            )

    def _convert_via_hwp(
        self,
        source: Path,
        destination: Path,
        *,
        options: Mapping[str, object] | None,
        direct_error: DocumentConversionError,
    ) -> Path:
        hwpx_to_hwp, hwp_to_pdf = self.fallback_converters or ()
        destination_path = destination.resolve()
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(
                prefix=".hwpx-pdf-fallback-",
                dir=destination_path.parent,
            ) as temporary_directory:
                intermediate_hwp = Path(temporary_directory) / "intermediate.hwp"
                hwpx_to_hwp.convert(
                    source,
                    intermediate_hwp,
                    options=options,
                )
                return hwp_to_pdf.convert(
                    intermediate_hwp,
                    destination_path,
                    options=options,
                )
        except DocumentConversionError as fallback_error:
            raise DocumentConversionError(
                "HWPX PDF conversion failed directly "
                f"({direct_error}); HWP fallback also failed ({fallback_error})"
            ) from fallback_error


__all__ = ["HwpxToPdfConverter"]
