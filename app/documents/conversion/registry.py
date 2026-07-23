"""Registry-driven converter selection and orchestration."""

from __future__ import annotations

import tempfile
from collections import deque
from collections.abc import Mapping
from pathlib import Path

from app.documents.common import DocumentFormat
from app.documents.conversion.errors import (
    ConversionNotSupportedError,
    DocumentConversionError,
)
from app.documents.conversion.protocol import DocumentConverter


class DocumentConversionService:
    """Resolve and run converters without leaking implementations into API code."""

    def __init__(self, converters: tuple[DocumentConverter, ...] = ()):
        self._converters: dict[tuple[DocumentFormat, DocumentFormat], DocumentConverter] = {}
        for converter in converters:
            self.register(converter)

    def register(self, converter: DocumentConverter) -> None:
        key = (converter.source_format, converter.target_format)
        if key in self._converters:
            raise DocumentConversionError(
                f"converter already registered: {key[0].value} -> {key[1].value}"
            )
        self._converters[key] = converter

    def supported_pairs(self) -> tuple[tuple[DocumentFormat, DocumentFormat], ...]:
        pairs = (
            (source_format, target_format)
            for source_format in DocumentFormat
            for target_format in DocumentFormat
            if source_format != target_format
            and self._find_path(source_format, target_format) is not None
        )
        return tuple(sorted(pairs, key=lambda pair: (pair[0].value, pair[1].value)))

    def convert(
        self,
        source: str | Path,
        destination: str | Path,
        *,
        source_format: DocumentFormat,
        target_format: DocumentFormat,
        options: Mapping[str, object] | None = None,
    ) -> Path:
        conversion_path = self._find_path(source_format, target_format)
        if conversion_path is None or not conversion_path:
            raise ConversionNotSupportedError(
                f"unsupported conversion: {source_format.value} -> {target_format.value}"
            )

        source_path = Path(source).resolve()
        destination_path = Path(destination).resolve()
        if len(conversion_path) == 1:
            return conversion_path[0].convert(
                source_path,
                destination_path,
                options=options,
            )

        destination_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".document-chain-",
            dir=destination_path.parent,
        ) as temporary_directory:
            working_directory = Path(temporary_directory)
            current_source = source_path
            for index, converter in enumerate(conversion_path):
                is_final = index == len(conversion_path) - 1
                current_destination = (
                    destination_path
                    if is_final
                    else working_directory
                    / f"step-{index + 1}.{converter.target_format.value}"
                )
                current_source = converter.convert(
                    current_source,
                    current_destination,
                    options=options,
                )
        return destination_path

    def _find_path(
        self,
        source_format: DocumentFormat,
        target_format: DocumentFormat,
    ) -> tuple[DocumentConverter, ...] | None:
        if source_format == target_format:
            return None
        queue: deque[tuple[DocumentFormat, tuple[DocumentConverter, ...]]] = deque(
            [(source_format, ())]
        )
        visited = {source_format}
        ordered_converters = sorted(
            self._converters.items(),
            key=lambda item: (item[0][0].value, item[0][1].value),
        )
        while queue:
            current_format, current_path = queue.popleft()
            for (edge_source, edge_target), converter in ordered_converters:
                if edge_source != current_format or edge_target in visited:
                    continue
                candidate_path = (*current_path, converter)
                if edge_target == target_format:
                    return candidate_path
                visited.add(edge_target)
                queue.append((edge_target, candidate_path))
        return None


__all__ = [
    "DocumentConversionService",
]
