from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .hwpx import DocumentError


class EditPlanError(DocumentError):
    """편집 계획이 현재 문서와 맞지 않거나 승인되지 않았습니다."""


class CellEditInput(BaseModel):
    """사용자가 확인한 셀 하나의 변경 요청입니다."""

    model_config = ConfigDict(extra="forbid")

    target_id: str = Field(min_length=1, max_length=200)
    expected_text: str = Field(max_length=10_000)
    value: str = Field(min_length=1, max_length=10_000)
    label: str | None = Field(default=None, max_length=200)


class EditOperation(BaseModel):
    """승인 전에 보여줄 수 있는 제한된 편집 작업입니다."""

    model_config = ConfigDict(extra="forbid")

    operation: Literal["set_cell_text"]
    target_id: str = Field(min_length=1, max_length=200)
    label: str | None = Field(default=None, max_length=200)
    old_value: str = Field(max_length=10_000)
    new_value: str = Field(min_length=1, max_length=10_000)
    confidence: Literal["confirmed"]


class EditPlan(BaseModel):
    """원본 지문과 작업 목록을 묶은 승인 대기 편집 계획입니다."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    plan_id: str = Field(min_length=64, max_length=64)
    input_path: str = Field(min_length=1, max_length=4096)
    document_sha256: str = Field(min_length=64, max_length=64)
    operations: list[EditOperation] = Field(min_length=1, max_length=100)
    approval_required: Literal[True] = True
    status: Literal["WAITING_APPROVAL"] = "WAITING_APPROVAL"


def create_edit_plan(
    input_path: str | Path,
    manifest: dict[str, Any],
    edits: list[CellEditInput],
) -> EditPlan:
    """현재 문서와 일치하는 셀 변경 요청을 승인 대기 계획으로 만듭니다."""
    input_path = Path(input_path)
    if not edits:
        raise EditPlanError("편집 계획에는 하나 이상의 변경이 필요합니다.")

    current_cells = {
        cell["id"]: cell["text"]
        for section in manifest["sections"]
        for table in section["tables"]
        for cell in table["cells"]
    }
    operations: list[EditOperation] = []
    seen_targets: set[str] = set()
    for edit in edits:
        if edit.target_id in seen_targets:
            raise EditPlanError(f"같은 셀을 중복 수정할 수 없습니다: {edit.target_id}")
        seen_targets.add(edit.target_id)
        if edit.target_id not in current_cells:
            raise EditPlanError(f"편집 대상 셀을 찾지 못했습니다: {edit.target_id}")
        current_text = current_cells[edit.target_id]
        if current_text != edit.expected_text:
            raise EditPlanError(
                f"셀 내용이 예상과 다릅니다: {edit.target_id}: {current_text!r}"
            )
        operations.append(
            EditOperation(
                operation="set_cell_text",
                target_id=edit.target_id,
                label=edit.label,
                old_value=current_text,
                new_value=edit.value,
                confidence="confirmed",
            )
        )

    document_sha256 = sha256_file(input_path)
    payload = {
        "version": 1,
        "input_path": str(input_path),
        "document_sha256": document_sha256,
        "operations": [operation.model_dump(exclude_none=True) for operation in operations],
    }
    plan_id = hashlib.sha256(_canonical_json(payload)).hexdigest()
    return EditPlan(
        plan_id=plan_id,
        input_path=str(input_path),
        document_sha256=document_sha256,
        operations=operations,
    )


def validate_edit_plan(plan: EditPlan, input_path: Path) -> None:
    """계획이 현재 파일을 대상으로 생성되었고 위조되지 않았는지 확인합니다."""
    if plan.input_path != str(input_path):
        raise EditPlanError("편집 계획의 대상 파일이 현재 입력 파일과 다릅니다.")
    current_sha256 = sha256_file(input_path)
    if plan.document_sha256 != current_sha256:
        raise EditPlanError("원본 문서가 계획 생성 후 변경되었습니다. 계획을 다시 만드세요.")

    payload = {
        "version": plan.version,
        "input_path": plan.input_path,
        "document_sha256": plan.document_sha256,
        "operations": [operation.model_dump(exclude_none=True) for operation in plan.operations],
    }
    expected_plan_id = hashlib.sha256(_canonical_json(payload)).hexdigest()
    if plan.plan_id != expected_plan_id:
        raise EditPlanError("편집 계획의 무결성 검증에 실패했습니다.")


def sha256_file(path: str | Path) -> str:
    """파일의 현재 지문을 계산합니다."""
    path = Path(path)
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
