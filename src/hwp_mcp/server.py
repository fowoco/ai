from __future__ import annotations

import logging
import os
from pathlib import Path
import shutil
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import ValidationError

from .compare import (
    compare_manifests,
    compare_rendered_pages,
    validate_expected_changes,
)
from .hwpx import (
    analyze_document as analyze_hwpx_document,
    DocumentError,
    extract_text as extract_hwpx_text,
    fill_cells as fill_hwpx_cells,
    inspect_document as inspect_file,
    replace_text as replace_hwpx_text,
    validate_document as validate_file,
)
from .plans import (
    CellEditInput,
    EditPlan,
    create_edit_plan as build_edit_plan,
    validate_edit_plan,
)
from .normalization import NormalizationRequest, normalize_field
from .rhwp import render_svg


logging.basicConfig(stream=sys.stderr, level=logging.INFO)
logger = logging.getLogger("hwp-editor-mcp")

mcp = FastMCP(
    "HWPX Editor",
    instructions=(
        "로컬 우선 HWPX 검사와 제한적인 텍스트 편집을 제공합니다. "
        "원본 파일은 절대 덮어쓰지 않습니다. HWP 레거시 바이너리 편집은 지원하지 않습니다."
    ),
    json_response=True,
)


def _allowed_root() -> Path:
    configured = os.environ.get("HWP_MCP_ROOT")
    return Path(configured).expanduser().resolve() if configured else Path.cwd().resolve()


def _resolve_path(raw_path: str, *, must_exist: bool) -> Path:
    if not raw_path or len(raw_path) > 4096:
        raise DocumentError("path가 비어 있거나 너무 깁니다.")
    root = _allowed_root()
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve(strict=must_exist)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise DocumentError(f"허용된 작업 폴더 밖의 경로입니다: {raw_path}") from exc
    if must_exist and not resolved.is_file():
        raise DocumentError(f"파일이 아닙니다: {raw_path}")
    return resolved


def _resolve_output_path(raw_path: str, input_path: Path) -> Path:
    if not raw_path:
        raise DocumentError("output_path를 명시해야 합니다. 원본 덮어쓰기를 방지합니다.")
    root = _allowed_root()
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise DocumentError(f"허용된 작업 폴더 밖의 출력 경로입니다: {raw_path}") from exc
    if resolved.exists():
        raise DocumentError(f"출력 파일이 이미 존재합니다. 새 경로를 지정하세요: {resolved}")
    if resolved == input_path:
        raise DocumentError("원본 파일을 덮어쓸 수 없습니다.")
    return resolved


def _resolve_render_dir(raw_path: str) -> Path:
    if not raw_path:
        raise DocumentError("output_dir를 명시해야 합니다.")
    root = _allowed_root()
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise DocumentError(f"허용된 작업 폴더 밖의 출력 경로입니다: {raw_path}") from exc
    if resolved.exists():
        raise DocumentError(f"새 출력 폴더를 지정해야 합니다: {resolved}")
    resolved.mkdir(parents=True, exist_ok=False)
    return resolved


@mcp.tool()
def inspect_document(path: str) -> dict[str, Any]:
    """로컬 HWPX 패키지를 검사하거나 HWP 레거시 형식을 미지원으로 보고합니다."""
    input_path = _resolve_path(path, must_exist=True)
    return inspect_file(input_path)


@mcp.tool()
def extract_text(path: str) -> dict[str, Any]:
    """유효한 로컬 HWPX 파일에서 구역과 문단 텍스트를 추출합니다."""
    input_path = _resolve_path(path, must_exist=True)
    return extract_hwpx_text(input_path)


@mcp.tool()
def analyze_document(path: str) -> dict[str, Any]:
    """로컬 HWPX 파일의 표·셀·문단·이미지 후보를 반환합니다."""
    input_path = _resolve_path(path, must_exist=True)
    return analyze_hwpx_document(input_path)


@mcp.tool()
def render_document(
    path: str, output_dir: str, debug_overlay: bool = True
) -> dict[str, Any]:
    """rhwp로 HWPX 페이지를 SVG로 렌더링합니다."""
    input_path = _resolve_path(path, must_exist=True)
    if input_path.suffix.lower() != ".hwpx":
        raise DocumentError("render_document는 .hwpx 파일만 지원합니다.")
    output_path = _resolve_render_dir(output_dir)
    try:
        return render_svg(input_path, output_path, debug_overlay=debug_overlay)
    except Exception:
        shutil.rmtree(output_path, ignore_errors=True)
        raise


@mcp.tool()
def compare_document_versions(
    original_path: str,
    modified_path: str,
    output_dir: str,
    debug_overlay: bool = True,
) -> dict[str, Any]:
    """두 HWPX 파일의 구조와 페이지별 SVG 렌더 결과를 비교합니다."""
    original = _resolve_path(original_path, must_exist=True)
    modified = _resolve_path(modified_path, must_exist=True)
    if original.suffix.lower() != ".hwpx" or modified.suffix.lower() != ".hwpx":
        raise DocumentError("compare_document_versions는 .hwpx 파일만 지원합니다.")
    output_path = _resolve_render_dir(output_dir)
    original_output = output_path / "original"
    modified_output = output_path / "modified"
    original_output.mkdir()
    modified_output.mkdir()
    try:
        original_render = render_svg(original, original_output, debug_overlay=debug_overlay)
        modified_render = render_svg(modified, modified_output, debug_overlay=debug_overlay)
        original_manifest = analyze_hwpx_document(original)
        modified_manifest = analyze_hwpx_document(modified)
        return {
            "original_path": str(original),
            "modified_path": str(modified),
            "structure": compare_manifests(original_manifest, modified_manifest),
            "visual": compare_rendered_pages(original_render, modified_render),
        }
    except Exception:
        shutil.rmtree(output_path, ignore_errors=True)
        raise


