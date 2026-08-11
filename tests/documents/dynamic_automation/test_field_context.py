from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import get_args

import pytest

from app.documents.dynamic_automation.catalog import CanonicalCatalog
from app.documents.dynamic_automation.field_context import build_field_contexts
from app.documents.dynamic_automation.models import RegistryFieldType as MappingRegistryFieldType

HWP_EDITOR_SRC = Path(__file__).parents[3] / "hwp-editor" / "src"
if str(HWP_EDITOR_SRC) not in sys.path:
    sys.path.insert(0, str(HWP_EDITOR_SRC))

from hwp_mcp.fields import RegistryField  # noqa: E402
from hwp_mcp.fields import RegistryFieldType as McpRegistryFieldType  # noqa: E402

FIXTURE_DIR = Path(__file__).parents[2] / "fixtures" / "dynamic_automation"
CATALOG_PATH = (
    Path(__file__).parents[3]
    / "app/documents/dynamic_automation/resources/canonical_fields.v1.yaml"
)


def registry_field(
    *,
    field_id: str,
    target_id: str,
    label: str,
    row: int,
    column: int,
    field_type: str = "phone",
) -> dict[str, object]:
    """Mirror every field emitted by MCP RegistryField.model_dump()."""
    return {
        "field_id": field_id,
        "target_id": target_id,
        "label": label,
        "type": field_type,
        "category": "step1_application",
        "row": row,
        "column": column,
        "current_text": "",
        "required": True,
        "options": None,
        "kind": "text_field",
        "xml_segments": [target_id],
        "visual_regions": [],
        "constraints": {},
        "disposition": None,
    }


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
                "target_id": "section0.table0.row1.cell1",
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
                "target_id": "section0.table0.row1.cell1",
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


def test_equal_coordinates_in_different_tables_are_container_local() -> None:
    registry = [
        registry_field(
            field_id="company-heading",
            target_id="section0.table0.row0.cell0",
            label="Company",
            row=0,
            column=0,
            field_type="text",
        ),
        registry_field(
            field_id="company-phone",
            target_id="section0.table0.row0.cell1",
            label="Phone",
            row=0,
            column=1,
        ),
        registry_field(
            field_id="company-address",
            target_id="section0.table0.row1.cell0",
            label="Company address",
            row=1,
            column=0,
            field_type="text",
        ),
        registry_field(
            field_id="worker-heading",
            target_id="section0.table1.row0.cell0",
            label="Worker",
            row=0,
            column=0,
            field_type="text",
        ),
        registry_field(
            field_id="worker-phone",
            target_id="section0.table1.row0.cell1",
            label="Phone",
            row=0,
            column=1,
        ),
        registry_field(
            field_id="worker-nationality",
            target_id="section0.table1.row1.cell0",
            label="Worker nationality",
            row=1,
            column=0,
            field_type="text",
        ),
    ]

    contexts = build_field_contexts(registry, document_title="Application")
    company = next(item for item in contexts if item.field_id == "company-phone")
    worker = next(item for item in contexts if item.field_id == "worker-phone")

    assert company.container_id == "section0.table0"
    assert company.row_labels == ("Company", "Phone")
    assert company.section == "Company"
    assert company.nearby_labels == ("Company address",)
    assert company.repeat_index == 0
    assert worker.container_id == "section0.table1"
    assert worker.row_labels == ("Worker", "Phone")
    assert worker.section == "Worker"
    assert worker.nearby_labels == ("Worker nationality",)
    assert worker.repeat_index == 0


def test_repeated_worker_and_company_phone_contexts_keep_compatible_candidates() -> None:
    registry = [
        registry_field(
            field_id="company-phone",
            target_id="section0.table0.row0.cell0",
            label="Phone",
            row=0,
            column=0,
        ),
        registry_field(
            field_id="worker-phone",
            target_id="section0.table0.row1.cell0",
            label="Phone",
            row=1,
            column=0,
        ),
    ]
    contexts = build_field_contexts(registry, document_title="Application")
    catalog = CanonicalCatalog.load(CATALOG_PATH)

    assert contexts[1].repeat_index == 1
    for context in contexts:
        candidate_ids = {item.field_id for item in catalog.compatible(context)}
        assert {"worker.phone", "company.phone"} <= candidate_ids


def test_registry_rejects_duplicate_and_oversized_field_identities() -> None:
    duplicate = registry_field(
        field_id="duplicate-field",
        target_id="section0.table0.row0.cell0",
        label="Name",
        row=0,
        column=0,
        field_type="text",
    )
    second = {
        **duplicate,
        "target_id": "section0.table0.row1.cell0",
        "row": 1,
        "xml_segments": ["section0.table0.row1.cell0"],
    }

    with pytest.raises(ValueError, match="duplicate field_id"):
        build_field_contexts([duplicate, second], document_title="Application")

    oversized = {
        **duplicate,
        "field_id": "x" * 201,
    }
    with pytest.raises(ValueError, match="field_id"):
        build_field_contexts([oversized], document_title="Application")


def test_actual_mcp_number_fields_keep_identifier_candidates(
    registry_fixture: list[dict[str, object]],
) -> None:
    contexts = build_field_contexts(registry_fixture, document_title="통합신청서")
    catalog = CanonicalCatalog.load(CATALOG_PATH)
    business = next(
        item for item in contexts if item.field_id == "business-registration-number"
    )
    alien = next(
        item for item in contexts if item.field_id == "alien-registration-number"
    )

    assert business.field_type == "number"
    assert alien.field_type == "number"
    assert "company.business_number" in {
        item.field_id for item in catalog.compatible(business)
    }
    assert "identity.alien_registration_number" in {
        item.field_id for item in catalog.compatible(alien)
    }


def test_registry_fixture_and_type_union_match_actual_mcp_contract(
    registry_fixture: list[dict[str, object]],
) -> None:
    serialized = [
        RegistryField.model_validate(item).model_dump(mode="json")
        for item in registry_fixture
    ]

    assert serialized == registry_fixture
    assert set(get_args(MappingRegistryFieldType)) == set(get_args(McpRegistryFieldType))
