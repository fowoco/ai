# 태스크 진행분 저장 — 같은 task_id로 다시 올 때 slots 병합

from __future__ import annotations

from typing import Any, Protocol

from .state import RenewalState


# task_id 기준 스냅샷 저장소
class TaskStore(Protocol):

    # 저장된 스냅샷 반환
    def load(self, task_id: str) -> dict[str, Any] | None:
        ...

    # 실행 결과 State 저장
    def save(self, state: RenewalState) -> None:
        ...


# 프로세스 메모리 태스크 저장소
class InMemoryTaskStore:

    # 빈 저장소 생성
    def __init__(self) -> None:
        self._items: dict[str, dict[str, Any]] = {}

    # task_id 스냅샷 조회
    def load(self, task_id: str) -> dict[str, Any] | None:
        item = self._items.get(task_id)
        return dict(item) if item else None

    # 재개용 필드 스냅샷 보관
    def save(self, state: RenewalState) -> None:
        self._items[state["task_id"]] = {
            "task_id": state["task_id"],
            "request_id": state["request_id"],
            "instruction": state.get("instruction", ""),
            "worker_id": state.get("worker_id"),
            "company_id": state.get("company_id"),
            "intent": state.get("intent", ""),
            "workflow_id": state.get("workflow_id", ""),
            "slots": dict(state.get("slots") or {}),
            "missing_slots": list(state.get("missing_slots") or []),
            "status": state.get("status", ""),
            "outcome": state.get("outcome", ""),
            "scenario": state.get("scenario"),
            "ocr_result": state.get("ocr_result"),
            "generated_documents": list(state.get("generated_documents") or []),
        }


# 이전 스냅샷과 새 요청을 합쳐 초기 초깃값 생성
def merge_resume_state(
    *,
    previous: dict[str, Any],
    instruction: str,
    slots: dict[str, Any] | None,
    documents: list[dict[str, Any]] | None,
    worker_id: str | None,
    company_id: str | None,
) -> dict[str, Any]:
    merged_slots = {**(previous.get("slots") or {}), **(slots or {})}
    return {
        "instruction": instruction or previous.get("instruction") or "",
        "slots": merged_slots,
        "documents": list(documents or []),
        "worker_id": worker_id if worker_id is not None else previous.get("worker_id"),
        "company_id": company_id if company_id is not None else previous.get("company_id"),
        "intent": previous.get("intent") or "",
        "workflow_id": previous.get("workflow_id") or "",
        "ocr_result": previous.get("ocr_result"),
    }
