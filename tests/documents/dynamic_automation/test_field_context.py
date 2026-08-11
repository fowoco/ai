from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.documents.dynamic_automation.field_context import build_field_contexts

FIXTURE_DIR = Path(__file__).parents[2] / "fixtures" / "dynamic_automation"


@pytest.fixture
def registry_fixture() -> list[dict[str, object]]:
    return json.loads(
        (FIXTURE_DIR / "integrated_application_registry.json").read_text(encoding="utf-8")
    )


def test_context_distinguishes_company_phone_from_worker_phone(
    registry_fixture: list[dict[str, object]],
) -> None:
    contexts = build_field_contexts(registry_fixture, document_title="통합신청서")

    phone = next(item for item in contexts if item.field_id == "workplace-phone")
    worker_phone = next(item for item in contexts if item.field_id == "worker-phone")

    assert phone.row_labels == ("현재 근무처", "사업자등록번호", "전화번호:")
    assert phone.section == "현재 근무처"
    assert worker_phone.row_labels == ("근로자", "전화번호")
    assert worker_phone.repeat_index == 1


def test_context_normalizes_and_bounds_untrusted_text() -> None:
    contexts = build_field_contexts(
        [
            {
                "field_id": "field-1",
                "label": "  Company—Phone:  ",
                "type": "phone",
                "kind": "text_field",
                "row": 1,
                "column": 1,
                "required": True,
                "options": ["x" * 201],
            }
        ],
        document_title="t" * 201,
    )

    context = contexts[0]
    assert context.normalized_label == "companyphone"
    assert context.document_title == "t" * 200
    assert context.options == ("x" * 200,)


def test_context_accepts_registry_null_options() -> None:
    contexts = build_field_contexts(
        [
            {
                "field_id": "field-1",
                "label": "Name",
                "type": "text",
                "kind": "text_field",
                "row": 1,
                "column": 1,
                "required": True,
                "options": None,
            }
        ],
        document_title="Application",
    )

    assert contexts[0].options == ()
