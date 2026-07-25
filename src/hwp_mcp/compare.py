from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def _items_by_id(manifest: dict[str, Any], key: str) -> dict[str, str]:
    items: dict[str, str] = {}
    for section in manifest["sections"]:
        for item in section[key]:
            items[item["id"]] = item["text"]
    return items


def compare_manifests(
    original: dict[str, Any], modified: dict[str, Any]
) -> dict[str, Any]:
    """두 문서 Manifest의 구조와 텍스트 차이를 반환합니다."""
    changed_cells = _changed_items(
        _cell_items_by_id(original), _cell_items_by_id(modified)
    )
    changed_paragraphs = _changed_items(
        _items_by_id(original, "paragraphs"), _items_by_id(modified, "paragraphs")
    )
    return {
        "same_shape": all(
            original[key] == modified[key]
            for key in ("paragraph_count", "table_count", "image_count")
        ),
        "counts": {
            "original": _manifest_counts(original),
            "modified": _manifest_counts(modified),
        },
        "changed_cells": changed_cells,
        "changed_paragraphs": changed_paragraphs,
    }


def validate_expected_changes(
    structure: dict[str, Any], expected_ids: list[str]
) -> dict[str, Any]:
    """승인된 셀 외의 변경과 예상 변경 누락을 확인합니다."""
    expected = set(expected_ids)
    actual_changes = {
        change["id"]: change for change in structure["changed_cells"]
    }
    unexpected = [
        actual_changes[item_id]
        for item_id in sorted(set(actual_changes) - expected)
    ]
    missing = sorted(expected - set(actual_changes))
    passed = structure["same_shape"] and not unexpected and not missing
    return {
        "passed": passed,
        "expected_ids": sorted(expected),
        "actual_ids": sorted(actual_changes),
        "unexpected_changes": unexpected,
        "missing_changes": missing,
    }


def _manifest_counts(manifest: dict[str, Any]) -> dict[str, int]:
    return {
        "paragraphs": manifest["paragraph_count"],
        "tables": manifest["table_count"],
        "images": manifest["image_count"],
    }


def _cell_items_by_id(manifest: dict[str, Any]) -> dict[str, str]:
    items: dict[str, str] = {}
    for section in manifest["sections"]:
        for table in section["tables"]:
            for cell in table["cells"]:
                items[cell["id"]] = cell["text"]
    return items


def _changed_items(original: dict[str, str], modified: dict[str, str]) -> list[dict[str, str]]:
    changes: list[dict[str, str]] = []
    for item_id in sorted(set(original) | set(modified)):
        old = original.get(item_id)
        new = modified.get(item_id)
        if old == new:
            continue
        changes.append(
            {
                "id": item_id,
                "original": old or "",
                "modified": new or "",
                "kind": "added" if old is None else "removed" if new is None else "changed",
            }
        )
    return changes


def compare_rendered_pages(
    original: dict[str, Any], modified: dict[str, Any]
) -> dict[str, Any]:
    """두 SVG 렌더 결과를 페이지 순서와 SHA-256으로 비교합니다."""
    original_files = original["files"]
    modified_files = modified["files"]
    page_count = max(len(original_files), len(modified_files))
    pages: list[dict[str, Any]] = []
    for index in range(page_count):
        old_path = Path(original_files[index]) if index < len(original_files) else None
        new_path = Path(modified_files[index]) if index < len(modified_files) else None
        old_hash = _sha256(old_path) if old_path else None
        new_hash = _sha256(new_path) if new_path else None
        pages.append(
            {
                "page": index + 1,
                "same": old_hash == new_hash and old_hash is not None,
                "original": str(old_path) if old_path else None,
                "modified": str(new_path) if new_path else None,
                "original_sha256": old_hash,
                "modified_sha256": new_hash,
            }
        )
    return {
        "method": "svg_sha256",
        "same_pages": all(page["same"] for page in pages),
        "pages": pages,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def svg_to_png(svg_path: str | Path, output_png_path: str | Path) -> Path:
    """SVG 파일을 PNG 캡처 이미지로 렌더링합니다."""
    import resvg_py

    svg_path = Path(svg_path)
    output_png_path = Path(output_png_path)
    output_png_path.parent.mkdir(parents=True, exist_ok=True)

    svg_text = svg_path.read_text(encoding="utf-8", errors="ignore")
    png_bytes = resvg_py.svg_to_bytes(svg_text)
    output_png_path.write_bytes(png_bytes)
    return output_png_path


def generate_visual_diff(
    orig_png_path: str | Path, mod_png_path: str | Path, diff_png_path: str | Path
) -> dict[str, Any]:
    """두 PNG 캡처를 비교하고 변경 영역에 빨간색 하이라이트 박스를 그린 차이 이미지를 작성합니다."""
    from PIL import Image, ImageDraw, ImageChops

    orig_path = Path(orig_png_path)
    mod_path = Path(mod_png_path)
    diff_path = Path(diff_png_path)
    diff_path.parent.mkdir(parents=True, exist_ok=True)

    img1 = Image.open(orig_path).convert("RGB")
    img2 = Image.open(mod_path).convert("RGB")

    diff = ImageChops.difference(img1, img2)
    bbox = diff.getbbox()

    if bbox:
        highlight = img2.copy()
        draw = ImageDraw.Draw(highlight)
        padding = 6
        x0 = max(0, bbox[0] - padding)
        y0 = max(0, bbox[1] - padding)
        x1 = min(img2.width, bbox[2] + padding)
        y1 = min(img2.height, bbox[3] + padding)
        draw.rectangle([x0, y0, x1, y1], outline="red", width=3)
        highlight.save(diff_path)
        has_diff = True
    else:
        img2.save(diff_path)
        has_diff = False

    return {
        "has_diff": has_diff,
        "diff_bbox": list(bbox) if bbox else None,
        "diff_png_path": str(diff_path),
    }

