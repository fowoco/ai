from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import secrets
from datetime import datetime, timezone
from typing import Any, Literal

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .hwpx import DocumentError
from .integrity import Signature, SigningKeyProvider, canonical_json_bytes


VisionVerdict = Literal["PASS", "FAIL", "NEEDS_HUMAN"]


class FieldVisionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_id: str = Field(min_length=1, max_length=240)
    verdict: VisionVerdict
    reason: str = Field(min_length=1, max_length=1000)
    evidence_view_ids: list[str] = Field(default_factory=list, max_length=20)


class VisionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: VisionVerdict
    summary: str = Field(min_length=1, max_length=2000)
    fields: list[FieldVisionDecision] = Field(min_length=1, max_length=100)


class VisionImage(BaseModel):
    """검토용 단일 PNG와 그 지문입니다."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=4096)
    sha256: str = Field(min_length=64, max_length=64)


class VisionView(BaseModel):
    """동일 구간의 원본·수정·diff 이미지 묶음입니다."""

    model_config = ConfigDict(extra="forbid")

    view_id: str = Field(min_length=1, max_length=200)
    page: int = Field(ge=1)
    kind: Literal["full", "detail"]
    bbox: list[int] | None = Field(default=None, min_length=4, max_length=4)
    field_ids: list[str] = Field(max_length=100)
    original: VisionImage
    modified: VisionImage
    diff: VisionImage


class VisionReviewRequest(BaseModel):
    """현재 attempt와 모든 시각 근거를 결합한 검토 요청입니다."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    review_id: str = Field(default="0" * 64, min_length=64, max_length=64)
    plan_id: str = Field(min_length=64, max_length=64)
    original_sha256: str = Field(min_length=64, max_length=64)
    modified_sha256: str = Field(min_length=64, max_length=64)
    verification_report_sha256: str = Field(min_length=64, max_length=64)
    expected_field_ids: list[str] = Field(min_length=1, max_length=100)
    views: list[VisionView] = Field(min_length=1, max_length=100)
    prompt: str = Field(min_length=1, max_length=200_000)


class HostReviewer(BaseModel):
    """Host가 사용한 모델 정보와 입력 capability 선언입니다."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=200)
    model: str = Field(min_length=1, max_length=300)
    capabilities: list[str] = Field(max_length=20)


class VisionDelivery(BaseModel):
    """Host에 실제 이미지 bytes를 전달한 1회성 증거입니다."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    delivery_id: str = Field(min_length=64, max_length=64)
    review_id: str = Field(min_length=64, max_length=64)
    plan_id: str = Field(min_length=64, max_length=64)
    manifest_sha256: str = Field(min_length=64, max_length=64)
    expires_at: str = Field(min_length=1, max_length=100)
    signature: Signature


def build_vision_review_request(
    *,
    plan_id: str,
    original_path: str | Path,
    modified_path: str | Path,
    verification_path: str | Path,
    views: list[VisionView],
    expected_field_ids: list[str],
    prompt: str,
) -> VisionReviewRequest:
    """현재 attempt와 이미지 묶음의 canonical review ID를 만듭니다."""
    request = VisionReviewRequest(
        plan_id=plan_id,
        original_sha256=_sha256_file(original_path),
        modified_sha256=_sha256_file(modified_path),
        verification_report_sha256=_sha256_file(verification_path),
        expected_field_ids=expected_field_ids,
        views=views,
        prompt=prompt,
    )
    return request.model_copy(update={"review_id": compute_review_id(request)})


def create_vision_delivery(
    request: VisionReviewRequest,
    *,
    signer: SigningKeyProvider,
    expires_at: datetime,
) -> VisionDelivery:
    if expires_at.tzinfo is None:
        raise DocumentError("Vision delivery 만료 시각에는 timezone이 필요합니다.")
    payload = {
        "version": 1,
        "delivery_id": secrets.token_hex(32),
        "review_id": request.review_id,
        "plan_id": request.plan_id,
        "manifest_sha256": image_manifest_sha256(request),
        "expires_at": expires_at.astimezone(timezone.utc).isoformat(),
    }
    return VisionDelivery(
        **payload,
        signature=signer.sign(canonical_json_bytes(payload)),
    )


