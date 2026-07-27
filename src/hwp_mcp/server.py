from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import sys
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import (
    ClientCapabilities,
    ElicitationCapability,
    ImageContent,
    SamplingCapability,
    SamplingMessage,
    TextContent,
)
from pydantic import BaseModel, ConfigDict, ValidationError

from .fields import RegistryField, reconcile_registry_with_svg
from .compare import (
    analyze_svg_geometry,
    attach_svg_regions,
    compare_manifests,
    compare_rendered_pages,
    generate_visual_diff,
    review_svg_geometry,
    svg_to_png,
    validate_expected_changes,
    validate_typed_postconditions,
)
from .hwpx import (
    _analyze_xml_document,
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
    create_approval_receipt,
    create_edit_plan as build_edit_plan,
    sha256_file,
    validate_approval_receipt,
    validate_edit_plan,
)
from .normalization import NormalizationRequest, normalize_field
from .rhwp import render_svg
from .vision import (
    HostReviewer,
    VisionDecision,
    VisionImage,
    VisionReviewRequest,
    VisionView,
    build_vision_prompt,
    build_vision_review_request,
    create_vision_detail_crops,
    parse_vision_decision,
    validate_host_vision_submission,
    validate_vision_review_request,
)
from .workspace import (
    finalize_attempt,
    prepare_workspace,
    read_workflow_state,
    update_workflow_state,
    write_json,
)


logging.basicConfig(stream=sys.stderr, level=logging.INFO)
logger = logging.getLogger("hwp-editor-mcp")
ANALYSIS_CONTRACT_VERSION = 2
MCP_INSTRUCTIONS = Path(__file__).with_name("instructions.md").read_text(encoding="utf-8")

mcp = FastMCP(
    "HWPX Editor",
    instructions=MCP_INSTRUCTIONS,
    json_response=True,
)


class ApprovalAnswer(BaseModel):
    """Edit Plan 실물 적용에 대한 사용자 응답입니다."""

    model_config = ConfigDict(extra="forbid")

    approved: bool


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


