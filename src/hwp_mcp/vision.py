from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .hwpx import DocumentError


VisionVerdict = Literal["PASS", "FAIL", "NEEDS_HUMAN"]


class FieldVisionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_id: str = Field(min_length=1, max_length=240)
    verdict: VisionVerdict
    reason: str = Field(min_length=1, max_length=1000)


class VisionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: VisionVerdict
    summary: str = Field(min_length=1, max_length=2000)
    fields: list[FieldVisionDecision] = Field(min_length=1, max_length=100)


def parse_vision_decision(text: str, expected_field_ids: list[str]) -> VisionDecision:
    """Vision 응답을 strict JSON으로 검증하고 모든 편집 field 판정을 강제합니다."""
    candidate = text.strip()
    if candidate.startswith("```") and candidate.endswith("```"):
        lines = candidate.splitlines()
        candidate = "\n".join(lines[1:-1]).strip()
    try:
        decision = VisionDecision.model_validate(json.loads(candidate))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise DocumentError("Vision 응답이 요구된 JSON 형식이 아닙니다.") from exc

    actual_ids = [field.field_id for field in decision.fields]
    if len(actual_ids) != len(set(actual_ids)):
        raise DocumentError("Vision 응답에 중복 field_id가 있습니다.")
    if set(actual_ids) != set(expected_field_ids):
        raise DocumentError("Vision 응답이 모든 편집 field를 정확히 판정하지 않았습니다.")

    field_verdicts = {field.verdict for field in decision.fields}
    expected_verdict = (
        "FAIL"
        if "FAIL" in field_verdicts
        else "NEEDS_HUMAN"
        if "NEEDS_HUMAN" in field_verdicts
        else "PASS"
    )
    if decision.verdict != expected_verdict:
        raise DocumentError("field 판정과 전체 Vision 판정이 일치하지 않습니다.")
    return decision


def build_vision_prompt(
    *,
    plan_id: str,
    operations: list[dict[str, Any]],
    registry: list[dict[str, Any]],
    verification: dict[str, Any],
) -> str:
    edited_ids = {operation["field_id"] for operation in operations}
    payload = {
        "plan_id": plan_id,
        "operations": operations,
        "edited_field_ids": sorted(edited_ids),
        "field_registry": registry,
        "automatic_verification": {
            "semantic": verification.get("review", {}).get("semantic"),
            "expected_changes": verification.get("review", {}).get(
                "expected_changes"
            ),
            "svg_geometry": verification.get("review", {})
            .get("visual", {})
            .get("svg_geometry"),
            "visual_components": [
                {
                    "page": item.get("page"),
                    "has_diff": item.get("has_diff"),
                    "components": item.get("components", []),
                }
                for item in verification.get("review", {})
                .get("visual", {})
                .get("visual_diffs", [])
            ],
        },
    }
    return (
        "당신은 HWPX 양식 편집 결과의 최종 시각 검토자다. "
        "각 페이지의 원본 PNG, 수정 PNG, diff PNG를 순서대로 비교하라. "
        "입력값의 물리적 위치, 셀 경계 침범/중첩, checkbox 제자리 치환, "
        "placeholder 잔존/중복, character_grid 문자별 배치를 확인하라. "
        "불확실하면 PASS하지 말고 NEEDS_HUMAN으로 판정하라. "
        "아래 JSON 객체만 반환하라: "
        '{"verdict":"PASS|FAIL|NEEDS_HUMAN","summary":"...",'
        '"fields":[{"field_id":"...","verdict":"PASS|FAIL|NEEDS_HUMAN",'
        '"reason":"..."}]}. 모든 편집 field_id를 정확히 한 번 포함해야 한다.\n'
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )
