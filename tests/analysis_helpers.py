from __future__ import annotations

from pathlib import Path
from typing import Any

from hwp_mcp.hwpx import _analyze_xml_document


def make_grounded_manifest(path: str | Path) -> dict[str, Any]:
    """SVG 외 동작을 단위 테스트하기 위한 최소 분석 계약 fixture."""
    manifest = _analyze_xml_document(path)
    registry = manifest.pop("xml_field_candidates")
    for field in registry:
        field["visual_regions"] = ["page_001:0,0,1,1"]
        field.setdefault("constraints", {})["visual_source"] = "rhwp_svg"
    manifest["analysis_stage"] = "XML_SVG_MAPPED"
    manifest["analysis_contract"] = {
        "version": 2,
        "stage": "XML_SVG_MAPPED",
        "registry_source": "rhwp_svg",
        "interview_ready": True,
    }
    manifest["field_registry"] = registry
    return manifest
