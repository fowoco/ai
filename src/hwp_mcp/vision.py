from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Literal

from PIL import Image
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


def create_vision_detail_crops(
    *,
    page_number: int,
    original_path: str | Path,
    modified_path: str | Path,
    diff_path: str | Path,
    field_regions: dict[str, list[int]],
    output_dir: str | Path,
    max_band_height: int = 420,
    max_bands: int = 3,
    overlap: int = 24,
) -> list[dict[str, Any]]:
    """큰 페이지에서 편집 field가 있는 가로 band만 상세 비교 이미지로 만듭니다."""
    paths = {
        "original": Path(original_path),
        "modified": Path(modified_path),
        "diff": Path(diff_path),
    }
    with (
        Image.open(paths["original"]) as original,
        Image.open(paths["modified"]) as modified,
        Image.open(paths["diff"]) as diff,
    ):
        sizes = {original.size, modified.size, diff.size}
        if len(sizes) != 1:
            raise DocumentError("Vision 상세 crop 원본·수정·diff 크기가 다릅니다.")
        width, height = original.size
        if height <= max_band_height or not field_regions:
            return []

        row_count = min(max_bands, math.ceil(height / max_band_height))
        band_height = math.ceil(height / row_count)
        touched_rows: set[int] = set()
        for region in field_regions.values():
            if len(region) != 4:
                raise DocumentError("Vision 상세 crop field region이 올바르지 않습니다.")
            top = min(max(0, region[1]), height - 1)
            bottom = min(max(top, region[3] - 1), height - 1)
            touched_rows.update(
                range(top // band_height, bottom // band_height + 1)
            )

        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        details = []
        images = {
            "original": original,
            "modified": modified,
            "diff": diff,
        }
        for row in sorted(touched_rows):
            box = (
                0,
                max(0, row * band_height - overlap),
                width,
                min(height, (row + 1) * band_height + overlap),
            )
            item: dict[str, Any] = {
                "page": page_number,
                "band": row + 1,
                "bbox": list(box),
            }
            for kind, image in images.items():
                output_path = (
                    destination
                    / f"page_{page_number:03d}_band_{row + 1:03d}_{kind}.png"
                )
                image.crop(box).save(output_path)
                item[kind] = str(output_path)
            details.append(item)
        return details


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
    reasons = {field.reason.strip() for field in decision.fields}
    if len(decision.fields) > 1 and len(reasons) == 1:
        raise DocumentError("Vision 응답이 모든 field에 같은 reason을 반복했습니다.")

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
        "이어지는 detail band는 같은 페이지의 확대 가로 구간이다. "
        "전체 페이지에서 위치를 확인하고 detail band에서 글자와 경계를 재확인하라. "
        "입력값의 물리적 위치, 셀 경계 침범/중첩, checkbox 제자리 치환, "
        "placeholder 잔존/중복, character_grid 문자별 배치를 확인하라. "
        "각 reason에는 해당 field 라벨과 원본 대비 위치 관계를 적고, "
        "여러 field에 같은 reason을 반복하지 마라. "
        "불확실하면 PASS하지 말고 NEEDS_HUMAN으로 판정하라. "
        "아래 JSON 객체만 반환하라: "
        '{"verdict":"PASS|FAIL|NEEDS_HUMAN","summary":"...",'
        '"fields":[{"field_id":"...","verdict":"PASS|FAIL|NEEDS_HUMAN",'
        '"reason":"..."}]}. 모든 편집 field_id를 정확히 한 번 포함해야 한다.\n'
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )
