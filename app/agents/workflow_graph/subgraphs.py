# Language / OCR / Document 서브그래프 — 메인 슈퍼바이저가 호출

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from app.db.memory import InMemoryDb
from app.db.protocols import IdentityStore

from .nodes.actions import persist_ocr
from .nodes.document_generator import DocumentGenerator, StubDocumentGenerator
from .nodes.language_stub import StubLanguageNode
from .nodes.ocr_stub import StubOcrNode
from .phases import WorkflowPhase, WorkflowStep, append_progress, progress_event
from .protocols import LanguageNode, OcrNode
from .state import RenewalState
from .workers import (
    BusinessRecognitionAgent,
    DocumentAutomationAgent,
    DocumentIntelligenceAgent,
    ValidationReviewAgent,
)


# Language 서브그래프 컴파일 (Intent·Slot·가이드)
def build_language_subgraph(*, language_node: LanguageNode | None = None) -> Any:
    language = BusinessRecognitionAgent(language_node or StubLanguageNode())

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
    intelligence = DocumentIntelligenceAgent()
    automation = DocumentAutomationAgent(docs)
    review = ValidationReviewAgent()

    def run_intelligence(state: RenewalState) -> dict[str, Any]:
        return dict(intelligence(state))

    def run_automation(state: RenewalState) -> dict[str, Any]:
        patch = dict(automation(state))
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

    def run_review(state: RenewalState) -> dict[str, Any]:
        return dict(review(state))

    g: StateGraph = StateGraph(RenewalState)
    g.add_node("document_intelligence", run_intelligence)
    g.add_node("document_automation", run_automation)
    g.add_node("validation_review", run_review)
    g.add_edge(START, "document_intelligence")
    g.add_edge("document_intelligence", "document_automation")
    g.add_edge("document_automation", "validation_review")
    g.add_edge("validation_review", END)
    return g.compile()
