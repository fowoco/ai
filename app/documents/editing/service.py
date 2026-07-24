"""Format-dispatching facade for template inspection, editing, and generation."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from app.documents.common import DocumentFormat, detect_document_format
from app.documents.hwp5 import (
    Hwp5DocumentService,
    Hwp5TemplateError,
    Hwp5TemplateNotFoundError,
)
from app.documents.hwp5.editor import Hwp5Error
from app.documents.hwpx import HwpxDocumentService, HwpxError

from .exceptions import (
    DocumentEditingError,
    DocumentEditingNotSupportedError,
    DocumentTemplateNotFoundError,
)
from .models import (
    DocumentInspection,
    DocumentMutationResult,
    DocumentTemplateDefinition,
    DocumentTemplateVariant,
    EditableField,
)
from .template_names import template_display_name


class DocumentEditingService:
    """Select the exact-format editor while exposing one stable API."""

    def __init__(
        self,
        hwp5_service: Hwp5DocumentService | None = None,
        hwpx_service: HwpxDocumentService | None = None,
    ):
        self.hwp5_service = hwp5_service or Hwp5DocumentService()
        self.hwpx_service = hwpx_service or HwpxDocumentService()

    def templates(self) -> tuple[DocumentTemplateDefinition, ...]:
        hwp_templates = {
            template.template_id: template
            for template in self.hwp5_service.templates()
        }
        hwpx_templates = {
            template.template_id: template
            for template in self.hwpx_service.templates()
        }
        definitions: list[DocumentTemplateDefinition] = []
        for template_id in sorted(hwp_templates.keys() | hwpx_templates.keys()):
            variants: list[DocumentTemplateVariant] = []
            hwp_template = hwp_templates.get(template_id)
            if hwp_template is not None:
                fields = tuple(
                    EditableField(
                        name=name,
                        field_type=str(specification.get("type", "text")),
                        width_mm=_optional_float(specification.get("width_mm")),
                        height_mm=_optional_float(specification.get("height_mm")),
                    )
                    for name, specification in hwp_template.fields.items()
                )
                variants.append(
                    DocumentTemplateVariant(
                        format=DocumentFormat.HWP,
                        fields=fields,
                        supports_dynamic_labels=False,
                        supports_assets=any(
                            field.field_type in {"image", "photo", "signature"}
                            for field in fields
                        ),
                    )
                )
            if template_id in hwpx_templates:
                variants.append(
                    DocumentTemplateVariant(
                        format=DocumentFormat.HWPX,
                        fields=(),
                        supports_dynamic_labels=True,
                        supports_assets=False,
                    )
                )
            definitions.append(
                DocumentTemplateDefinition(
                    template_id=template_id,
                    display_name=template_display_name(template_id),
                    variants=tuple(variants),
                )
            )
        return tuple(definitions)

    def template(self, template_id: str) -> DocumentTemplateDefinition:
        normalized_id = template_id.strip()
        for template in self.templates():
            if template.template_id == normalized_id:
                return template
        raise DocumentTemplateNotFoundError(
            f"unknown document template_id: {template_id}"
        )

    def inspect(self, source: str | Path) -> DocumentInspection:
        source_format = detect_document_format(source)
        template_id: str | None = None
        if source_format is DocumentFormat.HWP:
            try:
                template_id = self.hwp5_service.identify(source).template_id
            except Hwp5TemplateNotFoundError:
                pass
        elif source_format is DocumentFormat.HWPX:
            try:
                template_id = self.hwpx_service.registry.identify(source).template_id
            except HwpxError:
                pass
        return DocumentInspection(
            format=source_format,
            editable=source_format in {DocumentFormat.HWP, DocumentFormat.HWPX},
            template_id=template_id,
        )

    def edit(
        self,
        source: str | Path,
        destination: str | Path,
        *,
        values: Mapping[str, object] | None = None,
        application_options: Mapping[str, object] | None = None,
        assets: Mapping[str, str | Path] | None = None,
        template_id: str | None = None,
    ) -> DocumentMutationResult:
        source_format = detect_document_format(source)
        if source_format is DocumentFormat.HWP:
            if application_options:
                raise DocumentEditingNotSupportedError(
                    "HWP application_options must be supplied as named checkbox values"
                )
            try:
                result = self.hwp5_service.fill(
                    source,
                    destination,
                    values=values,
                    images=assets,
                    template_id=template_id,
                )
            except Hwp5TemplateNotFoundError as exc:
                raise DocumentTemplateNotFoundError(str(exc)) from exc
            except (Hwp5TemplateError, Hwp5Error, OSError, ValueError) as exc:
                raise DocumentEditingError(str(exc)) from exc
            return DocumentMutationResult(
                result.destination,
                DocumentFormat.HWP,
                result.template_id,
                result.changed_fields,
            )
        if source_format is DocumentFormat.HWPX:
            if assets:
                raise DocumentEditingNotSupportedError(
                    "HWPX structured asset insertion is not implemented"
                )
            if template_id is not None:
                try:
                    self.hwpx_service.registry.get(template_id)
                except HwpxError as exc:
                    raise DocumentTemplateNotFoundError(str(exc)) from exc
            try:
                result = self.hwpx_service.fill(
                    source,
                    destination,
                    values=values,
                    application_options=application_options,
                    template_id=template_id,
                )
            except HwpxError as exc:
                raise DocumentEditingError(str(exc)) from exc
            _ensure_fields_changed(
                result.changed_fields,
                values,
                application_options,
            )
            return DocumentMutationResult(
                result.destination,
                DocumentFormat.HWPX,
                result.template_id,
                result.changed_fields,
            )
        raise DocumentEditingNotSupportedError(
            f"structured editing is unsupported for {source_format.value}"
        )

    def generate(
        self,
        template_id: str,
        document_format: DocumentFormat,
        destination: str | Path,
        *,
        values: Mapping[str, object] | None = None,
        application_options: Mapping[str, object] | None = None,
        assets: Mapping[str, str | Path] | None = None,
    ) -> DocumentMutationResult:
        if document_format is DocumentFormat.HWP:
            if application_options:
                raise DocumentEditingNotSupportedError(
                    "HWP application_options must be supplied as named checkbox values"
                )
            try:
                result = self.hwp5_service.generate(
                    template_id,
                    destination,
                    values=values,
                    images=assets,
                )
            except Hwp5TemplateNotFoundError as exc:
                raise DocumentTemplateNotFoundError(str(exc)) from exc
            except (Hwp5TemplateError, Hwp5Error, OSError, ValueError) as exc:
                raise DocumentEditingError(str(exc)) from exc
            return DocumentMutationResult(
                result.destination,
                document_format,
                result.template_id,
                result.changed_fields,
            )
        if document_format is DocumentFormat.HWPX:
            if assets:
                raise DocumentEditingNotSupportedError(
                    "HWPX structured asset insertion is not implemented"
                )
            try:
                self.hwpx_service.registry.get(template_id)
            except HwpxError as exc:
                raise DocumentTemplateNotFoundError(str(exc)) from exc
            try:
                result = self.hwpx_service.generate(
                    template_id,
                    destination,
                    values=values,
                    application_options=application_options,
                )
            except HwpxError as exc:
                raise DocumentEditingError(str(exc)) from exc
            _ensure_fields_changed(
                result.changed_fields,
                values,
                application_options,
            )
            return DocumentMutationResult(
                result.destination,
                document_format,
                result.template_id,
                result.changed_fields,
            )
        raise DocumentEditingNotSupportedError(
            f"document generation is unsupported for {document_format.value}"
        )


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)


def _ensure_fields_changed(
    changed_fields: tuple[str, ...],
    values: Mapping[str, object] | None,
    application_options: Mapping[str, object] | None,
) -> None:
    requested = set(values or {}) | set(application_options or {})
    missing = requested - set(changed_fields)
    if missing:
        raise DocumentEditingError(
            f"fields were not found in the HWPX template: {sorted(missing)}"
        )


__all__ = ["DocumentEditingService"]
