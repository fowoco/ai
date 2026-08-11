from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.documents.dynamic_automation.catalog import CanonicalCatalog
from app.documents.dynamic_automation.field_context import build_field_contexts
from app.documents.dynamic_automation.models import DocumentFieldContext
from app.documents.dynamic_automation.rules import classify_non_data, exact_alias_matches

FIXTURE_DIR = Path(__file__).parents[2] / "fixtures" / "dynamic_automation"
CATALOG_PATH = (
    Path(__file__).parents[3]
    / "app"
    / "documents"
    / "dynamic_automation"
    / "resources"
    / "canonical_fields.v1.yaml"
)


def make_context(
    *, label: str, section: str = "", kind: str = "text_field", field_type: str = "text"
) -> DocumentFieldContext:
    return DocumentFieldContext(
        field_id="field-1",
        label=label,
        normalized_label=label,
        field_type=field_type,
        document_title="신청서",
        section=section,
        row_labels=(),
        nearby_labels=(),
        options=(),
        repeat_index=0,
        required=False,
        kind=kind,
    )


@pytest.mark.parametrize(
    ("label", "reason"),
    [
        ("확인검토", "process_flow_label"),
        ("→", "page_navigation_label"),
        ("For Official Use", "official_use_label"),
    ],
)
def test_non_data_labels_are_rejected(label: str, reason: str) -> None:
    decision = classify_non_data(make_context(label=label, section="처리절차"))

    assert decision.is_non_data is True
    assert decision.reason == reason


@pytest.mark.parametrize("kind", ["official_region", "signable_region"])
def test_non_data_regions_are_rejected(kind: str) -> None:
    decision = classify_non_data(make_context(label="입력란", kind=kind))

    assert decision.is_non_data is True
    assert decision.reason == kind


def test_exact_aliases_return_compatible_candidates_without_substring_matches() -> None:
    catalog = CanonicalCatalog.load(CATALOG_PATH)
    exact = make_context(label="전화번호", field_type="phone")
    substring = make_context(label="전화번호 안내", field_type="phone")

    assert [item.field_id for item in exact_alias_matches(exact, catalog)] == ["company.phone"]
    assert exact_alias_matches(substring, catalog) == ()


def test_extension_registry_rejects_process_flow_labels() -> None:
    registry = json.loads(
        (FIXTURE_DIR / "extension_application_registry.json").read_text(encoding="utf-8")
    )
    contexts = build_field_contexts(registry, document_title="신청서")

    intake = next(item for item in contexts if item.field_id == "intake")
    assert classify_non_data(intake).reason == "process_flow_label"
