"""Strict, value-free contracts for dynamic field mapping."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MappingStatus(StrEnum):
    MATCHED = "MATCHED"
    AMBIGUOUS = "AMBIGUOUS"
    UNMAPPED = "UNMAPPED"
    NON_DATA = "NON_DATA"


class CanonicalSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    view: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    column: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    scope_keys: tuple[Literal["tenant_id", "worker_id", "company_id", "task_id"], ...]


class CanonicalFieldDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field_id: str = Field(pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
    entity: str
    value_type: str
    aliases: tuple[str, ...]
    description: str
    compatible_field_types: tuple[str, ...]
    repeatable: bool = False
    source: CanonicalSource
    sensitivity: Literal["public", "business", "personal", "sensitive"]
    formatter: str


class DocumentFieldContext(BaseModel):
    """Bounded structural context for one untrusted document field."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field_id: str = Field(min_length=1, max_length=200)
    label: str = Field(max_length=200)
    normalized_label: str = Field(max_length=200)
    field_type: str = Field(min_length=1, max_length=100)
    document_title: str = Field(max_length=200)
    section: str = Field(max_length=200)
    row_labels: tuple[Annotated[str, Field(max_length=200)], ...] = Field(max_length=3)
    nearby_labels: tuple[Annotated[str, Field(max_length=200)], ...] = Field(max_length=4)
    options: tuple[Annotated[str, Field(max_length=200)], ...] = Field(max_length=50)
    repeat_index: int = Field(ge=0)
    required: bool
    kind: str = Field(min_length=1, max_length=100)


class ScoredCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    canonical_field_id: str = Field(pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
    score: float = Field(ge=0, le=1)
    rank: int = Field(ge=1)


class MappingEvidence(BaseModel):
    """Decision evidence without document values or database values."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reason: str
    rule: str | None = None
    embedding_rank: int | None = Field(default=None, ge=1)
    reranker_score: float | None = Field(default=None, ge=0, le=1)
    score_margin: float | None = Field(default=None, ge=0, le=1)
    type_compatible: bool | None = None
    entity_hint: str | None = None
    catalog_version: str
    model_version: str | None = None


class FieldMapping(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field_id: str = Field(min_length=1, max_length=200)
    status: MappingStatus
    canonical_field_id: str | None = Field(
        default=None, pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$"
    )
    candidates: tuple[ScoredCandidate, ...] = ()
    evidence: MappingEvidence

    @model_validator(mode="after")
    def _matched_mapping_has_canonical_field(self) -> FieldMapping:
        if self.status is MappingStatus.MATCHED and self.canonical_field_id is None:
            raise ValueError("matched mappings require a canonical_field_id")
        if self.status is not MappingStatus.MATCHED and self.canonical_field_id is not None:
            raise ValueError("only matched mappings may include a canonical_field_id")
        return self


class CanonicalMappingPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    catalog_version: str = Field(pattern=r"^v[1-9][0-9]*$")
    mappings: tuple[FieldMapping, ...]
