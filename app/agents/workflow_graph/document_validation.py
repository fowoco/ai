# 여권·외국인등록증 보유 조합 검증 — 회의 Step4 라우팅용

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .state import IDENTITY_SLOTS

DocPresence = Literal["present", "missing", "unknown"]
DocCombo = Literal[
    "both_present",
    "passport_only",
    "alien_only",
    "both_missing",
    "partial_unknown",
]


# 여권/등록증 슬롯·업로드 문서 존재 여부
@dataclass(frozen=True)
class DocumentValidation:

    passport: DocPresence
    alien_registration: DocPresence
    combo: DocCombo
    missing_identity_slots: tuple[str, ...]
    evidence: tuple[dict[str, str], ...]


# 문서 메타·슬롯에서 여권/등록증 보유 여부 판정
def _presence_from_docs_and_slots(
    *,
    documents: list[dict[str, Any]],
    slots: dict[str, Any],
    ocr_result: dict[str, Any] | None,
) -> tuple[DocPresence, DocPresence]:
    types = {
        str(d.get("document_type") or d.get("documentType") or "").lower()
        for d in documents
    }
    ocr = ocr_result or {}

    passport_keys = ("passport_number", "passportNumber")
    alien_keys = ("alien_registration_number", "alienRegistrationNumber")

    def has_slot(keys: tuple[str, ...]) -> bool:
        return any(slots.get(k) or ocr.get(k) for k in keys)

    passport: DocPresence = "unknown"
    if any("passport" in t or "여권" in t for t in types) or has_slot(passport_keys):
        passport = "present"
    elif "passport_number" in _explicit_missing(slots):
        passport = "missing"

    alien: DocPresence = "unknown"
    if any(
        "alien" in t or "registration" in t or "등록증" in t or "arc" in t for t in types
    ) or has_slot(alien_keys):
        alien = "present"
    elif "alien_registration_number" in _explicit_missing(slots):
        alien = "missing"

    # 신분 슬롯이 비어 있고 관련 문서도 없으면 missing으로 간주
    identity_missing = [k for k in IDENTITY_SLOTS if not slots.get(k) and not ocr.get(k)]
    if passport == "unknown" and "passport_number" in identity_missing and not documents:
        passport = "missing"
    if (
        alien == "unknown"
        and "alien_registration_number" in identity_missing
        and not documents
    ):
        alien = "missing"
    return passport, alien


# slots에 명시된 missing 표시는 쓰지 않고 키 존재만 본다
def _explicit_missing(slots: dict[str, Any]) -> set[str]:
    return {k for k, v in slots.items() if v in (None, "", "missing")}


# 여권×등록증 조합 코드
def _combo(passport: DocPresence, alien: DocPresence) -> DocCombo:
    if passport == "present" and alien == "present":
        return "both_present"
    if passport == "present" and alien in {"missing", "unknown"}:
        return "passport_only"
    if alien == "present" and passport in {"missing", "unknown"}:
        return "alien_only"
    if passport == "missing" and alien == "missing":
        return "both_missing"
    return "partial_unknown"


# Shared State 기준 서류 검증 결과
def validate_identity_documents(state: dict[str, Any]) -> DocumentValidation:
    slots = dict(state.get("slots") or {})
    documents = list(state.get("documents") or [])
    ocr = state.get("ocr_result")
    passport, alien = _presence_from_docs_and_slots(
        documents=documents, slots=slots, ocr_result=ocr if isinstance(ocr, dict) else None
    )
    missing = tuple(
        k
        for k in IDENTITY_SLOTS
        if not slots.get(k) and not (isinstance(ocr, dict) and ocr.get(k))
    )
    evidence: list[dict[str, str]] = []
    if passport == "present":
        evidence.append(
            {
                "type": "document",
                "key": "passport",
                "source": "upload_or_slot",
                "summary": "여권 정보/서류 확인",
            }
        )
    if alien == "present":
        evidence.append(
            {
                "type": "document",
                "key": "alien_registration",
                "source": "upload_or_slot",
                "summary": "외국인등록증 정보/서류 확인",
            }
        )
    for doc in documents:
        dtype = str(doc.get("document_type") or doc.get("documentType") or "unknown")
        evidence.append(
            {
                "type": "upload",
                "key": dtype,
                "source": "documents",
                "summary": f"업로드:{dtype}",
            }
        )
    return DocumentValidation(
        passport=passport,
        alien_registration=alien,
        combo=_combo(passport, alien),
        missing_identity_slots=missing,
        evidence=tuple(evidence),
    )
