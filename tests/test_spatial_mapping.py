from pathlib import Path

from hwp_mcp.hwpx import _analyze_xml_document
from hwp_mcp.fields import (
    infer_all_fields,
    infer_field_candidates_spatial,
    reconcile_registry_with_svg,
)


def test_spatial_geometry_infers_under_label_cells() -> None:
    sample_path = Path("samples/통합신청서(신고서)/original.hwpx")
    if not sample_path.exists():
        return

    manifest = _analyze_xml_document(sample_path)
    spatial_candidates = infer_field_candidates_spatial(manifest)

    # 1. 성 Surname 하단 빈 셀 추론 확인 (row14.cell0)
    surname_under = [c for c in spatial_candidates if "성 Surname" in c["label"]]
    assert len(surname_under) >= 1
    assert surname_under[0]["target_id"] == "section0.table0.row14.cell0"

    # 2. 명 Given names 하단 빈 셀 추론 확인 (row14.cell1)
    given_under = [c for c in spatial_candidates if "명 Given" in c["label"]]
    assert len(given_under) >= 1
    assert given_under[0]["target_id"] == "section0.table0.row14.cell1"

    # 3. 년 yyyy 하단 빈 셀 추론 확인 (row16.cell0)
    year_under = [c for c in spatial_candidates if "년 yyyy" in c["label"]]
    assert len(year_under) >= 1
    assert year_under[0]["target_id"] == "section0.table0.row16.cell0"


def _cell(cell_id: str, row: int, column: int, text: str) -> dict:
    return {"id": cell_id, "row": row, "column": column, "text": text}


def _manifest(cells: list[dict]) -> dict:
    return {
        "sections": [
            {"tables": [{"id": "section0.table0", "cells": cells}]}
        ]
    }


def _svg_analysis(regions: dict[str, list[float]]) -> dict:
    return {
        "status": "MAPPED",
        "cell_regions": {
            cell_id: {"bbox": bbox}
            for cell_id, bbox in regions.items()
        },
    }


def _text_field(
    field_id: str,
    target_id: str,
    label: str,
    row: int,
    column: int,
) -> dict:
    return {
        "field_id": field_id,
        "target_id": target_id,
        "label": label,
        "type": "text",
        "kind": "text_field",
        "category": "step1_application",
        "row": row,
        "column": column,
        "current_text": "",
        "required": True,
        "options": None,
        "xml_segments": [target_id],
        "visual_regions": [],
        "constraints": {},
        "disposition": None,
    }


def test_svg_prefers_aligned_right_cell_over_wide_below_cell() -> None:
    label = "section0.table0.row0.cell0"
    right = "section0.table0.row0.cell1"
    below = "section0.table0.row1.cell0"
    manifest = _manifest(
        [
            _cell(label, 0, 0, "직업 Occupation"),
            _cell(right, 0, 1, ""),
            _cell(below, 1, 0, ""),
        ]
    )
    registry = [_text_field(f"{below}.visual", below, "직업 Occupation", 1, 0)]
    svg = _svg_analysis(
        {
            label: [0, 0, 100, 20],
            right: [100, 0, 180, 20],
            below: [0, 20, 280, 40],
        }
    )

    reconciled = reconcile_registry_with_svg(manifest, registry, svg)

    assert reconciled[0]["target_id"] == right
    assert reconciled[0]["constraints"]["visual_relation"] == "right"


def test_svg_keeps_exact_width_below_cell_when_right_and_below_tie() -> None:
    label = "section0.table0.row0.cell0"
    right = "section0.table0.row0.cell1"
    below = "section0.table0.row1.cell0"
    manifest = _manifest(
        [
            _cell(label, 0, 0, "명 Given names"),
            _cell(right, 0, 1, ""),
            _cell(below, 1, 0, ""),
        ]
    )
    registry = [_text_field(f"{right}.blank", right, "명 Given names", 0, 1)]
    svg = _svg_analysis(
        {
            label: [0, 0, 100, 20],
            right: [100, 0, 200, 20],
            below: [0, 20, 100, 40],
        }
    )

    reconciled = reconcile_registry_with_svg(manifest, registry, svg)

    assert reconciled[0]["target_id"] == below
    assert reconciled[0]["constraints"]["visual_relation"] == "below"


