"""Contracts and catalog data for additive dynamic document automation."""

from .catalog import CanonicalCatalog
from .models import (
    CanonicalFieldDefinition,
    CanonicalMappingPlan,
    CanonicalSource,
    DocumentFieldContext,
    FieldMapping,
    MappingEvidence,
    MappingStatus,
    ScoredCandidate,
)

__all__ = [
    "CanonicalCatalog",
    "CanonicalFieldDefinition",
    "CanonicalMappingPlan",
    "CanonicalSource",
    "DocumentFieldContext",
    "FieldMapping",
    "MappingEvidence",
    "MappingStatus",
    "ScoredCandidate",
]