def validate_vision_delivery(
    request: VisionReviewRequest,
    delivery: VisionDelivery,
    *,
    signer: SigningKeyProvider,
    now: datetime,
) -> None:
    if now.tzinfo is None:
        raise DocumentError("Vision delivery 검증 시각에는 timezone이 필요합니다.")
    if (
        delivery.review_id != request.review_id
        or delivery.plan_id != request.plan_id
        or delivery.manifest_sha256 != image_manifest_sha256(request)
    ):
        raise DocumentError("현재 request와 다른 Vision delivery입니다.")
    payload = delivery.model_dump(exclude={"signature"})
    if not signer.verify(canonical_json_bytes(payload), delivery.signature):
        raise DocumentError("Vision delivery 서명 검증에 실패했습니다.")
    try:
        expires_at = datetime.fromisoformat(delivery.expires_at)
    except ValueError as exc:
        raise DocumentError("Vision delivery 만료 시각 형식이 올바르지 않습니다.") from exc
    if expires_at.tzinfo is None or now.astimezone(timezone.utc) >= expires_at.astimezone(
        timezone.utc
    ):
        raise DocumentError("Vision delivery가 만료되었습니다.")


def image_manifest_sha256(request: VisionReviewRequest) -> str:
    manifest = {
        "review_id": request.review_id,
        "views": [
            {
                "view_id": view.view_id,
                "page": view.page,
                "kind": view.kind,
                "bbox": view.bbox,
                "field_ids": view.field_ids,
                "original_sha256": view.original.sha256,
                "modified_sha256": view.modified.sha256,
                "diff_sha256": view.diff.sha256,
            }
            for view in request.views
        ],
    }
    return hashlib.sha256(canonical_json_bytes(manifest)).hexdigest()


def compute_review_id(request: VisionReviewRequest) -> str:
    payload = request.model_dump(exclude={"review_id"})
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_vision_review_request(
    request: VisionReviewRequest,
    attempt_dir: str | Path,
) -> None:
    """request ID와 attempt 내부 PNG 지문을 다시 검증합니다."""
    if request.review_id != compute_review_id(request):
        raise DocumentError("Vision review request 무결성 검증에 실패했습니다.")
    attempt = Path(attempt_dir).resolve()
    view_ids = [view.view_id for view in request.views]
    if len(view_ids) != len(set(view_ids)):
        raise DocumentError("Vision review request에 중복 view_id가 있습니다.")
    if len(request.expected_field_ids) != len(set(request.expected_field_ids)):
        raise DocumentError("Vision review request에 중복 field_id가 있습니다.")
    for view in request.views:
        for image in (view.original, view.modified, view.diff):
            image_path = Path(image.path).resolve()
            if not image_path.is_relative_to(attempt) or not image_path.is_file():
                raise DocumentError("Vision 이미지는 현재 attempt 내부에 있어야 합니다.")
            if image.sha256 != _sha256_file(image_path):
                raise DocumentError("Vision 이미지 무결성 검증에 실패했습니다.")


def validate_host_vision_submission(
    request: VisionReviewRequest,
    reviewer: HostReviewer,
    decision: VisionDecision,
) -> VisionDecision:
    """Host 판정이 모든 field와 실제 view를 근거로 삼았는지 검증합니다."""
    if "image_input" not in reviewer.capabilities:
        raise DocumentError("Host Vision 검토에는 image_input capability가 필요합니다.")
    _validate_vision_decision(decision, request.expected_field_ids)
    views_by_id = {view.view_id: view for view in request.views}
    for field in decision.fields:
        evidence = set(field.evidence_view_ids)
        if not evidence:
            raise DocumentError(f"{field.field_id}: Vision evidence view가 없습니다.")
        if not evidence.issubset(views_by_id):
            raise DocumentError(f"{field.field_id}: 존재하지 않는 Vision view입니다.")
        if any(
            field.field_id not in views_by_id[view_id].field_ids
            for view_id in evidence
        ):
            raise DocumentError(f"{field.field_id}: 다른 field의 Vision view를 인용했습니다.")
        mapped_views = [
            view for view in request.views if field.field_id in view.field_ids
        ]
        if not any(
            views_by_id[view_id].kind == "full" for view_id in evidence
        ):
            raise DocumentError(f"{field.field_id}: full page evidence가 필요합니다.")
        detail_views = {
            view.view_id for view in mapped_views if view.kind == "detail"
        }
        if detail_views and not evidence.intersection(detail_views):
            raise DocumentError(f"{field.field_id}: detail evidence가 필요합니다.")
    return decision


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
                "field_ids": sorted(
                    field_id
                    for field_id, region in field_regions.items()
                    if len(region) == 4
                    and region[3] > box[1]
                    and region[1] < box[3]
                ),
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
    _validate_vision_decision(decision, expected_field_ids)
    return decision


def _validate_vision_decision(
    decision: VisionDecision,
    expected_field_ids: list[str],
) -> None:
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
