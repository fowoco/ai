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

_INTENT_TO_WORKFLOWS: dict[str, list[str]] = {
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

        candidate_workflows = _INTENT_TO_WORKFLOWS.get(best_intent, [])
        if workflow_constraints:
            constrained = [w for w in candidate_workflows if w in workflow_constraints]
            if constrained:
                candidate_workflows = constrained

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
