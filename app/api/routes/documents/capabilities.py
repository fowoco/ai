"""Capability discovery for document generation and conversion."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import (
    get_document_conversion_service,
    get_hwp5_document_service,
    get_hwpx_document_service,
)
from app.api.openapi import DOCUMENT_CAPABILITIES_TAG
from app.api.schemas.documents import (
    DocumentCapabilitiesResponse,
    DocumentConversionCapability,
    DocumentTemplateCapability,
)
from app.documents import (
    DocumentConversionService,
    DocumentFormat,
    Hwp5DocumentService,
    HwpxDocumentService,
)

router = APIRouter(tags=[DOCUMENT_CAPABILITIES_TAG])


@router.get("/capabilities", response_model=DocumentCapabilitiesResponse)
def document_capabilities(
    hwp_service: Annotated[Hwp5DocumentService, Depends(get_hwp5_document_service)],
    hwpx_service: Annotated[HwpxDocumentService, Depends(get_hwpx_document_service)],
    conversion_service: Annotated[
        DocumentConversionService, Depends(get_document_conversion_service)
    ],
) -> DocumentCapabilitiesResponse:
    """List only document operations that are actually available in this worker."""

    return DocumentCapabilitiesResponse(
        editable_formats=(DocumentFormat.HWP, DocumentFormat.HWPX),
        templates=(
            *(
                DocumentTemplateCapability(
                    format=DocumentFormat.HWP,
                    template_id=template.template_id,
                    field_count=len(template.fields),
                )
                for template in hwp_service.templates()
            ),
            *(
                DocumentTemplateCapability(
                    format=DocumentFormat.HWPX,
                    template_id=template.template_id,
                    field_count=0,
                )
                for template in hwpx_service.templates()
            )
        ),
        conversions=tuple(
            DocumentConversionCapability(
                source_format=source_format,
                target_format=target_format,
            )
            for source_format, target_format in conversion_service.supported_pairs()
        ),
    )


__all__ = ["router"]
