"""Versioned canonical field catalog with allowlisted identifiers."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from types import MappingProxyType

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
    definitions: tuple[CanonicalFieldDefinition, ...]
    _fields_by_id: Mapping[str, CanonicalFieldDefinition] = dataclass_field(
        repr=False,
        compare=False,
    )

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

        definitions = tuple(sorted(fields_by_id.values(), key=lambda item: item.field_id))
        immutable_lookup = MappingProxyType(
            {definition.field_id: definition for definition in definitions}
        )
        return cls(
            version=document.version,
            definitions=definitions,
            _fields_by_id=immutable_lookup,
        )

    def __iter__(self) -> Iterator[CanonicalFieldDefinition]:
        return iter(self.definitions)

    def get(self, field_id: str) -> CanonicalFieldDefinition:
        try:
            return self._fields_by_id[field_id]
        except KeyError as error:
            raise KeyError(f"unknown canonical field: {field_id}") from error

    def compatible(self, context: DocumentFieldContext) -> tuple[CanonicalFieldDefinition, ...]:
        return tuple(
            field
            for field in self.definitions
            if context.field_type in field.compatible_field_types
        )
