from __future__ import annotations

from pathlib import Path

from hwp_mcp.compare import (
    analyze_svg_geometry,
    compare_rendered_pages,
    validate_expected_changes,
    validate_typed_postconditions,
)


def test_compare_rendered_pages_reports_changed_svg(tmp_path: Path) -> None:
    original = tmp_path / "original.svg"
    modified = tmp_path / "modified.svg"
    original.write_text("<svg>old</svg>", encoding="utf-8")
    modified.write_text("<svg>new</svg>", encoding="utf-8")

    result = compare_rendered_pages(
        {"files": [str(original)]},
        {"files": [str(modified)]},
    )

    assert result["method"] == "svg_sha256"
    assert result["same_pages"] is False
    assert result["pages"][0]["same"] is False


def test_validate_expected_changes_rejects_unapproved_cell_change() -> None:
    structure = {
        "same_shape": True,
        "changed_cells": [
            {"id": "section0.table0.row0.cell1", "original": "", "modified": "A"},
            {"id": "section0.table0.row0.cell2", "original": "", "modified": "B"},
        ],
    }

    result = validate_expected_changes(
        structure, ["section0.table0.row0.cell1"]
    )

    assert result["passed"] is False
    assert result["unexpected_changes"][0]["id"] == "section0.table0.row0.cell2"


def test_svg_geometry_rejects_same_count_in_wrong_cell_order(
    tmp_path: Path,
) -> None:
    svg = tmp_path / "page_001.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><defs>'
        '<clipPath id="cell-clip-1"><rect x="0" y="0" width="50" height="20"/></clipPath>'
        '<clipPath id="cell-clip-2"><rect x="50" y="0" width="50" height="20"/></clipPath>'
        "</defs>"
        '<g clip-path="url(#cell-clip-1)"><text transform="translate(2,12)">B</text></g>'
        '<g clip-path="url(#cell-clip-2)"><text transform="translate(52,12)">A</text></g>'
        "</svg>",
        encoding="utf-8",
    )
    manifest = {
        "sections": [
            {
                "tables": [
                    {
                        "cells": [
                            {"id": "cell-a", "text": "A"},
                            {"id": "cell-b", "text": "B"},
                        ]
                    }
                ]
            }
        ]
    }

    result = analyze_svg_geometry([svg], manifest)

    assert result["status"] == "NEEDS_HUMAN"
    assert result["text_mismatch_cell_ids"] == ["cell-a", "cell-b"]


def test_amount_postcondition_rejects_duplicate_prefix_unit() -> None:
    manifest = {
        "sections": [
            {
                "tables": [
                    {
                        "cells": [
                            {
                                "id": "section0.table0.row0.cell1",
                                "text": "4000만원 만원",
                            }
                        ]
                    }
                ],
                "paragraphs": [],
            }
        ]
    }
    result = validate_typed_postconditions(
        manifest,
        [
            {
                "operation": "set_amount",
                "field_id": "amount-field",
                "target_id": "section0.table0.row0.cell1",
                "xml_segments": ["section0.table0.row0.cell1"],
                "new_value": "4000만원",
                "anchor": "만원",
                "constraints": {"mode": "prefix_unit"},
            }
        ],
    )

    assert result["passed"] is False
    assert "금액" in result["failures"][0]
