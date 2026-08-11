"""Versioned canonical field catalog with allowlisted identifiers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .models import CanonicalFieldDefinition, DocumentFieldContext


class _CatalogDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str = Field(pattern=r"^v[1-9][0-9]*$")
    fields: tuple[CanonicalFieldDefinition, ...]


@dataclass(frozen=True)
class CanonicalCatalog:
    version: str
    _fields_by_id: dict[str, CanonicalFieldDefinition]

    @classmethod
    def load(cls, path: Path) -> CanonicalCatalog:
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as error:
            raise ValueError(f"invalid canonical catalog: {error}") from error

        try:
            document = _CatalogDocument.model_validate(raw)
        except ValidationError as error:
            if any("string_pattern_mismatch" == item["type"] for item in error.errors()):
                raise ValueError("catalog contains an unapproved identifier") from error
            raise ValueError(f"invalid canonical catalog: {error}") from error

        fields_by_id: dict[str, CanonicalFieldDefinition] = {}
        for field in document.fields:
            if field.field_id in fields_by_id:
                raise ValueError(f"duplicate canonical field identifier: {field.field_id}")
            fields_by_id[field.field_id] = field

        return cls(version=document.version, _fields_by_id=fields_by_id)

    def get(self, field_id: str) -> CanonicalFieldDefinition:
        try:
            return self._fields_by_id[field_id]
        except KeyError as error:
            raise KeyError(f"unknown canonical field: {field_id}") from error

    def compatible(self, context: DocumentFieldContext) -> tuple[CanonicalFieldDefinition, ...]:
        return tuple(
            field
            for field in self._fields_by_id.values()
            if context.field_type in field.compatible_field_types
            and (field.repeatable or context.repeat_index == 0)
        )
