"""Build bounded structural context from untrusted MCP field registries."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .models import DocumentFieldContext, RegistryFieldType

_MAX_TEXT_LENGTH = 200
_MAX_OPTIONS = 50


class _RegistryInput(BaseModel):
    """Only the registry fields needed for value-free mapping context."""

    model_config = ConfigDict(extra="ignore")

    field_id: str = Field(min_length=1, max_length=_MAX_TEXT_LENGTH)
    target_id: str = Field(min_length=1, max_length=_MAX_TEXT_LENGTH)
    label: str = ""
    type: RegistryFieldType
    kind: str = Field(min_length=1)
    row: int
    column: int
    required: bool = True
    options: tuple[str, ...] | None = None


def normalize_text(value: str) -> str:
    """Normalize user-facing labels for deterministic equality checks."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[\W_]+", "", normalized, flags=re.UNICODE)


def build_field_contexts(
    registry: Sequence[Mapping[str, Any]], *, document_title: str
) -> tuple[DocumentFieldContext, ...]:
    """Return one bounded structural context per registry item."""
    validated = [_RegistryInput.model_validate(item) for item in registry]
    field_ids = [item.field_id for item in validated]
    if len(set(field_ids)) != len(field_ids):
        raise ValueError("registry contains a duplicate field_id")
    repeat_indices = _repeat_indices(validated)
    row_groups = _row_groups(validated)
    return tuple(
        _context_for(
            item,
            validated,
            row_groups=row_groups,
            document_title=document_title,
            repeat_index=repeat_indices[index],
        )
        for index, item in enumerate(validated)
    )


def _context_for(
    item: _RegistryInput,
    registry: Sequence[_RegistryInput],
    *,
    row_groups: Mapping[tuple[str, int], tuple[_RegistryInput, ...]],
    document_title: str,
    repeat_index: int,
) -> DocumentFieldContext:
    container_id = _container_id(item.target_id)
    row_items = row_groups[(container_id, item.row)]
    row_labels = tuple(_bound_text(candidate.label) for candidate in row_items[:3])
    nearby = sorted(
        (
            candidate
            for candidate in registry
            if _container_id(candidate.target_id) == container_id
            and candidate.row != item.row
        ),
        key=lambda candidate: (
            abs(candidate.row - item.row),
            abs(candidate.column - item.column),
            candidate.row,
            candidate.column,
        ),
    )
    return DocumentFieldContext(
        field_id=item.field_id,
        container_id=container_id,
        label=_bound_text(item.label),
        normalized_label=_bound_text(normalize_text(item.label)),
        field_type=_bound_text(item.type),
        document_title=_bound_text(document_title),
        section=row_labels[0] if row_labels else "",
        row_labels=row_labels,
        nearby_labels=tuple(_bound_text(candidate.label) for candidate in nearby[:4]),
        options=tuple(_bound_text(option) for option in (item.options or ())[:_MAX_OPTIONS]),
        repeat_index=repeat_index,
        required=item.required,
        kind=_bound_text(item.kind),
    )


def _row_groups(
    registry: Sequence[_RegistryInput],
) -> dict[tuple[str, int], tuple[_RegistryInput, ...]]:
    grouped: dict[tuple[str, int], list[tuple[int, _RegistryInput]]] = defaultdict(list)
    for index, item in enumerate(registry):
        grouped[(_container_id(item.target_id), item.row)].append((index, item))
    return {
        group: tuple(
            item for _, item in sorted(items, key=lambda pair: (pair[1].column, pair[0]))
        )
        for group, items in grouped.items()
    }


def _repeat_indices(registry: Sequence[_RegistryInput]) -> tuple[int, ...]:
    counts: dict[tuple[str, str], int] = defaultdict(int)
    indices: list[int] = []
    for item in registry:
        key = (_container_id(item.target_id), normalize_text(item.label))
        indices.append(counts[key])
        counts[key] += 1
    return tuple(indices)


def _bound_text(value: str) -> str:
    return value[:_MAX_TEXT_LENGTH]


def _container_id(target_id: str) -> str:
    match = re.match(r"^(.*?\.table[^.]+)(?:\.|$)", target_id)
    return match.group(1) if match is not None else target_id
