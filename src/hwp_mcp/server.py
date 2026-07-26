from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import sys
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ImageContent, SamplingMessage, TextContent
from pydantic import ValidationError

from .fields import RegistryField
from .compare import (
    compare_manifests,
    compare_rendered_pages,
    generate_visual_diff,
    svg_to_png,
    validate_expected_changes,
    validate_typed_postconditions,
)
from .hwpx import (
    analyze_document as analyze_hwpx_document,
    apply_typed_edits,
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
    sha256_file,
    validate_edit_plan,
)
from .normalization import NormalizationRequest, normalize_field
from .rhwp import render_svg
from .vision import build_vision_prompt, parse_vision_decision
from .workspace import (
    finalize_attempt,
    prepare_workspace,
    read_workflow_state,
    update_workflow_state,
    write_json,
)


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
    resolved.mkdir(parents=True, exist_ok=True)
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
    """원본 복사·XML registry·SVG/PNG를 document workspace에 생성합니다."""
    input_path = _resolve_path(path, must_exist=True)
    workspace = prepare_workspace(input_path)
    original_path = workspace["original_path"]
    manifest = analyze_hwpx_document(original_path)
    original_render_dir = workspace["analysis_dir"] / "original"
    if original_render_dir.exists():
        shutil.rmtree(original_render_dir)
    render = render_svg(original_path, original_render_dir, debug_overlay=True)
    png_paths = []
    for index, svg_path in enumerate(render["files"], start=1):
        png_path = original_render_dir / f"page_{index:03d}.png"
        svg_to_png(svg_path, png_path)
        png_paths.append(str(png_path))

    analysis_payload = {
        "manifest": manifest,
        "render": render,
        "png_paths": png_paths,
    }
    analysis_id = hashlib.sha256(
        json.dumps(
            analysis_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    write_json(workspace["analysis_dir"] / "manifest.json", manifest)
    write_json(workspace["analysis_dir"] / "field-registry.json", manifest["field_registry"])
    visual_candidates_path = workspace["analysis_dir"] / "visual-candidates.json"
    if not visual_candidates_path.exists():
        write_json(visual_candidates_path, [])
    update_workflow_state(
        workspace["workspace_dir"],
        status="ANALYZED",
        analysis_id=analysis_id,
        alignment_status="NEEDS_REVIEW",
    )
    return {
        **manifest,
        "analysis_id": analysis_id,
        "status": "ANALYZED",
        "alignment_status": "NEEDS_REVIEW",
        "workspace_dir": str(workspace["workspace_dir"]),
        "original_path": str(original_path),
        "render": render,
        "png_paths": png_paths,
    }


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
    original_output.mkdir(parents=True, exist_ok=True)
    modified_output.mkdir(parents=True, exist_ok=True)
    try:
        original_render = render_svg(original, original_output, debug_overlay=debug_overlay)
        modified_render = render_svg(modified, modified_output, debug_overlay=debug_overlay)
        original_manifest = analyze_hwpx_document(original)
        modified_manifest = analyze_hwpx_document(modified)

        # SVG -> PNG 캡처 생성 및 Visual Diff 빨간 하이라이트 박스 이미지 배출
        visual_res = compare_rendered_pages(original_render, modified_render)
        diff_dir = output_path / "diffs"
        diff_dir.mkdir(parents=True, exist_ok=True)
        visual_diff_reports = []

        for page in visual_res.get("pages", []):
            orig_svg = page.get("original")
            mod_svg = page.get("modified")
            p_num = page.get("page", 1)
            if orig_svg and mod_svg and Path(orig_svg).exists() and Path(mod_svg).exists():
                orig_png = original_output / f"page_{p_num:03d}.png"
                mod_png = modified_output / f"page_{p_num:03d}.png"
                diff_png = diff_dir / f"page_{p_num:03d}_diff.png"
                svg_to_png(orig_svg, orig_png)
                svg_to_png(mod_svg, mod_png)
                v_diff = generate_visual_diff(orig_png, mod_png, diff_png)
                visual_diff_reports.append(v_diff)

        visual_res["visual_diffs"] = visual_diff_reports

        return {
            "original_path": str(original),
            "modified_path": str(modified),
            "structure": compare_manifests(original_manifest, modified_manifest),
            "visual": visual_res,
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
def confirm_visual_candidates(
    path: str,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    """사람이 판정한 SVG-only 후보를 증거로 저장하며 자동 편집 대상으로 만들지 않습니다."""
    input_path = _resolve_path(path, must_exist=True)
    workspace = prepare_workspace(input_path)
    state = read_workflow_state(workspace["workspace_dir"])
    if state["status"] != "ANALYZED":
        raise DocumentError("ANALYZED 상태에서만 visual candidate를 확정할 수 있습니다.")
    manifest = analyze_hwpx_document(workspace["original_path"])
    registry = manifest["field_registry"]
    known_cells = {
        cell["id"]
        for section in manifest["sections"]
        for table in section["tables"]
        for cell in table["cells"]
    }
    normalized = []
    seen_candidate_ids: set[str] = set()
    for candidate in candidates:
        candidate_id = str(candidate.get("candidate_id", "")).strip()
        decision = candidate.get("decision")
        if not candidate_id or decision not in {"confirmed", "rejected"}:
            raise DocumentError("각 visual candidate에 candidate_id와 confirmed/rejected decision이 필요합니다.")
        if candidate_id in seen_candidate_ids:
            raise DocumentError(f"중복 visual candidate입니다: {candidate_id}")
        seen_candidate_ids.add(candidate_id)
        normalized_candidate = {
            **candidate,
            "candidate_id": candidate_id,
            "decision": decision,
        }
        if decision == "confirmed":
            try:
                field = RegistryField.model_validate(candidate.get("field"))
            except ValidationError as exc:
                raise DocumentError(
                    "confirmed visual candidate에는 완전한 registry field가 필요합니다."
                ) from exc
            if not field.xml_segments or any(
                segment not in known_cells for segment in field.xml_segments
            ):
                raise DocumentError("confirmed visual candidate의 XML segment를 찾지 못했습니다.")
            if any(item["field_id"] == field.field_id for item in registry):
                raise DocumentError(f"중복 field_id입니다: {field.field_id}")
            registry.append(field.model_dump())
            normalized_candidate["field"] = field.model_dump()
        normalized.append(normalized_candidate)
    write_json(workspace["analysis_dir"] / "visual-candidates.json", normalized)
    write_json(workspace["analysis_dir"] / "field-registry.json", registry)
    update_workflow_state(
        workspace["workspace_dir"],
        status="READY_FOR_INTERVIEW",
        alignment_status="CONSISTENT",
    )
    return {
        "status": "READY_FOR_INTERVIEW",
        "alignment_status": "CONSISTENT",
        "candidates": normalized,
        "field_registry": registry,
    }


@mcp.tool()
def create_edit_plan(
    path: str,
    edits: list[CellEditInput],
    dispositions: dict[str, str] | None = None,
) -> dict[str, Any]:
    """모든 field disposition을 확인해 typed 승인 대기 계획을 저장합니다."""
    input_path = _resolve_path(path, must_exist=True)
    workspace = prepare_workspace(input_path)
    state = read_workflow_state(workspace["workspace_dir"])
    if state["status"] != "READY_FOR_INTERVIEW":
        raise DocumentError("analyze_document와 시각 후보 확인 후 계획을 만드세요.")
    if len(state.get("attempts", [])) >= 2:
        update_workflow_state(
            workspace["workspace_dir"],
            status="NEEDS_HUMAN",
        )
        raise DocumentError("XML/SVG 조정 2회를 소진해 사람 검토가 필요합니다.")
    original_path = workspace["original_path"]
    manifest = analyze_hwpx_document(original_path)
    registry_path = workspace["analysis_dir"] / "field-registry.json"
    if registry_path.exists():
        manifest["field_registry"] = json.loads(registry_path.read_text(encoding="utf-8"))
    plan = build_edit_plan(original_path, manifest, edits, dispositions)
    attempt_dir = workspace["attempts_dir"] / plan.plan_id
    attempt_dir.mkdir()
    write_json(attempt_dir / "edit-plan.json", plan.model_dump(exclude_none=True))
    update_workflow_state(
        workspace["workspace_dir"],
        status="WAITING_APPROVAL",
        plan_id=plan.plan_id,
        approved=False,
    )
    logger.info("Edit Plan created: plan_id=%s operations=%d", plan.plan_id, len(plan.operations))
    return plan.model_dump(exclude_none=True)


@mcp.tool()
def apply_edit_plan(
    path: str,
    output_path: str | None,
    plan: EditPlan,
    approved: bool = False,
    review_output_dir: str | None = None,
) -> dict[str, Any]:
    """승인된 typed plan을 workspace attempt에 적용하고 Vision 검토 대기로 전환합니다."""
    # v1 호출 호환용 인자이며 v2 산출물 경로는 workspace가 결정합니다.
    _ = output_path, review_output_dir
    if not approved:
        raise DocumentError("사용자 명시적 승인 없이는 Edit Plan을 적용할 수 없습니다.")
    if not isinstance(plan, EditPlan):
        try:
            plan = EditPlan.model_validate(plan)
        except ValidationError as exc:
            raise DocumentError("Edit Plan 형식이 올바르지 않습니다.") from exc
    input_path = _resolve_path(path, must_exist=True)
    workspace = prepare_workspace(input_path)
    state = read_workflow_state(workspace["workspace_dir"])
    if state.get("status") != "WAITING_APPROVAL" or state.get("plan_id") != plan.plan_id:
        raise DocumentError("현재 승인 대기 중인 plan이 아닙니다.")
    original_path = workspace["original_path"]
    validate_edit_plan(plan, original_path)
    attempt_dir = workspace["attempts_dir"] / plan.plan_id
    destination = attempt_dir / "modified.hwpx"
    if destination.exists():
        raise DocumentError("이 plan의 수정 attempt가 이미 존재합니다.")
    report: dict[str, Any] = {"plan_id": plan.plan_id, "approved": True}
    try:
        operation_dicts = [operation.model_dump(exclude_none=True) for operation in plan.operations]
        result = apply_typed_edits(original_path, destination, operation_dicts)
        original_manifest = analyze_hwpx_document(original_path)
        modified_manifest = analyze_hwpx_document(destination)
        structure = compare_manifests(
            original_manifest, modified_manifest
        )
        expected_ids = [
            segment
            for operation in plan.operations
            for segment in operation.xml_segments
        ]
        expected_changes = validate_expected_changes(
            structure, expected_ids
        )
        if not expected_changes["passed"]:
            raise DocumentError("승인 대상 외 변경 또는 예상 변경 누락이 감지되었습니다.")
        semantic = validate_typed_postconditions(modified_manifest, operation_dicts)
        if not semantic["passed"]:
            raise DocumentError("field 의미 검증에 실패했습니다: " + " | ".join(semantic["failures"]))

        original_output = attempt_dir / "original"
        modified_output = attempt_dir / "modified"
        diffs_output = attempt_dir / "diffs"
        for generated_dir in (original_output, modified_output, diffs_output):
            if generated_dir.exists():
                shutil.rmtree(generated_dir)
            generated_dir.mkdir()
        original_render = render_svg(original_path, original_output, debug_overlay=True)
        modified_render = render_svg(destination, modified_output, debug_overlay=True)
        if len(original_render["files"]) != len(modified_render["files"]):
            raise DocumentError("수정 후 페이지 수가 달라졌습니다.")
        original_warnings = set(original_render.get("layout_warnings", []))
        modified_warnings = set(modified_render.get("layout_warnings", []))
        new_layout_warnings = sorted(modified_warnings - original_warnings)
        if new_layout_warnings:
            raise DocumentError("수정 후 새 레이아웃 경고가 발생했습니다.")

        visual = compare_rendered_pages(original_render, modified_render)
        visual_diffs = []
        registry_path = workspace["analysis_dir"] / "field-registry.json"
        registry_for_visual = (
            json.loads(registry_path.read_text(encoding="utf-8"))
            if registry_path.exists()
            else modified_manifest["field_registry"]
        )
        for page in visual["pages"]:
            page_number = page["page"]
            original_png = original_output / f"page_{page_number:03d}.png"
            modified_png = modified_output / f"page_{page_number:03d}.png"
            diff_png = diffs_output / f"page_{page_number:03d}_diff.png"
            svg_to_png(page["original"], original_png)
            svg_to_png(page["modified"], modified_png)
            visual_diffs.append(
                {
                    "page": page_number,
                    **generate_visual_diff(
                        original_png,
                        modified_png,
                        diff_png,
                        _field_regions_for_page(registry_for_visual, page_number),
                    ),
                }
            )

        review = {
            "structure": structure,
            "expected_changes": expected_changes,
            "semantic": semantic,
            "visual": {
                **visual,
                "visual_diffs": visual_diffs,
                "page_count_preserved": True,
                "original_layout_warnings": sorted(original_warnings),
                "modified_layout_warnings": sorted(modified_warnings),
                "new_layout_warnings": [],
                "layout_warnings_preserved": True,
            },
        }
        report.update({"status": "PENDING_VISION_REVIEW", "review": review})
        write_json(attempt_dir / "verification-report.json", report)
        attempts = [*state.get("attempts", []), plan.plan_id]
        update_workflow_state(
            workspace["workspace_dir"],
            status="PENDING_VISION_REVIEW",
            plan_id=plan.plan_id,
            approved=True,
            vision_status=None,
            modified_path=str(destination),
            attempts=list(dict.fromkeys(attempts)),
        )
        result.update(
            {
                "plan_id": plan.plan_id,
                "approved": True,
                "status": "PENDING_VISION_REVIEW",
                "review": review,
                "workspace_dir": str(workspace["workspace_dir"]),
            }
        )
        logger.info("Edit Plan applied: plan_id=%s output=%s", plan.plan_id, destination)
        return result
    except Exception as exc:
        report.update({"status": "NEEDS_HUMAN", "error": str(exc)})
        write_json(attempt_dir / "verification-report.json", report)
        attempts = [*state.get("attempts", []), plan.plan_id]
        update_workflow_state(
            workspace["workspace_dir"],
            status="NEEDS_HUMAN",
            plan_id=plan.plan_id,
            approved=True,
            modified_path=str(destination) if destination.exists() else None,
            attempts=list(dict.fromkeys(attempts)),
        )
        raise


@mcp.tool()
def finalize_document(
    path: str,
    plan_id: str,
) -> dict[str, Any]:
    """서버가 기록한 Vision PASS attempt만 final/에 복사합니다."""
    input_path = _resolve_path(path, must_exist=True)
    workspace = prepare_workspace(input_path)
    return finalize_attempt(workspace["workspace_dir"], plan_id)


@mcp.tool()
async def review_document_vision(
    path: str,
    plan_id: str,
    ctx: Context,
) -> dict[str, Any]:
    """MCP client Vision sampling으로 원본·수정·diff PNG를 판정합니다."""
    input_path = _resolve_path(path, must_exist=True)
    workspace = prepare_workspace(input_path)
    state = read_workflow_state(workspace["workspace_dir"])
    if (
        state.get("status") != "PENDING_VISION_REVIEW"
        or state.get("plan_id") != plan_id
    ):
        raise DocumentError("현재 Vision 검토 대기 중인 plan이 아닙니다.")

    attempt_dir = workspace["attempts_dir"] / plan_id
    plan_path = attempt_dir / "edit-plan.json"
    verification_path = attempt_dir / "verification-report.json"
    if not plan_path.is_file() or not verification_path.is_file():
        raise DocumentError("Vision 검토에 필요한 plan 또는 검증 보고서가 없습니다.")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    operations = plan["operations"]
    expected_field_ids = [operation["field_id"] for operation in operations]
    registry_path = workspace["analysis_dir"] / "field-registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))

    prompt = build_vision_prompt(
        plan_id=plan_id,
        operations=operations,
        registry=registry,
        verification=verification,
    )
    content: list[TextContent | ImageContent] = [
        TextContent(type="text", text=prompt)
    ]
    total_image_bytes = 0
    page_sets = [
        sorted((attempt_dir / directory).glob(pattern))
        for directory, pattern in (
            ("original", "page_*.png"),
            ("modified", "page_*.png"),
            ("diffs", "page_*_diff.png"),
        )
    ]
    if not page_sets[0] or len({len(paths) for paths in page_sets}) != 1:
        raise DocumentError("Vision 검토용 원본·수정·diff PNG 구성이 일치하지 않습니다.")
    for page_index, paths in enumerate(zip(*page_sets), start=1):
        content.append(
            TextContent(
                type="text",
                text=f"page {page_index}: original, modified, diff 순서",
            )
        )
        for image_path in paths:
            data = image_path.read_bytes()
            total_image_bytes += len(data)
            content.append(
                ImageContent(
                    type="image",
                    data=base64.b64encode(data).decode("ascii"),
                    mimeType="image/png",
                )
            )
    if total_image_bytes > 30 * 1024 * 1024:
        return _record_vision_needs_human(
            workspace["workspace_dir"],
            attempt_dir,
            plan_id,
            expected_field_ids,
            "Vision 이미지가 30MB 제한을 초과했습니다.",
        )

    try:
        sampled = await ctx.session.create_message(
            messages=[SamplingMessage(role="user", content=content)],
            max_tokens=3000,
            system_prompt=(
                "문서 편집 시각 검증만 수행한다. 제공된 이미지와 JSON 근거 밖의 "
                "사실을 추측하지 않고, 요구된 JSON 객체만 반환한다."
            ),
            temperature=0,
            metadata={"task": "hwp-vision-review", "plan_id": plan_id},
        )
        if not isinstance(sampled.content, TextContent):
            raise DocumentError("Vision sampling이 텍스트 JSON을 반환하지 않았습니다.")
        decision = parse_vision_decision(sampled.content.text, expected_field_ids)
    except Exception as exc:
        return _record_vision_needs_human(
            workspace["workspace_dir"],
            attempt_dir,
            plan_id,
            expected_field_ids,
            f"Vision sampling 실패: {exc}",
        )

    review = {
        "source": "mcp_sampling",
        "plan_id": plan_id,
        "original_sha256": state["original_sha256"],
        "modified_sha256": sha256_file(attempt_dir / "modified.hwpx"),
        "model": sampled.model,
        **decision.model_dump(),
    }
    review_path = attempt_dir / "vision-review.json"
    write_json(review_path, review)
    next_status = (
        "PENDING_VISION_REVIEW"
        if decision.verdict == "PASS"
        else "NEEDS_HUMAN"
    )
    update_workflow_state(
        workspace["workspace_dir"],
        status=next_status,
        vision_status=decision.verdict,
        vision_review_path=str(review_path),
        vision_review_sha256=sha256_file(review_path),
    )
    return review


def _record_vision_needs_human(
    workspace_dir: Path,
    attempt_dir: Path,
    plan_id: str,
    field_ids: list[str],
    reason: str,
) -> dict[str, Any]:
    state = read_workflow_state(workspace_dir)
    review = {
        "source": "mcp_sampling",
        "plan_id": plan_id,
        "original_sha256": state["original_sha256"],
        "modified_sha256": sha256_file(attempt_dir / "modified.hwpx"),
        "model": None,
        "verdict": "NEEDS_HUMAN",
        "summary": reason,
        "fields": [
            {
                "field_id": field_id,
                "verdict": "NEEDS_HUMAN",
                "reason": reason,
            }
            for field_id in field_ids
        ],
    }
    review_path = attempt_dir / "vision-review.json"
    write_json(review_path, review)
    update_workflow_state(
        workspace_dir,
        status="NEEDS_HUMAN",
        vision_status="NEEDS_HUMAN",
        vision_review_path=str(review_path),
        vision_review_sha256=sha256_file(review_path),
    )
    return review


def _field_regions_for_page(
    registry: list[dict[str, Any]],
    page_number: int,
) -> dict[str, list[int]]:
    regions: dict[str, list[int]] = {}
    prefix = f"page_{page_number:03d}:"
    for field in registry:
        for raw_region in field.get("visual_regions", []):
            if not isinstance(raw_region, str) or not raw_region.startswith(prefix):
                continue
            try:
                bbox = [int(value) for value in raw_region[len(prefix) :].split(",")]
            except ValueError:
                continue
            if len(bbox) == 4:
                regions[field["field_id"]] = bbox
    return regions


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
