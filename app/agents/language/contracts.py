import re
import unicodedata
from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    StringConstraints,
    field_validator,
    model_validator,
)


def _normalize_bounded(
    value: object,
    *,
    field_name: str,
    min_length: int = 1,
    max_length: int,
) -> object:
    if not isinstance(value, str):
        return value
    normalized = value.strip()
    normalized = unicodedata.normalize("NFC", normalized)
    if not min_length <= len(normalized) <= max_length:
        raise ValueError(
            f"{field_name} must contain {min_length}..{max_length} characters"
        )
    return normalized


def _normalize_optional(
    value: object,
    *,
    field_name: str,
    max_length: int,
) -> object:
    if value is None:
        return None
    return _normalize_bounded(
        value,
        field_name=field_name,
        max_length=max_length,
    )


WorkerId = (
    Annotated[
        StrictStr,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
    ]
    | Annotated[
        StrictInt,
        Field(ge=0, le=9_223_372_036_854_775_807),
    ]
)

SupportedLanguage = Literal[
    "en",
    "zh-Hans",
    "vi",
    "th",
    "fil",
    "id",
    "mn",
    "si",
    "ru",
    "uz",
    "ky",
    "bn",
    "ur",
    "km",
    "tet",
]

EpsLanguageCode = Literal[
    "01",
    "02",
    "03",
    "04",
    "05",
    "06",
    "07",
    "08",
    "09",
    "10",
    "11",
    "13",
    "14",
    "15",
    "17",
]

GenerationStatus = Literal["success", "warning", "failed"]
ComponentGenerationStatus = Literal["success", "warning", "failed"]
ValidationStatus = Literal["passed", "failed", "inconclusive", "not_run"]
QueryStrategy = Literal["canonical", "reason_items", "action_deadline"]

ValidationCheckId = Literal[
    "request_reason.present",
    "requested_items.cardinality",
    "requested_items.source_alignment",
    "deadline.canonical_value",
    "submission_method.present",
    "machine_tokens.multiset",
    "facts.no_addition",
    "request_reason.semantic_equivalence",
    "requested_items.semantic_equivalence",
    "submission_method.semantic_equivalence",
    "modality.obligation",
    "modality.prohibition",
    "modality.warning_strength",
    "named_entities.semantic_preservation",
    "places.semantic_preservation",
    "documents.semantic_preservation",
    "legal_terms.semantic_preservation",
    "facts.no_semantic_addition",
]


class WarningCode(StrEnum):
    LANGUAGE_CODE_NORMALIZED = "LANGUAGE_CODE_NORMALIZED"
    LANGUAGE_INFERRED_FROM_NATIONALITY = "LANGUAGE_INFERRED_FROM_NATIONALITY"
    LANGUAGE_DEFAULTED_TO_EN = "LANGUAGE_DEFAULTED_TO_EN"
    DUPLICATE_REQUESTED_ITEM = "DUPLICATE_REQUESTED_ITEM"
    RETRIEVAL_NO_MATCH = "RETRIEVAL_NO_MATCH"
    RETRIEVAL_UNAVAILABLE = "RETRIEVAL_UNAVAILABLE"
    RETRIEVAL_ENCODER_UNAVAILABLE = "RETRIEVAL_ENCODER_UNAVAILABLE"
    RETRIEVAL_QUERY_TOO_LONG = "RETRIEVAL_QUERY_TOO_LONG"
    RETRIEVAL_DATASET_MISMATCH = "RETRIEVAL_DATASET_MISMATCH"
    RETRIEVAL_INDEX_PROVENANCE_MISMATCH = "RETRIEVAL_INDEX_PROVENANCE_MISMATCH"
    RETRIEVAL_SCHEMA_MISMATCH = "RETRIEVAL_SCHEMA_MISMATCH"
    RERANKER_UNAVAILABLE = "RERANKER_UNAVAILABLE"
    EPS_CONTEXT_INSUFFICIENT = "EPS_CONTEXT_INSUFFICIENT"
    TRANSLATION_FALLBACK_USED = "TRANSLATION_FALLBACK_USED"
    GENERATION_TIME_BUDGET_EXCEEDED = "GENERATION_TIME_BUDGET_EXCEEDED"
    EASY_KOREAN_CONTEXT_PACK_UNAVAILABLE = "EASY_KOREAN_CONTEXT_PACK_UNAVAILABLE"
    STANDARD_KOREAN_FALLBACK = "STANDARD_KOREAN_FALLBACK"
    SEMANTIC_VALIDATION_INCONCLUSIVE = "SEMANTIC_VALIDATION_INCONCLUSIVE"
    VALIDATION_RETRY_EXCEEDED = "VALIDATION_RETRY_EXCEEDED"
    EASY_KOREAN_GENERATION_FAILED = "EASY_KOREAN_GENERATION_FAILED"
    TRANSLATION_GENERATION_FAILED = "TRANSLATION_GENERATION_FAILED"


class FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RequestContext(FrozenContract):
    request_reason: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    requested_items: tuple[
        Annotated[str, StringConstraints(min_length=1, max_length=200)], ...
    ] = Field(min_length=1, max_length=20)
    deadline: date
    submission_method: Annotated[str, StringConstraints(min_length=1, max_length=1000)]

    @field_validator("request_reason", mode="before")
    @classmethod
    def normalize_request_reason(cls, value: object) -> object:
        return _normalize_bounded(
            value,
            field_name="request_reason",
            max_length=500,
        )

    @field_validator("requested_items", mode="before")
    @classmethod
    def normalize_requested_items(cls, value: object) -> object:
        if not isinstance(value, (list, tuple)):
            return value
        return tuple(
            _normalize_bounded(item, field_name="requested_items item", max_length=200)
            for item in value
        )

    @field_validator("submission_method", mode="before")
    @classmethod
    def normalize_submission_method(cls, value: object) -> object:
        return _normalize_bounded(
            value,
            field_name="submission_method",
            max_length=1000,
        )

    @field_validator("deadline", mode="before")
    @classmethod
    def require_iso_date(cls, value: object) -> object:
        if isinstance(value, datetime):
            raise ValueError("deadline must be an ISO date, not datetime")
        if isinstance(value, str) and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("deadline must use YYYY-MM-DD")
        return value


