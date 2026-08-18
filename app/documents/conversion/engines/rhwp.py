"""Adapter for the pinned rhwp document conversion binary."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import olefile
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.documents.conversion.errors import (
    ConversionEngineUnavailableError,
    DocumentConversionError,
)

HWP5_SIGNATURE = b"HWP Document File"


class RhwpNotAvailableError(ConversionEngineUnavailableError):
    """The configured rhwp executable is unavailable."""


@dataclass(frozen=True)
class RhwpEngine:
    """Run verified HWP/HWPX conversion in an isolated directory."""

    executable: str = "rhwp"
    timeout_seconds: int = 120

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

    def require_available(self) -> Path:
        resolved = shutil.which(self.executable)
        if resolved is None:
            executable_path = Path(self.executable)
            if executable_path.is_file():
                resolved = str(executable_path.resolve())
        if resolved is None:
            raise RhwpNotAvailableError(
                f"rhwp executable is unavailable: {self.executable}"
            )
        return Path(resolved)

    def convert(self, source: str | Path, destination: str | Path) -> Path:
        """Convert HWPX to a verified HWP 5.x document."""

        executable = self.require_available()
        source_path = Path(source).resolve()
        destination_path = Path(destination).resolve()
        if not source_path.is_file():
            raise FileNotFoundError(source_path)

        destination_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".rhwp-",
            dir=destination_path.parent,
        ) as temporary_directory:
            working_directory = Path(temporary_directory)
            input_path = working_directory / "input.hwpx"
            output_path = working_directory / "output.hwp"
            shutil.copy2(source_path, input_path)
            completed = self._run(
                [
                    str(executable),
                    "convert",
                    str(input_path),
                    str(output_path),
                    "--verify",
                    "--verify-pages",
                ]
            )
            if not output_path.is_file():
                details = self._details(completed)
                message = "rhwp did not create the expected HWP"
                if details:
                    message = f"{message}: {details}"
                raise DocumentConversionError(message)
            self._validate_hwp(output_path)
            os.replace(output_path, destination_path)
        return destination_path

    def export_pdf(self, source: str | Path, destination: str | Path) -> Path:
        """Render an HWP or HWPX document with rhwp's native PDF exporter."""

        executable = self.require_available()
        source_path = Path(source).resolve()
        destination_path = Path(destination).resolve()
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        if source_path.suffix.casefold() not in {".hwp", ".hwpx"}:
            raise DocumentConversionError("rhwp PDF input must be HWP or HWPX")

        destination_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".rhwp-pdf-",
            dir=destination_path.parent,
        ) as temporary_directory:
            working_directory = Path(temporary_directory)
            input_path = working_directory / f"input{source_path.suffix.casefold()}"
            output_path = working_directory / "output.pdf"
            shutil.copy2(source_path, input_path)
            completed = self._run(
                [
                    str(executable),
                    "export-pdf",
                    str(input_path),
                    "--output",
                    str(output_path),
                    "--profile",
                    "high-quality",
                    "--text-as-paths",
                ]
            )
            if not output_path.is_file():
                details = self._details(completed)
                message = "rhwp did not create the expected PDF"
                if details:
                    message = f"{message}: {details}"
                raise DocumentConversionError(message)
            self._validate_pdf(output_path)
            os.replace(output_path, destination_path)
        return destination_path

    def _run(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise DocumentConversionError(
                f"rhwp conversion timed out after {self.timeout_seconds} seconds"
            ) from exc
        except OSError as exc:
            raise DocumentConversionError(
                f"failed to start rhwp: {self.executable}"
            ) from exc
        if completed.returncode != 0:
            details = self._details(completed)
            message = f"rhwp conversion or verification failed ({completed.returncode})"
            if details:
                message = f"{message}: {details}"
            raise DocumentConversionError(message)
        return completed

    @staticmethod
    def _validate_hwp(output_path: Path) -> None:
        try:
            with olefile.OleFileIO(str(output_path)) as document:
                if not document.exists("FileHeader"):
                    raise DocumentConversionError("generated HWP has no FileHeader stream")
                signature = document.openstream("FileHeader").read(len(HWP5_SIGNATURE))
        except OSError as exc:
            raise DocumentConversionError("generated HWP has an invalid CFB container") from exc
        if signature != HWP5_SIGNATURE:
            raise DocumentConversionError("generated HWP has an invalid HWP 5.x signature")

    @staticmethod
    def _validate_pdf(output_path: Path) -> None:
        """Validate the PDF container and every page, not only its signature."""

        try:
            with output_path.open("rb") as stream:
                if stream.read(5) != b"%PDF-":
                    raise DocumentConversionError("generated output is not a PDF document")
                stream.seek(0)
                document = PdfReader(stream, strict=True)
                if document.is_encrypted:
                    raise DocumentConversionError("generated PDF must not be encrypted")
                if not document.pages:
                    raise DocumentConversionError("generated PDF has no pages")
                for page in document.pages:
                    width = float(page.mediabox.width)
                    height = float(page.mediabox.height)
                    if width <= 0 or height <= 0:
                        raise DocumentConversionError(
                            "generated PDF contains a page with an invalid media box"
                        )
        except DocumentConversionError:
            raise
        except (PdfReadError, OSError, TypeError, ValueError) as exc:
            raise DocumentConversionError("generated PDF has an invalid structure") from exc

    @staticmethod
    def _details(completed: subprocess.CompletedProcess[str]) -> str:
        return (completed.stderr or completed.stdout).strip()[-2_000:]


__all__ = ["RhwpEngine", "RhwpNotAvailableError"]
