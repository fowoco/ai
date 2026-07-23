import shutil
import subprocess
from pathlib import Path

import pytest

from app.documents.conversion import (
    DocumentConversionError,
    HwpxToHwpConverter,
    RhwpNotAvailableError,
)
from app.documents.hwp5 import Hwp5DocumentService
from app.documents.hwpx import HwpxDocumentService


def _source_hwpx() -> Path:
    return HwpxDocumentService().registry.get(
        "immigration_integrated_application_v34"
    ).source_path


def _valid_hwp() -> Path:
    return Hwp5DocumentService().registry.get(
        "immigration_integrated_application_v34"
    ).source_path


def test_hwpx_to_hwp_runs_verified_rhwp_conversion(
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
        shutil.copy2(_valid_hwp(), Path(command[3]))
        assert kwargs["timeout"] == 30
        assert kwargs["check"] is False
        return subprocess.CompletedProcess(command, 0, "verified", "")

    monkeypatch.setattr(
        "app.documents.conversion.engines.rhwp.subprocess.run",
        fake_run,
    )
    output = tmp_path / "result.hwp"

    result = HwpxToHwpConverter(timeout_seconds=30).convert(_source_hwpx(), output)

    assert result == output.resolve()
    assert Path(observed_command[0]) == Path("/runtime/rhwp")
    assert observed_command[1] == "convert"
    assert Path(observed_command[2]).name == "input.hwpx"
    assert Path(observed_command[3]).name == "output.hwp"
    assert observed_command[4:] == ["--verify", "--verify-pages"]


def test_hwpx_to_hwp_fails_when_rhwp_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.documents.conversion.engines.rhwp.shutil.which",
        lambda executable: None,
    )

    with pytest.raises(RhwpNotAvailableError, match="rhwp executable"):
        HwpxToHwpConverter("missing-rhwp").require_available()


def test_hwpx_to_hwp_rejects_failed_verification(
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
            3,
            "",
            "IR verification failed",
        ),
    )
    output = tmp_path / "result.hwp"

    with pytest.raises(DocumentConversionError, match="IR verification failed"):
        HwpxToHwpConverter().convert(_source_hwpx(), output)
    assert not output.exists()


def test_hwpx_to_hwp_rejects_malformed_cfb(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.documents.conversion.engines.rhwp.shutil.which",
        lambda executable: f"/runtime/{executable}",
    )

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        Path(command[3]).write_bytes(b"not an OLE document")
        return subprocess.CompletedProcess(command, 0, "verified", "")

    monkeypatch.setattr(
        "app.documents.conversion.engines.rhwp.subprocess.run",
        fake_run,
    )
    output = tmp_path / "result.hwp"

    with pytest.raises(DocumentConversionError, match="invalid CFB"):
        HwpxToHwpConverter().convert(_source_hwpx(), output)
    assert not output.exists()
