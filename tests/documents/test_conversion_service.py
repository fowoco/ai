import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api import dependencies
from app.documents import DocumentConversionService, DocumentFormat
from app.documents.conversion import (
    ConversionNotSupportedError,
    HwpToHwpxConverter,
    RhwpEngine,
)


class StubHwpxToXmlConverter:
    source_format = DocumentFormat.HWPX
    target_format = DocumentFormat.XML

    def convert(self, source: Path, destination: Path, *, options=None) -> Path:
        return destination


class RecordingConverter:
    def __init__(
        self,
        source_format: DocumentFormat,
        target_format: DocumentFormat,
        calls: list[tuple[DocumentFormat, DocumentFormat, dict[str, object]]],
    ):
        self.source_format = source_format
        self.target_format = target_format
        self.calls = calls

    def convert(self, source: Path, destination: Path, *, options=None) -> Path:
        self.calls.append((self.source_format, self.target_format, dict(options or {})))
        destination.write_bytes(
            source.read_bytes() + f"|{self.target_format.value}".encode()
        )
        return destination


def test_conversion_service_resolves_registered_pair(tmp_path: Path) -> None:
    service = DocumentConversionService((StubHwpxToXmlConverter(),))
    destination = tmp_path / "document.xml"

    result = service.convert(
        tmp_path / "document.hwpx",
        destination,
        source_format=DocumentFormat.HWPX,
        target_format=DocumentFormat.XML,
    )

    assert result == destination.resolve()
    assert service.supported_pairs() == ((DocumentFormat.HWPX, DocumentFormat.XML),)


def test_conversion_service_rejects_unimplemented_pair(tmp_path: Path) -> None:
    service = DocumentConversionService()

    with pytest.raises(ConversionNotSupportedError, match="hwp -> hwpx"):
        service.convert(
            tmp_path / "document.hwp",
            tmp_path / "document.hwpx",
            source_format=DocumentFormat.HWP,
            target_format=DocumentFormat.HWPX,
        )


def test_conversion_service_composes_shortest_path_and_cleans_intermediate(
    tmp_path: Path,
) -> None:
    calls: list[tuple[DocumentFormat, DocumentFormat, dict[str, object]]] = []
    service = DocumentConversionService(
        (
            RecordingConverter(DocumentFormat.HWP, DocumentFormat.HWPX, calls),
            RecordingConverter(DocumentFormat.HWPX, DocumentFormat.XML, calls),
        )
    )
    source = tmp_path / "document.hwp"
    source.write_bytes(b"source")
    destination = tmp_path / "document.xml"

    result = service.convert(
        source,
        destination,
        source_format=DocumentFormat.HWP,
        target_format=DocumentFormat.XML,
        options={"fixture": True},
    )

    assert result == destination.resolve()
    assert destination.read_bytes() == b"source|hwpx|xml"
    assert calls == [
        (DocumentFormat.HWP, DocumentFormat.HWPX, {"fixture": True}),
        (DocumentFormat.HWPX, DocumentFormat.XML, {"fixture": True}),
    ]
    assert (DocumentFormat.HWP, DocumentFormat.XML) in service.supported_pairs()
    assert not list(tmp_path.glob(".document-chain-*"))


def test_pdf_converters_are_registered_only_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        dependencies,
        "get_settings",
        lambda: SimpleNamespace(
            hwp_to_hwpx_enabled=False,
            java_path="java",
            hwpx_to_hwp_enabled=False,
            rhwp_path="rhwp",
            hwpx_pdf_enabled=True,
            document_conversion_timeout_seconds=120,
            document_snapshot_dir=Path(tempfile.gettempdir()) / "fowoco-test-snapshots",
        ),
    )
    monkeypatch.setattr(
        RhwpEngine,
        "require_available",
        lambda self: Path("/runtime/rhwp"),
    )
    dependencies.get_document_conversion_service.cache_clear()
    try:
        pairs = dependencies.get_document_conversion_service().supported_pairs()
    finally:
        dependencies.get_document_conversion_service.cache_clear()

    assert (DocumentFormat.HWP, DocumentFormat.PDF) in pairs
    assert (DocumentFormat.HWPX, DocumentFormat.PDF) in pairs


def test_conversion_service_prefers_direct_hwp_to_pdf_path(
    tmp_path: Path,
) -> None:
    calls: list[tuple[DocumentFormat, DocumentFormat, dict[str, object]]] = []
    service = DocumentConversionService(
        (
            RecordingConverter(DocumentFormat.HWP, DocumentFormat.HWPX, calls),
            RecordingConverter(DocumentFormat.HWPX, DocumentFormat.PDF, calls),
            RecordingConverter(DocumentFormat.HWP, DocumentFormat.PDF, calls),
        )
    )
    source = tmp_path / "document.hwp"
    source.write_bytes(b"source")
    destination = tmp_path / "document.pdf"

    service.convert(
        source,
        destination,
        source_format=DocumentFormat.HWP,
        target_format=DocumentFormat.PDF,
    )

    assert destination.read_bytes() == b"source|pdf"
    assert calls == [(DocumentFormat.HWP, DocumentFormat.PDF, {})]


def test_hwp_to_hwpx_converter_is_registered_only_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        dependencies,
        "get_settings",
        lambda: SimpleNamespace(
            hwp_to_hwpx_enabled=True,
            java_path="java",
            hwpx_to_hwp_enabled=False,
            rhwp_path="rhwp",
            hwpx_pdf_enabled=False,
            document_conversion_timeout_seconds=120,
            document_snapshot_dir=Path(tempfile.gettempdir()) / "fowoco-test-snapshots",
        ),
    )
    monkeypatch.setattr(
        HwpToHwpxConverter,
        "require_available",
        lambda self: Path("/runtime/java"),
    )
    dependencies.get_document_conversion_service.cache_clear()
    try:
        pairs = dependencies.get_document_conversion_service().supported_pairs()
    finally:
        dependencies.get_document_conversion_service.cache_clear()

    assert (DocumentFormat.HWP, DocumentFormat.HWPX) in pairs


def test_hwpx_to_hwp_converter_is_registered_only_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        dependencies,
        "get_settings",
        lambda: SimpleNamespace(
            hwp_to_hwpx_enabled=False,
            java_path="java",
            hwpx_to_hwp_enabled=True,
            rhwp_path="rhwp",
            hwpx_pdf_enabled=False,
            document_conversion_timeout_seconds=120,
            document_snapshot_dir=Path(tempfile.gettempdir()) / "fowoco-test-snapshots",
        ),
    )
    monkeypatch.setattr(
        RhwpEngine,
        "require_available",
        lambda self: Path("/runtime/rhwp"),
    )
    dependencies.get_document_conversion_service.cache_clear()
    try:
        pairs = dependencies.get_document_conversion_service().supported_pairs()
    finally:
        dependencies.get_document_conversion_service.cache_clear()

    assert (DocumentFormat.HWPX, DocumentFormat.HWP) in pairs
