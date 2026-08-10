# 그래프에 꽂는 Language/OCR 노드 계약 — 동료 구현이 stub 대체

from __future__ import annotations

from typing import Any, Protocol

from .state import RenewalState


# 발화→intent/slot/가이드 문구를 State에 채움
class LanguageNode(Protocol):

    # State를 읽어 부분 업데이트 반환
    def __call__(self, state: RenewalState) -> dict[str, Any]:
        ...


# 업로드 신분서류에서 슬롯을 추출해 State에 반영
class OcrNode(Protocol):

    # documents를 OCR해 slots/ocr_result 부분 업데이트 반환
    def __call__(self, state: RenewalState) -> dict[str, Any]:
        ...