class LanguageAssistantInput(FrozenContract):
    worker_id: WorkerId
    preferred_language: Annotated[str, StringConstraints(min_length=1, max_length=32)] | None = None
    nationality_code: Annotated[str, StringConstraints(min_length=1, max_length=8)] | None = None
    request_context: RequestContext

    @field_validator("worker_id", mode="before")
    @classmethod
    def normalize_worker_id(cls, value: object) -> object:
        return _normalize_bounded(
            value,
            field_name="worker_id",
            max_length=128,
        )

    @field_validator("preferred_language", mode="before")
    @classmethod
    def normalize_preferred_language(cls, value: object) -> object:
        return _normalize_optional(
            value,
            field_name="preferred_language",
            max_length=32,
        )

    @field_validator("nationality_code", mode="before")
    @classmethod
    def normalize_nationality_code(cls, value: object) -> object:
        return _normalize_optional(
            value,
            field_name="nationality_code",
            max_length=8,
        )


class WarningItem(FrozenContract):
    component: str
    code: WarningCode
    message: str


class ComponentValidation(FrozenContract):
    status: ValidationStatus
    failed_checks: tuple[ValidationCheckId, ...] = ()
    inconclusive_checks: tuple[ValidationCheckId, ...] = ()
    retry_count: int = Field(ge=0, le=2)

    @model_validator(mode="after")
    def validate_status_contract(self) -> "ComponentValidation":
        if self.status == "passed" and (self.failed_checks or self.inconclusive_checks):
            raise ValueError("passed validation cannot contain failed or inconclusive checks")
        if self.status == "failed" and not self.failed_checks:
            raise ValueError("failed validation requires failed checks")
        if self.status == "inconclusive":
            if self.failed_checks or not self.inconclusive_checks:
                raise ValueError(
                    "inconclusive validation requires only inconclusive checks"
                )
        if self.status == "not_run" and (
            self.failed_checks or self.inconclusive_checks or self.retry_count != 0
        ):
            raise ValueError("not_run validation cannot contain checks or retries")
        return self


class ValidationSummary(FrozenContract):
    standard_korean: ComponentValidation
    easy_korean: ComponentValidation
    translation: ComponentValidation


class ComponentStatus(FrozenContract):
    standard_korean: ComponentGenerationStatus
    easy_korean: ComponentGenerationStatus
    translation: ComponentGenerationStatus


class RetrievalMetadata(FrozenContract):
    dataset_version: str | None
    query_strategies: tuple[QueryStrategy, ...]
    reference_ids: tuple[str, ...]
    reference_count: int = Field(ge=0)
    fallback_used: bool
    degraded_components: tuple[str, ...]


class LanguageAssistantOutput(FrozenContract):
    worker_id: WorkerId
    target_language: SupportedLanguage
    generation_status: GenerationStatus
    requires_human_review: bool
    standard_korean_text: str
    easy_korean_text: str
    translated_text: str | None
    component_status: ComponentStatus
    validation: ValidationSummary
    warnings: tuple[WarningItem, ...]
    retrieval_metadata: RetrievalMetadata

    @model_validator(mode="after")
    def validate_output_contract(self) -> "LanguageAssistantOutput":
        standard_status = self.component_status.standard_korean
        easy_status = self.component_status.easy_korean
        translation_status = self.component_status.translation
        standard_validation = self.validation.standard_korean
        easy_validation = self.validation.easy_korean
        translation_validation = self.validation.translation

        if standard_status != "success" or standard_validation.status != "passed":
            raise ValueError("standard Korean must always be success/passed")
        if not self.standard_korean_text:
            raise ValueError("standard Korean text must not be empty")
        if not self.easy_korean_text:
            raise ValueError("easy Korean text must not be empty")
        if easy_status == "success" and easy_validation.status != "passed":
            raise ValueError("successful easy Korean requires passed validation")
        if easy_status == "failed":
            raise ValueError("easy Korean must fall back with warning, not failed status")

        if self.translated_text is None:
            if translation_status != "failed":
                raise ValueError("missing translation requires failed status")
            if translation_validation.status != "not_run":
                raise ValueError("missing translation requires not_run validation")
        elif translation_status == "failed":
            raise ValueError("failed translation requires no candidate")

        if self.retrieval_metadata.reference_count != len(
            self.retrieval_metadata.reference_ids
        ):
            raise ValueError("reference_count must match reference_ids")

        expected_status: GenerationStatus
        if self.translated_text is None:
            expected_status = "failed"
        else:
            degraded = (
                easy_status != "success"
                or translation_status != "success"
                or any(
                    component.status != "passed"
                    for component in (
                        self.validation.standard_korean,
                        self.validation.easy_korean,
                        self.validation.translation,
                    )
                )
                or bool(self.warnings)
            )
            expected_status = "warning" if degraded else "success"

        if self.generation_status != expected_status:
            raise ValueError(
                f"generation_status must be {expected_status} for component results"
            )
        if self.requires_human_review != (self.generation_status != "success"):
            raise ValueError("requires_human_review must reflect generation_status")
        return self
