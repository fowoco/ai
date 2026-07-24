"""Official Korean display names for bundled document templates."""

from __future__ import annotations

from types import MappingProxyType

TEMPLATE_DISPLAY_NAMES = MappingProxyType(
    {
        "immigration_integrated_application_v34": "통합신청서(신고서)",
        "standard_labor_contract_v6": (
            "[별지 제6호서식] 표준근로계약서(Standard Labor Contract)"
            "(외국인근로자의 고용 등에 관한 법률 시행규칙)"
        ),
        "employment_extension_application_v12_3": (
            "[별지 제12호의3서식] 취업기간 만료자 취업활동 기간 연장신청서"
            "(외국인근로자의 고용 등에 관한 법률 시행규칙)"
        ),
        "identity_guaranty_v129": "신원보증서(한글)",
    }
)


def template_display_name(template_id: str) -> str:
    """Return an official filename-safe display name or the unknown ID itself."""

    return TEMPLATE_DISPLAY_NAMES.get(template_id, template_id)


__all__ = ["TEMPLATE_DISPLAY_NAMES", "template_display_name"]
