import io
import json
import zipfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image, ImageDraw

from app.documents.hwp5 import Hwp5BinaryDocument, Hwp5DocumentService
from app.documents.hwpx import HwpxDocumentService
from app.main import app


def _image_bytes(format_name: str, *, signature: bool = False) -> bytes:
    if signature:
        image = Image.new("RGBA", (700, 200), (255, 255, 255, 0))
        draw = ImageDraw.Draw(image)
        draw.line((20, 150, 220, 40, 430, 155, 680, 30), fill="black", width=12)
    else:
        image = Image.new("RGB", (350, 450), "royalblue")
    output = io.BytesIO()
    image.save(output, format=format_name)
    return output.getvalue()


@pytest.mark.asyncio
async def test_template_endpoints_expose_format_variants_and_fields() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v1/documents/templates")
        detail = await client.get(
            "/api/v1/documents/templates/identity_guaranty_v129"
        )
        missing = await client.get("/api/v1/documents/templates/missing")

    assert response.status_code == 200
    assert len(response.json()) == 4
    assert detail.status_code == 200
    assert detail.json()["display_name"] == "신원보증서(한글)"
    variants = detail.json()["variants"]
    assert [variant["format"] for variant in variants] == ["hwp", "hwpx"]
    hwp_fields = {field["name"]: field for field in variants[0]["fields"]}
    assert hwp_fields["foreign_name"]["type"] == "text"
    assert hwp_fields["guarantor_signature"]["type"] == "signature"
    assert variants[1]["supports_dynamic_labels"] is True
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_inspect_identifies_uploaded_hwp_template() -> None:
    template = Hwp5DocumentService().registry.get("identity_guaranty_v129")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/documents/inspect",
            files={
                "file": (
                    "identity.hwp",
                    template.source_path.read_bytes(),
                    "application/vnd.hancom.hwp",
                )
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "format": "hwp",
        "editable": True,
        "template_id": "identity_guaranty_v129",
    }


@pytest.mark.asyncio
async def test_edit_hwp_text_checkbox_photo_and_signature(tmp_path: Path) -> None:
    template = Hwp5DocumentService().registry.get(
        "immigration_integrated_application_v34"
    )
    payload = {
        "template_id": template.template_id,
        "values": {
            "family_name": "API",
            "given_names": "EDITOR",
            "application_stay_extension": True,
        },
        "assets": {
            "photo": "photo.jpg",
            "applicant_signature": "signature.png",
        },
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/documents/edit",
            data={"payload": json.dumps(payload)},
            files=[
                (
                    "file",
                    (
                        "application.hwp",
                        template.source_path.read_bytes(),
                        "application/vnd.hancom.hwp",
                    ),
                ),
                ("assets", ("photo.jpg", _image_bytes("JPEG"), "image/jpeg")),
                (
                    "assets",
                    (
                        "signature.png",
                        _image_bytes("PNG", signature=True),
                        "image/png",
                    ),
                ),
            ],
        )

    assert response.status_code == 200, response.text
    assert response.headers["x-document-template-id"] == template.template_id
    assert response.headers["x-changed-field-count"] == "5"
    output = tmp_path / "edited.hwp"
    output.write_bytes(response.content)
    document = Hwp5BinaryDocument(output)
    assert document.paragraphs()[46].text == "API"
    assert document.paragraphs()[47].text == "EDITOR"
    assert "[√ " in document.paragraphs()[24].text
    assert [image.extension for image in document.embedded_images()] == ["jpg", "png"]


@pytest.mark.asyncio
async def test_generate_hwpx_with_values_and_application_options() -> None:
    payload = {
        "template_id": "immigration_integrated_application_v34",
        "format": "hwpx",
        "values": {"성": "PARK", "명": "API"},
        "application_options": {"외국인 등록": True},
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/documents/generate",
            data={"payload": json.dumps(payload, ensure_ascii=False)},
        )

    assert response.status_code == 200, response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as package:
        section = package.read("Contents/section0.xml").decode("utf-8")
    assert "PARK" in section
    assert "API" in section
    assert "[v]" in section


