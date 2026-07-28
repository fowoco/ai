"""Intent 분류 + Slot 추출 에이전트.

MVP: 키워드 규칙 기반 분류. LLM 설정이 있으면 Structured Output 호출.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_INTENT_KEYWORDS: dict[str, list[str]] = {
    "WORKER_ONBOARDING": ["등록", "입사", "신규", "정보변경", "onboarding"],
    "EXPIRY_RENEWAL": ["만료", "연장", "갱신", "체류", "비자", "expiry", "renewal"],
    "DOCUMENT_REQUEST": ["서류", "문서", "사본", "발급", "확인서", "document"],
    "PAYROLL_EXPLANATION": ["급여", "월급", "공제", "명세", "payroll", "salary"],
    "WORK_INSTRUCTION": ["업무", "근무", "스케줄", "일정", "출근", "work", "schedule"],
    "EMPLOYMENT_CHANGE": ["퇴사", "해고", "이탈", "고용변동", "사업장변경", "change"],
}

INTENT_TO_WORKFLOWS: dict[str, list[str]] = {
    "WORKER_ONBOARDING": ["WF-WRK-001"],
    "EXPIRY_RENEWAL": ["WF-STY-001", "WF-CON-001"],
    "DOCUMENT_REQUEST": ["WF-DOC-001", "WF-ADM-001"],
    "PAYROLL_EXPLANATION": ["WF-PAY-001"],
    "WORK_INSTRUCTION": ["WF-INS-001"],
    "EMPLOYMENT_CHANGE": ["WF-CHG-001"],
}

_SLOT_PATTERNS: dict[str, re.Pattern[str]] = {
    "stay_expiry_date": re.compile(r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}"),
    "worker_id": re.compile(r"(?:WRK|W)-\d+", re.IGNORECASE),
    "document_type": re.compile(r"(?:여권|외국인등록증|고용허가서|근로계약서|건강보험|보험)"),
    "pay_period": re.compile(r"\d{4}[-/.]\d{1,2}"),
}

_WF_ID_PATTERN = re.compile(r"^WF-[A-Z]{3}-\d{3}$")


def expand_workflow_constraints(constraints: list[str]) -> list[str]:
    """Intent형(EXPIRY_RENEWAL)과 WF형(WF-STY-001) constraint를 WF id 목록으로 펼친다."""
    expanded: list[str] = []
    seen: set[str] = set()
    for item in constraints:
        targets = INTENT_TO_WORKFLOWS.get(item, [item])
        for workflow_id in targets:
            if workflow_id not in seen:
                seen.add(workflow_id)
                expanded.append(workflow_id)
    return expanded


def is_workflow_catalog_id(value: str) -> bool:
    return bool(_WF_ID_PATTERN.match(value))


def public_workflow_id(
    *,
    internal_workflow_id: str,
    intent: str,
    constraints: list[str],
) -> str:
    """응답용 workflowId.

    Server 계약 fixture는 Intent형 id(EXPIRY_RENEWAL)를 쓰고,
    knowledge catalog는 WF-STY-001 형태다. 요청 constraint에 있던 id를
    그대로 되돌려야 Server 검증을 통과한다.
    """
    if not constraints:
        return internal_workflow_id
    if intent in constraints:
        return intent
    if internal_workflow_id in constraints:
        return internal_workflow_id
    for constraint in constraints:
        mapped = INTENT_TO_WORKFLOWS.get(constraint, [])
        if internal_workflow_id in mapped:
            return constraint
    return internal_workflow_id


@dataclass
class IntentResult:
    intent: str
    confidence: float
    workflow_id: str
    extracted_slots: dict[str, str] = field(default_factory=dict)


class IntentSlotAgent:
    """키워드 기반 Intent 분류 + 정규식 Slot 추출 (MVP)."""

    def classify(
        self,
        instruction: str,
        *,
        workflow_constraints: list[str] | None = None,
    ) -> IntentResult:
        scores: dict[str, int] = {}
        lowered = instruction.lower()
        for intent, keywords in _INTENT_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in lowered)
            if score > 0:
                scores[intent] = score

        if not scores:
            return IntentResult(
                intent="OUT_OF_SCOPE",
                confidence=0.1,
                workflow_id="",
            )

        best_intent = max(scores, key=lambda k: scores[k])
        max_score = scores[best_intent]
        total_keywords = len(_INTENT_KEYWORDS[best_intent])
        confidence = min(0.95, 0.5 + (max_score / total_keywords) * 0.45)

        candidate_workflows = list(INTENT_TO_WORKFLOWS.get(best_intent, []))
        if workflow_constraints:
            expanded = set(expand_workflow_constraints(workflow_constraints))
            constrained = [w for w in candidate_workflows if w in expanded]
            if constrained:
                candidate_workflows = constrained
            elif best_intent not in workflow_constraints and not any(
                is_workflow_catalog_id(c) for c in workflow_constraints
            ):
                # Intent형 constraint만 있는데 현재 intent와 불일치하면 비움
                candidate_workflows = []

        workflow_id = candidate_workflows[0] if candidate_workflows else ""

        extracted = self._extract_slots(instruction)

        return IntentResult(
            intent=best_intent,
            confidence=round(confidence, 2),
            workflow_id=workflow_id,
            extracted_slots=extracted,
        )

    def _extract_slots(self, instruction: str) -> dict[str, str]:
        slots: dict[str, str] = {}
        for slot_key, pattern in _SLOT_PATTERNS.items():
            match = pattern.search(instruction)
            if match:
                slots[slot_key] = match.group()
        return slots
