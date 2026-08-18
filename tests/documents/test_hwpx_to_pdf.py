import subprocess
from pathlib import Path

import pytest
from pypdf import PdfWriter

from app.documents.conversion import (
    DocumentConversionError,
    HwpxToPdfConverter,
    RhwpNotAvailableError,
)
from app.documents.hwpx import HwpxDocumentService


def _source_hwpx() -> Path:
    return HwpxDocumentService().registry.get(
        "immigration_integrated_application_v34"
    ).source_path


def test_hwpx_to_pdf_runs_verified_rhwp_conversion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_command: list[str] = []
    monkeypatch.setattr(
        "app.documents.conversion.engines.rhwp.shutil.which",
        lambda executable: f"/runtime/{executable}",
    )

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        observed_command.extend(command)
        output = Path(command[command.index("--output") + 1])
        writer = PdfWriter()
        writer.add_blank_page(width=595, height=842)
        writer.write(output)
        assert kwargs["timeout"] == 30
        assert kwargs["check"] is False
        return subprocess.CompletedProcess(command, 0, "rendered", "")

    monkeypatch.setattr(
        "app.documents.conversion.engines.rhwp.subprocess.run",
        fake_run,
    )
    output = tmp_path / "result.pdf"

    result = HwpxToPdfConverter(timeout_seconds=30).convert(_source_hwpx(), output)

    assert result == output.resolve()
    assert output.read_bytes().startswith(b"%PDF-")
    assert observed_command[1] == "export-pdf"
    assert observed_command[2].endswith(".hwpx")
    assert "high-quality" in observed_command
    assert "--text-as-paths" in observed_command


def test_hwpx_to_pdf_fails_when_rhwp_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.documents.conversion.engines.rhwp.shutil.which",
        lambda executable: None,
    )

    with pytest.raises(RhwpNotAvailableError, match="rhwp executable"):
        HwpxToPdfConverter("missing-rhwp").require_available()


def test_hwpx_to_pdf_rejects_failed_conversion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.documents.conversion.engines.rhwp.shutil.which",
        lambda executable: f"/runtime/{executable}",
    )
    monkeypatch.setattr(
        "app.documents.conversion.engines.rhwp.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            1,
            "",
            "render failed",
        ),
    )
    output = tmp_path / "result.pdf"

    with pytest.raises(DocumentConversionError, match="render failed"):
        HwpxToPdfConverter().convert(_source_hwpx(), output)
    assert not output.exists()


def test_hwpx_to_pdf_rejects_structurally_invalid_pdf_and_cleans_temporary_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.documents.conversion.engines.rhwp.shutil.which",
        lambda executable: f"/runtime/{executable}",
    )

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        del kwargs
        output = Path(command[command.index("--output") + 1])
        output.write_bytes(b"%PDF-1.7\nnot-a-real-pdf\n%%EOF\n")
        return subprocess.CompletedProcess(command, 0, "rendered", "")

    monkeypatch.setattr(
        "app.documents.conversion.engines.rhwp.subprocess.run",
        fake_run,
    )
    output = tmp_path / "result.pdf"

    with pytest.raises(DocumentConversionError, match="invalid structure"):
        HwpxToPdfConverter().convert(_source_hwpx(), output)

    assert not output.exists()
    assert not list(tmp_path.glob(".rhwp-pdf-*"))
