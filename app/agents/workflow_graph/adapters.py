# 동료 Language/OCR 결과를 Shared State 키로 맞추는 어댑터

from __future__ import annotations

from typing import Any, Protocol

from .state import RenewalState


# 동료 Language 엔진 계약 (자체 입출력을 써도 됨)
class ExternalLanguageEngine(Protocol):

    # Language 전용 입력을 처리해 결과 dict 반환
    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...


# 동료 OCR 엔진 계약 (자체 입출력을 써도 됨)
class ExternalOcrEngine(Protocol):

    # OCR 전용 입력을 처리해 결과 dict 반환
    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...


# 우리 State에서 Language 엔진에 넘길 입력만 추출
def language_payload_from_state(state: RenewalState) -> dict[str, Any]:
    return {
        "task_id": state["task_id"],
        "request_id": state["request_id"],
        "instruction": state["instruction"],
        "worker_id": state.get("worker_id"),
        "company_id": state.get("company_id"),
        "slots": dict(state.get("slots") or {}),
        "worker_record": state.get("worker_record"),
        "company_record": state.get("company_record"),
    }


# 우리 State에서 OCR 엔진에 넘길 입력만 추출
def ocr_payload_from_state(state: RenewalState) -> dict[str, Any]:
    return {
        "task_id": state["task_id"],
        "worker_id": state.get("worker_id"),
        "documents": list(state.get("documents") or []),
        "slots": dict(state.get("slots") or {}),
        "missing_slots": list(state.get("missing_slots") or []),
    }


# 동료 Language 결과 키(별칭 포함)를 우리 State 부분 업데이트로 맞춤
def normalize_language_output(
    raw: dict[str, Any], *, base_slots: dict[str, Any]
) -> dict[str, Any]:
    # 동료마다 키 이름이 다를 수 있어 후보를 넓게 받는다
    slots_in = raw.get("slots") or raw.get("extracted_slots") or raw.get("extractedSlots") or {}
    missing = (
        raw.get("missing_slots")
        or raw.get("missingSlots")
        or raw.get("required_missing")
        or []
    )
    return {
        "intent": str(raw.get("intent") or raw.get("Intent") or ""),
        "workflow_id": str(
            raw.get("workflow_id") or raw.get("workflowId") or raw.get("workflow") or ""
        ),
        "confidence": float(raw.get("confidence") or raw.get("score") or 0.0),
        "slots": {**base_slots, **dict(slots_in)},
        "missing_slots": [str(x) for x in missing],
        "guide_message": raw.get("guide_message")
        or raw.get("guideMessage")
        or raw.get("message"),
    }


# 동료 OCR 결과 키(별칭 포함)를 우리 State 부분 업데이트로 맞춤
def normalize_ocr_output(
    raw: dict[str, Any], *, base_slots: dict[str, Any], base_missing: list[str]
) -> dict[str, Any]:
    from .ocr_bridge import normalize_ocr_fields

    extracted = (
        raw.get("ocr_result")
        or raw.get("ocrResult")
        or raw.get("fields")
        or raw.get("extracted")
        or {}
    )
    slots_in = raw.get("slots") or {}
    normalized = normalize_ocr_fields({**dict(extracted), **dict(slots_in)})
    merged = {**base_slots, **normalized}
    missing_raw = raw.get("missing_slots") or raw.get("missingSlots")
    if missing_raw is None:
        missing = [m for m in base_missing if not merged.get(m)]
    else:
        missing = [str(x) for x in missing_raw]
    return {
        "ocr_result": normalized,
        "slots": merged,
        "missing_slots": missing,
    }


# 동료 Language 엔진을 그래프 LanguageNode 자리에 꽂기 위한 래퍼
class LanguageNodeAdapter:

    # 동료 Language 엔진 보관
    def __init__(self, engine: ExternalLanguageEngine) -> None:
        self._engine = engine

    # State → 동료 입력 → 우리 형식 결과
    def __call__(self, state: RenewalState) -> dict[str, Any]:
        raw = self._engine.run(language_payload_from_state(state))
        return normalize_language_output(raw, base_slots=dict(state.get("slots") or {}))


# 동료 OCR 엔진을 그래프 OcrNode 자리에 꽂기 위한 래퍼
class OcrNodeAdapter:

    # 동료 OCR 엔진 보관
    def __init__(self, engine: ExternalOcrEngine) -> None:
        self._engine = engine

    # State → 동료 입력 → 우리 형식 결과
    def __call__(self, state: RenewalState) -> dict[str, Any]:
        raw = self._engine.run(ocr_payload_from_state(state))
        return normalize_ocr_output(
            raw,
            base_slots=dict(state.get("slots") or {}),
            base_missing=list(state.get("missing_slots") or []),
        )
