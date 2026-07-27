from __future__ import annotations

import hashlib
from pathlib import Path
import re
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .fields import Disposition
from .hwpx import DocumentError
from .integrity import (
    Signature,
    SigningKeyProvider,
    canonical_json_bytes,
)


class EditPlanError(DocumentError):
    """편집 계획이 현재 문서와 맞지 않거나 승인되지 않았습니다."""


ValueOrigin = Literal["user", "example"]


class CellEditInput(BaseModel):
    """사용자가 확인한 typed field 변경 요청입니다."""

    model_config = ConfigDict(extra="forbid")

    field_id: str | None = Field(default=None, min_length=1, max_length=240)
    target_id: str = Field(min_length=1, max_length=200)
    expected_text: str = Field(max_length=10_000)
    value: str = Field(min_length=1, max_length=10_000)
    value_origin: ValueOrigin = "user"
    label: str | None = Field(default=None, max_length=200)
    anchor: str | None = Field(default=None, min_length=1, max_length=10_000)
    expected_match_count: Literal[1] = 1


class EditOperation(BaseModel):
    """승인 전에 보여줄 수 있는 제한된 편집 작업입니다."""

    model_config = ConfigDict(extra="forbid")

    operation: Literal[
        "replace_text_range",
        "write_character_grid",
        "set_checkbox",
        "set_date_segments",
        "set_amount",
        "set_signature_placeholder",
    ]
    field_id: str = Field(min_length=1, max_length=240)
    target_id: str = Field(min_length=1, max_length=200)
    label: str | None = Field(default=None, max_length=200)
    old_value: str = Field(max_length=10_000)
    new_value: str = Field(min_length=1, max_length=10_000)
    value_origin: ValueOrigin = "user"
    anchor: str | None = Field(default=None, min_length=1, max_length=10_000)
    expected_match_count: Literal[1] = 1
    xml_segments: list[str] = Field(min_length=1, max_length=100)
    constraints: dict[str, Any] = Field(default_factory=dict)
    postcondition: Literal["value_once"] = "value_once"
    confidence: Literal["confirmed"]


class EditPlan(BaseModel):
    """원본 지문과 작업 목록을 묶은 승인 대기 편집 계획입니다."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[2] = 2
    plan_id: str = Field(min_length=64, max_length=64)
    input_path: str = Field(min_length=1, max_length=4096)
    document_sha256: str = Field(min_length=64, max_length=64)
    operations: list[EditOperation] = Field(min_length=1, max_length=100)
    dispositions: dict[str, Disposition]
    approval_required: Literal[True] = True
    status: Literal["WAITING_APPROVAL"] = "WAITING_APPROVAL"


class ApprovalReceipt(BaseModel):
    """MCP elicitation으로 승인된 저장 plan의 지문입니다."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[2] = 2
    plan_id: str = Field(min_length=64, max_length=64)
    document_sha256: str = Field(min_length=64, max_length=64)
    edit_plan_sha256: str = Field(min_length=64, max_length=64)
    approver_subject: str = Field(min_length=1, max_length=200)
    source: Literal["mcp_elicitation"] = "mcp_elicitation"
    approved_at: str = Field(min_length=1, max_length=100)
    signature: Signature


def create_approval_receipt(
    plan: EditPlan,
    plan_path: str | Path,
    *,
    approved_at: str,
    approver_subject: str,
    signer: SigningKeyProvider,
) -> ApprovalReceipt:
    """현재 저장된 plan 파일에 결합된 승인 receipt를 만듭니다."""
    stored_plan = Path(plan_path)
    if not stored_plan.is_file():
        raise EditPlanError("승인할 저장 Edit Plan을 찾지 못했습니다.")
    payload = {
        "version": 2,
        "plan_id": plan.plan_id,
        "document_sha256": plan.document_sha256,
        "edit_plan_sha256": sha256_file(stored_plan),
        "approver_subject": approver_subject,
        "source": "mcp_elicitation",
        "approved_at": approved_at,
    }
    signature = signer.sign(canonical_json_bytes(payload))
    return ApprovalReceipt(**payload, signature=signature)


