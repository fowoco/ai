"""Application service for template-driven HWP5 document generation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .editor import Hwp5BinaryDocument
from .exceptions import Hwp5TemplateError
from .template_registry import Hwp5Template, Hwp5TemplateRegistry, file_sha256


@dataclass(frozen=True)
class Hwp5EditResult:
    """Stable result returned to API or workflow layers after generation."""

    destination: Path
    template_id: str
    changed_fields: tuple[str, ...]


def load_template_map(
    template: str | Path | Mapping[str, object],
) -> Mapping[str, object]:
    """Load and minimally validate an external or hard-coded template map."""

    if isinstance(template, Mapping):
        data = dict(template)
    else:
        path = Path(template)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise Hwp5TemplateError(f"could not read template map: {path}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("fields"), dict):
        raise Hwp5TemplateError("template map must contain an object named 'fields'")
    return data


def edit_hwp5(
    source: str | Path,
    destination: str | Path,
    *,
    template: str | Path | Mapping[str, object],
    values: Mapping[str, object] | None = None,
    images: Mapping[str, str | Path] | None = None,
    verify_template_hash: bool = True,
) -> Hwp5EditResult:
    """Apply fields to an existing HWP5 file using an explicit template map."""

    source_path = Path(source).resolve()
    destination_path = Path(destination).resolve()
    template_data = load_template_map(template)
    expected_hash = str(template_data.get("template_hash", "")).casefold()
    actual_hash = file_sha256(source_path)
    if verify_template_hash and expected_hash and actual_hash != expected_hash:
        raise Hwp5TemplateError(
            f"template hash mismatch: expected {expected_hash}, got {actual_hash}"
        )

    document = Hwp5BinaryDocument(source_path)
    text_values = {name: str(value) for name, value in (values or {}).items()}
    changed = document.apply_fields(
        template_data["fields"],
        text_values,
        images or {},
    )
    document.save(destination_path)
    return Hwp5EditResult(
        destination=destination_path,
        template_id=str(template_data.get("template_id", "hwp5-template")),
        changed_fields=tuple(changed),
    )


class Hwp5DocumentService:
    """Use bundled templates without exposing filesystem details to callers."""

    def __init__(self, registry: Hwp5TemplateRegistry | None = None):
        self.registry = registry or Hwp5TemplateRegistry()

    def templates(self) -> tuple[Hwp5Template, ...]:
        return self.registry.list()

    def identify(self, source: str | Path) -> Hwp5Template:
        return self.registry.identify(source)

    def generate(
        self,
        template_id: str,
        destination: str | Path,
        *,
        values: Mapping[str, object] | None = None,
        images: Mapping[str, str | Path] | None = None,
    ) -> Hwp5EditResult:
        """Generate from the source HWP bundled with ``template_id``."""

        template = self.registry.get(template_id)
        return self._apply(template, template.source_path, destination, values, images)

    def fill(
        self,
        source: str | Path,
        destination: str | Path,
        *,
        values: Mapping[str, object] | None = None,
        images: Mapping[str, str | Path] | None = None,
        template_id: str | None = None,
    ) -> Hwp5EditResult:
        """Fill an uploaded HWP, identifying its template when ID is omitted."""

        template = (
            self.registry.get(template_id)
            if template_id is not None
            else self.registry.identify(source)
        )
        return self._apply(template, source, destination, values, images)

    @staticmethod
    def _apply(
        template: Hwp5Template,
        source: str | Path,
        destination: str | Path,
        values: Mapping[str, object] | None,
        images: Mapping[str, str | Path] | None,
    ) -> Hwp5EditResult:
        template_map = {
            "template_id": template.template_id,
            "template_hash": template.template_hash,
            "fields": template.fields,
        }
        return edit_hwp5(
            source,
            destination,
            template=template_map,
            values=values,
            images=images,
        )


__all__ = [
    "Hwp5DocumentService",
    "Hwp5EditResult",
    "edit_hwp5",
    "load_template_map",
]
