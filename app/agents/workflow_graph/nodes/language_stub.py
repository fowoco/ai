# Language 임시 구현 — 동료 Language 노드가 오기 전 Intent/Ambiguity 규칙 사용

from __future__ import annotations

from typing import Any

from app.agents.ambiguity import AmbiguityAgent
from app.agents.intent import IntentClassifier, build_intent_agent

from ..state import HR_EXCLUDED_SLOTS, IDENTITY_SLOTS, RenewalState

# 담당자 입력 — 클라이언트가 채우는 계약·근무 슬롯.
CONTRACT_SLOTS: tuple[str, ...] = (
    "wage",
    "working_hours",
    "job_description",
    "work_location",
    "lodging",
    "contract_period",
)


# 규칙 기반 Language stub. 동료 Language 노드로 교체
class StubLanguageNode:

    # Intent·Ambiguity 에이전트 주입 (기본: 설정 기반 Intent 분류기)
    def __init__(
        self,
        *,
        intent_agent: IntentClassifier | None = None,
        ambiguity_agent: AmbiguityAgent | None = None,
    ) -> None:
        self._intent = intent_agent or build_intent_agent()
        self._ambiguity = ambiguity_agent or AmbiguityAgent()

    # intent·slots·missing·가이드 문구 채움
    def __call__(self, state: RenewalState) -> dict[str, Any]:
        task_workflow_id = str(state.get("workflow_id") or "").strip()
        result = self._intent.classify(
            state["instruction"],
            workflow_constraints=[task_workflow_id] if task_workflow_id else None,
        )
        slots = {**state.get("slots", {}), **result.extracted_slots}

        if result.intent == "OUT_OF_SCOPE":
            return {
                "intent": "OUT_OF_SCOPE",
                "workflow_id": "",
                "confidence": result.confidence,
                "slots": slots,
                "missing_slots": [],
                "guide_message": "요청이 지원 범위를 벗어났습니다. 다시 시작해 주세요.",
                "scenario": "out_of_scope",
                "status": "CANCELLED",
                "outcome": "OUT_OF_SCOPE",
            }

        workflow_id = result.workflow_id or "UNKNOWN"
        amb = self._ambiguity.check(workflow_id, slots, state["instruction"])
        missing = [key for key in amb.missing_slots if key not in HR_EXCLUDED_SLOTS]

        # 재갱신: 신분(근로자 서류) + 계약(담당자 입력) 슬롯 누락 함께 확인
        if result.intent == "EXPIRY_RENEWAL":
            for key in IDENTITY_SLOTS:
                if not slots.get(key) and key not in missing:
                    missing.append(key)
            for key in CONTRACT_SLOTS:
                if not slots.get(key) and key not in missing:
                    missing.append(key)

        guide = None
        if missing:
            guide = (
                "재갱신에 필요한 정보가 부족합니다. 다음 항목을 입력해 주세요: "
                + ", ".join(missing)
            )

        return {
            "intent": result.intent,
            "workflow_id": workflow_id,
            "confidence": result.confidence,
            "slots": slots,
            "missing_slots": missing,
            "guide_message": guide,
        }
