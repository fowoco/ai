"""Isolated headless LibreOffice process adapter."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.documents.conversion.errors import (
    ConversionEngineUnavailableError,
    DocumentConversionError,
)


class SofficeNotAvailableError(ConversionEngineUnavailableError):
    """The configured LibreOffice executable is unavailable."""


@dataclass(frozen=True)
class LibreOfficeEngine:
    """Run one conversion per isolated profile and temporary directory."""

    executable: str = "soffice"
    timeout_seconds: int = 120

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

    def require_available(self) -> Path:
        """Resolve the executable or fail before advertising its capabilities."""

        resolved = shutil.which(self.executable)
        if resolved is None:
            executable_path = Path(self.executable)
            if executable_path.is_file():
                resolved = str(executable_path.resolve())
        if resolved is None:
            raise SofficeNotAvailableError(
                f"LibreOffice executable is unavailable: {self.executable}"
            )
        return Path(resolved)

    def export_pdf(
        self,
        source: str | Path,
        destination: str | Path,
        *,
        input_filter: str,
    ) -> Path:
        """Import one document and atomically export it as PDF."""

        executable = self.require_available()
        source_path = Path(source).resolve()
        destination_path = Path(destination).resolve()
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".document-pdf-",
            dir=destination_path.parent,
        ) as temporary_directory:
            working_directory = Path(temporary_directory)
            input_path = working_directory / f"input{source_path.suffix.casefold()}"
            output_directory = working_directory / "output"
            profile_directory = working_directory / "profile"
            output_directory.mkdir()
            profile_directory.mkdir()
            shutil.copy2(source_path, input_path)

            command = [
                str(executable),
                "--headless",
                "--nologo",
                "--nodefault",
                "--nofirststartwizard",
                "--nolockcheck",
                f"-env:UserInstallation={profile_directory.as_uri()}",
                f"--infilter={input_filter}",
                "--convert-to",
                "pdf:writer_pdf_Export",
                "--outdir",
                str(output_directory),
                str(input_path),
            ]
            completed = self._run(command)
            generated_pdf = output_directory / "input.pdf"
            if not generated_pdf.is_file():
                details = self._details(completed)
                message = "LibreOffice did not create the expected PDF"
                if details:
                    message = f"{message}: {details}"
                raise DocumentConversionError(message)
            with generated_pdf.open("rb") as pdf:
                if pdf.read(5) != b"%PDF-":
                    raise DocumentConversionError(
                        "LibreOffice output is not a valid PDF document"
                    )
            os.replace(generated_pdf, destination_path)
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
                f"LibreOffice conversion timed out after {self.timeout_seconds} seconds"
            ) from exc
        except OSError as exc:
            raise DocumentConversionError(
                f"failed to start LibreOffice: {self.executable}"
            ) from exc
        if completed.returncode != 0:
            details = self._details(completed)
            message = f"LibreOffice conversion failed ({completed.returncode})"
            if details:
                message = f"{message}: {details}"
            raise DocumentConversionError(message)
        return completed

    @staticmethod
    def _details(completed: subprocess.CompletedProcess[str]) -> str:
        return (completed.stderr or completed.stdout).strip()[-2_000:]


__all__ = ["LibreOfficeEngine", "SofficeNotAvailableError"]
