from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import unicodedata
from typing import Any, Literal

from pydantic import ValidationError

from .hwpx import DocumentError, validate_document
from .vision import VisionReviewRequest, validate_vision_review_request


WorkflowStatus = Literal[
    "ANALYZED",
    "READY_FOR_INTERVIEW",
    "WAITING_APPROVAL",
    "APPROVED",
    "PENDING_VISION_REVIEW",
    "VERIFIED_FINAL",
    "NEEDS_HUMAN",
]


def prepare_workspace(input_path: str | Path) -> dict[str, Path]:
    """원본을 이동하지 않고 hash로 격리된 document workspace에 복사합니다."""
    source = Path(input_path).resolve()
    if source.name == "original.hwpx" and (source.parent / "workflow-state.json").exists():
        paths = _workspace_paths(source.parent)
        state = json.loads(paths["state_path"].read_text(encoding="utf-8"))
        current_hash = _sha256(source)
        if state.get("original_sha256") != current_hash:
            raise DocumentError(f"workspace 원본 hash가 다릅니다: {source}")
        if not state.get("document_id"):
            state["document_id"] = workflow_document_id(source.parent, current_hash)
            _write_json(paths["state_path"], state)
        return paths

    digest = _sha256(source)
    safe_stem = _safe_stem(source.stem)
    workspace_dir = source.parent / f"{safe_stem}-{digest[:12]}"
    paths = _workspace_paths(workspace_dir)
    if (
        workspace_dir.exists()
        and not paths["state_path"].exists()
        and any(workspace_dir.iterdir())
    ):
        raise DocumentError(f"기존 폴더를 workspace로 사용할 수 없습니다: {workspace_dir}")
    paths["analysis_dir"].mkdir(parents=True, exist_ok=True)
    paths["attempts_dir"].mkdir(parents=True, exist_ok=True)

    original = paths["original_path"]
    if original.exists():
        if _sha256(original) != digest:
            raise DocumentError(f"workspace 원본 hash가 다릅니다: {original}")
    else:
        shutil.copy2(source, original)

    if not paths["state_path"].exists():
        _write_json(
            paths["state_path"],
            {
                "status": "ANALYZED",
                "document_stem": safe_stem,
                "original_sha256": digest,
                "analysis_id": None,
                "plan_id": None,
                "approved": False,
                "vision_status": None,
                "modified_path": None,
                "final_path": None,
                "attempts": [],
                "document_id": workflow_document_id(workspace_dir, digest),
            },
        )
    else:
        state = json.loads(paths["state_path"].read_text(encoding="utf-8"))
        if not state.get("document_id"):
            state["document_id"] = workflow_document_id(workspace_dir, digest)
            _write_json(paths["state_path"], state)
    return paths


def update_workflow_state(
    workspace_dir: str | Path,
    *,
    status: WorkflowStatus,
    **updates: Any,
) -> dict[str, Any]:
    state_path = Path(workspace_dir) / "workflow-state.json"
    if not state_path.exists():
        raise DocumentError(f"workflow state를 찾지 못했습니다: {state_path}")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update(updates)
    state["status"] = status
    _write_json(state_path, state)
    return state


def read_workflow_state(workspace_dir: str | Path) -> dict[str, Any]:
    state_path = Path(workspace_dir) / "workflow-state.json"
    if not state_path.exists():
        raise DocumentError(f"workflow state를 찾지 못했습니다: {state_path}")
    return json.loads(state_path.read_text(encoding="utf-8"))


