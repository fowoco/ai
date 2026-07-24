from __future__ import annotations

import pytest

from hwp_mcp.hwpx import DocumentError
from hwp_mcp.normalization import NormalizationRequest, normalize_field


def test_normalizes_date_and_keeps_original() -> None:
    result = normalize_field(NormalizationRequest(field_type="date", value="1990.1.1"))

    assert result.original == "1990.1.1"
    assert result.normalized == "1990년 1월 1일"
    assert result.changed is True


def test_normalizes_phone() -> None:
    result = normalize_field(NormalizationRequest(field_type="phone", value="01012345678"))

    assert result.normalized == "010-1234-5678"


def test_rejects_invalid_date_and_phone() -> None:
    with pytest.raises(DocumentError):
        normalize_field(NormalizationRequest(field_type="date", value="2025.2.29"))
    with pytest.raises(DocumentError):
        normalize_field(NormalizationRequest(field_type="phone", value="1234"))
