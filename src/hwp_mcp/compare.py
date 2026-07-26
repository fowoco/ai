from __future__ import annotations

from difflib import SequenceMatcher
import hashlib
import math
from pathlib import Path
import re
from typing import Any

from defusedxml import ElementTree as ET


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
            empty_cell = operation.get("constraints", {}).get("mode") == "empty_cell"
            invalid = match is None
            if match is not None and inline:
                invalid = any(component not in segment_texts[0] for component in match.groups())
            elif match is not None and empty_cell:
                invalid = segment_texts != [value]
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


def analyze_svg_geometry(
    svg_paths: list[str | Path],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """rhwp SVG의 cell clip 순서를 XML cell과 결합해 좌표 근거를 만듭니다."""
    cells = [
        cell
        for section in manifest["sections"]
        for table in section["tables"]
        for cell in table["cells"]
    ]
    rendered_regions: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    for page_number, svg_path in enumerate(map(Path, svg_paths), start=1):
        root = ET.parse(svg_path).getroot()
        clips = {
            element.attrib["id"]: child
            for element in root.iter()
            if _local_name(element.tag) == "clipPath"
            and element.attrib.get("id", "").startswith("cell-clip-")
            for child in element
            if _local_name(child.tag) == "rect"
        }
        page_regions = []
        for group in root.iter():
            if _local_name(group.tag) != "g":
                continue
            match = re.fullmatch(
                r"url\(#(cell-clip-[^)]+)\)",
                group.attrib.get("clip-path", ""),
            )
            if match is None or match.group(1) not in clips:
                continue
            rect = clips[match.group(1)]
            x = float(rect.attrib["x"])
            y = float(rect.attrib["y"])
            bbox = [
                x,
                y,
                x + float(rect.attrib["width"]),
                y + float(rect.attrib["height"]),
            ]
            text_nodes = [
                node for node in group.iter() if _local_name(node.tag) == "text"
            ]
            text_bbox = _svg_text_bbox(text_nodes)
            page_regions.append(
                {
                    "page": page_number,
                    "clip_id": match.group(1),
                    "bbox": bbox,
                    "text": "".join("".join(node.itertext()) for node in text_nodes),
                    "text_bbox": text_bbox,
                    "overflow": bool(
                        text_bbox
                        and (
                            text_bbox[0] < bbox[0] - 0.5
                            or text_bbox[1] < bbox[1] - 0.5
                            or text_bbox[2] > bbox[2] + 0.5
                            or text_bbox[3] > bbox[3] + 0.5
                        )
                    ),
                }
            )
        rendered_regions.extend(page_regions)
        pages.append(
            {
                "page": page_number,
                "svg_path": str(svg_path),
                "cell_clip_count": len(page_regions),
            }
        )

    cell_regions = {
        cell["id"]: {**region, "cell_id": cell["id"]}
        for cell, region in zip(cells, rendered_regions)
    }
    text_mismatches = sorted(
        cell["id"]
        for cell, region in zip(cells, rendered_regions)
        if not _cell_text_matches(cell["text"], region["text"])
    )
    mapped = len(cells) == len(rendered_regions) and not text_mismatches
    return {
        "method": "rhwp_svg_geometry",
        "status": "MAPPED" if mapped else "NEEDS_HUMAN",
        "xml_cell_count": len(cells),
        "svg_cell_clip_count": len(rendered_regions),
        "pages": pages,
        "cell_regions": cell_regions,
        "unmapped_cell_ids": [cell["id"] for cell in cells[len(rendered_regions) :]],
        "text_mismatch_cell_ids": text_mismatches,
        "overflow_cell_ids": sorted(
            cell_id
            for cell_id, region in cell_regions.items()
            if region["overflow"]
        ),
    }


def attach_svg_regions(
    registry: list[dict[str, Any]],
    svg_analysis: dict[str, Any],
) -> list[dict[str, Any]]:
    """registry field에 rhwp SVG의 페이지별 합성 bbox를 붙입니다."""
    regions_by_cell = svg_analysis["cell_regions"]
    enriched: list[dict[str, Any]] = []
    for field in registry:
        item = {**field, "constraints": dict(field.get("constraints", {}))}
        by_page: dict[int, list[list[float]]] = {}
        clip_ids = []
        for cell_id in field.get("xml_segments") or [field["target_id"]]:
            region = regions_by_cell.get(cell_id)
            if region is None:
                continue
            by_page.setdefault(region["page"], []).append(region["bbox"])
            clip_ids.append(region["clip_id"])
        item["visual_regions"] = [
            (
                f"page_{page:03d}:"
                f"{math.floor(min(box[0] for box in boxes))},"
                f"{math.floor(min(box[1] for box in boxes))},"
                f"{math.ceil(max(box[2] for box in boxes))},"
                f"{math.ceil(max(box[3] for box in boxes))}"
            )
            for page, boxes in sorted(by_page.items())
        ]
        if clip_ids:
            item["constraints"]["visual_source"] = "rhwp_svg"
            item["constraints"]["visual_clip_ids"] = clip_ids
        enriched.append(item)
    return enriched


def review_svg_geometry(
    original_svg_paths: list[str | Path],
    modified_svg_paths: list[str | Path],
    original_manifest: dict[str, Any],
    modified_manifest: dict[str, Any],
    operations: list[dict[str, Any]],
) -> dict[str, Any]:
    """원본/수정 rhwp SVG에서 값 가시성·overflow·cell 이동을 검증합니다."""
    original = analyze_svg_geometry(original_svg_paths, original_manifest)
    modified = analyze_svg_geometry(modified_svg_paths, modified_manifest)
    original_regions = original["cell_regions"]
    modified_regions = modified["cell_regions"]
    moved = sorted(
        cell_id
        for cell_id in set(original_regions) & set(modified_regions)
        if any(
            abs(before - after) > 0.5
            for before, after in zip(
                original_regions[cell_id]["bbox"],
                modified_regions[cell_id]["bbox"],
            )
        )
    )
    new_overflow = sorted(
        set(modified["overflow_cell_ids"]) - set(original["overflow_cell_ids"])
    )
    field_checks = []
    for operation in operations:
        segment_ids = operation.get("xml_segments") or [operation["target_id"]]
        rendered = "".join(
            modified_regions.get(cell_id, {}).get("text", "")
            for cell_id in segment_ids
        )
        field_checks.append(
            {
                "field_id": operation["field_id"],
                "cell_ids": segment_ids,
                "regions_mapped": all(
                    cell_id in modified_regions for cell_id in segment_ids
                ),
                "rendered_value_present": _rendered_value_present(
                    operation["new_value"],
                    rendered,
                ),
                "new_overflow_cell_ids": sorted(set(segment_ids) & set(new_overflow)),
            }
        )
    mapped = original["status"] == modified["status"] == "MAPPED"
    page_count_preserved = len(original_svg_paths) == len(modified_svg_paths)
    passed = (
        mapped
        and page_count_preserved
        and not moved
        and not new_overflow
        and all(
            check["regions_mapped"]
            and check["rendered_value_present"]
            and not check["new_overflow_cell_ids"]
            for check in field_checks
        )
    )
    return {
        "method": "rhwp_svg_geometry",
        "passed": passed,
        "page_count_preserved": page_count_preserved,
        "original_status": original["status"],
        "modified_status": modified["status"],
        "moved_cell_ids": moved,
        "new_overflow_cell_ids": new_overflow,
        "field_checks": field_checks,
    }


def _rendered_value_present(expected: str, rendered: str) -> bool:
    rendered_compact = _compact_text(rendered)
    tokens = [
        token.casefold()
        for token in re.findall(r"[0-9A-Za-z가-힣]+", expected)
    ]
    return bool(tokens) and all(token in rendered_compact for token in tokens)


def _compact_text(value: str) -> str:
    return "".join(
        character.casefold() for character in value if character.isalnum()
    )


def _cell_text_matches(xml_text: str, svg_text: str) -> bool:
    expected = _compact_text(xml_text)
    actual = _compact_text(svg_text)
    if not expected:
        return True
    return (
        expected == actual
        or actual.startswith(expected)
        or expected.startswith(actual)
        or SequenceMatcher(None, expected, actual).ratio() >= 0.85
    )


def _svg_text_bbox(nodes: list[ET.Element]) -> list[float] | None:
    boxes = []
    for node in nodes:
        transform = node.attrib.get("transform", "")
        translated = re.search(
            r"translate\(\s*([-+0-9.eE]+)[,\s]+([-+0-9.eE]+)\s*\)",
            transform,
        )
        if translated is None:
            continue
        x, baseline = map(float, translated.groups())
        scale_match = re.search(r"scale\(\s*([-+0-9.eE]+)", transform)
        scale = float(scale_match.group(1)) if scale_match else 1.0
        font_size = float(node.attrib.get("font-size", 12))
        text = "".join(node.itertext())
        width = float(
            node.attrib.get("textLength", max(len(text), 1) * font_size * 0.6)
        ) * scale
        boxes.append([x, baseline - font_size, x + width, baseline + font_size * 0.2])
    if not boxes:
        return None
    return [
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    ]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


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
