"""Privacy-safe, append-only reviewer feedback for mapping decisions."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import CanonicalMappingPlan, DocumentFieldContext, MappingStatus, ScoredCandidate

_CANONICAL_ID_PATTERN = r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$"
_HASH_PATTERN = r"^[0-9a-f]{64}$"
_FORBIDDEN_KEY = re.compile(
    r"(?:^|[_.-])(?:value|passport|registration_number|resident_number)(?:$|[_.-])",
    flags=re.IGNORECASE,
)


class ReviewerDecision(StrEnum):
    ACCEPTED = "accepted"
    CORRECTED = "corrected"
    REJECTED = "rejected"


class MappingFeedbackRecord(BaseModel):
    """Value-free metadata for one reviewed field-mapping decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["v1"] = "v1"
    layout_hash: str = Field(pattern=_HASH_PATTERN)
    field_context_hash: str = Field(pattern=_HASH_PATTERN)
    field_id: str = Field(min_length=1, max_length=200)
    repeat_index: int = Field(ge=0)
    label: str = Field(max_length=200)
    section: str = Field(max_length=200)
    row_labels: tuple[Annotated[str, Field(max_length=200)], ...] = Field(max_length=3)
    nearby_labels: tuple[Annotated[str, Field(max_length=200)], ...] = Field(max_length=4)
    predicted_status: MappingStatus
    predicted_canonical_field_id: str | None = Field(
        default=None, pattern=_CANONICAL_ID_PATTERN
    )
    final_canonical_field_id: str | None = Field(default=None, pattern=_CANONICAL_ID_PATTERN)
    decision: ReviewerDecision
    candidate_scores: tuple[ScoredCandidate, ...] = Field(default=(), max_length=20)
    catalog_version: str = Field(pattern=r"^v[1-9][0-9]*$")
    model_version: str | None = Field(default=None, max_length=200)

    @model_validator(mode="before")
    @classmethod
    def _reject_sensitive_keys(cls, value: Any) -> Any:
        _validate_keys(value)
        return value

    @model_validator(mode="after")
    def _validate_prediction(self) -> MappingFeedbackRecord:
        has_id = self.predicted_canonical_field_id is not None
        if (self.predicted_status is MappingStatus.MATCHED) != has_id:
            raise ValueError("only matched predictions may include a canonical field ID")
        return self

    @classmethod
    def from_review(
        cls,
        plan: CanonicalMappingPlan,
        context: DocumentFieldContext,
        *,
        layout_hash: str,
        decision: ReviewerDecision,
        final_canonical_field_id: str | None,
    ) -> MappingFeedbackRecord:
        """Build one record from an existing mapping plan and reviewer decision."""
        matches = tuple(
            mapping
            for mapping in plan.mappings
            if mapping.field_id == context.field_id
            and mapping.repeat_index == context.repeat_index
        )
        if len(matches) != 1:
            raise ValueError("mapping plan must contain exactly one matching field context")
        mapping = matches[0]
        return cls(
            layout_hash=layout_hash,
            field_context_hash=hash_field_context(context),
            field_id=context.field_id,
            repeat_index=context.repeat_index,
            label=context.label,
            section=context.section,
            row_labels=context.row_labels,
            nearby_labels=context.nearby_labels,
            predicted_status=mapping.status,
            predicted_canonical_field_id=mapping.canonical_field_id,
            final_canonical_field_id=final_canonical_field_id,
            decision=decision,
            candidate_scores=mapping.candidates,
            catalog_version=plan.catalog_version,
            model_version=mapping.evidence.model_version,
        )

class JsonlMappingFeedbackStore:
    """Append validated feedback records without providing update or delete operations."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, record: MappingFeedbackRecord) -> None:
        if not isinstance(record, MappingFeedbackRecord):
            raise TypeError("record must be a MappingFeedbackRecord")
        validated = MappingFeedbackRecord.model_validate(
            record.model_dump(mode="json", warnings="none")
        )
        serialized = json.dumps(
            validated.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(serialized)
            stream.write("\n")


def hash_field_context(context: DocumentFieldContext) -> str:
    """Return a deterministic hash without retaining an unbounded source payload."""
    serialized = json.dumps(
        context.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _validate_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str) or _FORBIDDEN_KEY.search(key):
                raise ValueError(f"feedback contains a forbidden key: {key!r}")
            _validate_keys(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _validate_keys(nested)
