"""Java adapter for the Apache-2.0 hwp2hwpx converter."""

from __future__ import annotations

import importlib.resources
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.documents.conversion.errors import (
    ConversionEngineUnavailableError,
    DocumentConversionError,
)
from app.documents.hwpx import HwpxPackage


class Hwp2HwpxNotAvailableError(ConversionEngineUnavailableError):
    """The Java runtime or bundled hwp2hwpx JAR is unavailable."""


@dataclass(frozen=True)
class JavaHwp2HwpxEngine:
    """Convert HWP to HWPX in an isolated ASCII-only working directory."""

    executable: str = "java"
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
            raise Hwp2HwpxNotAvailableError(
                f"Java executable is unavailable: {self.executable}"
            )
        self._jar_resource()
        return Path(resolved)

    def convert(self, source: str | Path, destination: str | Path) -> Path:
        executable = self.require_available()
        source_path = Path(source).resolve()
        destination_path = Path(destination).resolve()
        if not source_path.is_file():
            raise FileNotFoundError(source_path)

        destination_path.parent.mkdir(parents=True, exist_ok=True)
        with importlib.resources.as_file(self._jar_resource()) as jar_path:
            with tempfile.TemporaryDirectory(
                prefix=".hwp2hwpx-",
                dir=destination_path.parent,
            ) as temporary_directory:
                working_directory = Path(temporary_directory)
                input_path = working_directory / "input.hwp"
                output_path = working_directory / "output.hwpx"
                shutil.copy2(source_path, input_path)
                command = [
                    str(executable),
                    "-Dfile.encoding=UTF-8",
                    "-jar",
                    str(jar_path),
                    str(input_path),
                    str(output_path),
                ]
                completed = self._run(command)
                if not output_path.is_file():
                    details = self._details(completed)
                    message = "hwp2hwpx did not create the expected HWPX"
                    if details:
                        message = f"{message}: {details}"
                    raise DocumentConversionError(message)

                package = HwpxPackage(output_path)
                package.section_name(0)
                package.save(destination_path)
        return destination_path

    def _jar_resource(self):
        try:
            package_root = importlib.resources.files("hwp2hwpx")
        except (ModuleNotFoundError, TypeError) as exc:
            raise Hwp2HwpxNotAvailableError(
                "Python package 'hwp2hwpx' is unavailable"
            ) from exc
        jar_resource = package_root.joinpath("jars", "hwp2hwpx.jar")
        if not jar_resource.is_file():
            raise Hwp2HwpxNotAvailableError(
                "hwp2hwpx package does not contain jars/hwp2hwpx.jar"
            )
        return jar_resource

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
                f"hwp2hwpx conversion timed out after {self.timeout_seconds} seconds"
            ) from exc
        except OSError as exc:
            raise DocumentConversionError(
                f"failed to start Java: {self.executable}"
            ) from exc
        if completed.returncode != 0:
            details = self._details(completed)
            message = f"hwp2hwpx conversion failed ({completed.returncode})"
            if details:
                message = f"{message}: {details}"
            raise DocumentConversionError(message)
        return completed

    @staticmethod
    def _details(completed: subprocess.CompletedProcess[str]) -> str:
        return (completed.stderr or completed.stdout).strip()[-2_000:]


__all__ = ["Hwp2HwpxNotAvailableError", "JavaHwp2HwpxEngine"]