def test_svg_keeps_right_fields_on_adjacent_rows_distinct() -> None:
    occupation_label = "section0.table0.row0.cell0"
    occupation_input = "section0.table0.row0.cell1"
    email_label = "section0.table0.row1.cell0"
    email_input = "section0.table0.row1.cell1"
    manifest = _manifest(
        [
            _cell(occupation_label, 0, 0, "Occupation"),
            _cell(occupation_input, 0, 1, ""),
            _cell(email_label, 1, 0, "E-Mail"),
            _cell(email_input, 1, 1, ""),
        ]
    )
    registry = [
        _text_field(
            f"{email_input}.occupation",
            email_input,
            "Occupation",
            1,
            1,
        ),
        _text_field(
            f"{email_input}.email",
            email_input,
            "E-Mail",
            1,
            1,
        ),
    ]
    svg = _svg_analysis(
        {
            occupation_label: [100, 0, 180, 20],
            occupation_input: [180, 0, 240, 20],
            email_label: [0, 20, 100, 40],
            email_input: [100, 20, 240, 40],
        }
    )

    reconciled = reconcile_registry_with_svg(manifest, registry, svg)
    targets = {field["label"]: field["target_id"] for field in reconciled}

    assert targets == {
        "Occupation": occupation_input,
        "E-Mail": email_input,
    }


def test_svg_maps_split_date_headers_to_three_empty_cells_below() -> None:
    headers = [
        "section0.table0.row0.cell0",
        "section0.table0.row0.cell1",
        "section0.table0.row0.cell2",
    ]
    inputs = [
        "section0.table0.row1.cell0",
        "section0.table0.row1.cell1",
        "section0.table0.row1.cell2",
    ]
    manifest = _manifest(
        [
            _cell(headers[0], 0, 0, "년 yyyy"),
            _cell(headers[1], 0, 1, "월 mm"),
            _cell(headers[2], 0, 2, "일 dd"),
            _cell(inputs[0], 1, 0, "  "),
            _cell(inputs[1], 1, 1, ""),
            _cell(inputs[2], 1, 2, ""),
        ]
    )
    registry = [
        {
            **_text_field(
                f"{headers[0]}.date_segments",
                headers[0],
                "생년월일 Date of Birth",
                0,
                0,
            ),
            "type": "date",
            "kind": "date_segments",
            "current_text": "년 yyyy / 월 mm / 일 dd",
            "xml_segments": headers,
            "constraints": {"anchors": ["yyyy", "mm", "dd"]},
        }
    ]
    svg = _svg_analysis(
        {
            headers[0]: [0, 0, 100, 20],
            headers[1]: [100, 0, 160, 20],
            headers[2]: [160, 0, 220, 20],
            inputs[0]: [0, 20, 100, 40],
            inputs[1]: [100, 20, 160, 40],
            inputs[2]: [160, 20, 220, 40],
        }
    )

    reconciled = reconcile_registry_with_svg(manifest, registry, svg)

    assert reconciled[0]["target_id"] == inputs[0]
    assert reconciled[0]["xml_segments"] == inputs
    assert reconciled[0]["constraints"]["mode"] == "empty_cells"
    assert reconciled[0]["constraints"]["visual_label_cell_ids"] == headers


def test_amount_unit_cell_becomes_prefix_field_not_adjacent_blank() -> None:
    unit = "section0.table0.row0.cell1"
    unused_blank = "section0.table0.row0.cell2"
    registry = infer_all_fields(
        _manifest(
            [
                _cell(
                    "section0.table0.row0.cell0",
                    0,
                    0,
                    "연 소득금액 Annual Income Amount",
                ),
                _cell(unit, 0, 1, "만원(ten thousand won)"),
                _cell(unused_blank, 0, 2, ""),
            ]
        )
    )

    amount = next(field for field in registry if field["type"] == "amount")

    assert amount["target_id"] == unit
    assert amount["constraints"]["mode"] == "prefix_unit"
    assert amount["constraints"]["anchor"] == "만원(ten thousand won)"
    assert not any(
        field["target_id"] == unused_blank and field["type"] == "amount"
        for field in registry
    )
