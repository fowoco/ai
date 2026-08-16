# 워크플로 목록 조회 — Knowledge 카탈로그 또는 내장 목록

from __future__ import annotations

from dataclasses import dataclass, field

_DEFAULT_WORKFLOW_BY_INTENT: dict[str, str] = {
    "WORKER_ONBOARDING": "WF-WRK-001",
    "EXPIRY_RENEWAL": "WF-STY-001",
    "DOCUMENT_REQUEST": "WF-DOC-001",
    "PAYROLL_EXPLANATION": "WF-PAY-001",
    "WORK_INSTRUCTION": "WF-INS-001",
    "EMPLOYMENT_CHANGE": "WF-CHG-001",
}

# 하나의 대표 Intent 아래 여러 Knowledge Workflow가 있을 때 사용하는 업무 신호다.
# Intent 모델을 다시 호출하지 않고 발화/evidence만으로 canonical Workflow를 고른다.
_WORKFLOW_ROUTING_TERMS: dict[str, tuple[str, ...]] = {
    "WF-STY-001": (
        "체류기간 연장",
        "체류 연장",
        "체류기간",
        "비자 연장",
        "외국인등록증",
        "체류",
        "비자",
    ),
    "WF-CON-001": (
        "근로계약 갱신",
        "근로계약",
        "재계약",
        "취업활동기간 연장",
        "취업 활동 기간 연장",
        "고용허가기간 연장",
        "고용 허가 기간 연장",
        "계약 종료",
        "계약 만료",
        "계약 갱신",
    ),
    "WF-DOC-001": (
        "여권 사본",
        "등록증 사본",
        "사본 요청",
        "서류 요청",
        "제출 요청",
        "업로드",
        "사본",
    ),
    "WF-ADM-001": (
        "재직증명서",
        "경력증명서",
        "증명서 발급",
        "행정 서류",
        "기관 제출",
        "신고서",
        "발급",
    ),
}

_BUILTIN_CATALOG: dict[str, dict[str, object]] = {
    "WF-WRK-001": {
        "name": "근로자 등록·정보변경",
        "intent": "WORKER_ONBOARDING",
        "sensitivity": "high",
        "required_slots": ["source_document_id"],
        "context_slots": [],
        "input_modes": ["AGENT_TASK", "INTERNAL_REQUEST"],
    },
    "WF-STY-001": {
        "name": "체류기간 연장 준비",
        "intent": "EXPIRY_RENEWAL",
        "sensitivity": "high",
        "required_slots": ["worker_id", "due_at"],
        "context_slots": [
            "worker_id",
            "due_at",
            "stay_expiry_date",
            "passport_status",
            "arc_status",
        ],
        "input_modes": ["AGENT_TASK", "INTERNAL_REQUEST"],
    },
    "WF-CON-001": {
        "name": "근로계약 갱신 준비",
        "intent": "EXPIRY_RENEWAL",
        "sensitivity": "high",
        "required_slots": ["worker_id", "due_at"],
        "context_slots": ["worker_id", "due_at", "contract_end_date"],
        "input_modes": ["AGENT_TASK", "INTERNAL_REQUEST"],
    },
    "WF-DOC-001": {
        "name": "서류 요청·확인",
        "intent": "DOCUMENT_REQUEST",
        "sensitivity": "medium",
        "required_slots": [
            "worker_id",
            "document_type",
            "due_at",
            "submission_channel",
        ],
        "context_slots": ["worker_id"],
        "input_modes": ["AGENT_TASK", "INTERNAL_REQUEST", "WORKER_MESSAGE"],
    },
    "WF-PAY-001": {
        "name": "급여·공제 설명",
        "intent": "PAYROLL_EXPLANATION",
        "sensitivity": "high",
        "required_slots": ["worker_id", "pay_period", "source_document_id"],
        "context_slots": ["worker_id", "source_document_id"],
        "input_modes": ["AGENT_TASK", "INTERNAL_REQUEST", "WORKER_MESSAGE"],
    },
    "WF-INS-001": {
        "name": "업무·근무일정 안내",
        "intent": "WORK_INSTRUCTION",
        "sensitivity": "medium",
        "required_slots": ["worker_id", "effective_at", "work_action"],
        "context_slots": ["worker_id"],
        "input_modes": ["AGENT_TASK", "INTERNAL_REQUEST"],
    },
    "WF-CHG-001": {
        "name": "고용변동·이탈 후속조치",
        "intent": "EMPLOYMENT_CHANGE",
        "sensitivity": "critical",
        "required_slots": ["worker_id", "change_type", "incident_at"],
        "context_slots": ["worker_id"],
        "input_modes": ["AGENT_TASK", "INTERNAL_REQUEST"],
    },
    "WF-ADM-001": {
        "name": "행정 서류 발급·제출",
        "intent": "DOCUMENT_REQUEST",
        "sensitivity": "medium",
        "required_slots": ["worker_id", "document_type", "due_at"],
        "context_slots": ["worker_id"],
        "input_modes": ["AGENT_TASK", "INTERNAL_REQUEST"],
    },
}


def _normalized_text(value: str) -> str:
    return "".join(value.casefold().split())


# Intent 후보 안에서 발화 근거가 가장 강한 Workflow를 고른다.
# 매칭 신호가 없으면 catalog 순서가 아니라 명시된 MVP 기본 Workflow를 사용한다.
def select_workflow_id(
    *,
    intent: str,
    instruction: str,
    candidate_workflow_ids: list[str],
) -> str | None:
    if not candidate_workflow_ids:
        return None
    if len(candidate_workflow_ids) == 1:
        return candidate_workflow_ids[0]

    normalized = _normalized_text(instruction)
    ranked: list[tuple[int, int, str]] = []
    for workflow_id in candidate_workflow_ids:
        matches: list[tuple[str, int]] = []
        for term in _WORKFLOW_ROUTING_TERMS.get(workflow_id, ()):
            normalized_term = _normalized_text(term)
            position = normalized.find(normalized_term)
            if position >= 0:
                matches.append((normalized_term, position))
        if matches:
            score = sum(len(term) for term, _ in matches)
            first_position = min(position for _, position in matches)
            ranked.append((score, -first_position, workflow_id))

    if ranked:
        return max(ranked)[2]

    default_workflow = _DEFAULT_WORKFLOW_BY_INTENT.get(intent)
    if default_workflow in candidate_workflow_ids:
        return default_workflow
    return None


@dataclass
# 워크플로 카탈로그 한 건의 스냅샷
class WorkflowInfo:

    workflow_id: str
    name: str
    intent: str
    sensitivity: str
    required_slots: list[str] = field(default_factory=list)
    context_slots: list[str] = field(default_factory=list)
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
            context_slots=list(entry.get("context_slots", [])),  # type: ignore[arg-type]
            input_modes=list(entry.get("input_modes", [])),  # type: ignore[arg-type]
        )

    # 등록된 모든 워크플로 반환
    def list_workflows(self) -> list[WorkflowInfo]:
        return [self.get_workflow(wid) for wid in self._catalog if self.get_workflow(wid)]  # type: ignore[misc]

    # Intent와 선택적 constraint로 최적 워크플로 선택
    def resolve_workflow(
        self,
        intent: str,
        constraints: list[str] | None = None,
        *,
        instruction: str = "",
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

        selected_id = select_workflow_id(
            intent=intent,
            instruction=instruction,
            candidate_workflow_ids=[candidate.workflow_id for candidate in candidates],
        )
        return self.get_workflow(selected_id) if selected_id else None