def finalize_attempt(
    workspace_dir: str | Path,
    plan_id: str,
) -> dict[str, Any]:
    """서버가 기록한 Vision PASS인 현재 attempt만 final 경로에 복사합니다."""
    workspace = Path(workspace_dir).resolve()
    state = read_workflow_state(workspace)
    if state.get("status") != "PENDING_VISION_REVIEW" or state.get("plan_id") != plan_id:
        raise DocumentError("현재 Vision 검토 대기 중인 plan이 아닙니다.")
    if state.get("vision_status") != "PASS":
        raise DocumentError("서버 Vision PASS 판정이 없어 최종화할 수 없습니다.")

    modified = Path(state.get("modified_path") or "").resolve()
    attempt_dir = (workspace / "attempts" / plan_id).resolve()
    if modified != attempt_dir / "modified.hwpx":
        raise DocumentError("attempt의 고정 수정본만 최종화할 수 있습니다.")
    if not modified.is_file():
        raise DocumentError("최종화할 수정본을 찾지 못했습니다.")
    report_path = attempt_dir / "verification-report.json"
    if not report_path.is_file():
        raise DocumentError("최종화 검증 보고서를 찾지 못했습니다.")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("status") != "PENDING_VISION_REVIEW":
        raise DocumentError("자동 검증을 통과한 attempt가 아닙니다.")
    if not validate_document(modified)["valid"]:
        raise DocumentError("수정본 HWPX 재검증에 실패했습니다.")
    request_path = attempt_dir / "vision-review-request.json"
    if (
        state.get("vision_review_request_path") != str(request_path)
        or not request_path.is_file()
        or state.get("vision_review_request_sha256") != _sha256(request_path)
    ):
        raise DocumentError("Vision review request 무결성 검증에 실패했습니다.")
    try:
        request = VisionReviewRequest.model_validate_json(
            request_path.read_text(encoding="utf-8")
        )
    except ValidationError as exc:
        raise DocumentError("Vision review request 형식이 올바르지 않습니다.") from exc
    validate_vision_review_request(request, attempt_dir)
    if (
        request.review_id != state.get("vision_review_id")
        or request.plan_id != plan_id
        or request.original_sha256 != state.get("original_sha256")
        or request.modified_sha256 != _sha256(modified)
        or request.verification_report_sha256 != _sha256(report_path)
    ):
        raise DocumentError("현재 attempt와 다른 Vision review request입니다.")
    vision_path = attempt_dir / "vision-review.json"
    if state.get("vision_review_path") != str(vision_path) or not vision_path.is_file():
        raise DocumentError("서버 Vision 검토 보고서를 찾지 못했습니다.")
    if state.get("vision_review_sha256") != _sha256(vision_path):
        raise DocumentError("Vision 검토 보고서 무결성 검증에 실패했습니다.")
    vision_review = json.loads(vision_path.read_text(encoding="utf-8"))
    if (
        vision_review.get("source")
        not in {"mcp_sampling", "host_vision_submission"}
        or vision_review.get("review_id") != request.review_id
        or vision_review.get("plan_id") != plan_id
        or vision_review.get("verdict") != "PASS"
        or vision_review.get("original_sha256") != request.original_sha256
        or vision_review.get("modified_sha256") != _sha256(modified)
        or vision_review.get("verification_report_sha256")
        != request.verification_report_sha256
    ):
        raise DocumentError("현재 attempt와 일치하는 Vision PASS가 아닙니다.")

    final_dir = workspace / "final"
    final_dir.mkdir(exist_ok=True)
    destination = final_dir / f"{state['document_stem']}_verified.hwpx"
    if destination.exists():
        raise DocumentError(f"최종 파일이 이미 존재합니다: {destination}")
    shutil.copy2(modified, destination)
    return update_workflow_state(
        workspace,
        status="VERIFIED_FINAL",
        vision_status="PASS",
        final_path=str(destination),
    )


def write_json(path: str | Path, value: Any) -> None:
    _write_json(Path(path), value)


def workflow_document_id(
    workspace_dir: str | Path,
    original_sha256: str,
) -> str:
    workspace = str(Path(workspace_dir).resolve())
    return hashlib.sha256(f"{workspace}\0{original_sha256}".encode("utf-8")).hexdigest()


def _workspace_paths(workspace_dir: Path) -> dict[str, Path]:
    return {
        "workspace_dir": workspace_dir,
        "original_path": workspace_dir / "original.hwpx",
        "analysis_dir": workspace_dir / "analysis",
        "attempts_dir": workspace_dir / "attempts",
        "state_path": workspace_dir / "workflow-state.json",
    }


def _safe_stem(stem: str) -> str:
    normalized = unicodedata.normalize("NFC", stem)
    safe = re.sub(r"[^\w가-힣.-]+", "-", normalized, flags=re.UNICODE).strip("-.")
    return (safe or "document")[:80]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)