@mcp.tool()
def fill_cells(path: str, output_path: str, edits: list[dict[str, str]]) -> dict[str, Any]:
    """확인된 값을 HWPX 셀에 추가하고 검증된 새 파일을 작성합니다."""
    input_path = _resolve_path(path, must_exist=True)
    destination = _resolve_output_path(output_path, input_path)
    return fill_hwpx_cells(input_path, destination, edits)


@mcp.tool()
def create_edit_plan(path: str, edits: list[CellEditInput]) -> dict[str, Any]:
    """확인된 셀 변경을 파일을 만들지 않는 승인 대기 계획으로 반환합니다."""
    input_path = _resolve_path(path, must_exist=True)
    manifest = analyze_hwpx_document(input_path)
    plan = build_edit_plan(input_path, manifest, edits)
    logger.info("Edit Plan created: plan_id=%s operations=%d", plan.plan_id, len(plan.operations))
    return plan.model_dump(exclude_none=True)


@mcp.tool()
def apply_edit_plan(
    path: str,
    output_path: str,
    plan: EditPlan,
    approved: bool = False,
    review_output_dir: str | None = None,
) -> dict[str, Any]:
    """승인·재검증 후 적용하고 선택하면 rhwp 검토 결과까지 연결합니다."""
    if not approved:
        raise DocumentError("사용자 명시적 승인 없이는 Edit Plan을 적용할 수 없습니다.")
    if not isinstance(plan, EditPlan):
        try:
            plan = EditPlan.model_validate(plan)
        except ValidationError as exc:
            raise DocumentError("Edit Plan 형식이 올바르지 않습니다.") from exc
    input_path = _resolve_path(path, must_exist=True)
    validate_edit_plan(plan, input_path)
    destination = _resolve_output_path(output_path, input_path)
    review_path: Path | None = None
    try:
        edits = [
            {
                "target_id": operation.target_id,
                "expected_text": operation.old_value,
                "value": operation.new_value,
            }
            for operation in plan.operations
        ]
        result = fill_hwpx_cells(input_path, destination, edits)
        structure = compare_manifests(
            analyze_hwpx_document(input_path), analyze_hwpx_document(destination)
        )
        expected_changes = validate_expected_changes(
            structure, [operation.target_id for operation in plan.operations]
        )
        if not expected_changes["passed"]:
            raise DocumentError(
                "승인되지 않은 문서 변경이 감지되어 결과를 제공하지 않습니다."
            )

        review: dict[str, Any] = {
            "structure": structure,
            "expected_changes": expected_changes,
        }
        if review_output_dir:
            review_path = _resolve_render_dir(review_output_dir)
            original_output = review_path / "original"
            modified_output = review_path / "modified"
            original_output.mkdir()
            modified_output.mkdir()
            original_render = render_svg(
                input_path, original_output, debug_overlay=True
            )
            modified_render = render_svg(
                destination, modified_output, debug_overlay=True
            )
            visual = compare_rendered_pages(original_render, modified_render)
            if len(original_render["files"]) != len(modified_render["files"]):
                raise DocumentError("수정 후 페이지 수가 달라져 결과를 제공하지 않습니다.")
            original_warnings = set(original_render.get("layout_warnings", []))
            modified_warnings = set(modified_render.get("layout_warnings", []))
            new_layout_warnings = sorted(modified_warnings - original_warnings)
            if new_layout_warnings:
                raise DocumentError(
                    "수정 후 새 레이아웃 경고가 발생해 결과를 제공하지 않습니다."
                )
            review["visual"] = {
                **visual,
                "page_count_preserved": True,
                "original_layout_warnings": sorted(original_warnings),
                "modified_layout_warnings": sorted(modified_warnings),
                "new_layout_warnings": new_layout_warnings,
                "layout_warnings_preserved": True,
            }
        else:
            review["visual"] = {
                "status": "NOT_REQUESTED",
                "page_count_preserved": None,
            }

        result.update(
            {
                "plan_id": plan.plan_id,
                "approved": True,
                "status": "APPLIED",
                "review": review,
            }
        )
        logger.info("Edit Plan applied: plan_id=%s output=%s", plan.plan_id, destination)
        return result
    except Exception:
        destination.unlink(missing_ok=True)
        if review_path:
            shutil.rmtree(review_path, ignore_errors=True)
        raise


@mcp.tool()
def normalize_field_value(request: NormalizationRequest) -> dict[str, Any]:
    """날짜·전화번호 변환안을 반환하며 자동으로 문서에 적용하지 않습니다."""
    return normalize_field(request).model_dump()


@mcp.tool()
def replace_text(path: str, output_path: str, old: str, new: str) -> dict[str, Any]:
    """HWPX 텍스트를 정확히 치환하고 새 출력 파일을 재검증합니다."""
    input_path = _resolve_path(path, must_exist=True)
    destination = _resolve_output_path(output_path, input_path)
    return replace_hwpx_text(input_path, destination, old, new)


@mcp.tool()
def validate_document(path: str) -> dict[str, Any]:
    """문서를 변경하지 않고 HWPX ZIP/XML 파트를 검증합니다."""
    input_path = _resolve_path(path, must_exist=True)
    return validate_file(input_path)


def main() -> None:
    logger.info("Starting HWPX Editor MCP Server; root=%s", _allowed_root())
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