@pytest.mark.asyncio
async def test_generate_hwp_with_signature(tmp_path: Path) -> None:
    payload = {
        "template_id": "identity_guaranty_v129",
        "format": "hwp",
        "values": {"foreign_name": "GENERATED"},
        "assets": {"guarantor_signature": "signature.png"},
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/documents/generate",
            data={"payload": json.dumps(payload)},
            files={
                "assets": (
                    "signature.png",
                    _image_bytes("PNG", signature=True),
                    "image/png",
                )
            },
        )

    assert response.status_code == 200, response.text
    output = tmp_path / "generated.hwp"
    output.write_bytes(response.content)
    document = Hwp5BinaryDocument(output)
    assert "GENERATED" in document.paragraphs()[8].text
    assert [image.extension for image in document.embedded_images()] == ["png"]


@pytest.mark.asyncio
async def test_edit_hwpx_with_dynamic_labels() -> None:
    template = HwpxDocumentService().registry.get(
        "immigration_integrated_application_v34"
    )
    payload = {
        "template_id": template.template_id,
        "values": {"성": "EDIT", "명": "HWPX"},
        "application_options": {"외국인 등록": True},
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/documents/edit",
            data={"payload": json.dumps(payload, ensure_ascii=False)},
            files={
                "file": (
                    "application.hwpx",
                    template.source_path.read_bytes(),
                    "application/vnd.hancom.hwpx",
                )
            },
        )

    assert response.status_code == 200, response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as package:
        section = package.read("Contents/section0.xml").decode("utf-8")
    assert "EDIT" in section
    assert "HWPX" in section
    assert "[v]" in section


@pytest.mark.asyncio
async def test_generate_rejects_hwpx_assets() -> None:
    payload = {
        "template_id": "identity_guaranty_v129",
        "format": "hwpx",
        "assets": {"signature": "signature.png"},
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/documents/generate",
            data={"payload": json.dumps(payload)},
            files={
                "assets": (
                    "signature.png",
                    _image_bytes("PNG", signature=True),
                    "image/png",
                )
            },
        )

    assert response.status_code == 422
    assert "HWPX structured asset insertion" in response.json()["detail"]


def test_openapi_exposes_separate_document_actions() -> None:
    schema = app.openapi()
    paths = schema["paths"]

    assert "/api/v1/documents/convert" in paths
    assert "/api/v1/documents/edit" in paths
    assert "/api/v1/documents/generate" in paths
    assert "/api/v1/documents/generate/from-txt" in paths
    assert "/api/v1/documents/inspect" in paths
    assert "/api/v1/documents/templates" in paths
    assert "/api/v1/documents/templates/{template_id}" in paths

    assert [tag["name"] for tag in schema["tags"]] == [
        "Analyses",
        "Document Capabilities",
        "Document Templates",
        "Document Inspection",
        "Document Editing",
        "Document Generation",
        "Document Conversion",
    ]
    assert [tag["description"] for tag in schema["tags"]] == [
        (
            "Server가 호출하는 핵심 분석 API. "
            "analysisInput 지시문에서 Intent 분류, Slot 추출, 모호성 검사 수행"
        ),
        "현재 서버에서 사용할 수 있는 문서 처리 기능과 변환 조합을 조회합니다.",
        "등록된 문서 템플릿 목록과 편집 가능한 필드를 조회합니다.",
        "업로드한 문서의 실제 포맷을 감지하고 일치하는 템플릿을 식별합니다.",
        "HWP 또는 HWPX 문서에 구조화된 값, 사진, 서명 등의 파일을 입력합니다.",
        "등록된 템플릿을 기반으로 새로운 HWP 또는 HWPX 문서를 생성합니다.",
        "지원되는 HWP, HWPX, XML, PDF 포맷 사이에서 문서를 변환합니다.",
    ]
    assert paths["/api/v1/documents/capabilities"]["get"]["tags"] == [
        "Document Capabilities"
    ]
    assert paths["/api/v1/documents/templates"]["get"]["tags"] == [
        "Document Templates"
    ]
    assert paths["/api/v1/documents/templates/{template_id}"]["get"]["tags"] == [
        "Document Templates"
    ]
    assert paths["/api/v1/documents/inspect"]["post"]["tags"] == [
        "Document Inspection"
    ]
    assert paths["/api/v1/documents/edit"]["post"]["tags"] == ["Document Editing"]
    assert paths["/api/v1/documents/generate"]["post"]["tags"] == [
        "Document Generation"
    ]
    assert paths["/api/v1/documents/generate/from-txt"]["post"]["tags"] == [
        "Document Generation"
    ]
    assert paths["/api/v1/documents/convert"]["post"]["tags"] == [
        "Document Conversion"
    ]
