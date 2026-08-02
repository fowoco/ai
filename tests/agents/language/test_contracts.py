import json
from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from app.agents.language.contracts import (
    ComponentStatus,
    ComponentValidation,
    LanguageAssistantInput,
    LanguageAssistantOutput,
    RetrievalMetadata,
    ValidationSummary,
    WarningCode,
    WarningItem,
)


def input_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "worker_id": "worker-1",
        "preferred_language": "vi",
        "nationality_code": "VN",
        "request_context": {
            "request_reason": "체류기간 연장 신청",
            "requested_items": ["여권 사본", "외국인등록증"],
            "deadline": "2026-08-10",
            "submission_method": "이메일로 보내 주세요.",
        },
    }
    data.update(overrides)
    return data


def validation(
    status: str = "passed",
    *,
    failed_checks: tuple[str, ...] = (),
    inconclusive_checks: tuple[str, ...] = (),
    retry_count: int = 0,
) -> ComponentValidation:
    return ComponentValidation(
        status=status,
        failed_checks=failed_checks,
        inconclusive_checks=inconclusive_checks,
        retry_count=retry_count,
    )


def output_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "worker_id": "worker-1",
        "target_language": "vi",
        "generation_status": "success",
        "requires_human_review": False,
        "standard_korean_text": "표준 요청",
        "easy_korean_text": "쉬운 요청",
        "translated_text": "translated request",
        "component_status": {
            "standard_korean": "success",
            "easy_korean": "success",
            "translation": "success",
        },
        "validation": {
            "standard_korean": validation(),
            "easy_korean": validation(),
            "translation": validation(),
        },
        "warnings": (),
        "retrieval_metadata": {
            "dataset_version": "sha256:dataset",
            "query_strategies": ("canonical", "reason_items", "action_deadline"),
            "reference_ids": (),
            "reference_count": 0,
            "fallback_used": False,
            "degraded_components": (),
        },
    }
    data.update(overrides)
    return data


def test_accepts_structured_request_context() -> None:
    value = LanguageAssistantInput.model_validate(input_data())

    assert value.request_context.requested_items == ("여권 사본", "외국인등록증")
    assert value.request_context.deadline == date(2026, 8, 10)


@pytest.mark.parametrize("field", ["source_text", "message_context"])
def test_rejects_removed_top_level_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        LanguageAssistantInput.model_validate(input_data(**{field: "ignored"}))


def test_rejects_missing_request_reason() -> None:
    data = input_data()
    del data["request_context"]["request_reason"]

    with pytest.raises(ValidationError):
        LanguageAssistantInput.model_validate(data)


def test_rejects_empty_requested_items() -> None:
    data = input_data(request_context={**input_data()["request_context"], "requested_items": []})

    with pytest.raises(ValidationError):
        LanguageAssistantInput.model_validate(data)


def test_rejects_invalid_deadline() -> None:
    data = input_data(
        request_context={**input_data()["request_context"], "deadline": "2026/08/10"}
    )

    with pytest.raises(ValidationError):
        LanguageAssistantInput.model_validate(data)


def test_rejects_values_over_approved_length_and_item_count_bounds() -> None:
    base_context = input_data()["request_context"]

    with pytest.raises(ValidationError):
        LanguageAssistantInput.model_validate(
            input_data(request_context={**base_context, "request_reason": "x" * 501})
        )

    with pytest.raises(ValidationError):
        LanguageAssistantInput.model_validate(
            input_data(
                request_context={
                    **base_context,
                    "requested_items": [f"item-{index}" for index in range(21)],
                }
            )
        )

    with pytest.raises(ValidationError):
        LanguageAssistantInput.model_validate(
            input_data(
                request_context={
                    **base_context,
                    "submission_method": "x" * 1001,
                }
            )
        )


def test_trims_and_nfc_normalizes_strings() -> None:
    data = input_data(
        worker_id="  cafe\u0301  ",
        preferred_language="  vi  ",
        nationality_code=" VN ",
        request_context={
            "request_reason": "  cafe\u0301 신청 ",
            "requested_items": ["  여권 사본  "],
            "deadline": "2026-08-10",
            "submission_method": "  이메일  ",
        },
    )

    value = LanguageAssistantInput.model_validate(data)

    assert value.worker_id == "café"
    assert value.preferred_language == "vi"
    assert value.nationality_code == "VN"
    assert value.request_context.request_reason == "café 신청"
    assert value.request_context.requested_items == ("여권 사본",)
    assert value.request_context.submission_method == "이메일"


def test_worker_id_is_opaque_and_preserves_string_or_integer_type() -> None:
    string_value = LanguageAssistantInput.model_validate(input_data(worker_id=" 001 "))
    integer_value = LanguageAssistantInput.model_validate(input_data(worker_id=1))

    assert string_value.worker_id == "001"
    assert isinstance(string_value.worker_id, str)
    assert integer_value.worker_id == 1
    assert isinstance(integer_value.worker_id, int)