def _require_visual_analysis_contract(
    state: dict[str, Any],
    *,
    require_interview_ready: bool = True,
) -> None:
    if (
        state.get("analysis_contract_version") != ANALYSIS_CONTRACT_VERSION
        or state.get("registry_source") != "rhwp_svg"
        or (
            require_interview_ready
            and state.get("interview_ready") is not True
        )
    ):
        raise DocumentError(
            "현재 rhwp SVG 분석 계약이 없습니다. 최신 MCP 서버에서 analyze_document를 다시 실행하세요."
        )


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
    manifest = _analyze_xml_document(original_path)
    xml_field_candidates = manifest.pop("xml_field_candidates")
    manifest.pop("field_candidates", None)
    manifest.pop("field_segments", None)
    original_render_dir = workspace["analysis_dir"] / "original"
    if original_render_dir.exists():
        shutil.rmtree(original_render_dir)
    render = render_svg(original_path, original_render_dir, debug_overlay=True)
    svg_analysis = analyze_svg_geometry(render["files"], manifest)
    field_registry: list[dict[str, Any]] = []
    if svg_analysis["status"] == "MAPPED":
        field_registry = reconcile_registry_with_svg(
            manifest,
            xml_field_candidates,
            svg_analysis,
        )
        ambiguous_field_ids = [
            field["field_id"]
            for field in field_registry
            if field.get("constraints", {}).get("ambiguous_target_labels")
        ]
        if ambiguous_field_ids:
            svg_analysis["status"] = "NEEDS_HUMAN"
            svg_analysis["ambiguous_field_ids"] = ambiguous_field_ids
            field_registry = []
        else:
            field_registry = attach_svg_regions(field_registry, svg_analysis)
            ungrounded_field_ids = [
                field["field_id"]
                for field in field_registry
                if not field.get("visual_regions")
                or field.get("constraints", {}).get("visual_source") != "rhwp_svg"
            ]
            if ungrounded_field_ids:
                svg_analysis["status"] = "NEEDS_HUMAN"
                svg_analysis["ungrounded_field_ids"] = ungrounded_field_ids
                field_registry = []
    interview_ready = svg_analysis["status"] == "MAPPED"
    manifest["analysis_stage"] = (
        "XML_SVG_MAPPED" if interview_ready else "XML_SVG_NEEDS_HUMAN"
    )
    manifest["field_registry"] = field_registry
    analysis_contract = {
        "version": ANALYSIS_CONTRACT_VERSION,
        "stage": manifest["analysis_stage"],
        "registry_source": "rhwp_svg" if interview_ready else None,
        "interview_ready": False,
    }
    manifest["analysis_contract"] = analysis_contract
    png_paths = []
    for index, svg_path in enumerate(render["files"], start=1):
        png_path = original_render_dir / f"page_{index:03d}.png"
        svg_to_png(svg_path, png_path)
        png_paths.append(str(png_path))

    analysis_payload = {
        "manifest": manifest,
        "render": render,
        "svg_analysis": svg_analysis,
        "analysis_contract": analysis_contract,
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
        analysis_contract_version=analysis_contract["version"],
        registry_source=analysis_contract["registry_source"],
        interview_ready=False,
        alignment_status=(
            "NEEDS_REVIEW"
            if svg_analysis["status"] == "MAPPED"
            else "NEEDS_HUMAN"
        ),
        svg_analysis_status=svg_analysis["status"],
    )
    return {
        **manifest,
        "analysis_id": analysis_id,
        "status": "ANALYZED",
        "interview_ready": False,
        "next_action": (
            "confirm_visual_candidates"
            if svg_analysis["status"] == "MAPPED"
            else "manual_review"
        ),
        "alignment_status": (
            "NEEDS_REVIEW"
            if svg_analysis["status"] == "MAPPED"
            else "NEEDS_HUMAN"
        ),
        "workspace_dir": str(workspace["workspace_dir"]),
        "original_path": str(original_path),
        "render": render,
        "svg_analysis": svg_analysis,
        "analysis_contract": analysis_contract,
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
        original_manifest = _analyze_xml_document(original)
        modified_manifest = _analyze_xml_document(modified)

        # SVG -> PNG 캡처 생성 및 Visual Diff 빨간 하이라이트 박스 이미지 배출
        visual_res = compare_rendered_pages(original_render, modified_render)
        visual_res["svg_geometry"] = review_svg_geometry(
            original_render["files"],
            modified_render["files"],
            original_manifest,
            modified_manifest,
            [],
        )
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
    if state.get("svg_analysis_status") != "MAPPED":
        raise DocumentError("rhwp SVG cell geometry가 XML 구조와 매핑되지 않았습니다.")
    _require_visual_analysis_contract(
        state,
        require_interview_ready=False,
    )
    manifest = _analyze_xml_document(workspace["original_path"])
    registry_path = workspace["analysis_dir"] / "field-registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
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
            if not field.visual_regions:
                raise DocumentError("confirmed visual candidate에는 SVG visual region이 필요합니다.")
            if any(item["field_id"] == field.field_id for item in registry):
                raise DocumentError(f"중복 field_id입니다: {field.field_id}")
            field_payload = field.model_dump()
            field_payload["constraints"]["visual_source"] = "human_confirmed_svg"
            registry.append(field_payload)
            normalized_candidate["field"] = field_payload
        normalized.append(normalized_candidate)
    write_json(workspace["analysis_dir"] / "visual-candidates.json", normalized)
    write_json(workspace["analysis_dir"] / "field-registry.json", registry)
    analysis_contract = {
        "version": ANALYSIS_CONTRACT_VERSION,
        "stage": "XML_SVG_MAPPED",
        "registry_source": "rhwp_svg",
        "interview_ready": True,
    }
    saved_manifest_path = workspace["analysis_dir"] / "manifest.json"
    saved_manifest = (
        json.loads(saved_manifest_path.read_text(encoding="utf-8"))
        if saved_manifest_path.is_file()
        else manifest
    )
    saved_manifest["field_registry"] = registry
    saved_manifest["analysis_contract"] = analysis_contract
    write_json(saved_manifest_path, saved_manifest)
    update_workflow_state(
        workspace["workspace_dir"],
        status="READY_FOR_INTERVIEW",
        alignment_status="CONSISTENT",
        interview_ready=True,
    )
    return {
        "status": "READY_FOR_INTERVIEW",
        "alignment_status": "CONSISTENT",
        "interview_ready": True,
        "next_action": "collect_field_values",
        "analysis_contract": analysis_contract,
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
    _require_visual_analysis_contract(state)
    if len(state.get("attempts", [])) >= 2:
        update_workflow_state(
            workspace["workspace_dir"],
            status="NEEDS_HUMAN",
        )
        raise DocumentError("XML/SVG 조정 2회를 소진해 사람 검토가 필요합니다.")
    original_path = workspace["original_path"]
    manifest_path = workspace["analysis_dir"] / "manifest.json"
    if not manifest_path.exists():
        raise DocumentError("저장된 XML/SVG 분석 manifest가 없습니다. analyze_document를 다시 실행하세요.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
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
async def approve_edit_plan(
    path: str,
    plan_id: str,
    ctx: Context,
) -> dict[str, Any]:
    """현재 저장 Edit Plan을 사용자 elicitation으로 승인합니다."""
    input_path = _resolve_path(path, must_exist=True)
    workspace = prepare_workspace(input_path)
    state = read_workflow_state(workspace["workspace_dir"])
    if (
        state.get("status") != "WAITING_APPROVAL"
        or state.get("plan_id") != plan_id
    ):
        raise DocumentError("현재 승인 대기 중인 plan이 아닙니다.")
    if not ctx.session.check_client_capability(
        ClientCapabilities(elicitation=ElicitationCapability())
    ):
        raise DocumentError(
            "MCP client가 사용자 approval elicitation을 지원하지 않습니다."
        )

    attempt_dir = workspace["attempts_dir"] / plan_id
    plan_path = attempt_dir / "edit-plan.json"
    plan = _read_stored_plan(plan_path)
    validate_edit_plan(plan, workspace["original_path"])
    operation_summary = "\n".join(
        (
            f"- {operation.label or operation.field_id}: "
            f"{operation.old_value!r} -> {operation.new_value!r} "
            f"(origin={operation.value_origin})"
        )
        for operation in plan.operations
    )
    result = await ctx.elicit(
        (
            "다음 HWPX Edit Plan을 실물 수정본에 적용할까요?\n"
            f"plan_id={plan.plan_id}\n{operation_summary}"
        ),
        ApprovalAnswer,
    )
    if (
        result.action != "accept"
        or result.data.approved is not True
    ):
        raise DocumentError("사용자가 Edit Plan 적용을 승인하지 않았습니다.")

    receipt = create_approval_receipt(
        plan,
        plan_path,
        approved_at=datetime.now(timezone.utc).isoformat(),
    )
    receipt_path = attempt_dir / "approval-receipt.json"
    write_json(receipt_path, receipt.model_dump())
    update_workflow_state(
        workspace["workspace_dir"],
        status="APPROVED",
        approved=True,
        approval_receipt_path=str(receipt_path),
        approval_receipt_sha256=sha256_file(receipt_path),
    )
    return {
        **receipt.model_dump(),
        "status": "APPROVED",
        "next_action": "apply_edit_plan",
    }


@mcp.tool()
def apply_edit_plan(
    path: str,
    plan_id: str,
) -> dict[str, Any]:
    """승인된 typed plan을 workspace attempt에 적용하고 Vision 검토 대기로 전환합니다."""
    input_path = _resolve_path(path, must_exist=True)
    workspace = prepare_workspace(input_path)
    state = read_workflow_state(workspace["workspace_dir"])
    if state.get("status") != "APPROVED" or state.get("plan_id") != plan_id:
        raise DocumentError("서버 승인 receipt가 있는 현재 plan이 아닙니다.")
    _require_visual_analysis_contract(state)
    registry_path = workspace["analysis_dir"] / "field-registry.json"
    if not registry_path.exists():
        raise DocumentError("저장된 SVG field_registry가 없습니다. analyze_document를 다시 실행하세요.")
    original_path = workspace["original_path"]
    attempt_dir = workspace["attempts_dir"] / plan_id
    plan_path = attempt_dir / "edit-plan.json"
    receipt_path = attempt_dir / "approval-receipt.json"
    plan = _read_stored_plan(plan_path)
    validate_edit_plan(plan, original_path)
    validate_approval_receipt(plan, plan_path, receipt_path)
    if (
        state.get("approval_receipt_path") != str(receipt_path)
        or state.get("approval_receipt_sha256") != sha256_file(receipt_path)
    ):
        raise DocumentError("workflow 승인 receipt 무결성 검증에 실패했습니다.")
    destination = attempt_dir / "modified.hwpx"
    if destination.exists():
        raise DocumentError("이 plan의 수정 attempt가 이미 존재합니다.")
    report: dict[str, Any] = {"plan_id": plan.plan_id, "approved": True}
    try:
        operation_dicts = [operation.model_dump(exclude_none=True) for operation in plan.operations]
        result = apply_typed_edits(original_path, destination, operation_dicts)
        original_manifest = _analyze_xml_document(original_path)
        modified_manifest = _analyze_xml_document(destination)
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

        svg_geometry = review_svg_geometry(
            original_render["files"],
            modified_render["files"],
            original_manifest,
            modified_manifest,
            operation_dicts,
        )
        if not svg_geometry["passed"]:
            report["review"] = {"svg_geometry": svg_geometry}
            raise DocumentError("rhwp SVG geometry 검증에 실패했습니다.")

        visual = compare_rendered_pages(original_render, modified_render)
        visual_diffs = []
        registry_for_visual = json.loads(registry_path.read_text(encoding="utf-8"))
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
                "svg_geometry": svg_geometry,
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


def _read_stored_plan(plan_path: Path) -> EditPlan:
    if not plan_path.is_file():
        raise DocumentError("저장된 Edit Plan을 찾지 못했습니다.")
    try:
        return EditPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        raise DocumentError("저장된 Edit Plan 형식이 올바르지 않습니다.") from exc


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
    """Sampling을 우선하고 미지원 시 Host Vision 검토 묶음을 반환합니다."""
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
    expected_field_id_set = set(expected_field_ids)
    registry_path = workspace["analysis_dir"] / "field-registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    edited_registry = [
        field
        for field in registry
        if field["field_id"] in expected_field_id_set
    ]

    prompt = build_vision_prompt(
        plan_id=plan_id,
        operations=operations,
        registry=registry,
        verification=verification,
    )
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
    views: list[VisionView] = []
    for page_index, paths in enumerate(zip(*page_sets), start=1):
        field_regions = _field_regions_for_page(edited_registry, page_index)
        views.append(
            VisionView(
                view_id=f"page-{page_index:03d}-full",
                page=page_index,
                kind="full",
                bbox=None,
                field_ids=sorted(field_regions),
                original=_vision_image(paths[0]),
                modified=_vision_image(paths[1]),
                diff=_vision_image(paths[2]),
            )
        )
        page_details = create_vision_detail_crops(
            page_number=page_index,
            original_path=paths[0],
            modified_path=paths[1],
            diff_path=paths[2],
            field_regions=field_regions,
            output_dir=attempt_dir / "vision-details",
        )
        for detail in page_details:
            views.append(
                VisionView(
                    view_id=(
                        f"page-{page_index:03d}-band-{detail['band']:03d}"
                    ),
                    page=page_index,
                    kind="detail",
                    bbox=detail["bbox"],
                    field_ids=detail["field_ids"],
                    original=_vision_image(Path(detail["original"])),
                    modified=_vision_image(Path(detail["modified"])),
                    diff=_vision_image(Path(detail["diff"])),
                )
            )

    request = build_vision_review_request(
        plan_id=plan_id,
        original_path=workspace["original_path"],
        modified_path=attempt_dir / "modified.hwpx",
        verification_path=verification_path,
        views=views,
        expected_field_ids=expected_field_ids,
        prompt=prompt,
    )
    validate_vision_review_request(request, attempt_dir)
    request_path = attempt_dir / "vision-review-request.json"
    write_json(request_path, request.model_dump())
    update_workflow_state(
        workspace["workspace_dir"],
        status="PENDING_VISION_REVIEW",
        vision_review_id=request.review_id,
        vision_review_request_path=str(request_path),
        vision_review_request_sha256=sha256_file(request_path),
    )
    total_image_bytes = sum(
        Path(image.path).stat().st_size
        for view in request.views
        for image in (view.original, view.modified, view.diff)
    )
    if total_image_bytes > 30 * 1024 * 1024:
        return _vision_fallback_response(
            request,
            request_path,
            "Sampling 이미지 payload가 30MB 제한을 초과했습니다.",
        )
    if not ctx.session.check_client_capability(
        ClientCapabilities(sampling=SamplingCapability())
    ):
        return _vision_fallback_response(
            request,
            request_path,
            "MCP client가 sampling/createMessage를 지원하지 않습니다.",
        )

    content: list[TextContent | ImageContent] = [
        TextContent(type="text", text=prompt)
    ]
    for view in request.views:
        content.append(
            TextContent(
                type="text",
                text=(
                    f"{view.view_id}: "
                    f"{'detail band' if view.kind == 'detail' else 'full page'}; "
                    f"page={view.page}; "
                    f"bbox={view.bbox}; field_ids={view.field_ids}; "
                    "original, modified, diff 순서"
                ),
            )
        )
        for image in (view.original, view.modified, view.diff):
            data = Path(image.path).read_bytes()
            content.append(
                ImageContent(
                    type="image",
                    data=base64.b64encode(data).decode("ascii"),
                    mimeType="image/png",
                )
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
    except Exception as exc:
        return _vision_fallback_response(
            request,
            request_path,
            f"Vision sampling transport 실패: {exc}",
        )
    try:
        if not isinstance(sampled.content, TextContent):
            raise DocumentError("Vision sampling이 텍스트 JSON을 반환하지 않았습니다.")
        decision = parse_vision_decision(sampled.content.text, expected_field_ids)
    except Exception as exc:
        return _record_vision_needs_human(
            workspace["workspace_dir"],
            attempt_dir,
            request,
            f"Vision sampling 응답 검증 실패: {exc}",
        )

    review = {
        "source": "mcp_sampling",
        "review_id": request.review_id,
        "plan_id": request.plan_id,
        "original_sha256": request.original_sha256,
        "modified_sha256": request.modified_sha256,
        "verification_report_sha256": request.verification_report_sha256,
        "model": sampled.model,
        "detail_bands": [
            view.model_dump() for view in request.views if view.kind == "detail"
        ],
        **decision.model_dump(),
    }
    _save_vision_review(
        workspace["workspace_dir"],
        attempt_dir,
        review,
        decision.verdict,
    )
    return review


@mcp.tool()
def submit_host_vision_review(
    path: str,
    plan_id: str,
    review_id: str,
    reviewer: HostReviewer,
    decision: VisionDecision,
) -> dict[str, Any]:
    """Host의 image-input LLM 판정을 현재 review request에 결합합니다."""
    input_path = _resolve_path(path, must_exist=True)
    workspace = prepare_workspace(input_path)
    state = read_workflow_state(workspace["workspace_dir"])
    if (
        state.get("status") != "PENDING_VISION_REVIEW"
        or state.get("plan_id") != plan_id
        or state.get("vision_review_id") != review_id
    ):
        raise DocumentError("현재 Host Vision 검토 대기 중인 request가 아닙니다.")
    attempt_dir = workspace["attempts_dir"] / plan_id
    request_path = attempt_dir / "vision-review-request.json"
    if (
        state.get("vision_review_request_path") != str(request_path)
        or not request_path.is_file()
        or state.get("vision_review_request_sha256") != sha256_file(request_path)
    ):
        raise DocumentError("Vision review request 무결성 검증에 실패했습니다.")
    try:
        request = VisionReviewRequest.model_validate_json(
            request_path.read_text(encoding="utf-8")
        )
    except ValidationError as exc:
        raise DocumentError("Vision review request 형식이 올바르지 않습니다.") from exc
    if request.review_id != review_id or request.plan_id != plan_id:
        raise DocumentError("현재 attempt와 다른 Vision review request입니다.")
    validate_vision_review_request(request, attempt_dir)
    verification_path = attempt_dir / "verification-report.json"
    if (
        request.original_sha256 != sha256_file(workspace["original_path"])
        or request.modified_sha256 != sha256_file(attempt_dir / "modified.hwpx")
        or request.verification_report_sha256 != sha256_file(verification_path)
    ):
        raise DocumentError("Vision review artifact 무결성 검증에 실패했습니다.")
    validate_host_vision_submission(request, reviewer, decision)
    review = {
        "source": "host_vision_submission",
        "review_id": request.review_id,
        "plan_id": request.plan_id,
        "original_sha256": request.original_sha256,
        "modified_sha256": request.modified_sha256,
        "verification_report_sha256": request.verification_report_sha256,
        "reviewer": reviewer.model_dump(),
        "model": reviewer.model,
        **decision.model_dump(),
    }
    _save_vision_review(
        workspace["workspace_dir"],
        attempt_dir,
        review,
        decision.verdict,
    )
    return review


def _record_vision_needs_human(
    workspace_dir: Path,
    attempt_dir: Path,
    request: VisionReviewRequest,
    reason: str,
) -> dict[str, Any]:
    review = {
        "source": "mcp_sampling",
        "review_id": request.review_id,
        "plan_id": request.plan_id,
        "original_sha256": request.original_sha256,
        "modified_sha256": request.modified_sha256,
        "verification_report_sha256": request.verification_report_sha256,
        "model": None,
        "verdict": "NEEDS_HUMAN",
        "summary": reason,
        "fields": [
            {
                "field_id": field_id,
                "verdict": "NEEDS_HUMAN",
                "reason": reason,
                "evidence_view_ids": [],
            }
            for field_id in request.expected_field_ids
        ],
    }
    _save_vision_review(
        workspace_dir,
        attempt_dir,
        review,
        "NEEDS_HUMAN",
    )
    return review


def _save_vision_review(
    workspace_dir: Path,
    attempt_dir: Path,
    review: dict[str, Any],
    verdict: str,
) -> None:
    review_path = attempt_dir / "vision-review.json"
    write_json(review_path, review)
    update_workflow_state(
        workspace_dir,
        status=(
            "PENDING_VISION_REVIEW"
            if verdict == "PASS"
            else "NEEDS_HUMAN"
        ),
        vision_status=verdict,
        vision_review_path=str(review_path),
        vision_review_sha256=sha256_file(review_path),
    )


def _vision_fallback_response(
    request: VisionReviewRequest,
    request_path: Path,
    reason: str,
) -> dict[str, Any]:
    return {
        **request.model_dump(),
        "status": "VISION_REVIEW_REQUIRED",
        "next_action": "submit_host_vision_review",
        "review_request_path": str(request_path),
        "sampling_unavailable_reason": reason,
    }


def _vision_image(path: Path) -> VisionImage:
    return VisionImage(
        path=str(path),
        sha256=sha256_file(path),
    )


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
