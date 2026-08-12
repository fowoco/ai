# 재갱신 업무·문서 워커 경계
from __future__ import annotations

from typing import Any

from .document_field_map import values_for_template
from .nodes.document_generator import DocumentGenerator, draft_template_ids
from .phases import WorkflowPhase, WorkflowStep
from .protocols import LanguageNode
from .state import RenewalState
from .status import TaskStatus


class BusinessRecognitionAgent:
    def __init__(self, language_node: LanguageNode) -> None:
        self._language_node = language_node

    def __call__(self, state: RenewalState) -> dict[str, Any]:
        return dict(self._language_node(state))


class DocumentIntelligenceAgent:
    def __call__(self, state: RenewalState) -> dict[str, Any]:
        return {
            "document_field_values": {
                template_id: values_for_template(template_id, state)
                for template_id in draft_template_ids(state)
            }
        }


class DocumentAutomationAgent:
    def __init__(self, document_generator: DocumentGenerator) -> None:
        self._document_generator = document_generator

    def __call__(self, state: RenewalState) -> dict[str, Any]:
        return {"generated_documents": self._document_generator(state)}


class ValidationReviewAgent:
    def __call__(self, state: RenewalState) -> dict[str, Any]:
        del state
        return {
            "scenario": "generate",
            "status": TaskStatus.READY_FOR_REVIEW.value,
            "outcome": "REVIEW_REQUIRED",
            "missing_slots": [],
            "guide_message": None,
            "worker_request_message": None,
            "case_signals": ["GENERATE_DRAFTS", "READY_FOR_REVIEW"],
            "phase": WorkflowPhase.EXTRACTION_DOCUMENT.value,
            "step": WorkflowStep.STEP_13_DOCUMENT_DRAFT.value,
        }
