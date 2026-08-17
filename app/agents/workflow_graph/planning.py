from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .document_validation import validate_identity_documents
from .state import HR_EXCLUDED_SLOTS, IDENTITY_SLOTS

ShadowRoute = Literal["ask_hr", "ask_worker", "generate", "ocr", "out_of_scope"]
ActionType = Literal["TOOL", "SERVER_CONTROL"]


@dataclass(frozen=True)
class AgentPlanStep:
    step_id: str
    action_type: ActionType
    action: str
    reason: str

    def as_event_payload(self) -> dict[str, str]:
        return {
            "stepId": self.step_id,
            "actionType": self.action_type,
            "action": self.action,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ShadowPlan:
    proposed_route: ShadowRoute
    steps: tuple[AgentPlanStep, ...]


def _step(
    step_id: str,
    action_type: ActionType,
    action: str,
    reason: str,
) -> AgentPlanStep:
    return AgentPlanStep(step_id, action_type, action, reason)


def build_shadow_plan(state: dict[str, Any]) -> ShadowPlan:
    """현재 Supervisor와 독립적으로 다음 행동 계획을 제안한다.

    Shadow 계획은 비교·관측 전용이며 실제 Graph 분기를 변경하지 않는다.
    """

    if state.get("outcome") == "OUT_OF_SCOPE" or state.get("intent") == "OUT_OF_SCOPE":
        return ShadowPlan(
            proposed_route="out_of_scope",
            steps=(
                _step(
                    "CANCEL_OUT_OF_SCOPE",
                    "SERVER_CONTROL",
                    "CANCEL_OUT_OF_SCOPE",
                    "지원 범위 밖 요청은 Server가 업무 생성을 중단해야 합니다.",
                ),
            ),
        )

    validation = validate_identity_documents(state)
    missing = list(state.get("missing_slots") or [])
    identity_missing = [key for key in missing if key in IDENTITY_SLOTS]
    other_missing = [
        key for key in missing if key not in IDENTITY_SLOTS | HR_EXCLUDED_SLOTS
    ]
    has_documents = bool(state.get("documents"))
    has_ocr = bool(state.get("ocr_result"))

    if has_documents and not has_ocr:
        return ShadowPlan(
            proposed_route="ocr",
            steps=(
                _step(
                    "RUN_OCR",
                    "TOOL",
                    "RUN_OCR",
                    "업로드된 신분서류에서 구조화 값을 추출해야 합니다.",
                ),
                _step(
                    "GENERATE_RENEWAL_DOCUMENTS",
                    "TOOL",
                    "GENERATE_RENEWAL_DOCUMENTS",
                    "OCR 결과를 검증한 뒤 갱신 문서 초안을 생성합니다.",
                ),
            ),
        )

    if not state.get("intent"):
        return ShadowPlan(
            proposed_route="ask_hr",
            steps=(
                _step(
                    "REQUEST_INTENT_REVIEW",
                    "SERVER_CONTROL",
                    "REQUEST_HR_INPUT",
                    "업무 종류를 확정할 수 없어 HR 확인이 필요합니다.",
                ),
            ),
        )

    needs_identity_documents = validation.combo in {
        "both_missing",
        "passport_only",
        "partial_unknown",
    } and bool(identity_missing or validation.missing_identity_slots)
    if needs_identity_documents and not has_ocr:
        return ShadowPlan(
            proposed_route="ask_worker",
            steps=(
                _step(
                    "REQUEST_IDENTITY_DOCUMENTS",
                    "SERVER_CONTROL",
                    "REQUEST_WORKER_DOCUMENTS",
                    f"신분서류 조합이 {validation.combo}이므로 근로자 제출이 필요합니다.",
                ),
            ),
        )

    if other_missing:
        return ShadowPlan(
            proposed_route="ask_hr",
            steps=(
                _step(
                    "REQUEST_CONTRACT_SLOTS",
                    "SERVER_CONTROL",
                    "REQUEST_HR_SLOTS",
                    "계약·근무 조건의 누락값을 HR이 확인해야 합니다.",
                ),
            ),
        )

    return ShadowPlan(
        proposed_route="generate",
        steps=(
            _step(
                "GENERATE_RENEWAL_DOCUMENTS",
                "TOOL",
                "GENERATE_RENEWAL_DOCUMENTS",
                "필수 업무정보와 신분서류가 준비되어 초안을 생성할 수 있습니다.",
            ),
            _step(
                "REQUEST_HR_REVIEW",
                "SERVER_CONTROL",
                "REQUEST_HR_REVIEW",
                "생성 결과는 자동 발송하지 않고 HR 검토로 전달합니다.",
            ),
        ),
    )
