from __future__ import annotations

from pathlib import Path

from app.documents.dynamic_automation.catalog import CanonicalCatalog
from app.documents.dynamic_automation.global_validation import validate_global_mapping
from app.documents.dynamic_automation.models import (
    CanonicalMappingPlan,
    FieldMapping,
    MappingEvidence,
    MappingStatus,
)

CATALOG_YAML = """
version: v1
fields:
  - field_id: worker.legal_name
    entity: worker
    value_type: string
    aliases: [Name]
    description: Worker's legal name.
    compatible_field_types: [text]
    repeatable: false
    source: {view: document_worker_view, column: legal_name, scope_keys: [tenant_id, worker_id]}
    sensitivity: personal
    formatter: person_name
  - field_id: worker.dependent_name
    entity: worker
    value_type: string
    aliases: [Dependent name]
    description: Repeated dependent name.
    compatible_field_types: [text]
    repeatable: true
    source: {view: document_worker_view, column: dependent_name, scope_keys: [tenant_id, worker_id]}
    sensitivity: personal
    formatter: person_name
  - field_id: company.name
    entity: company
    value_type: string
    aliases: [Company]
    description: Company name.
    compatible_field_types: [text]
    repeatable: false
    source: {view: document_company_view, column: name, scope_keys: [tenant_id, company_id]}
    sensitivity: business
    formatter: string
"""


def make_catalog(tmp_path: Path) -> CanonicalCatalog:
    path = tmp_path / "catalog.yaml"
    path.write_text(CATALOG_YAML, encoding="utf-8")
    return CanonicalCatalog.load(path)


def matched(
    field_id: str,
    canonical_field_id: str,
    *,
    repeat_index: int = 0,
    entity_hint: str | None = None,
) -> FieldMapping:
    return FieldMapping(
        field_id=field_id,
        repeat_index=repeat_index,
        status=MappingStatus.MATCHED,
        canonical_field_id=canonical_field_id,
        evidence=MappingEvidence(
            reason="decision_gate_passed",
            rule="semantic_decision_gate",
            embedding_rank=1,
            reranker_score=0.96,
            score_margin=0.20,
            type_compatible=True,
            entity_hint=entity_hint,
            catalog_version="v1",
            model_version="fake-reranker-v1",
        ),
    )


def test_three_non_repeatable_identity_fields_are_all_downgraded(tmp_path: Path) -> None:
    catalog = make_catalog(tmp_path)
    mappings = tuple(
        matched(f"name-{index}", "worker.legal_name", repeat_index=index)
        for index in range(3)
    )

    result = validate_global_mapping(
        CanonicalMappingPlan(catalog_version="v1", mappings=mappings), catalog
    )

    assert [item.status for item in result.mappings] == [MappingStatus.AMBIGUOUS] * 3
    assert {item.evidence.reason for item in result.mappings} == {
        "duplicate_non_repeatable_canonical_field"
    }


def test_repeatable_field_allows_distinct_repeat_indexes(tmp_path: Path) -> None:
    catalog = make_catalog(tmp_path)
    mappings = (
        matched("dependent-1", "worker.dependent_name", repeat_index=0),
        matched("dependent-2", "worker.dependent_name", repeat_index=1),
    )

    result = validate_global_mapping(
        CanonicalMappingPlan(catalog_version="v1", mappings=mappings), catalog
    )

    assert [item.status for item in result.mappings] == [MappingStatus.MATCHED] * 2


def test_repeatable_field_duplicate_repeat_index_is_downgraded(tmp_path: Path) -> None:
    catalog = make_catalog(tmp_path)
    mappings = (
        matched("dependent-1", "worker.dependent_name", repeat_index=1),
        matched("dependent-2", "worker.dependent_name", repeat_index=1),
    )

    result = validate_global_mapping(
        CanonicalMappingPlan(catalog_version="v1", mappings=mappings), catalog
    )

    assert [item.status for item in result.mappings] == [MappingStatus.AMBIGUOUS] * 2
    assert {item.evidence.reason for item in result.mappings} == {"duplicate_repeat_index"}


def test_incompatible_entity_role_is_downgraded(tmp_path: Path) -> None:
    catalog = make_catalog(tmp_path)
    mapping = matched("employer", "company.name", entity_hint="worker")

    result = validate_global_mapping(
        CanonicalMappingPlan(catalog_version="v1", mappings=(mapping,)), catalog
    )

    assert result.mappings[0].status is MappingStatus.AMBIGUOUS
    assert result.mappings[0].evidence.reason == "incompatible_entity_role"


def test_incomplete_matched_evidence_is_downgraded(tmp_path: Path) -> None:
    catalog = make_catalog(tmp_path)
    mapping = FieldMapping(
        field_id="worker-name",
        repeat_index=0,
        status=MappingStatus.MATCHED,
        canonical_field_id="worker.legal_name",
        evidence=MappingEvidence(reason="decision_gate_passed", catalog_version="v1"),
    )

    result = validate_global_mapping(
        CanonicalMappingPlan(catalog_version="v1", mappings=(mapping,)), catalog
    )

    assert result.mappings[0].status is MappingStatus.AMBIGUOUS
    assert result.mappings[0].evidence.reason == "incomplete_mapping_evidence"


def test_catalog_version_mismatch_is_downgraded(tmp_path: Path) -> None:
    catalog = make_catalog(tmp_path)
    base_mapping = matched("worker-name", "worker.legal_name")
    mapping = base_mapping.model_copy(
        update={
            "evidence": base_mapping.evidence.model_copy(update={"catalog_version": "v2"})
        }
    )

    result = validate_global_mapping(
        CanonicalMappingPlan(catalog_version="v2", mappings=(mapping,)), catalog
    )

    assert result.mappings[0].status is MappingStatus.AMBIGUOUS
    assert result.mappings[0].evidence.reason == "catalog_version_mismatch"


def test_unknown_canonical_id_is_downgraded(tmp_path: Path) -> None:
    catalog = make_catalog(tmp_path)
    mapping = matched("rogue", "rogue.value")

    result = validate_global_mapping(
        CanonicalMappingPlan(catalog_version="v1", mappings=(mapping,)), catalog
    )

    assert result.mappings[0].status is MappingStatus.AMBIGUOUS
    assert result.mappings[0].evidence.reason == "unknown_canonical_field"


def test_non_data_and_unmapped_fields_remain_unchanged(tmp_path: Path) -> None:
    catalog = make_catalog(tmp_path)
    mappings = (
        FieldMapping(
            field_id="official",
            repeat_index=0,
            status=MappingStatus.NON_DATA,
            evidence=MappingEvidence(reason="official_region", catalog_version="v1"),
        ),
        FieldMapping(
            field_id="unknown",
            repeat_index=0,
            status=MappingStatus.UNMAPPED,
            evidence=MappingEvidence(reason="no_match", catalog_version="v1"),
        ),
    )

    plan = CanonicalMappingPlan(catalog_version="v1", mappings=mappings)

    assert validate_global_mapping(plan, catalog) == plan