@pytest.mark.parametrize("worker_id", [True, False, 1.5, -1, 2**63])
def test_rejects_boolean_float_and_out_of_range_worker_id(worker_id: object) -> None:
    with pytest.raises(ValidationError):
        LanguageAssistantInput.model_validate(input_data(worker_id=worker_id))


def test_output_supports_last_candidate_with_warning() -> None:
    value = LanguageAssistantOutput.model_validate(
        output_data(
            generation_status="warning",
            requires_human_review=True,
            component_status={
                "standard_korean": "success",
                "easy_korean": "success",
                "translation": "warning",
            },
            validation={
                "standard_korean": validation(),
                "easy_korean": validation(),
                "translation": validation(
                    "inconclusive",
                    inconclusive_checks=("requested_items.semantic_equivalence",),
                    retry_count=2,
                ),
            },
            warnings=(
                WarningItem(
                    component="translation_validation",
                    code=WarningCode.VALIDATION_RETRY_EXCEEDED,
                    message="일부 정보 보존 검증이 완료되지 않았습니다.",
                ),
            ),
        )
    )

    assert value.translated_text == "translated request"
    assert value.validation.translation.retry_count == 2


def test_output_accepts_clean_success() -> None:
    value = LanguageAssistantOutput.model_validate(output_data())

    assert value.generation_status == "success"
    assert value.requires_human_review is False


def test_output_supports_missing_translation_after_hard_failure() -> None:
    value = LanguageAssistantOutput.model_validate(
        output_data(
            generation_status="failed",
            requires_human_review=True,
            translated_text=None,
            component_status={
                "standard_korean": "success",
                "easy_korean": "success",
                "translation": "failed",
            },
            validation={
                "standard_korean": validation(),
                "easy_korean": validation(),
                "translation": validation("not_run"),
            },
            warnings=(
                WarningItem(
                    component="translation_generation",
                    code=WarningCode.TRANSLATION_GENERATION_FAILED,
                    message="번역 후보를 만들지 못했습니다.",
                ),
            ),
        )
    )

    assert value.generation_status == "failed"
    assert value.translated_text is None


def test_component_validation_rejects_contradictory_status_and_check_lists() -> None:
    with pytest.raises(ValidationError):
        ComponentValidation(
            status="passed",
            failed_checks=("facts.no_addition",),
        )

    with pytest.raises(ValidationError):
        ComponentValidation(
            status="inconclusive",
            failed_checks=("facts.no_addition",),
            inconclusive_checks=("facts.no_semantic_addition",),
        )

    with pytest.raises(ValidationError):
        ComponentValidation(status="not_run", retry_count=1)


def test_missing_translation_requires_not_run_validation() -> None:
    with pytest.raises(ValidationError):
        LanguageAssistantOutput.model_validate(
            output_data(
                generation_status="failed",
                requires_human_review=True,
                translated_text=None,
                component_status={
                    "standard_korean": "success",
                    "easy_korean": "success",
                    "translation": "failed",
                },
                validation={
                    "standard_korean": validation(),
                    "easy_korean": validation(),
                    "translation": validation("passed"),
                },
            )
        )


def test_easy_standard_fallback_requires_not_run_validation_and_warning_status() -> None:
    value = LanguageAssistantOutput.model_validate(
        output_data(
            generation_status="warning",
            requires_human_review=True,
            easy_korean_text="표준 요청",
            component_status={
                "standard_korean": "success",
                "easy_korean": "warning",
                "translation": "success",
            },
            validation={
                "standard_korean": validation(),
                "easy_korean": validation("not_run"),
                "translation": validation(),
            },
            warnings=(
                WarningItem(
                    component="easy_korean",
                    code=WarningCode.STANDARD_KOREAN_FALLBACK,
                    message="쉬운 한국어 후보가 없어 일반 한국어를 사용했습니다.",
                ),
            ),
        )
    )

    assert value.easy_korean_text == value.standard_korean_text


def test_output_schema_has_no_removed_fields() -> None:
    schema_text = json.dumps(LanguageAssistantOutput.model_json_schema())

    for removed_field in (
        "source_text",
        "message_context",
        "worker_documents",
        "company",
        "send_allowed",
        "delivery_recommendation",
        "pronunciation",
        "romanization",
    ):
        assert removed_field not in schema_text


def test_retrieval_metadata_requires_reference_count_match() -> None:
    with pytest.raises(ValidationError):
        LanguageAssistantOutput.model_validate(
            output_data(
                retrieval_metadata=RetrievalMetadata(
                    dataset_version="sha256:dataset",
                    query_strategies=("canonical",),
                    reference_ids=("point-1",),
                    reference_count=0,
                    fallback_used=False,
                    degraded_components=(),
                )
            )
        )


def test_component_status_model_is_explicit() -> None:
    assert ComponentStatus.model_fields.keys() == {
        "standard_korean",
        "easy_korean",
        "translation",
    }


def test_validation_summary_model_is_explicit() -> None:
    assert ValidationSummary.model_fields.keys() == {
        "standard_korean",
        "easy_korean",
        "translation",
    }
