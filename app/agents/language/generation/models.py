from collections.abc import Mapping
from typing import Literal, Protocol, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.agents.language.contracts import ValidationCheckId, _normalize_bounded
from app.agents.language.ports import GenerationOperation

DraftT = TypeVar("DraftT", bound=BaseModel)


class EasyKoreanDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_reason: str = Field(..., min_length=1, max_length=1000)
    requested_items: tuple[str, ...] = Field(..., min_length=1, max_length=20)
    submission_method: str = Field(..., min_length=1, max_length=2000)

    @field_validator("request_reason", mode="before")
    @classmethod
    def _norm_reason(cls, value: object) -> object:
        return _normalize_bounded(value, field_name="request_reason", max_length=1000)

    @field_validator("requested_items", mode="before")
    @classmethod
    def _norm_items(cls, value: object) -> object:
        if isinstance(value, (list, tuple)):
            return tuple(
                _normalize_bounded(item, field_name="requested_items item", max_length=400)
                for item in value
            )
        return value

    @field_validator("submission_method", mode="before")
    @classmethod
    def _norm_sub_method(cls, value: object) -> object:
        return _normalize_bounded(value, field_name="submission_method", max_length=2000)


class TranslationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    translated_reason: str = Field(..., min_length=1, max_length=1000)
    translated_items: tuple[str, ...] = Field(..., min_length=1, max_length=20)
    translated_submission_method: str = Field(..., min_length=1, max_length=2000)

    @field_validator("translated_reason", mode="before")
    @classmethod
    def _norm_reason(cls, value: object) -> object:
        return _normalize_bounded(value, field_name="translated_reason", max_length=1000)

    @field_validator("translated_items", mode="before")
    @classmethod
    def _norm_items(cls, value: object) -> object:
        if isinstance(value, (list, tuple)):
            return tuple(
                _normalize_bounded(item, field_name="translated_items item", max_length=400)
                for item in value
            )
        return value

    @field_validator("translated_submission_method", mode="before")
    @classmethod
    def _norm_sub_method(cls, value: object) -> object:
        return _normalize_bounded(
            value, field_name="translated_submission_method", max_length=2000
        )


class SemanticValidationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["passed", "failed", "inconclusive"]
    failed_checks: tuple[ValidationCheckId, ...] = ()
    inconclusive_checks: tuple[ValidationCheckId, ...] = ()

    @model_validator(mode="after")
    def validate_status_contract(self) -> "SemanticValidationDraft":
        if self.status == "passed" and (self.failed_checks or self.inconclusive_checks):
            raise ValueError("passed validation cannot contain failed or inconclusive checks")
        if self.status == "failed" and (
            not self.failed_checks or self.inconclusive_checks
        ):
            raise ValueError("failed validation requires only failed checks")
        if self.status == "inconclusive" and (
            self.failed_checks or not self.inconclusive_checks
        ):
            raise ValueError("inconclusive validation requires only inconclusive checks")
        return self


class StructuredGenerator(Protocol):
    def generate(
        self,
        *,
        operation: GenerationOperation,
        payload: Mapping[str, object],
        response_model: type[DraftT],
    ) -> DraftT: ...


__all__ = [
    "DraftT",
    "EasyKoreanDraft",
    "SemanticValidationDraft",
    "StructuredGenerator",
    "TranslationDraft",
]
