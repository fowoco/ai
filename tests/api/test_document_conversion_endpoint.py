from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.dependencies import get_document_conversion_service
from app.core.config import get_settings
from app.documents import DocumentConversionService, DocumentFormat
from app.documents.conversion import (
    ConversionEngineUnavailableError,
    DocumentConversionError,
)
from app.main import app


class RecordingConverter:
    source_format = DocumentFormat.HWP
    target_format = DocumentFormat.HWPX

    def __init__(self, *, error: Exception | None = None):
        self.error = error
        self.source_path: Path | None = None
        self.options: Mapping[str, object] | None = None

    def convert(
        self,
        source: Path,
        destination: Path,
        *,
        options: Mapping[str, object] | None = None,
    ) -> Path:
        self.source_path = source
        self.options = options
        if self.error is not None:
            raise self.error
        destination.write_bytes(b"converted:" + source.read_bytes())
        return destination


class RecordingXmlConverter(RecordingConverter):
    source_format = DocumentFormat.XML
    target_format = DocumentFormat.HWPX


@pytest.fixture(autouse=True)
def isolate_api_dependencies(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.api.routes.documents.convert.detect_document_format",
        lambda source: DocumentFormat.HWP,
    )
    yield
    app.dependency_overrides.clear()


def test_convert_openapi_exposes_only_simple_conversion_fields() -> None:
    schema = app.openapi()
    request_schema = schema["paths"]["/api/v1/documents/convert"]["post"]["requestBody"][
        "content"
    ]["multipart/form-data"]["schema"]
    component_name = request_schema["$ref"].rsplit("/", 1)[-1]
    form_schema = schema["components"]["schemas"][component_name]

    assert "source_format" not in form_schema["properties"]
    assert "options" not in form_schema["properties"]
    assert set(form_schema["required"]) == {"file", "target_format"}

    xml_request_schema = schema["paths"]["/api/v1/documents/convert/from-xml"]["post"][
        "requestBody"
    ]["content"]["multipart/form-data"]["schema"]
    xml_component_name = xml_request_schema["$ref"].rsplit("/", 1)[-1]
    xml_form_schema = schema["components"]["schemas"][xml_component_name]
    assert set(xml_form_schema["required"]) == {"file", "target_format"}
    assert "template_id" not in xml_form_schema["properties"]
    assert "section" not in xml_form_schema["properties"]


@pytest.mark.asyncio
async def test_convert_downloads_result_and_removes_temporary_files() -> None:
    converter = RecordingConverter()
    service = DocumentConversionService((converter,))
    app.dependency_overrides[get_document_conversion_service] = lambda: service

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/documents/convert",
            data={"target_format": "hwpx"},
            files={"file": ("신청서.hwp", b"source-content", "application/octet-stream")},
        )

    assert response.status_code == 200
    assert response.content == b"converted:source-content"
    assert response.headers["content-type"] == "application/vnd.hancom.hwpx"
    assert "attachment;" in response.headers["content-disposition"]
    assert ".hwpx" in response.headers["content-disposition"]
    assert response.headers["x-detected-source-format"] == "hwp"
    assert converter.options == {"document_name": "신청서"}
    assert converter.source_path is not None
    assert not converter.source_path.parent.exists()


@pytest.mark.asyncio
async def test_convert_rejects_oversized_upload_before_conversion() -> None:
    converter = RecordingConverter()
    service = DocumentConversionService((converter,))
    app.dependency_overrides[get_document_conversion_service] = lambda: service
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
        document_upload_max_bytes=4
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/documents/convert",
            data={"target_format": "hwpx"},
            files={"file": ("document.hwp", b"12345", "application/octet-stream")},
        )

    assert response.status_code == 413
    assert converter.source_path is None


@pytest.mark.asyncio
async def test_convert_accepts_xml_input_with_automatic_snapshot_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.routes.documents.convert.detect_document_format",
        lambda source: DocumentFormat.XML,
    )

    converter = RecordingXmlConverter()
    app.dependency_overrides[get_document_conversion_service] = lambda: (
        DocumentConversionService((converter,))
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/documents/convert",
            data={"target_format": "hwpx"},
            files={"file": ("document.xml", b"<root/>", "application/xml")},
        )

    assert response.status_code == 200
    assert response.content == b"converted:<root/>"
    assert converter.options == {"document_name": "document"}


@pytest.mark.asyncio
async def test_convert_from_xml_passes_explicit_template_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.routes.documents.convert.detect_document_format",
        lambda source: DocumentFormat.XML,
    )
    converter = RecordingXmlConverter()
    app.dependency_overrides[get_document_conversion_service] = lambda: (
        DocumentConversionService((converter,))
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/documents/convert/from-xml",
            data={"target_format": "hwpx"},
            files={"file": ("document.xml", b"<root/>", "application/xml")},
        )

    assert response.status_code == 200
    assert response.content == b"converted:<root/>"
    assert converter.options == {"document_name": "document"}


@pytest.mark.asyncio
async def test_convert_maps_conversion_failure_and_removes_temporary_files() -> None:
    converter = RecordingConverter(
        error=DocumentConversionError("fixture conversion failed")
    )
    app.dependency_overrides[get_document_conversion_service] = lambda: (
        DocumentConversionService((converter,))
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/documents/convert",
            data={"target_format": "hwpx"},
            files={"file": ("document.hwp", b"source", "application/octet-stream")},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "fixture conversion failed"
    assert converter.source_path is not None
    assert not converter.source_path.parent.exists()


@pytest.mark.asyncio
async def test_convert_maps_unavailable_engine_to_service_unavailable() -> None:
    converter = RecordingConverter(
        error=ConversionEngineUnavailableError("fixture engine unavailable")
    )
    app.dependency_overrides[get_document_conversion_service] = lambda: (
        DocumentConversionService((converter,))
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/documents/convert",
            data={"target_format": "hwpx"},
            files={"file": ("document.hwp", b"source", "application/octet-stream")},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "fixture engine unavailable"


@pytest.mark.asyncio
async def test_convert_maps_dependency_engine_failure_to_service_unavailable() -> None:
    def unavailable_service() -> DocumentConversionService:
        raise ConversionEngineUnavailableError("configured engine is missing")

    app.dependency_overrides[get_document_conversion_service] = unavailable_service

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/documents/convert",
            data={"target_format": "hwpx"},
            files={"file": ("document.hwp", b"source", "application/octet-stream")},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "configured engine is missing"


@pytest.mark.asyncio
async def test_convert_rejects_unregistered_conversion_pair() -> None:
    app.dependency_overrides[get_document_conversion_service] = (
        lambda: DocumentConversionService()
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/documents/convert",
            data={"target_format": "pdf"},
            files={"file": ("document.hwp", b"source", "application/octet-stream")},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "unsupported conversion: hwp -> pdf"


@pytest.mark.asyncio
async def test_convert_rejects_known_mismatched_filename_extension() -> None:
    converter = RecordingConverter()
    app.dependency_overrides[get_document_conversion_service] = lambda: (
        DocumentConversionService((converter,))
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/documents/convert",
            data={"target_format": "hwpx"},
            files={"file": ("document.hwpx", b"source", "application/octet-stream")},
        )

    assert response.status_code == 400
    assert "does not match" in response.json()["detail"]
    assert converter.source_path is None
