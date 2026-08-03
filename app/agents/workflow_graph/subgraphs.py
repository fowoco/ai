# Language / OCR / Document 서브그래프 — 메인 슈퍼바이저가 호출

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from app.db.memory import InMemoryDb
from app.db.protocols import IdentityStore

from .nodes.actions import generate_docs, persist_ocr
from .nodes.document_generator import DocumentGenerator, StubDocumentGenerator
from .nodes.language_stub import StubLanguageNode
from .nodes.ocr_stub import StubOcrNode
from .phases import WorkflowPhase, WorkflowStep, append_progress, progress_event
from .protocols import LanguageNode, OcrNode
from .state import RenewalState


# Language 서브그래프 컴파일 (Intent·Slot·가이드)
def build_language_subgraph(*, language_node: LanguageNode | None = None) -> Any:
    language = language_node or StubLanguageNode()

    def run_language(state: RenewalState) -> dict[str, Any]:
        patch = dict(language(state))
        events = append_progress(
            state,
            progress_event(
                phase=WorkflowPhase.INTAKE_ANALYSIS,
                step=WorkflowStep.STEP_2_INTENT_SLOT,
                message="Language 서브그래프: Intent·Slot 분석",
                subgraph="language",
            ),
        )
        if patch.get("guide_message"):
            events = append_progress(
                {**state, "progress_events": events},
                progress_event(
                    phase=WorkflowPhase.VALIDATION_COMMUNICATION,
                    step=WorkflowStep.STEP_7_LANGUAGE_GUIDE,
                    message="Language 가이드 문구 생성",
                    subgraph="language",
                ),
            )
        patch["progress_events"] = events
        patch["active_subgraph"] = "language"
        patch["phase"] = WorkflowPhase.INTAKE_ANALYSIS.value
        patch["step"] = WorkflowStep.STEP_2_INTENT_SLOT.value
        return patch

    g: StateGraph = StateGraph(RenewalState)
    g.add_node("language_run", run_language)
    g.add_edge(START, "language_run")
    g.add_edge("language_run", END)
    return g.compile()


# OCR 서브그래프 컴파일 (추출 + 신분 저장)
def build_ocr_subgraph(
    *,
    ocr_node: OcrNode | None = None,
    store: IdentityStore | None = None,
) -> Any:
    ocr = ocr_node or StubOcrNode()
    db_store = store or InMemoryDb()

    def run_ocr(state: RenewalState) -> dict[str, Any]:
        patch = dict(ocr(state))
        events = append_progress(
            state,
            progress_event(
                phase=WorkflowPhase.EXTRACTION_DOCUMENT,
                step=WorkflowStep.STEP_11_OCR,
                message="OCR 서브그래프: 서류 추출",
                subgraph="ocr",
            ),
        )
        patch["progress_events"] = events
        patch["active_subgraph"] = "ocr"
        patch["phase"] = WorkflowPhase.EXTRACTION_DOCUMENT.value
        patch["step"] = WorkflowStep.STEP_11_OCR.value
        return patch

    def run_persist(state: RenewalState) -> dict[str, Any]:
        patch = dict(persist_ocr(state, store=db_store))
        events = append_progress(
            state,
            progress_event(
                phase=WorkflowPhase.EXTRACTION_DOCUMENT,
                step=WorkflowStep.STEP_11_OCR,
                message="OCR 결과 신분 슬롯 저장",
                subgraph="ocr",
            ),
        )
        patch["progress_events"] = events
        return patch

    g: StateGraph = StateGraph(RenewalState)
    g.add_node("ocr_run", run_ocr)
    g.add_node("ocr_persist", run_persist)
    g.add_edge(START, "ocr_run")
    g.add_edge("ocr_run", "ocr_persist")
    g.add_edge("ocr_persist", END)
    return g.compile()


# Document 서브그래프 컴파일 (HWP 초안)
def build_document_subgraph(
    *, document_generator: DocumentGenerator | None = None
) -> Any:
    docs = document_generator or StubDocumentGenerator()

    def run_generate(state: RenewalState) -> dict[str, Any]:
        patch = dict(generate_docs(state, document_generator=docs))
        events = append_progress(
            state,
            progress_event(
                phase=WorkflowPhase.EXTRACTION_DOCUMENT,
                step=WorkflowStep.STEP_13_DOCUMENT_DRAFT,
                message="Document 서브그래프: 초안 생성",
                subgraph="document",
            ),
        )
        patch["progress_events"] = events
        patch["active_subgraph"] = "document"
        patch["phase"] = WorkflowPhase.EXTRACTION_DOCUMENT.value
        patch["step"] = WorkflowStep.STEP_13_DOCUMENT_DRAFT.value
        return patch

    g: StateGraph = StateGraph(RenewalState)
    g.add_node("document_run", run_generate)
    g.add_edge(START, "document_run")
    g.add_edge("document_run", END)
    return g.compile()
