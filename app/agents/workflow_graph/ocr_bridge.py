# documents에 실린 CLOVA/사전 OCR 필드를 신분 슬롯으로 정규화 (주현 연동)

from __future__ import annotations

from typing import Any

from .nodes.ocr_stub import StubOcrNode
from .state import RenewalState

# CLOVA/정규화 필드 → Renewal IDENTITY 슬롯
_FIELD_ALIASES: dict[str, str] = {
    "passport_number": "passport_number",
    "alien_registration_number": "alien_registration_number",
    "date_of_birth": "date_of_birth",
    "nationality": "nationality",
    "full_name": "full_name",
    "legal_name": "full_name",
    "stay_expiration_date": "stay_expiry_date",
}


# document dict에서 원시 필드 맵 추출
def _raw_fields_from_document(doc: dict[str, Any]) -> dict[str, Any]:
    for key in ("fields", "ocr_fields", "ocrFields", "extracted", "hints"):
        raw = doc.get(key)
        if isinstance(raw, dict) and raw:
            return dict(raw)
    return {}


# surname+given_names → full_name 등 슬롯 정규화
def normalize_ocr_fields(raw: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if value in (None, ""):
            continue
        if isinstance(value, dict) and "value" in value:
            value = value.get("value")
        if value in (None, ""):
            continue
        mapped = _FIELD_ALIASES.get(str(key))
        if mapped:
            out[mapped] = value
    surname = raw.get("surname")
    given = raw.get("given_names") or raw.get("givenNames")
    if not out.get("full_name") and (surname or given):
        parts = [str(p).strip() for p in (surname, given) if p]
        if parts:
            out["full_name"] = " ".join(parts)
    return out


# CLOVA 결과 우선·없으면 StubOcrNode 폴백
class DocumentOcrNode:

    # stub 폴백 보관
    def __init__(self, *, fallback: StubOcrNode | None = None) -> None:
        self._fallback = fallback or StubOcrNode()

    # documents 필드 병합 → ocr_result/slots
    def __call__(self, state: RenewalState) -> dict[str, Any]:
        extracted: dict[str, Any] = {}
        for doc in state.get("documents") or []:
            if not isinstance(doc, dict):
                continue
            extracted.update(normalize_ocr_fields(_raw_fields_from_document(doc)))
        existing = state.get("ocr_result")
        if isinstance(existing, dict):
            nested = existing.get("fields") if isinstance(existing.get("fields"), dict) else {}
            flat = {
                k: v
                for k, v in existing.items()
                if k not in ("fields", "extracted", "status", "error") and v not in (None, "")
            }
            extracted = {**normalize_ocr_fields({**flat, **dict(nested or {})}), **extracted}

        if extracted:
            slots = {**state.get("slots", {}), **extracted}
            missing = [m for m in state.get("missing_slots", []) if not slots.get(m)]
            return {
                "ocr_result": extracted,
                "slots": slots,
                "missing_slots": missing,
            }
        return self._fallback(state)
