# Intent·Slot — EXPIRY_RENEWAL 고정. WF 매핑은 Knowledge workflow_catalog 근거

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

# Knowledge workflow_catalog.yaml: intent → workflow id (동일 intent면 catalog 등장 순)
INTENT_TO_WORKFLOWS: dict[str, list[str]] = {
    "WORKER_ONBOARDING": ["WF-WRK-001"],
    "EXPIRY_RENEWAL": ["WF-STY-001", "WF-CON-001"],
    "DOCUMENT_REQUEST": ["WF-DOC-001", "WF-ADM-001"],
    "PAYROLL_EXPLANATION": ["WF-PAY-001"],
    "WORK_INSTRUCTION": ["WF-INS-001"],
    "EMPLOYMENT_CHANGE": ["WF-CHG-001"],
}

_WF_ID_PATTERN = re.compile(r"^WF-[A-Z]{3}-\d{3}$")


# Intent형·WF형 constraint를 WF catalog id 목록으로 정규화
def expand_workflow_constraints(constraints: list[str]) -> list[str]:
    expanded: list[str] = []
    seen: set[str] = set()
    for item in constraints:
        targets = INTENT_TO_WORKFLOWS.get(item, [item])
        for workflow_id in targets:
            if workflow_id not in seen:
                seen.add(workflow_id)
                expanded.append(workflow_id)
    return expanded


# WF-XXX-000 형태인지 확인
def is_workflow_catalog_id(value: str) -> bool:
    return bool(_WF_ID_PATTERN.match(value))


# 요청 constraint에 맞춰 응답에 실을 workflowId 결정
def public_workflow_id(
    *,
    internal_workflow_id: str,
    intent: str,
    constraints: list[str],
) -> str:
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


# 의도 후보 WF에 constraint 적용 (다후보는 catalog 순 첫 id)
def resolve_workflow_id(
    intent: str,
    workflow_constraints: list[str] | None,
) -> str:
    candidate_workflows = list(INTENT_TO_WORKFLOWS.get(intent, []))
    if workflow_constraints:
        expanded = set(expand_workflow_constraints(workflow_constraints))
        constrained = [w for w in candidate_workflows if w in expanded]
        if constrained:
            candidate_workflows = constrained
        elif intent not in workflow_constraints and not any(
            is_workflow_catalog_id(c) for c in workflow_constraints
        ):
            candidate_workflows = []
    return candidate_workflows[0] if candidate_workflows else ""


@dataclass
# Intent 분류와 Slot 추출 결과
class IntentResult:

    intent: str
    confidence: float
    workflow_id: str
    extracted_slots: dict[str, str] = field(default_factory=dict)


# 교체 가능한 Intent 분류기 계약
class IntentClassifier(Protocol):

    # 지시문 Intent 분류·관련 Slot 추출
    def classify(
        self,
        instruction: str,
        *,
        workflow_constraints: list[str] | None = None,
    ) -> IntentResult: ...


# 재갱신 Intent 고정 — 슬롯은 Server worker 시드에 맡김 (발화 정규식 추출 없음)
class FixedExpiryRenewalIntentAgent:

    # 항상 EXPIRY_RENEWAL로 두고 workflowId만 채움
    def classify(
        self,
        instruction: str,
        *,
        workflow_constraints: list[str] | None = None,
    ) -> IntentResult:
        del instruction
        intent = "EXPIRY_RENEWAL"
        return IntentResult(
            intent=intent,
            confidence=1.0,
            workflow_id=resolve_workflow_id(intent, workflow_constraints),
            extracted_slots={},
        )


# 재갱신 고정 Intent 분류기 생성
def build_intent_agent() -> IntentClassifier:
    return FixedExpiryRenewalIntentAgent()
