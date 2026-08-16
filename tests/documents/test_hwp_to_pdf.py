import subprocess
from pathlib import Path

import pytest
from pypdf import PdfWriter

from app.documents.conversion import (
    DocumentConversionError,
    HwpToPdfConverter,
    RhwpNotAvailableError,
)
from app.documents.hwp5 import Hwp5DocumentService


def _source_hwp() -> Path:
    return Hwp5DocumentService().registry.get(
        "standard_labor_contract_v6"
    ).source_path


def test_hwp_to_pdf_runs_verified_rhwp_conversion(
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

    result = HwpToPdfConverter(timeout_seconds=30).convert(_source_hwp(), output)

    assert result == output.resolve()
    assert output.read_bytes().startswith(b"%PDF-")
    assert observed_command[1] == "export-pdf"
    assert observed_command[2].endswith(".hwp")
    assert "high-quality" in observed_command
    assert "--text-as-paths" in observed_command


def test_hwp_to_pdf_rejects_invalid_hwp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.documents.conversion.engines.rhwp.shutil.which",
        lambda executable: f"/runtime/{executable}",
    )
    source = tmp_path / "invalid.hwp"
    source.write_bytes(b"not-an-hwp")

    with pytest.raises(DocumentConversionError, match="invalid HWP 5.x input"):
        HwpToPdfConverter().convert(source, tmp_path / "result.pdf")


def test_hwp_to_pdf_fails_when_rhwp_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.documents.conversion.engines.rhwp.shutil.which",
        lambda executable: None,
    )

    with pytest.raises(RhwpNotAvailableError, match="rhwp executable"):
        HwpToPdfConverter("missing-rhwp").require_available()
