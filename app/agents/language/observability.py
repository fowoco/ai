"""T14 — 프라이버시 안전 트레이싱, 프롬프트 인젝션 방어, 장애 격리 유틸리티.

원칙:
- TraceEvent에 PII(원문, 쿼리, 프롬프트, API Key) 절대 포함 금지
- 사용자 입력은 build_safe_payload()로 정규화 후 LLM 페이로드에 삽입
- 컴포넌트 장애는 with_fault_isolation()으로 격리 — 상위 그래프 미전파

ponytail: 최소 구현. 정규식 기반 인젝션 방어 — 충분한 수준.
ceiling: 벡터 기반 인젝션 탐지 필요 시 별도 파이프라인으로 교체.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, TypeVar

from app.agents.language.contracts import SupportedLanguage, WarningCode, WarningItem
from app.agents.language.ports import TraceEvent  # noqa: F401 (re-export)

# 허용 TraceEvent 필드 — PII 절대 포함 금지
TRACE_ALLOWLIST = frozenset(
    TraceEvent.model_fields.keys()
)

# 프롬프트 인젝션 위험 패턴 (순서 중요 — 더 구체적 패턴 먼저)
_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"```[\s\S]*?```", re.MULTILINE),           # 코드 블록
    re.compile(r"\[INST\][\s\S]*?\[/INST\]", re.IGNORECASE),  # Llama 태그
    re.compile(r"<<SYS>>[\s\S]*?<<\/SYS>>", re.IGNORECASE),   # 시스템 태그
    re.compile(r"^\s*---+\s*$", re.MULTILINE),             # 수평선 구분자
    re.compile(
        r"(?i)(?:^|\n)\s*(?:SYSTEM|ASSISTANT|USER|HUMAN|AI)\s*[:\|>]",
        re.MULTILINE,
    ),  # 역할 헤더
    re.compile(
        r"(?i)ignore\s+(?:all\s+)?(?:previous|above|prior)\s+(?:instructions?|context|prompt)",
    ),  # 인젝션 명령
]


def sanitize_user_input(text: str) -> str:
    """사용자 입력에서 프롬프트 인젝션 패턴 제거.

    원문 의미를 최대한 보존하면서 시스템 지시 결합을 방지.
    """
    result = text
    for pattern in _INJECTION_PATTERNS:
        result = pattern.sub(" ", result)
    # 연속 공백/개행 정규화
    result = re.sub(r"\n{3,}", "\n\n", result)
    result = re.sub(r"[ \t]{2,}", " ", result)
    return result.strip()


def build_safe_payload(
    context: object,
    *,
    target_language: SupportedLanguage,
) -> dict[str, object]:
    """RequestContext를 LLM 안전 페이로드로 변환.

    - 각 필드를 sanitize_user_input()으로 이스케이프
    - 시스템 프롬프트와 결합 불가한 형태로 구조화
    """
    from app.agents.language.contracts import RequestContext

    if not isinstance(context, RequestContext):
        raise TypeError(f"RequestContext 필요, 받은 타입: {type(context)}")

    return {
        "request_reason": sanitize_user_input(context.request_reason),
        "requested_items": [
            sanitize_user_input(item) for item in context.requested_items
        ],
        "deadline": context.deadline.isoformat(),
        "submission_method": sanitize_user_input(context.submission_method),
        "target_language": target_language,
    }


# ---------------------------------------------------------------------------
# 장애 격리 데코레이터
# ---------------------------------------------------------------------------

_COMPONENT_TO_WARNING_CODE: dict[str, WarningCode] = {
    "translation": WarningCode.TRANSLATION_GENERATION_FAILED,
    "easy_korean": WarningCode.EASY_KOREAN_GENERATION_FAILED,
    "retrieval": WarningCode.RETRIEVAL_UNAVAILABLE,
    "reranker": WarningCode.RERANKER_UNAVAILABLE,
    "encoder": WarningCode.RETRIEVAL_ENCODER_UNAVAILABLE,
    "semantic_validation": WarningCode.SEMANTIC_VALIDATION_INCONCLUSIVE,
}

_DEFAULT_WARNING_CODE = WarningCode.RETRIEVAL_UNAVAILABLE

ReturnT = TypeVar("ReturnT")


def with_fault_isolation(
    component: str,
) -> Callable[[Callable[..., ReturnT]], Callable[..., tuple[ReturnT | None, WarningItem | None]]]:
    """컴포넌트 장애 격리 데코레이터.

    장애 발생 시 (None, WarningItem) 반환 — 예외 미전파.
    성공 시 (result, None) 반환.

    사용:
        @with_fault_isolation("translation")
        def call_llm() -> str: ...
        result, warn = call_llm()
    """

    def decorator(
        fn: Callable[..., ReturnT],
    ) -> Callable[..., tuple[ReturnT | None, WarningItem | None]]:
        def wrapper(*args: Any, **kwargs: Any) -> tuple[ReturnT | None, WarningItem | None]:
            try:
                return fn(*args, **kwargs), None
            except Exception as exc:
                code = _COMPONENT_TO_WARNING_CODE.get(component, _DEFAULT_WARNING_CODE)
                warning = WarningItem(
                    component=component,
                    code=code,
                    # ponytail: 예외 타입만 포함 — 원문/PII 절대 미포함
                    message=f"{type(exc).__name__} in {component}",
                )
                return None, warning

        return wrapper

    return decorator


__all__ = [
    "TRACE_ALLOWLIST",
    "build_safe_payload",
    "sanitize_user_input",
    "with_fault_isolation",
]
