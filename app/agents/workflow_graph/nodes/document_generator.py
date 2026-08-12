# 문서생성 훅 — DB·OCR 병합 후 HWP 초안 생성 (필수 4종)

from __future__ import annotations

import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from app.documents.common import DocumentFormat
from app.documents.editing import DocumentEditingService
from app.documents.editing.template_names import template_display_name

from ..document_field_map import values_for_template
from ..state import RenewalState

# Step 13 필수 초안 4종
RENEWAL_DRAFT_TEMPLATE_IDS: tuple[str, ...] = (
    "standard_labor_contract_v6",
    "employment_extension_application_v12_3",
    "immigration_integrated_application_v34",
    "identity_guaranty_v129",
)

# 하위 호환 별칭
PRIMARY_DRAFT_TEMPLATE_IDS = RENEWAL_DRAFT_TEMPLATE_IDS
OPTIONAL_DRAFT_TEMPLATE_IDS: tuple[str, ...] = ()
RENEWAL_TEMPLATE_IDS = RENEWAL_DRAFT_TEMPLATE_IDS


# 필수 초안 4종
def draft_template_ids(state: RenewalState) -> tuple[str, ...]:
    del state
    return RENEWAL_DRAFT_TEMPLATE_IDS


# 슬롯으로 문서 메타/파일 생성
class DocumentGenerator(Protocol):

    # generated_documents 목록 반환
    def __call__(self, state: RenewalState) -> list[dict[str, Any]]:
        ...


# 파일 없이 메타만 채우는 stub
class StubDocumentGenerator:

    # 템플릿 id 기준 stub 목록 생성
    def __call__(self, state: RenewalState) -> list[dict[str, Any]]:
        return [
            {
                "template_id": tid,
                "name": template_display_name(tid),
                "format": "hwp",
                "status": "stub",
                "mapped_fields": sorted(values_for_template(tid, state).keys()),
            }
            for tid in draft_template_ids(state)
        ]


# DocumentEditingService로 초안 생성 시도 실패 시 stub 메타
class EditingServiceDocumentGenerator:

    # 편집 서비스·출력 경로·템플릿 목록 주입
    def __init__(
        self,
        editing: DocumentEditingService | None = None,
        *,
        output_dir: Path | None = None,
        template_ids: Sequence[str] | None = None,
    ) -> None:
        self._editing = editing or DocumentEditingService()
        self._output_dir = output_dir
        self._template_ids = tuple(template_ids) if template_ids else None

    # 템플릿별 필드 매핑으로 HWP 생성 시도
    def __call__(self, state: RenewalState) -> list[dict[str, Any]]:
        out_dir = self._output_dir or Path(tempfile.mkdtemp(prefix="fowoco-renewal-"))
        out_dir.mkdir(parents=True, exist_ok=True)
        template_ids = self._template_ids or draft_template_ids(state)
        plans = state.get("document_field_values") or {}
        results: list[dict[str, Any]] = []
        for tid in template_ids:
            dest = out_dir / f"{tid}.hwp"
            values = dict(plans[tid]) if tid in plans else values_for_template(tid, state)
            try:
                mutation = self._editing.generate(
                    tid,
                    DocumentFormat.HWP,
                    dest,
                    values=values or None,
                )
                results.append(
                    {
                        "template_id": tid,
                        "name": template_display_name(tid),
                        "format": mutation.document_format.value,
                        "status": "generated",
                        "path": str(mutation.destination),
                        "changed_fields": list(mutation.changed_fields),
                        "mapped_fields": sorted(values.keys()),
                    }
                )
            except Exception as exc:  # noqa: BLE001 — 문서별 실패는 stub로 흡수
                results.append(
                    {
                        "template_id": tid,
                        "name": template_display_name(tid),
                        "format": "hwp",
                        "status": "stub",
                        "error": str(exc),
                        "mapped_fields": sorted(values.keys()),
                    }
                )
        return results
