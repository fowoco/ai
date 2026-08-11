"""Deterministic rules that precede any mapping decision."""

from __future__ import annotations

from dataclasses import dataclass

from .catalog import CanonicalCatalog
from .field_context import normalize_text
from .models import CanonicalFieldDefinition, DocumentFieldContext

_PROCESS_FLOW_LABELS = frozenset(
    map(normalize_text, ("접수", "확인검토", "전산입력", "신청서작성", "고용센터"))
)
_OFFICIAL_USE_LABELS = frozenset(
    map(normalize_text, ("관공서용", "공용란", "For Official Use", "결재", "관할관서"))
)
_PAGE_ARROWS = frozenset({"←", "→", "↑", "↓", "◀", "▶", "‹", "›", "«", "»", "<", ">"})
_NON_DATA_KINDS = frozenset({"official_region", "signable_region"})


@dataclass(frozen=True)
class NonDataDecision:
    is_non_data: bool
    reason: str | None = None


def classify_non_data(context: DocumentFieldContext) -> NonDataDecision:
    """Identify regions and labels that can never receive document data."""
    normalized_label = normalize_text(context.label)
    if context.kind in _NON_DATA_KINDS:
        return NonDataDecision(is_non_data=True, reason=context.kind)
    if context.label.strip() in _PAGE_ARROWS:
        return NonDataDecision(is_non_data=True, reason="page_navigation_label")
    if normalized_label in _PROCESS_FLOW_LABELS:
        return NonDataDecision(is_non_data=True, reason="process_flow_label")
    if normalized_label in _OFFICIAL_USE_LABELS:
        return NonDataDecision(is_non_data=True, reason="official_use_label")
    return NonDataDecision(is_non_data=False)


def exact_alias_matches(
    context: DocumentFieldContext, catalog: CanonicalCatalog
) -> tuple[CanonicalFieldDefinition, ...]:
    """Return compatible canonical candidates whose aliases exactly match the label."""
    return tuple(
        field
        for field in catalog.compatible(context)
        if any(normalize_text(alias) == normalize_text(context.label) for alias in field.aliases)
    )
