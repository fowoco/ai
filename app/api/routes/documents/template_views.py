"""Mapping between document template domain models and API responses."""

from app.api.schemas.documents import (
    DocumentTemplateResponse,
    DocumentTemplateVariantResponse,
    EditableFieldResponse,
)
from app.documents.editing import DocumentTemplateDefinition


def template_response(
    template: DocumentTemplateDefinition,
) -> DocumentTemplateResponse:
    return DocumentTemplateResponse(
        template_id=template.template_id,
        display_name=template.display_name,
        variants=tuple(
            DocumentTemplateVariantResponse(
                format=variant.format,
                field_count=len(variant.fields),
                fields=tuple(
                    EditableFieldResponse(
                        name=field.name,
                        type=field.field_type,
                        width_mm=field.width_mm,
                        height_mm=field.height_mm,
                    )
                    for field in variant.fields
                ),
                supports_dynamic_labels=variant.supports_dynamic_labels,
                supports_assets=variant.supports_assets,
            )
            for variant in template.variants
        ),
    )


__all__ = ["template_response"]
