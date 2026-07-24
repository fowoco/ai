from __future__ import annotations

from pathlib import Path

from hwp_mcp.compare import compare_rendered_pages, validate_expected_changes


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
