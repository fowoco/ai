"""Cached application services injected into Internal API routes."""

from functools import lru_cache

from app.core.config import get_settings
from app.documents import (
    DocumentConversionService,
    DocumentEditingService,
    DocumentRecordGenerationService,
    Hwp5DocumentService,
    HwpxDocumentService,
)
from app.documents.conversion.converters import (
    HwpToHwpxConverter,
    HwpToPdfConverter,
    HwpxToHwpConverter,
    HwpxToPdfConverter,
    HwpxToXmlConverter,
    XmlToHwpxConverter,
)
from app.documents.conversion.engines import LibreOfficeEngine
from app.documents.snapshots import DocumentSnapshotRepository


@lru_cache
def get_hwp5_document_service() -> Hwp5DocumentService:
    """Return one immutable-template registry per API worker process."""

    return Hwp5DocumentService()


@lru_cache
def get_hwpx_document_service() -> HwpxDocumentService:
    """Return one HWPX template registry per API worker process."""

    return HwpxDocumentService()


@lru_cache
def get_document_snapshot_repository() -> DocumentSnapshotRepository:
    """Return the persistent package snapshot repository for this worker."""

    return DocumentSnapshotRepository(get_settings().document_snapshot_dir)


@lru_cache
def get_document_editing_service() -> DocumentEditingService:
    """Return the format-dispatching document editor for this worker."""

    return DocumentEditingService(
        get_hwp5_document_service(),
        get_hwpx_document_service(),
    )


@lru_cache
def get_document_record_generation_service() -> DocumentRecordGenerationService:
    """Return the TXT/DB-record rule-based document generator."""

    return DocumentRecordGenerationService(get_hwpx_document_service())


@lru_cache
def get_document_conversion_service() -> DocumentConversionService:
    """Return the converter registry for one API worker process."""

    hwpx_service = get_hwpx_document_service()
    snapshot_repository = get_document_snapshot_repository()
    converters = [
        HwpxToXmlConverter(hwpx_service, snapshot_repository),
        XmlToHwpxConverter(hwpx_service, snapshot_repository),
    ]
    settings = get_settings()
    hwpx_to_hwp_converter = None
    if settings.hwp_to_hwpx_enabled:
        hwp_converter = HwpToHwpxConverter(
            settings.java_path,
            timeout_seconds=settings.document_conversion_timeout_seconds,
        )
        hwp_converter.require_available()
        converters.append(hwp_converter)
    if settings.hwpx_to_hwp_enabled:
        hwpx_to_hwp_converter = HwpxToHwpConverter(
            settings.rhwp_path,
            timeout_seconds=settings.document_conversion_timeout_seconds,
        )
        hwpx_to_hwp_converter.require_available()
        converters.append(hwpx_to_hwp_converter)
    if settings.hwpx_pdf_enabled:
        pdf_engine = LibreOfficeEngine(
            settings.soffice_path,
            settings.document_conversion_timeout_seconds,
        )
        pdf_engine.require_available()
        hwp_to_pdf_converter = HwpToPdfConverter(engine=pdf_engine)
        fallback_converters = (
            (hwpx_to_hwp_converter, hwp_to_pdf_converter)
            if hwpx_to_hwp_converter is not None
            else None
        )
        converters.extend(
            (
                hwp_to_pdf_converter,
                HwpxToPdfConverter(
                    engine=pdf_engine,
                    fallback_converters=fallback_converters,
                ),
            )
        )
    return DocumentConversionService(tuple(converters))


__all__ = [
    "get_document_conversion_service",
    "get_document_editing_service",
    "get_document_record_generation_service",
    "get_document_snapshot_repository",
    "get_hwp5_document_service",
    "get_hwpx_document_service",
]
