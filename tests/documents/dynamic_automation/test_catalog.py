from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.documents.dynamic_automation.catalog import CanonicalCatalog
from app.documents.dynamic_automation.models import DocumentFieldContext

DEFAULT_CATALOG_PATH = (
    Path(__file__).parents[3]
    / "app"
    / "documents"
    / "dynamic_automation"
    / "resources"
    / "canonical_fields.v1.yaml"
)

VALID_FIELD = """
version: v1
fields:
  - field_id: company.phone
    entity: company
    value_type: phone
    aliases: [전화번호, Company phone]
    description: Company contact telephone number.
    compatible_field_types: [phone, text]
    source:
      view: document_company_view
      column: phone
      scope_keys: [tenant_id, company_id]
    sensitivity: business
    formatter: phone
"""


def _context(*, field_type: str = "phone", repeat_index: int = 0) -> DocumentFieldContext:
    return DocumentFieldContext(
        field_id="field-1",
        label="전화번호",
        normalized_label="전화번호",
        field_type=field_type,
        document_title="통합신청서",
        section="현재 근무처",
        row_labels=("현재 근무처", "전화번호"),
        nearby_labels=(),
        options=(),
        repeat_index=repeat_index,
        required=True,
        kind="text_field",
    )


def test_catalog_rejects_duplicate_ids_and_unapproved_identifiers(tmp_path: Path) -> None:
    path = tmp_path / "catalog.yaml"
    path.write_text(
        VALID_FIELD
        + """
  - field_id: company.phone
    entity: company
    value_type: phone
    aliases: [전화번호]
    description: Duplicate.
    compatible_field_types: [phone]
    source:
      view: document_company_view
      column: phone
      scope_keys: [tenant_id, company_id]
    sensitivity: business
    formatter: phone
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate"):
        CanonicalCatalog.load(path)

    path.write_text(
        VALID_FIELD.replace("document_company_view", "document-company-view"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="identifier"):
        CanonicalCatalog.load(path)


def test_catalog_returns_known_field_and_rejects_unknown_field() -> None:
    catalog = CanonicalCatalog.load(DEFAULT_CATALOG_PATH)

    assert catalog.get("company.phone").source.column == "phone"
    with pytest.raises(KeyError, match="unknown canonical field"):
        catalog.get("company.unknown")


def test_compatible_filters_wrong_type_and_non_repeatable_role() -> None:
    catalog = CanonicalCatalog.load(DEFAULT_CATALOG_PATH)

    compatible_ids = {item.field_id for item in catalog.compatible(_context())}
    assert "company.phone" in compatible_ids
    assert "worker.date_of_birth" not in compatible_ids

    repeated_ids = {item.field_id for item in catalog.compatible(_context(repeat_index=1))}
    assert "company.phone" not in repeated_ids


def test_document_field_context_rejects_oversized_labels_and_options() -> None:
    with pytest.raises(ValidationError):
        DocumentFieldContext(**{**_context().model_dump(), "row_labels": ("x" * 201,)})

    with pytest.raises(ValidationError):
        DocumentFieldContext(**{**_context().model_dump(), "nearby_labels": ("x" * 201,)})

    with pytest.raises(ValidationError):
        DocumentFieldContext(
            **{**_context().model_dump(), "options": tuple("option" for _ in range(51))}
        )

    with pytest.raises(ValidationError):
        DocumentFieldContext(**{**_context().model_dump(), "options": ("x" * 201,)})
