from __future__ import annotations

from datetime import date
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .hwpx import DocumentError


FieldType = Literal["date", "phone", "checkbox"]


class NormalizationRequest(BaseModel):
    """문서 입력 전에 확인할 값과 형식입니다."""

    model_config = ConfigDict(extra="forbid")

    field_type: FieldType
    value: str = Field(min_length=1, max_length=10_000)


class NormalizationResult(BaseModel):
    """원본과 변환안을 함께 보여주는 결과입니다."""

    field_type: FieldType
    original: str
    normalized: str
    changed: bool
    status: Literal["NORMALIZED", "UNCHANGED"]


def normalize_field(request: NormalizationRequest) -> NormalizationResult:
    """전화번호·날짜·체크박스를 문서 입력 후보로 변환하되 원본은 보존합니다."""
    if request.field_type == "date":
        normalized = _normalize_date(request.value)
    elif request.field_type == "checkbox":
        normalized = _normalize_checkbox(request.value)
    else:
        normalized = _normalize_phone(request.value)
    return NormalizationResult(
        field_type=request.field_type,
        original=request.value,
        normalized=normalized,
        changed=request.value != normalized,
        status="NORMALIZED" if request.value != normalized else "UNCHANGED",
    )


def _normalize_checkbox(value: str) -> str:
    cleaned = value.strip().upper()
    if cleaned in ("V", "[V]", "■", "[■]", "TRUE", "YES", "예", "선택", "남", "남성", "여", "여성", "CHECKED"):
        return "[V]"
    if cleaned in ("FALSE", "NO", "아니오", "미선택", "UNCHECKED", "[ ]", "□"):
        return "[ ]"
    return "[V]"


def _normalize_date(value: str) -> str:
    match = re.fullmatch(
        r"\s*(\d{4})\s*(?:년|[./-])\s*(\d{1,2})\s*(?:월|[./-])\s*(\d{1,2})\s*일?\s*",
        value,
    )
    if match is None:
        raise DocumentError("날짜는 YYYY-MM-DD, YYYY.MM.DD 또는 YYYY년 M월 D일 형식이어야 합니다.")
    year, month, day = (int(part) for part in match.groups())
    try:
        date(year, month, day)
    except ValueError as exc:
        raise DocumentError(f"유효하지 않은 날짜입니다: {value}") from exc
    return f"{year}년 {month}월 {day}일"


def _normalize_phone(value: str) -> str:
    compact = re.sub(r"[^0-9+]", "", value)
    if compact.startswith("+82"):
        compact = "0" + compact[3:]
    elif compact.startswith("0082"):
        compact = "0" + compact[4:]
    if not compact.isdigit():
        raise DocumentError("전화번호에는 숫자와 일반 구분 기호만 사용할 수 있습니다.")

    if compact.startswith("02"):
        if len(compact) == 9:
            return f"02-{compact[2:5]}-{compact[5:]}"
        if len(compact) == 10:
            return f"02-{compact[2:6]}-{compact[6:]}"
    if len(compact) == 10:
        return f"{compact[:3]}-{compact[3:6]}-{compact[6:]}"
    if len(compact) == 11:
        return f"{compact[:3]}-{compact[3:7]}-{compact[7:]}"
    raise DocumentError("지원하는 전화번호 길이가 아닙니다.")
