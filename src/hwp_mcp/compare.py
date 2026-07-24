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
