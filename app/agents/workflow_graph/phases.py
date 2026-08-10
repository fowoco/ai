# 회의 4 Phase·15 Step 신호 — Server UI/대기 Task용 진행 표시

from __future__ import annotations

from enum import StrEnum
from typing import Any


# 전체 워크플로 4 Phase
class WorkflowPhase(StrEnum):

    INTAKE_ANALYSIS = "PHASE_1_INTAKE_ANALYSIS"
    VALIDATION_COMMUNICATION = "PHASE_2_VALIDATION_COMMUNICATION"
    EXTRACTION_DOCUMENT = "PHASE_3_EXTRACTION_DOCUMENT"
    REVIEW_CLOSE = "PHASE_4_REVIEW_CLOSE"


# AI가 신호로 쓰는 주요 Step (Server Case/Task 생성은 제외)
class WorkflowStep(StrEnum):

    STEP_2_INTENT_SLOT = "STEP_2_INTENT_SLOT"
    STEP_4_DOCUMENT_CHECK = "STEP_4_DOCUMENT_CHECK"
    STEP_5_CASE_SIGNAL = "STEP_5_CASE_SIGNAL"
    STEP_7_LANGUAGE_GUIDE = "STEP_7_LANGUAGE_GUIDE"
    STEP_11_OCR = "STEP_11_OCR"
    STEP_13_DOCUMENT_DRAFT = "STEP_13_DOCUMENT_DRAFT"
    STEP_WAIT_SERVER = "STEP_WAIT_SERVER"


# progress 이벤트 한 줄 생성
def progress_event(
    *,
    phase: WorkflowPhase | str,
    step: WorkflowStep | str,
    message: str,
    subgraph: str | None = None,
) -> dict[str, Any]:
    return {
        "phase": str(phase),
        "step": str(step),
        "message": message,
        "subgraph": subgraph,
    }


# 기존 progress 목록에 이벤트 append
def append_progress(
    state: dict[str, Any], event: dict[str, Any]
) -> list[dict[str, Any]]:
    events = list(state.get("progress_events") or [])
    events.append(event)
    return events
