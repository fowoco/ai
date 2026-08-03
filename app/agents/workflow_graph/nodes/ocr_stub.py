# OCR 임시 구현 — 동료 OCR 노드가 오기 전 업로드 메타/힌트로 신분 값 채움

from __future__ import annotations

from typing import Any

from ..state import RenewalState


# 가짜 OCR 매핑. documents[].hints 또는 고정 stub 값 사용
class StubOcrNode:

    # documents에서 신분 슬롯을 뽑아 ocr_result로 반환
    def __call__(self, state: RenewalState) -> dict[str, Any]:
        extracted: dict[str, Any] = {}
        for doc in state.get("documents") or []:
            hints = doc.get("hints") or {}
            if isinstance(hints, dict):
                extracted.update({k: v for k, v in hints.items() if v})
            doc_type = str(doc.get("document_type") or doc.get("type") or "").lower()
            if "passport" in doc_type or "여권" in doc_type:
                extracted.setdefault("passport_number", "P-STUB-0001")
                extracted.setdefault("nationality", "VN")
                extracted.setdefault("full_name", "STUB WORKER")
            if "alien" in doc_type or "외국인" in doc_type or "arc" in doc_type:
                extracted.setdefault("alien_registration_number", "000000-0000000")
                extracted.setdefault("date_of_birth", "1990-01-01")

        if not extracted and state.get("documents"):
            extracted = {
                "passport_number": "P-STUB-0001",
                "alien_registration_number": "000000-0000000",
                "nationality": "VN",
                "full_name": "STUB WORKER",
                "date_of_birth": "1990-01-01",
            }

        slots = {**state.get("slots", {}), **extracted}
        missing = [m for m in state.get("missing_slots", []) if not slots.get(m)]
        return {
            "ocr_result": extracted,
            "slots": slots,
            "missing_slots": missing,
        }
