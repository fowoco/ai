# 재갱신 실행 진입점 — task 재개 시 slots/OCR 병합 후 그래프 실행

from __future__ import annotations

from typing import Any
from uuid import uuid4

from .agent_mode import AgentExecutionMode
from .graph import build_renewal_graph
from .init_state import init_renewal_state_from_bundle
from .nodes.document_generator import DocumentGenerator
from .protocols import LanguageNode, OcrNode
from .state import RenewalState, empty_renewal_state
from .status import TaskStatus, to_public_status
from .task_store import InMemoryTaskStore, TaskStore, merge_resume_state


# 요청·재개 State에 선행 OCR 스냅샷 주입 (CLOVA 필드명 정규화 + slots 병합)
def _seed_ocr_result(state: RenewalState, ocr_result: dict[str, Any] | None) -> None:
    if not ocr_result:
        return
    from .ocr_bridge import normalize_ocr_fields

    normalized = normalize_ocr_fields(dict(ocr_result))
    if not normalized:
        state["ocr_result"] = dict(ocr_result)
        return
    state["ocr_result"] = normalized
    state["slots"] = {**state.get("slots", {}), **normalized}
    missing = [m for m in state.get("missing_slots", []) if not state["slots"].get(m)]
    state["missing_slots"] = missing


# 재갱신 그래프를 한 번 실행 후 결과를 저장·반환
class RenewalOrchestrator:

    # Language/OCR/안내문/DB/서류생성/태스크 저장소 주입
    def __init__(
        self,
        *,
        language_node: LanguageNode | None = None,
        ocr_node: OcrNode | None = None,
        guide_node: Any | None = None,
        lookup: Any | None = None,
        store: Any | None = None,
        document_generator: DocumentGenerator | None = None,
        task_store: TaskStore | None = None,
        graph: Any | None = None,
    ) -> None:
        self._task_store = task_store or InMemoryTaskStore()
        self._graph = graph or build_renewal_graph(
            language_node=language_node,
            ocr_node=ocr_node,
            guide_node=guide_node,
            lookup=lookup,
            store=store,
            document_generator=document_generator,
        )

    # 요청을 State로 구성 후 그래프를 실행, 다음 호출을 위해 스냅샷 보관
    def run(
        self,
        *,
        request_id: str,
        instruction: str,
        worker_id: str | None = None,
        company_id: str | None = None,
        task_id: str | None = None,
        slots: dict[str, Any] | None = None,
        documents: list[dict[str, Any]] | None = None,
        ocr_result: dict[str, Any] | None = None,
        worker: dict[str, Any] | None = None,
        company: dict[str, Any] | None = None,
        task: dict[str, Any] | None = None,
        agent_mode: AgentExecutionMode = AgentExecutionMode.LEGACY,
    ) -> RenewalState:
        resolved_task_id = (
            task_id
            or (task or {}).get("task_id")
            or (task or {}).get("taskId")
            or f"task-{uuid4().hex[:12]}"
        )
        previous = self._task_store.load(str(resolved_task_id)) if task_id or task else None

        if previous:
            merged = merge_resume_state(
                previous=previous,
                instruction=instruction,
                slots=slots,
                documents=documents,
                worker_id=worker_id,
                company_id=company_id,
            )
            initial = empty_renewal_state(
                task_id=str(resolved_task_id),
                request_id=request_id,
                instruction=str(merged["instruction"]),
                worker_id=merged.get("worker_id"),  # type: ignore[arg-type]
                company_id=merged.get("company_id"),  # type: ignore[arg-type]
                slots=merged.get("slots"),  # type: ignore[arg-type]
                documents=merged.get("documents"),  # type: ignore[arg-type]
                agent_mode=agent_mode,
            )
            if merged.get("ocr_result"):
                initial["ocr_result"] = merged["ocr_result"]  # type: ignore[typeddict-item]
            if merged.get("intent"):
                initial["intent"] = str(merged["intent"])
            if merged.get("workflow_id"):
                initial["workflow_id"] = str(merged["workflow_id"])
            _seed_ocr_result(initial, ocr_result)
        elif worker or company or task:
            initial = init_renewal_state_from_bundle(
                request_id=request_id,
                instruction=instruction,
                task_id=str(resolved_task_id),
                worker_id=worker_id,
                company_id=company_id,
                slots=slots,
                documents=documents,
                worker=worker,
                company=company,
                task=task,
            )
            _seed_ocr_result(initial, ocr_result)
            initial["agent_mode"] = agent_mode
        else:
            initial = empty_renewal_state(
                task_id=str(resolved_task_id),
                request_id=request_id,
                instruction=instruction,
                worker_id=worker_id,
                company_id=company_id,
                slots=slots,
                documents=documents,
                agent_mode=agent_mode,
            )
            _seed_ocr_result(initial, ocr_result)

        # 실행 중 내부 표기 — 응답 직전 서버 공개 status로 정규화
        initial["status"] = TaskStatus.DRAFT.value
        result = self._graph.invoke(initial)
        result["status"] = to_public_status(result.get("status"))  # type: ignore[index]
        self._task_store.save(result)  # type: ignore[arg-type]
        return result  # type: ignore[no-any-return]
