# RenewalState ↔ Language Assistant 투영·안내문 브리지 (태정 계약)

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Protocol

from app.agents.language.contracts import LanguageAssistantInput, LanguageAssistantOutput
from app.agents.language.projection import project_language_input
from app.agents.language.service import LanguageAssistantService

from .nodes.actions import mark_guide_placeholder
from .state import IDENTITY_SLOTS, RenewalState

logger = logging.getLogger(__name__)

_DOC_ITEM_LABELS: dict[str, str] = {
    "passport_number": "여권 사본 1부",
    "alien_registration_number": "외국인등록증 사본 1부",
    "nationality": "국적 확인 서류",
    "full_name": "성명 확인 서류",
    "date_of_birth": "생년월일 확인 서류",
}


# Language Assistant invoke 계약
class SupportsLanguageInvoke(Protocol):

    def invoke(self, request: LanguageAssistantInput) -> LanguageAssistantOutput: ...


# ask_worker용 RequestContext dict 생성
def build_ask_worker_request_context(state: RenewalState) -> dict[str, Any]:
    slots = state.get("slots") or {}
    missing = [m for m in (state.get("missing_slots") or []) if m in IDENTITY_SLOTS]
    items = [_DOC_ITEM_LABELS.get(m, m) for m in missing] or [
        "여권 사본 1부",
        "외국인등록증 사본 1부",
    ]
    raw_deadline = slots.get("stay_expiry_date") or slots.get("contract_end_date")
    try:
        deadline = date.fromisoformat(str(raw_deadline)[:10]) if raw_deadline else (
            date.today() + timedelta(days=14)
        )
    except ValueError:
        deadline = date.today() + timedelta(days=14)
    return {
        "request_reason": "체류기간 연장 신청",
        "requested_items": tuple(items),
        "deadline": deadline,
        "submission_method": "담당자(HR)에게 직접 제출",
    }


# RenewalState → Language projection 부모 dict
def renewal_as_language_parent(state: RenewalState) -> dict[str, Any]:
    worker = state.get("worker_record") or {}
    slots = state.get("slots") or {}
    ctx = state.get("request_context") or build_ask_worker_request_context(state)
    worker_id = (
        state.get("worker_id")
        or worker.get("worker_id")
        or worker.get("workerId")
        or slots.get("worker_id")
        or state["task_id"]
    )
    preferred = (
        state.get("preferred_language")
        or worker.get("preferred_language")
        or worker.get("preferredLanguage")
    )
    nationality = (
        state.get("nationality_code")
        or worker.get("nationality_code")
        or worker.get("nationalityCode")
        or slots.get("nationality")
        or slots.get("nationality_code")
    )
    parent: dict[str, Any] = {
        "worker_id": str(worker_id),
        "request_context": ctx,
    }
    if preferred:
        parent["preferred_language"] = str(preferred)
    if nationality:
        parent["nationality_code"] = str(nationality)
    return parent


# Language 출력을 근로자 안내 문구로 합침
def worker_message_from_language_output(output: LanguageAssistantOutput) -> str:
    parts = [output.standard_korean_text.strip()]
    if output.easy_korean_text and output.easy_korean_text != output.standard_korean_text:
        parts.append(output.easy_korean_text.strip())
    if output.translated_text:
        parts.append(output.translated_text.strip())
    return "\n\n".join(p for p in parts if p)


# 안내문 노드 — Language Assistant 가능 시 호출, 실패 시 placeholder
class LanguageGuideBridge:

    # 선택적 LanguageAssistantService 주입
    def __init__(self, service: SupportsLanguageInvoke | None = None) -> None:
        self._service = service

    # guide 단계 State 패치
    def __call__(self, state: RenewalState) -> dict[str, Any]:
        base = mark_guide_placeholder(state)
        if self._service is None:
            return {
                **base,
                "worker_request_message": None,
                "guide_review_required": True,
                "guide_failure_code": "LANGUAGE_ASSISTANT_NOT_CONFIGURED",
            }
        try:
            parent = renewal_as_language_parent(state)
            request = project_language_input(parent)
            output = self._service.invoke(request)
            message = worker_message_from_language_output(output)
            review_required = output.requires_human_review
            return {
                **base,
                "request_context": parent.get("request_context"),
                "preferred_language": parent.get("preferred_language"),
                "nationality_code": parent.get("nationality_code"),
                "language_assistant": output.model_dump(mode="json"),
                "guide_message": output.standard_korean_text,
                "worker_request_message": None if review_required else message,
                "guide_review_required": review_required,
                "guide_failure_code": (
                    "LANGUAGE_ASSISTANT_REVIEW_REQUIRED" if review_required else None
                ),
            }
        except Exception:
            logger.exception("Language Assistant guide failed — placeholder fallback")
            return {
                **base,
                "worker_request_message": None,
                "guide_review_required": True,
                "guide_failure_code": "LANGUAGE_ASSISTANT_INVOCATION_FAILED",
            }


# LanguageAssistantService용 노드 팩토리 (태정 build_language_assistant_node 래핑)
def build_renewal_language_guide(
    service: LanguageAssistantService | None,
) -> LanguageGuideBridge:
    return LanguageGuideBridge(service=service)
