# 메인 슈퍼바이저 — 서브그래프 라우팅 (규칙 기본, LLM 옵션)

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Literal

from app.core.config import get_settings

from .document_validation import DocumentValidation, validate_identity_documents
from .phases import WorkflowPhase, WorkflowStep
from .state import IDENTITY_SLOTS

logger = logging.getLogger(__name__)

SupervisorRoute = Literal[
    "out_of_scope",
    "ask_hr",
    "ask_worker",
    "ocr",
    "generate",
]

_ALLOWED: frozenset[str] = frozenset(
    {"out_of_scope", "ask_hr", "ask_worker", "ocr", "generate"}
)


# 슈퍼바이저 한 번의 판단 결과
@dataclass(frozen=True)
class SupervisorDecision:

    route: SupervisorRoute
    phase: WorkflowPhase
    step: WorkflowStep
    reason: str
    source: Literal["rules", "llm"]
    document_validation: DocumentValidation | None = None
    case_signals: tuple[str, ...] = ()


# 규칙 기반 슈퍼바이저 라우팅 (회의 조합 라우팅 반영)
def decide_route_rules(state: dict[str, Any]) -> SupervisorDecision:
    if state.get("outcome") == "OUT_OF_SCOPE" or state.get("intent") == "OUT_OF_SCOPE":
        return SupervisorDecision(
            route="out_of_scope",
            phase=WorkflowPhase.INTAKE_ANALYSIS,
            step=WorkflowStep.STEP_2_INTENT_SLOT,
            reason="범위 밖 Intent",
            source="rules",
        )

    validation = validate_identity_documents(state)
    missing = list(state.get("missing_slots") or [])
    identity_missing = [m for m in missing if m in IDENTITY_SLOTS]
    other_missing = [m for m in missing if m not in IDENTITY_SLOTS]
    has_docs = bool(state.get("documents"))
    has_ocr = bool(state.get("ocr_result"))

    # 서류 업로드 재호출 → OCR 서브그래프
    if has_docs and not has_ocr:
        return SupervisorDecision(
            route="ocr",
            phase=WorkflowPhase.EXTRACTION_DOCUMENT,
            step=WorkflowStep.STEP_11_OCR,
            reason="업로드 서류 OCR 필요",
            source="rules",
            document_validation=validation,
            case_signals=("RUN_OCR",),
        )

    # Intent 없으면 슬롯 대기로 안전 폴백
    if not state.get("intent"):
        return SupervisorDecision(
            route="ask_hr",
            phase=WorkflowPhase.INTAKE_ANALYSIS,
            step=WorkflowStep.STEP_2_INTENT_SLOT,
            reason="Intent 비어 있음 → NEEDS_INFO 폴백",
            source="rules",
            document_validation=validation,
            case_signals=("NEEDS_INFO",),
        )

    # 여권/등록증 조합 — 둘 다 없거나 등록증만 비면 근로자 서류 요청
    if validation.combo in {"both_missing", "passport_only", "partial_unknown"} and (
        identity_missing or validation.missing_identity_slots
    ) and not has_ocr:
        signals = ["REQUEST_IDENTITY_DOCUMENT"]
        if validation.passport == "missing":
            signals.append("REQUEST_PASSPORT")
        if validation.alien_registration in {"missing", "unknown"}:
            signals.append("REQUEST_ALIEN_REGISTRATION")
        return SupervisorDecision(
            route="ask_worker",
            phase=WorkflowPhase.VALIDATION_COMMUNICATION,
            step=WorkflowStep.STEP_5_CASE_SIGNAL,
            reason=f"신분서류 조합={validation.combo}",
            source="rules",
            document_validation=validation,
            case_signals=tuple(signals),
        )

    if other_missing or missing:
        return SupervisorDecision(
            route="ask_hr",
            phase=WorkflowPhase.VALIDATION_COMMUNICATION,
            step=WorkflowStep.STEP_5_CASE_SIGNAL,
            reason="계약·근무 슬롯 부족",
            source="rules",
            document_validation=validation,
            case_signals=("REQUEST_CONTRACT_SLOTS", "NEEDS_INFO"),
        )

    return SupervisorDecision(
        route="generate",
        phase=WorkflowPhase.EXTRACTION_DOCUMENT,
        step=WorkflowStep.STEP_13_DOCUMENT_DRAFT,
        reason="슬롯·서류 충분 → 초안 생성",
        source="rules",
        document_validation=validation,
        case_signals=("GENERATE_DRAFTS", "READY_FOR_REVIEW"),
    )


# LLM 응답에서 라우트 토큰 추출
def _parse_llm_route(text: str) -> SupervisorRoute | None:
    lowered = text.strip().lower()
    for name in _ALLOWED:
        if re.search(rf"\b{re.escape(name)}\b", lowered):
            return name  # type: ignore[return-value]
    try:
        data = json.loads(text)
        route = str(data.get("route") or "")
        if route in _ALLOWED:
            return route  # type: ignore[return-value]
    except json.JSONDecodeError:
        pass
    return None


# OpenAI 호환 Chat API로 라우트 제안 (실패 시 None)
def _llm_suggest_route(state: dict[str, Any], fallback: SupervisorDecision) -> str | None:
    settings = get_settings()
    if not settings.llm_api_key or not settings.llm_provider:
        return None
    try:
        from urllib import request

        validation = fallback.document_validation or validate_identity_documents(state)
        payload = {
            "model": settings.llm_model or "gpt-4o-mini",
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a renewal workflow supervisor. "
                        "Reply with JSON only: {\"route\": one of "
                        "[out_of_scope, ask_hr, ask_worker, ocr, generate]}."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "intent": state.get("intent"),
                            "missing_slots": state.get("missing_slots"),
                            "documents": len(state.get("documents") or []),
                            "has_ocr": bool(state.get("ocr_result")),
                            "doc_combo": validation.combo,
                            "rule_fallback": fallback.route,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        base = "https://api.openai.com/v1/chat/completions"
        if settings.llm_provider not in {"openai", "OpenAI"}:
            if str(settings.llm_provider).startswith("http"):
                base = str(settings.llm_provider).rstrip("/") + "/chat/completions"
        req = request.Request(
            base,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {settings.llm_api_key}",
            },
            method="POST",
        )
        with request.urlopen(req, timeout=20) as resp:  # noqa: S310 — 내부 LLM 엔드포인트
            body = json.loads(resp.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        return _parse_llm_route(str(content))
    except Exception:  # noqa: BLE001 — 슈퍼바이저 LLM 실패 시 규칙으로 폴백
        logger.exception("supervisor LLM failed; using rules")
        return None


# 규칙 판단 후 설정되면 LLM으로 재확인 (허용 라우트만 채택)
def decide_route(state: dict[str, Any]) -> SupervisorDecision:
    rules = decide_route_rules(state)
    settings = get_settings()
    if settings.supervisor_mode != "llm":
        return rules
    suggested = _llm_suggest_route(state, rules)
    if not suggested or suggested == rules.route:
        return rules
    if suggested not in _ALLOWED:
        return rules
    return SupervisorDecision(
        route=suggested,  # type: ignore[arg-type]
        phase=rules.phase,
        step=rules.step,
        reason=f"LLM 제안={suggested} (규칙={rules.route})",
        source="llm",
        document_validation=rules.document_validation,
        case_signals=rules.case_signals,
    )
