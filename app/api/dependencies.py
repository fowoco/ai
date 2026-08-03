# Cached application services injected into Internal API routes

from functools import lru_cache

from app.agents.ambiguity import AmbiguityAgent
from app.agents.intent import IntentClassifier, build_intent_agent
from app.agents.knowledge_support import (
    load_ambiguity_patterns,
    load_required_slots,
    load_workflow_catalog,
    try_get_repository,
)
from app.agents.pipeline import AnalysisPipeline
from app.agents.workflow import WorkflowAgent
from app.agents.workflow_graph import RenewalOrchestrator
from app.agents.workflow_graph.nodes.document_generator import (
    EditingServiceDocumentGenerator,
)
from app.agents.workflow_graph.nodes.language_stub import StubLanguageNode
from app.agents.workflow_graph.nodes.ocr_stub import StubOcrNode
from app.agents.workflow_graph.task_store import InMemoryTaskStore
from app.core.config import get_settings
from app.db.memory import InMemoryDb
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
# 설정(intent_mode)에 맞는 Intent 분류기 싱글톤
def get_intent_agent() -> IntentClassifier:
    return build_intent_agent()


@lru_cache
# Analyses 파이프라인 싱글톤 (선택적 knowledge 연동)
def get_analysis_pipeline() -> AnalysisPipeline:
    settings = get_settings()
    intent_agent = get_intent_agent()
    if not settings.knowledge_enabled:
        return AnalysisPipeline(intent_agent=intent_agent)

    repository = try_get_repository(settings.knowledge_root)
    if repository is None:
        return AnalysisPipeline(intent_agent=intent_agent)

    return AnalysisPipeline(
        intent_agent=intent_agent,
        ambiguity_agent=AmbiguityAgent(
            required_slots=load_required_slots(repository),
            ambiguity_patterns=load_ambiguity_patterns(repository),
        ),
        workflow_agent=WorkflowAgent(catalog=load_workflow_catalog(repository)),
    )


@lru_cache
# 재갱신 조회/저장용 인메모리 DB 싱글톤
def get_in_memory_db() -> InMemoryDb:
    return InMemoryDb()


@lru_cache
# 재갱신 태스크 재개용 인메모리 저장소
def get_task_store() -> InMemoryTaskStore:
    return InMemoryTaskStore()


@lru_cache
# 재갱신 LangGraph 오케스트레이터 싱글톤 (Language/OCR stub + 문서생성 훅)
def get_renewal_orchestrator() -> RenewalOrchestrator:
    db = get_in_memory_db()
    return RenewalOrchestrator(
        language_node=StubLanguageNode(intent_agent=get_intent_agent()),
        ocr_node=StubOcrNode(),
        lookup=db,
        store=db,
        document_generator=EditingServiceDocumentGenerator(
            get_document_editing_service()
        ),
        task_store=get_task_store(),
    )


@lru_cache
# Return one immutable-template registry per API worker process
def get_hwp5_document_service() -> Hwp5DocumentService:

    return Hwp5DocumentService()


@lru_cache
# Return one HWPX template registry per API worker process
def get_hwpx_document_service() -> HwpxDocumentService:

    return HwpxDocumentService()


@lru_cache
# Return the persistent package snapshot repository for this worker
def get_document_snapshot_repository() -> DocumentSnapshotRepository:

    return DocumentSnapshotRepository(get_settings().document_snapshot_dir)


@lru_cache
# Return the format-dispatching document editor for this worker
def get_document_editing_service() -> DocumentEditingService:

    return DocumentEditingService(
        get_hwp5_document_service(),
        get_hwpx_document_service(),
    )


@lru_cache
# Return the TXT/DB-record rule-based document generator
def get_document_record_generation_service() -> DocumentRecordGenerationService:

    return DocumentRecordGenerationService(get_hwpx_document_service())


@lru_cache
# Return the converter registry for one API worker process
def get_document_conversion_service() -> DocumentConversionService:

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
    "get_analysis_pipeline",
    "get_document_conversion_service",
    "get_document_editing_service",
    "get_document_record_generation_service",
    "get_document_snapshot_repository",
    "get_hwp5_document_service",
    "get_hwpx_document_service",
    "get_in_memory_db",
    "get_intent_agent",
    "get_renewal_orchestrator",
    "get_task_store",
]
