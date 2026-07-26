from __future__ import annotations

import hashlib
from pathlib import Path
import re
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


def validate_typed_postconditions(
    modified_manifest: dict[str, Any],
    operations: list[dict[str, Any]],
) -> dict[str, Any]:
    """typed operation별 의미 postcondition을 manifest에서 재검증합니다."""
    cells = _cell_items_by_id(modified_manifest)
    failures: list[str] = []
    for operation in operations:
        field_id = operation["field_id"]
        segment_ids = operation.get("xml_segments") or [operation["target_id"]]
        segment_texts = [cells.get(segment_id, "") for segment_id in segment_ids]
        name = operation["operation"]
        value = operation["new_value"]

        if name == "write_character_grid":
            separators = {
                item.get("value", "")
                for item in operation.get("constraints", {}).get("separators", [])
            }
            expected = [character for character in value if character not in separators]
            if segment_texts != expected:
                failures.append(f"{field_id}: 문자칸 postcondition 불일치")
        elif name == "set_date_segments":
            match = re.fullmatch(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})", value)
            inline = operation.get("constraints", {}).get("mode") == "inline"
            invalid = match is None
            if match is not None and inline:
                invalid = any(component not in segment_texts[0] for component in match.groups())
            elif match is not None:
                invalid = any(
                    component not in text
                    for component, text in zip(match.groups(), segment_texts)
                )
            if invalid:
                failures.append(f"{field_id}: 날짜 postcondition 불일치")
        elif name == "set_checkbox":
            target = segment_texts[0]
            if target.count("[V]") != 1:
                failures.append(f"{field_id}: checkbox 선택 수가 1이 아님")
            anchor = operation.get("anchor")
            if anchor and anchor in target:
                failures.append(f"{field_id}: checkbox 원본 marker 잔존")
        elif "".join(segment_texts).count(value) != 1:
            failures.append(f"{field_id}: 입력값이 승인 segment에 정확히 1회 있지 않음")

    return {"passed": not failures, "failures": failures}


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
    orig_png_path: str | Path,
    mod_png_path: str | Path,
    diff_png_path: str | Path,
    field_regions: dict[str, list[int]] | None = None,
) -> dict[str, Any]:
    """두 PNG의 변경 픽셀 연결 영역별 하이라이트와 field 관계를 반환합니다."""
    from collections import deque
    from PIL import Image, ImageChops, ImageDraw, ImageFilter

    orig_path = Path(orig_png_path)
    mod_path = Path(mod_png_path)
    diff_path = Path(diff_png_path)
    diff_path.parent.mkdir(parents=True, exist_ok=True)

    img1 = Image.open(orig_path).convert("RGB")
    img2 = Image.open(mod_path).convert("RGB")

    diff = ImageChops.difference(img1, img2)
    bbox = diff.getbbox()
    components: list[dict[str, Any]] = []

    if bbox:
        highlight = img2.copy()
        draw = ImageDraw.Draw(highlight)
        padding = 6
        mask = (
            diff.convert("L")
            .point(lambda value: 255 if value else 0)
            .filter(ImageFilter.MaxFilter(9))
        )
        pixels = mask.load()
        width, height = mask.size
        visited = bytearray(width * height)
        for y in range(height):
            for x in range(width):
                offset = y * width + x
                if visited[offset] or not pixels[x, y]:
                    continue
                queue = deque([(x, y)])
                visited[offset] = 1
                min_x = max_x = x
                min_y = max_y = y
                while queue:
                    current_x, current_y = queue.popleft()
                    min_x = min(min_x, current_x)
                    min_y = min(min_y, current_y)
                    max_x = max(max_x, current_x)
                    max_y = max(max_y, current_y)
                    for next_x, next_y in (
                        (current_x - 1, current_y),
                        (current_x + 1, current_y),
                        (current_x, current_y - 1),
                        (current_x, current_y + 1),
                    ):
                        if not (0 <= next_x < width and 0 <= next_y < height):
                            continue
                        next_offset = next_y * width + next_x
                        if visited[next_offset] or not pixels[next_x, next_y]:
                            continue
                        visited[next_offset] = 1
                        queue.append((next_x, next_y))
                component_bbox = [min_x, min_y, max_x + 1, max_y + 1]
                related = [
                    field_id
                    for field_id, region in (field_regions or {}).items()
                    if _boxes_intersect(component_bbox, region)
                ]
                components.append(
                    {
                        "bbox": component_bbox,
                        "related_field_ids": sorted(related),
                    }
                )
                draw.rectangle(
                    [
                        max(0, min_x - padding),
                        max(0, min_y - padding),
                        min(width, max_x + 1 + padding),
                        min(height, max_y + 1 + padding),
                    ],
                    outline="red",
                    width=3,
                )
        highlight.save(diff_path)
        has_diff = True
    else:
        img2.save(diff_path)
        has_diff = False

    return {
        "has_diff": has_diff,
        "diff_bbox": list(bbox) if bbox else None,
        "components": components,
        "diff_png_path": str(diff_path),
    }


def _boxes_intersect(first: list[int], second: list[int]) -> bool:
    return not (
        first[2] <= second[0]
        or second[2] <= first[0]
        or first[3] <= second[1]
        or second[3] <= first[1]
    )