def validate_approval_receipt(
    plan: EditPlan,
    plan_path: str | Path,
    receipt_path: str | Path,
    *,
    signer: SigningKeyProvider,
) -> ApprovalReceipt:
    """receipt가 현재 저장 plan과 정확히 결합됐는지 검증합니다."""
    stored_plan = Path(plan_path)
    stored_receipt = Path(receipt_path)
    if not stored_plan.is_file() or not stored_receipt.is_file():
        raise EditPlanError("서버 승인 receipt가 없습니다.")
    try:
        receipt = ApprovalReceipt.model_validate_json(
            stored_receipt.read_text(encoding="utf-8")
        )
    except ValidationError as exc:
        raise EditPlanError("승인 receipt 형식이 올바르지 않습니다.") from exc
    if (
        receipt.plan_id != plan.plan_id
        or receipt.document_sha256 != plan.document_sha256
        or receipt.edit_plan_sha256 != sha256_file(stored_plan)
    ):
        raise EditPlanError("승인 receipt 무결성 검증에 실패했습니다.")
    if not signer.verify(
        canonical_json_bytes(receipt.model_dump(exclude={"signature"})),
        receipt.signature,
    ):
        raise EditPlanError("승인 receipt 서명 검증에 실패했습니다.")
    return receipt


def create_edit_plan(
    input_path: str | Path,
    manifest: dict[str, Any],
    edits: list[CellEditInput],
    dispositions: dict[str, Disposition] | None = None,
) -> EditPlan:
    """모든 field disposition과 typed operation을 승인 대기 계획으로 만듭니다."""
    input_path = Path(input_path)
    if not edits:
        raise EditPlanError("편집 계획에는 하나 이상의 변경이 필요합니다.")

    analysis_contract = manifest.get("analysis_contract", {})
    if (
        analysis_contract.get("version") != 2
        or analysis_contract.get("registry_source") != "rhwp_svg"
        or analysis_contract.get("interview_ready") is not True
    ):
        raise EditPlanError(
            "rhwp SVG 분석 계약이 확인된 field_registry에서만 편집 계획을 만들 수 있습니다."
        )
    registry = manifest.get("field_registry", [])
    ungrounded_fields = [
        field["field_id"]
        for field in registry
        if not field.get("visual_regions")
        or field.get("constraints", {}).get("visual_source")
        not in {"rhwp_svg", "human_confirmed_svg"}
    ]
    if ungrounded_fields:
        raise EditPlanError(
            "SVG 시각 근거가 없는 field가 있습니다: " + ", ".join(ungrounded_fields[:5])
        )
    registry_by_id = {field["field_id"]: field for field in registry}
    dispositions = dispositions or {}
    missing_dispositions = sorted(set(registry_by_id) - set(dispositions))
    if missing_dispositions:
        raise EditPlanError(
            "모든 field에 disposition이 필요합니다: "
            + ", ".join(missing_dispositions[:5])
        )
    unknown_dispositions = sorted(set(dispositions) - set(registry_by_id))
    if unknown_dispositions:
        raise EditPlanError(
            "registry에 없는 disposition 대상입니다: "
            + ", ".join(unknown_dispositions[:5])
        )

    for field_id, disposition in dispositions.items():
        kind = registry_by_id[field_id].get("kind")
        if kind == "official_region" and disposition != "intentionally_blank":
            raise EditPlanError(f"official_region은 intentionally_blank여야 합니다: {field_id}")
        if kind == "signable_region" and disposition != "manual_after_export":
            if disposition == "future_e_signature":
                raise EditPlanError("전자서명은 아직 지원하지 않습니다.")
            raise EditPlanError(
                f"signable_region은 manual_after_export여야 합니다: {field_id}"
            )
        if disposition in {"manual_after_export", "future_e_signature"}:
            if kind != "signable_region":
                raise EditPlanError(
                    f"서명 disposition은 signable_region에만 허용됩니다: {field_id}"
                )

    operations: list[EditOperation] = []
    seen_fields: set[str] = set()
    for edit in edits:
        matches = (
            [registry_by_id[edit.field_id]]
            if edit.field_id and edit.field_id in registry_by_id
            else [field for field in registry if field["target_id"] == edit.target_id]
        )
        if len(matches) != 1:
            raise EditPlanError(
                f"편집 대상 field를 정확히 하나 찾지 못했습니다: {edit.field_id or edit.target_id}"
            )
        field = matches[0]
        field_id = field["field_id"]
        if field_id in seen_fields:
            raise EditPlanError(f"같은 field를 중복 수정할 수 없습니다: {field_id}")
        seen_fields.add(field_id)
        if dispositions[field_id] != "provided":
            raise EditPlanError(
                f"편집 field의 disposition은 provided여야 합니다: {field_id}"
            )
        if field.get("kind") in {"official_region", "signable_region"}:
            raise EditPlanError(f"자동 편집할 수 없는 field입니다: {field_id}")
        current_text = field["current_text"]
        if current_text != edit.expected_text:
            raise EditPlanError(
                f"field 내용이 예상과 다릅니다: {field_id}: {current_text!r}"
            )
        _validate_edit_input(field, edit)
        operations.append(
            EditOperation(
                operation=_operation_for_field(field),
                field_id=field_id,
                target_id=field["target_id"],
                label=edit.label or field["label"],
                old_value=current_text,
                new_value=edit.value,
                value_origin=edit.value_origin,
                anchor=edit.anchor or field.get("constraints", {}).get("anchor"),
                expected_match_count=edit.expected_match_count,
                xml_segments=field.get("xml_segments") or [field["target_id"]],
                constraints=field.get("constraints", {}),
                confidence="confirmed",
            )
        )

    document_sha256 = sha256_file(input_path)
    payload = {
        "version": 2,
        "input_path": str(input_path),
        "document_sha256": document_sha256,
        "operations": [operation.model_dump(exclude_none=True) for operation in operations],
        "dispositions": dispositions,
    }
    plan_id = hashlib.sha256(_canonical_json(payload)).hexdigest()
    return EditPlan(
        plan_id=plan_id,
        input_path=str(input_path),
        document_sha256=document_sha256,
        operations=operations,
        dispositions=dispositions,
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
        "dispositions": plan.dispositions,
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
    return canonical_json_bytes(value)


def _operation_for_field(field: dict[str, Any]) -> str:
    kind = field.get("kind")
    if kind == "character_grid":
        return "write_character_grid"
    if kind in {"checkbox", "checkbox_group"}:
        return "set_checkbox"
    if kind == "date_segments":
        return "set_date_segments"
    if field.get("type") == "amount":
        return "set_amount"
    if kind == "signable_region":
        return "set_signature_placeholder"
    return "replace_text_range"


def _validate_edit_input(
    field: dict[str, Any],
    edit: CellEditInput,
) -> None:
    """적용 전에 typed 값과 anchor의 결정 가능성을 검증합니다."""
    value = edit.value
    constraints = field.get("constraints", {})
    kind = field.get("kind")
    field_type = field.get("type")
    segments = field.get("xml_segments") or [field.get("target_id")]

    if kind == "date_segments":
        match = re.fullmatch(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})", value)
        if match is None:
            raise EditPlanError("날짜 값은 YYYY-MM-DD 형식이어야 합니다.")
        try:
            date(*(int(component) for component in match.groups()))
        except ValueError as exc:
            raise EditPlanError("유효한 날짜를 입력하세요.") from exc
        mode = constraints.get("mode")
        if len(segments) == 1 and mode not in {"empty_cell", "inline"}:
            raise EditPlanError("한 칸 날짜는 empty_cell 또는 inline mode여야 합니다.")
        if len(segments) == 3 and mode not in {"empty_cells", "inline"}:
            raise EditPlanError("분할 날짜의 mode가 올바르지 않습니다.")
        if len(segments) not in {1, 3}:
            raise EditPlanError("날짜는 한 칸 또는 세 칸 segment여야 합니다.")

    if kind in {"checkbox", "checkbox_group"}:
        marker = re.compile(r"\[\s*\]")
        anchor = edit.anchor or constraints.get("anchor")
        current_text = field.get("current_text", "")
        if anchor:
            if (
                marker.search(anchor) is None
                or current_text.count(anchor) != 1
            ):
                raise EditPlanError(
                    "checkbox anchor는 미선택 marker를 포함해 정확히 1회 일치해야 합니다."
                )
        elif len(marker.findall(current_text)) != 1:
            raise EditPlanError("checkbox marker는 정확히 1개여야 합니다.")

    if kind == "character_grid":
        separators = {
            item.get("value", "")
            for item in constraints.get("separators", [])
        }
        characters = [character for character in value if character not in separators]
        if len(characters) != len(segments):
            raise EditPlanError("문자칸 수와 입력 문자 수가 다릅니다.")

    if field_type == "amount" and constraints.get("mode") == "prefix_unit":
        if re.fullmatch(r"\d[\d,]*", value) is None:
            raise EditPlanError(
                "prefix_unit 금액은 단위를 제외한 숫자만 입력하세요."
            )

    if field_type == "number" and re.fullmatch(r"[+-]?\d[\d,]*(?:\.\d+)?", value) is None:
        raise EditPlanError("숫자 field에는 숫자만 입력하세요.")

    if field_type == "phone" and re.fullmatch(r"[0-9+() .-]+", value) is None:
        raise EditPlanError("전화번호 형식에 허용되지 않은 문자가 있습니다.")
