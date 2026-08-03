# 워크플로 목록 조회 — Knowledge 카탈로그 또는 내장 목록

from __future__ import annotations

from dataclasses import dataclass, field

_BUILTIN_CATALOG: dict[str, dict[str, object]] = {
    "WF-WRK-001": {
        "name": "근로자 등록·정보변경",
        "intent": "WORKER_ONBOARDING",
        "sensitivity": "high",
        "required_slots": ["worker_id"],
        "input_modes": ["AGENT_TASK", "INTERNAL_REQUEST"],
    },
    "WF-STY-001": {
        "name": "체류기간 연장 준비",
        "intent": "EXPIRY_RENEWAL",
        "sensitivity": "high",
        "required_slots": ["worker_id", "stay_expiry_date"],
        "input_modes": ["AGENT_TASK", "INTERNAL_REQUEST"],
    },
    "WF-CON-001": {
        "name": "근로계약 갱신 준비",
        "intent": "EXPIRY_RENEWAL",
        "sensitivity": "high",
        "required_slots": ["worker_id", "contract_end_date"],
        "input_modes": ["AGENT_TASK", "INTERNAL_REQUEST"],
    },
    "WF-DOC-001": {
        "name": "서류 요청·확인",
        "intent": "DOCUMENT_REQUEST",
        "sensitivity": "medium",
        "required_slots": ["worker_id", "document_type"],
        "input_modes": ["AGENT_TASK", "INTERNAL_REQUEST", "WORKER_MESSAGE"],
    },
    "WF-PAY-001": {
        "name": "급여·공제 설명",
        "intent": "PAYROLL_EXPLANATION",
        "sensitivity": "high",
        "required_slots": ["worker_id", "pay_period"],
        "input_modes": ["AGENT_TASK", "INTERNAL_REQUEST", "WORKER_MESSAGE"],
    },
    "WF-INS-001": {
        "name": "업무·근무일정 안내",
        "intent": "WORK_INSTRUCTION",
        "sensitivity": "medium",
        "required_slots": ["worker_id"],
        "input_modes": ["AGENT_TASK", "INTERNAL_REQUEST"],
    },
    "WF-CHG-001": {
        "name": "고용변동·이탈 후속조치",
        "intent": "EMPLOYMENT_CHANGE",
        "sensitivity": "critical",
        "required_slots": ["worker_id", "change_type"],
        "input_modes": ["AGENT_TASK", "INTERNAL_REQUEST"],
    },
    "WF-ADM-001": {
        "name": "행정 서류 발급·제출",
        "intent": "DOCUMENT_REQUEST",
        "sensitivity": "medium",
        "required_slots": ["worker_id", "document_type"],
        "input_modes": ["AGENT_TASK", "INTERNAL_REQUEST"],
    },
}


@dataclass
# 워크플로 카탈로그 한 건의 스냅샷
class WorkflowInfo:

    workflow_id: str
    name: str
    intent: str
    sensitivity: str
    required_slots: list[str] = field(default_factory=list)
    input_modes: list[str] = field(default_factory=list)


# 워크플로 id·intent로 카탈로그 조회
class WorkflowAgent:

    # 카탈로그 주입 미주입 시 builtin
    def __init__(self, catalog: dict[str, dict[str, object]] | None = None) -> None:
        self._catalog = catalog or _BUILTIN_CATALOG

    # workflow_id로 카탈로그 항목 반환
    def get_workflow(self, workflow_id: str) -> WorkflowInfo | None:
        entry = self._catalog.get(workflow_id)
        if entry is None:
            return None
        return WorkflowInfo(
            workflow_id=workflow_id,
            name=str(entry.get("name", "")),
            intent=str(entry.get("intent", "")),
            sensitivity=str(entry.get("sensitivity", "medium")),
            required_slots=list(entry.get("required_slots", [])),  # type: ignore[arg-type]
            input_modes=list(entry.get("input_modes", [])),  # type: ignore[arg-type]
        )

    # 등록된 모든 워크플로 반환
    def list_workflows(self) -> list[WorkflowInfo]:
        return [self.get_workflow(wid) for wid in self._catalog if self.get_workflow(wid)]  # type: ignore[misc]

    # Intent와 선택적 constraint로 최적 워크플로 선택
    def resolve_workflow(
        self, intent: str, constraints: list[str] | None = None
    ) -> WorkflowInfo | None:
        candidates = [
            self.get_workflow(wid)
            for wid, entry in self._catalog.items()
            if entry.get("intent") == intent
        ]
        candidates = [c for c in candidates if c is not None]

        if constraints:
            constrained = [c for c in candidates if c.workflow_id in constraints]
            if constrained:
                candidates = constrained

        return candidates[0] if candidates else None
