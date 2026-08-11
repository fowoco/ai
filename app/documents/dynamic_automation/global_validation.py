"""Document-wide validation for independently mapped fields."""

from __future__ import annotations

from collections import defaultdict

from .catalog import CanonicalCatalog
from .models import CanonicalMappingPlan, FieldMapping, MappingStatus


def validate_global_mapping(
    plan: CanonicalMappingPlan, catalog: CanonicalCatalog
) -> CanonicalMappingPlan:
    """Downgrade globally conflicting matches without changing unresolved fields."""
    reasons: dict[int, str] = {}
    matched_by_canonical: dict[str, list[tuple[int, FieldMapping]]] = defaultdict(list)

    for index, mapping in enumerate(plan.mappings):
        if mapping.status is not MappingStatus.MATCHED:
            continue
        canonical_field_id = mapping.canonical_field_id
        if canonical_field_id is None:
            continue
        if (
            plan.catalog_version != catalog.version
            or mapping.evidence.catalog_version != catalog.version
        ):
            reasons[index] = "catalog_version_mismatch"
        elif not _has_complete_match_evidence(mapping):
            reasons[index] = "incomplete_mapping_evidence"
        definition = catalog.get(canonical_field_id)
        if (
            mapping.evidence.entity_hint is not None
            and mapping.evidence.entity_hint != definition.entity
        ):
            reasons.setdefault(index, "incompatible_entity_role")
        matched_by_canonical[canonical_field_id].append((index, mapping))

    for canonical_field_id, indexed_mappings in matched_by_canonical.items():
        definition = catalog.get(canonical_field_id)
        if not definition.repeatable and len(indexed_mappings) > 1:
            for index, _ in indexed_mappings:
                reasons.setdefault(index, "duplicate_non_repeatable_canonical_field")
            continue

        by_repeat_index: dict[int, list[int]] = defaultdict(list)
        for index, mapping in indexed_mappings:
            by_repeat_index[mapping.repeat_index].append(index)
        for indexes in by_repeat_index.values():
            if len(indexes) > 1:
                for index in indexes:
                    reasons.setdefault(index, "duplicate_repeat_index")

    mappings = tuple(
        _downgrade(mapping, reasons[index]) if index in reasons else mapping
        for index, mapping in enumerate(plan.mappings)
    )
    return plan.model_copy(update={"mappings": mappings})


def _has_complete_match_evidence(mapping: FieldMapping) -> bool:
    evidence = mapping.evidence
    common_complete = evidence.type_compatible is True and bool(evidence.model_version)
    if evidence.rule == "exact_alias":
        return (
            common_complete
            and evidence.reason == "exact_alias"
            and evidence.entity_hint is not None
        )
    if evidence.rule == "semantic_decision_gate":
        return (
            common_complete
            and evidence.reason == "decision_gate_passed"
            and evidence.embedding_rank is not None
            and evidence.reranker_score is not None
            and evidence.score_margin is not None
        )
    return False


def _downgrade(mapping: FieldMapping, reason: str) -> FieldMapping:
    evidence = mapping.evidence.model_copy(update={"reason": reason})
    return mapping.model_copy(
        update={
            "status": MappingStatus.AMBIGUOUS,
            "canonical_field_id": None,
            "evidence": evidence,
        }
    )
