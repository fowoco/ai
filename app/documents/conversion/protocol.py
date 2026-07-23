"""Converter contract used by the registry and API composition root."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from app.documents.common import DocumentFormat


class DocumentConverter(Protocol):
    """Port implemented by one concrete source/target converter."""

    source_format: DocumentFormat
    target_format: DocumentFormat

    def convert(
        self,
        source: Path,
        destination: Path,
        *,
        options: Mapping[str, object] | None = None,
    ) -> Path: ...


__all__ = ["DocumentConverter"]
