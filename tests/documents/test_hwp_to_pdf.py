import subprocess
from pathlib import Path

import pytest

from app.documents.conversion import (
    DocumentConversionError,
    HwpToPdfConverter,
    SofficeNotAvailableError,
)
from app.documents.hwp5 import Hwp5DocumentService


def _source_hwp() -> Path:
    return Hwp5DocumentService().registry.get(
        "standard_labor_contract_v6"
    ).source_path


def test_hwp_to_pdf_runs_direct_isolated_headless_conversion(
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

    result = HwpToPdfConverter(timeout_seconds=30).convert(_source_hwp(), output)

    assert result == output.resolve()
    assert output.read_bytes().startswith(b"%PDF-")
    assert "--infilter=Hwp2002_File" in observed_command
    assert observed_command[-1].endswith(".hwp")


def test_hwp_to_pdf_rejects_invalid_hwp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.documents.conversion.engines.libreoffice.shutil.which",
        lambda executable: f"/runtime/{executable}",
    )
    source = tmp_path / "invalid.hwp"
    source.write_bytes(b"not-an-hwp")

    with pytest.raises(DocumentConversionError, match="invalid HWP 5.x input"):
        HwpToPdfConverter().convert(source, tmp_path / "result.pdf")


def test_hwp_to_pdf_fails_when_soffice_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.documents.conversion.engines.libreoffice.shutil.which",
        lambda executable: None,
    )

    with pytest.raises(SofficeNotAvailableError, match="LibreOffice executable"):
        HwpToPdfConverter("missing-soffice").require_available()
