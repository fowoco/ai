from __future__ import annotations

from pathlib import Path

from hwp_mcp.compare import compare_rendered_pages


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
