import subprocess
from pathlib import Path

import pytest

from app.documents.common import DocumentFormat
from app.documents.conversion import (
    DocumentConversionError,
    HwpxToPdfConverter,
    SofficeNotAvailableError,
)
from app.documents.hwpx import HwpxDocumentService


def _source_hwpx() -> Path:
    return HwpxDocumentService().registry.get(
        "immigration_integrated_application_v34"
    ).source_path


class StubConverter:
    def __init__(
        self,
        source_format: DocumentFormat,
        target_format: DocumentFormat,
        *,
        output: bytes = b"",
        error: DocumentConversionError | None = None,
    ):
        self.source_format = source_format
        self.target_format = target_format
        self.output = output
        self.error = error
        self.calls: list[tuple[Path, Path]] = []

    def convert(self, source: Path, destination: Path, *, options=None) -> Path:
        del options
        self.calls.append((source, destination))
        if self.error is not None:
            raise self.error
        destination.write_bytes(self.output)
        return destination


def test_hwpx_to_pdf_runs_isolated_headless_conversion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_command: list[str] = []
    monkeypatch.setattr(
        "app.documents.conversion.engines.libreoffice.shutil.which",
        lambda executable: f"/runtime/{executable}",
    )

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        observed_command.extend(command)
        output_directory = Path(command[command.index("--outdir") + 1])
        (output_directory / "input.pdf").write_bytes(b"%PDF-1.7\n%%EOF\n")
        assert kwargs["timeout"] == 30
        assert kwargs["check"] is False
        return subprocess.CompletedProcess(command, 0, "converted", "")

    monkeypatch.setattr(
        "app.documents.conversion.engines.libreoffice.subprocess.run",
        fake_run,
    )
    output = tmp_path / "result.pdf"

    result = HwpxToPdfConverter(timeout_seconds=30).convert(_source_hwpx(), output)

    assert result == output.resolve()
    assert output.read_bytes().startswith(b"%PDF-")
    assert "--headless" in observed_command
    assert "--infilter=Hwp2002_File" in observed_command
    assert "pdf:writer_pdf_Export" in observed_command
    assert any(argument.startswith("-env:UserInstallation=file:") for argument in observed_command)


def test_hwpx_to_pdf_fails_when_soffice_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.documents.conversion.engines.libreoffice.shutil.which",
        lambda executable: None,
    )

    with pytest.raises(SofficeNotAvailableError, match="LibreOffice executable"):
        HwpxToPdfConverter("missing-soffice").require_available()


def test_hwpx_to_pdf_rejects_failed_conversion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.documents.conversion.engines.libreoffice.shutil.which",
        lambda executable: f"/runtime/{executable}",
    )
    monkeypatch.setattr(
        "app.documents.conversion.engines.libreoffice.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            1,
            "",
            "import filter failed",
        ),
    )
    output = tmp_path / "result.pdf"

    with pytest.raises(DocumentConversionError, match="import filter failed"):
        HwpxToPdfConverter().convert(_source_hwpx(), output)
    assert not output.exists()


def test_hwpx_to_pdf_falls_back_through_hwp_and_cleans_intermediate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.documents.conversion.engines.libreoffice.shutil.which",
        lambda executable: f"/runtime/{executable}",
    )
    monkeypatch.setattr(
        "app.documents.conversion.engines.libreoffice.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            1,
            "",
            "direct import failed",
        ),
    )
    hwpx_to_hwp = StubConverter(
        DocumentFormat.HWPX,
        DocumentFormat.HWP,
        output=b"intermediate-hwp",
    )
    hwp_to_pdf = StubConverter(
        DocumentFormat.HWP,
        DocumentFormat.PDF,
        output=b"%PDF-1.7\n%%EOF\n",
    )
    output = tmp_path / "result.pdf"

    result = HwpxToPdfConverter(
        fallback_converters=(hwpx_to_hwp, hwp_to_pdf)
    ).convert(_source_hwpx(), output)

    assert result == output
    assert output.read_bytes().startswith(b"%PDF-")
    assert len(hwpx_to_hwp.calls) == 1
    assert len(hwp_to_pdf.calls) == 1
    intermediate = hwp_to_pdf.calls[0][0]
    assert intermediate.suffix == ".hwp"
    assert not intermediate.parent.exists()


def test_hwpx_to_pdf_reports_direct_and_fallback_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.documents.conversion.engines.libreoffice.shutil.which",
        lambda executable: f"/runtime/{executable}",
    )
    monkeypatch.setattr(
        "app.documents.conversion.engines.libreoffice.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            1,
            "",
            "direct import failed",
        ),
    )
    hwpx_to_hwp = StubConverter(
        DocumentFormat.HWPX,
        DocumentFormat.HWP,
        error=DocumentConversionError("rhwp failed"),
    )
    hwp_to_pdf = StubConverter(
        DocumentFormat.HWP,
        DocumentFormat.PDF,
        output=b"%PDF-1.7\n%%EOF\n",
    )

    with pytest.raises(
        DocumentConversionError,
        match=r"direct import failed.*HWP fallback also failed.*rhwp failed",
    ):
        HwpxToPdfConverter(
            fallback_converters=(hwpx_to_hwp, hwp_to_pdf)
        ).convert(_source_hwpx(), tmp_path / "result.pdf")
