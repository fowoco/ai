# Intent 분류 + Slot 추출 — 지금은 EXPIRY_RENEWAL 고정, 나중에 분류기 교체 가능

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal, Protocol

# 의도별 힌트 단어 (대소문자 무시 비교용으로 instruction을 lower)
_INTENT_KEYWORDS: dict[str, list[str]] = {
    "WORKER_ONBOARDING": ["등록", "입사", "신규", "정보변경", "onboarding"],
    "EXPIRY_RENEWAL": ["만료", "연장", "갱신", "체류", "비자", "expiry", "renewal"],
    "DOCUMENT_REQUEST": ["서류", "문서", "사본", "발급", "확인서", "document"],
    "PAYROLL_EXPLANATION": ["급여", "월급", "공제", "명세", "payroll", "salary"],
    "WORK_INSTRUCTION": ["업무", "근무", "스케줄", "일정", "출근", "work", "schedule"],
    "EMPLOYMENT_CHANGE": ["퇴사", "해고", "이탈", "고용변동", "사업장변경", "change"],
}

# 의도 하나당 후보 워크플로 (앞에 있는 id를 기본으로 선택)
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

IntentMode = Literal["fixed_expiry_renewal", "keyword"]


# Intent형 constraint → 실제 WF id 목록 전개
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


# Catalog형 workflow id 여부만 판별
# WF-XXX-000 형태인지 확인
def is_workflow_catalog_id(value: str) -> bool:
    return bool(_WF_ID_PATTERN.match(value))


# Server 검증을 통과하도록 응답용 workflowId 선택
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


# 정규식으로 알려진 Slot 값 추출
def extract_slots(instruction: str) -> dict[str, str]:
    slots: dict[str, str] = {}
    for slot_key, pattern in _SLOT_PATTERNS.items():
        match = pattern.search(instruction)
        if match:
            slots[slot_key] = match.group()
    return slots


# 의도 후보 WF 목록에 constraint 적용
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


# 교체 가능한 Intent 분류기 계약 (나중에 모델/외부 엔진 붙일 때 이 시그니처 유지)
class IntentClassifier(Protocol):

    # 지시문 Intent 분류·관련 Slot 추출
    def classify(
        self,
        instruction: str,
        *,
        workflow_constraints: list[str] | None = None,
    ) -> IntentResult: ...


# 재갱신 Intent로 고정 — 슬롯 추출·WF constraint만 수행 (현재 기본)
class FixedExpiryRenewalIntentAgent:

    # 항상 EXPIRY_RENEWAL로 두고 Slot·workflowId만 채움
    def classify(
        self,
        instruction: str,
        *,
        workflow_constraints: list[str] | None = None,
    ) -> IntentResult:
        intent = "EXPIRY_RENEWAL"
        return IntentResult(
            intent=intent,
            confidence=1.0,
            workflow_id=resolve_workflow_id(intent, workflow_constraints),
            extracted_slots=extract_slots(instruction),
        )


# 키워드 기반 Intent 분류 + 정규식 Slot 추출 (교체용·테스트용)
class KeywordIntentSlotAgent:

    # 지시문 6+1 Intent 분류·관련 Slot 추출
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

        return IntentResult(
            intent=best_intent,
            confidence=round(confidence, 2),
            workflow_id=resolve_workflow_id(best_intent, workflow_constraints),
            extracted_slots=extract_slots(instruction),
        )


# 하위 호환: 예전 이름은 키워드 분류기를 가리킴 (테스트·명시 주입용)
IntentSlotAgent = KeywordIntentSlotAgent


# FOWOCO_INTENT_MODE에 맞는 분류기 생성 (기본: 재갱신 고정)
def build_intent_agent(mode: IntentMode | str | None = None) -> IntentClassifier:
    from app.core.config import get_settings

    resolved = mode or get_settings().intent_mode
    if resolved == "keyword":
        return KeywordIntentSlotAgent()
    return FixedExpiryRenewalIntentAgent()
