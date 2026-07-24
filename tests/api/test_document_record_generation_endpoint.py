import zipfile
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import unquote

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.dependencies import get_document_conversion_service
from app.documents import DocumentConversionService, DocumentFormat
from app.main import app

RECORD_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "documents" / "records"
TEMPLATE_IDS = (
    "identity_guaranty_v129",
    "employment_extension_application_v12_3",
    "immigration_integrated_application_v34",
    "standard_labor_contract_v6",
)
CHANGED_FIELD_COUNTS = {
    "identity_guaranty_v129": 24,
    "employment_extension_application_v12_3": 21,
    "immigration_integrated_application_v34": 40,
    "standard_labor_contract_v6": 70,
}
DISPLAY_NAMES = {
    "identity_guaranty_v129": "신원보증서(한글)",
    "employment_extension_application_v12_3": (
        "[별지 제12호의3서식] 취업기간 만료자 취업활동 기간 연장신청서"
        "(외국인근로자의 고용 등에 관한 법률 시행규칙)"
    ),
    "immigration_integrated_application_v34": "통합신청서(신고서)",
    "standard_labor_contract_v6": (
        "[별지 제6호서식] 표준근로계약서(Standard Labor Contract)"
        "(외국인근로자의 고용 등에 관한 법률 시행규칙)"
    ),
}


class MockHwpxToHwpConverter:
    source_format = DocumentFormat.HWPX
    target_format = DocumentFormat.HWP

    def convert(
        self,
        source: Path,
        destination: Path,
        *,
        options: Mapping[str, object] | None = None,
    ) -> Path:
        del options
        with zipfile.ZipFile(source) as package:
            assert package.testzip() is None
            assert package.read("mimetype") == b"application/hwp+zip"
        destination.write_bytes(b"mock-hwp")
        return destination


@pytest.fixture(autouse=True)
def mock_hwpx_to_hwp_conversion():
    service = DocumentConversionService((MockHwpxToHwpConverter(),))
    app.dependency_overrides[get_document_conversion_service] = lambda: service
    yield
    app.dependency_overrides.pop(get_document_conversion_service, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("template_id", TEMPLATE_IDS)
async def test_generate_from_txt_endpoint_for_all_templates(
    template_id: str,
) -> None:
    source = RECORD_ROOT / f"{template_id}.txt"

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/documents/generate/from-txt",
            data={"template_id": template_id},
            files={"file": (source.name, source.read_bytes(), "text/plain")},
        )

    assert response.status_code == 200, response.text
    assert response.headers["x-document-template-id"] == template_id
    assert int(response.headers["x-changed-field-count"]) == CHANGED_FIELD_COUNTS[
        template_id
    ]
    assert response.headers["content-type"] == "application/vnd.hancom.hwp"
    content_disposition = unquote(response.headers["content-disposition"])
    assert f"{DISPLAY_NAMES[template_id]}.hwp" in content_disposition
    assert response.content == b"mock-hwp"


@pytest.mark.asyncio
async def test_generate_from_txt_rejects_non_txt_upload() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/documents/generate/from-txt",
            data={"template_id": "identity_guaranty_v129"},
            files={"file": ("record.json", b"{}", "application/json")},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "record file must use the .txt extension"
