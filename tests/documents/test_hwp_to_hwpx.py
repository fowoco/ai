import subprocess
import zipfile
from pathlib import Path

import pytest

from app.documents.conversion import (
    DocumentConversionError,
    Hwp2HwpxNotAvailableError,
    HwpToHwpxConverter,
)
from app.documents.hwp5 import Hwp5DocumentService
from app.documents.hwpx import HwpxDocumentService, HwpxPackage


def _source_hwp() -> Path:
    return Hwp5DocumentService().registry.get(
        "immigration_integrated_application_v34"
    ).source_path


def _valid_hwpx() -> Path:
    return HwpxDocumentService().registry.get(
        "immigration_integrated_application_v34"
    ).source_path


def test_hwp_to_hwpx_runs_isolated_java_conversion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_root = tmp_path / "python-package"
    jar_path = package_root / "jars" / "hwp2hwpx.jar"
    jar_path.parent.mkdir(parents=True)
    jar_path.write_bytes(b"test jar")
    observed_command: list[str] = []

    monkeypatch.setattr(
        "app.documents.conversion.engines.hwp2hwpx_java.shutil.which",
        lambda executable: f"/runtime/{executable}",
    )
    monkeypatch.setattr(
        "app.documents.conversion.engines.hwp2hwpx_java.importlib.resources.files",
        lambda package: package_root,
    )

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        observed_command.extend(command)
        with (
            zipfile.ZipFile(_valid_hwpx(), "r") as source_archive,
            zipfile.ZipFile(
                Path(command[-1]),
                "w",
                compression=zipfile.ZIP_DEFLATED,
            ) as output_archive,
        ):
            for entry in source_archive.infolist():
                output_archive.writestr(entry.filename, source_archive.read(entry))
        assert kwargs["timeout"] == 30
        assert kwargs["check"] is False
        return subprocess.CompletedProcess(command, 0, "converted", "")

    monkeypatch.setattr(
        "app.documents.conversion.engines.hwp2hwpx_java.subprocess.run",
        fake_run,
    )
    output = tmp_path / "result.hwpx"

    result = HwpToHwpxConverter(timeout_seconds=30).convert(_source_hwp(), output)

    assert result == output.resolve()
    assert HwpxPackage(output).section_name(0) == "Contents/section0.xml"
    with zipfile.ZipFile(output) as archive:
        assert archive.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
    assert Path(observed_command[0]) == Path("/runtime/java")
    assert observed_command[1:4] == [
        "-Dfile.encoding=UTF-8",
        "-jar",
        str(jar_path),
    ]
    assert Path(observed_command[-2]).name == "input.hwp"
    assert Path(observed_command[-1]).name == "output.hwpx"


def test_hwp_to_hwpx_fails_when_java_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.documents.conversion.engines.hwp2hwpx_java.shutil.which",
        lambda executable: None,
    )

    with pytest.raises(Hwp2HwpxNotAvailableError, match="Java executable"):
        HwpToHwpxConverter("missing-java").require_available()


def test_hwp_to_hwpx_rejects_missing_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_root = tmp_path / "python-package"
    jar_path = package_root / "jars" / "hwp2hwpx.jar"
    jar_path.parent.mkdir(parents=True)
    jar_path.write_bytes(b"test jar")
    monkeypatch.setattr(
        "app.documents.conversion.engines.hwp2hwpx_java.shutil.which",
        lambda executable: f"/runtime/{executable}",
    )
    monkeypatch.setattr(
        "app.documents.conversion.engines.hwp2hwpx_java.importlib.resources.files",
        lambda package: package_root,
    )
    monkeypatch.setattr(
        "app.documents.conversion.engines.hwp2hwpx_java.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "", ""),
    )
    output = tmp_path / "result.hwpx"

    with pytest.raises(DocumentConversionError, match="expected HWPX"):
        HwpToHwpxConverter().convert(_source_hwp(), output)
    assert not output.exists()


def test_hwp_to_hwpx_rejects_invalid_hwp_before_starting_java(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = False

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal started
        started = True
        return subprocess.CompletedProcess(args[0], 0, "", "")

    monkeypatch.setattr(
        "app.documents.conversion.engines.hwp2hwpx_java.subprocess.run",
        fake_run,
    )
    source = tmp_path / "invalid.hwp"
    source.write_bytes(b"not an HWP document")

    with pytest.raises(DocumentConversionError, match="invalid HWP"):
        HwpToHwpxConverter().convert(source, tmp_path / "result.hwpx")
    assert not started
