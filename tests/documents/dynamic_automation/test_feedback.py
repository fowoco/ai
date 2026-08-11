from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.documents.dynamic_automation.feedback import (
    JsonlMappingFeedbackStore,
    MappingFeedbackRecord,
    ReviewerDecision,
)
from app.documents.dynamic_automation.models import (
    CanonicalMappingPlan,
    DocumentFieldContext,
    FieldMapping,
    MappingEvidence,
    MappingStatus,
    ScoredCandidate,
)


def feedback_payload(**updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "v1",
        "layout_hash": "a" * 64,
        "field_context_hash": "b" * 64,
        "field_id": "passport-field-1",
        "repeat_index": 0,
        "label": "Passport number",
        "section": "Identity",
        "row_labels": ["Identity", "Passport number"],
        "nearby_labels": ["Nationality"],
        "predicted_status": "MATCHED",
        "predicted_canonical_field_id": "identity.passport_number",
        "final_canonical_field_id": "identity.passport_number",
        "decision": "accepted",
        "candidate_scores": [
            {
                "canonical_field_id": "identity.passport_number",
                "score": 1.0,
                "rank": 1,
            }
        ],
        "catalog_version": "v1",
        "model_version": "deterministic-rules-v1",
    }
    payload.update(updates)
    return payload


def test_feedback_schema_has_no_value_field() -> None:
    schema = MappingFeedbackRecord.model_json_schema()
    serialized = json.dumps(schema)

    assert "resolved_value" not in serialized
    assert "db_value" not in serialized
    assert "document_value" not in serialized


@pytest.mark.parametrize(
    "forbidden_key",
    ("resolved_value", "passport", "registration_number", "resident_number"),
)
def test_feedback_rejects_extra_and_sensitive_keys(forbidden_key: str) -> None:
    with pytest.raises(ValidationError):
        MappingFeedbackRecord.model_validate(
            {**feedback_payload(), forbidden_key: "must-never-be-persisted"}
        )


def test_sensitive_words_are_allowed_inside_valid_canonical_ids() -> None:
    record = MappingFeedbackRecord.model_validate(feedback_payload())

    assert record.predicted_canonical_field_id == "identity.passport_number"
    assert record.final_canonical_field_id == "identity.passport_number"
    assert record.candidate_scores[0].canonical_field_id == "identity.passport_number"


def test_feedback_bounds_structural_text() -> None:
    with pytest.raises(ValidationError):
        MappingFeedbackRecord.model_validate(feedback_payload(label="x" * 201))


@pytest.mark.parametrize(
    "updates",
    (
        {"predicted_canonical_field_id": "identity." + "x" * 200},
        {"final_canonical_field_id": "identity." + "x" * 200},
        {
            "candidate_scores": [
                {
                    "canonical_field_id": "identity." + "x" * 200,
                    "score": 1.0,
                    "rank": 1,
                }
            ]
        },
        {"catalog_version": "v" + "1" * 200},
    ),
)
def test_feedback_bounds_every_persisted_identifier(updates: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        MappingFeedbackRecord.model_validate(feedback_payload(**updates))


def test_feedback_rejects_inconsistent_matched_prediction() -> None:
    with pytest.raises(ValidationError):
        MappingFeedbackRecord.model_validate(
            feedback_payload(predicted_canonical_field_id=None)
        )


def test_feedback_builds_deterministic_record_from_mapping_plan() -> None:
    context = DocumentFieldContext(
        field_id="passport-field-1",
        label="Passport number",
        normalized_label="passportnumber",
        field_type="passport_number",
        document_title="Employment application",
        section="Identity",
        row_labels=("Identity", "Passport number"),
        nearby_labels=("Nationality",),
        options=(),
        repeat_index=0,
        required=True,
        kind="text_field",
    )
    plan = CanonicalMappingPlan(
        catalog_version="v1",
        mappings=(
            FieldMapping(
                field_id=context.field_id,
                repeat_index=0,
                status=MappingStatus.MATCHED,
                canonical_field_id="identity.passport_number",
                candidates=(
                    ScoredCandidate(
                        canonical_field_id="identity.passport_number", score=1.0, rank=1
                    ),
                ),
                evidence=MappingEvidence(
                    reason="exact_alias",
                    catalog_version="v1",
                    model_version="deterministic-rules-v1",
                ),
            ),
        ),
    )

    record = MappingFeedbackRecord.from_review(
        plan,
        context,
        layout_hash="a" * 64,
        decision=ReviewerDecision.ACCEPTED,
        final_canonical_field_id="identity.passport_number",
    )

    assert record.field_context_hash == (
        "428f0f637ef4c20f9e085ee4b25c30af9f5d2ec6822e7f3bdc4555eba35ddc5a"
    )
    assert [candidate.model_dump() for candidate in record.candidate_scores] == [
        {
            "canonical_field_id": "identity.passport_number",
            "score": 1.0,
            "rank": 1,
        }
    ]
    assert record.model_version == "deterministic-rules-v1"


def test_feedback_store_appends_one_valid_json_object_per_line(tmp_path: Path) -> None:
    path = tmp_path / "mapping-feedback.jsonl"
    store = JsonlMappingFeedbackStore(path)
    first = MappingFeedbackRecord.model_validate(feedback_payload())
    second = MappingFeedbackRecord.model_validate(
        feedback_payload(
            field_context_hash="c" * 64,
            predicted_status=MappingStatus.AMBIGUOUS,
            predicted_canonical_field_id=None,
            final_canonical_field_id="worker.legal_name",
            decision=ReviewerDecision.CORRECTED,
            candidate_scores=[],
        )
    )

    store.append(first)
    store.append(second)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["decision"] == "accepted"
    assert json.loads(lines[1])["decision"] == "corrected"
    assert "must-never-be-persisted" not in path.read_text(encoding="utf-8")


def test_feedback_store_accepts_records_only(tmp_path: Path) -> None:
    store = JsonlMappingFeedbackStore(tmp_path / "mapping-feedback.jsonl")

    with pytest.raises(TypeError):
        store.append(feedback_payload())  # type: ignore[arg-type]


def test_feedback_store_revalidates_constructed_records_before_writing(tmp_path: Path) -> None:
    path = tmp_path / "mapping-feedback.jsonl"
    store = JsonlMappingFeedbackStore(path)
    unvalidated = MappingFeedbackRecord.model_construct(
        **feedback_payload(label="x" * 201)
    )

    with pytest.raises(ValidationError):
        store.append(unvalidated)

    assert not path.exists()
