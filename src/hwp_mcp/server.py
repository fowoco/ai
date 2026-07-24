from __future__ import annotations

import logging
import os
from pathlib import Path
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from .hwpx import (
    DocumentError,
    analyze_document as analyze_hwpx_document,
    extract_text as extract_hwpx_text,
    fill_cells as fill_hwpx_cells,
    inspect_document as inspect_file,
    replace_text as replace_hwpx_text,
    validate_document as validate_file,
)


logging.basicConfig(stream=sys.stderr, level=logging.INFO)
logger = logging.getLogger("hwp-editor-mcp")

mcp = FastMCP(
    "HWPX Editor",
    instructions=(
        "Local-first HWPX inspection and narrow text editing. "
        "Original files are never overwritten. HWP legacy binary editing is unsupported."
    ),
    json_response=True,
)


def _allowed_root() -> Path:
    configured = os.environ.get("HWP_MCP_ROOT")
    return Path(configured).expanduser().resolve() if configured else Path.cwd().resolve()


def _resolve_path(raw_path: str, *, must_exist: bool) -> Path:
    if not raw_path or len(raw_path) > 4096:
        raise DocumentError("path가 비어 있거나 너무 깁니다.")
    root = _allowed_root()
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve(strict=must_exist)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise DocumentError(f"허용된 작업 폴더 밖의 경로입니다: {raw_path}") from exc
    if must_exist and not resolved.is_file():
        raise DocumentError(f"파일이 아닙니다: {raw_path}")
    return resolved


def _resolve_output_path(raw_path: str, input_path: Path) -> Path:
    if not raw_path:
        raise DocumentError("output_path를 명시해야 합니다. 원본 덮어쓰기를 방지합니다.")
    root = _allowed_root()
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise DocumentError(f"허용된 작업 폴더 밖의 출력 경로입니다: {raw_path}") from exc
    if resolved.exists():
        raise DocumentError(f"출력 파일이 이미 존재합니다. 새 경로를 지정하세요: {resolved}")
    if resolved == input_path:
        raise DocumentError("원본 파일을 덮어쓸 수 없습니다.")
    return resolved


@mcp.tool()
def inspect_document(path: str) -> dict[str, Any]:
    """Inspect a local HWPX package or report HWP legacy as unsupported."""
    input_path = _resolve_path(path, must_exist=True)
    return inspect_file(input_path)


@mcp.tool()
def extract_text(path: str) -> dict[str, Any]:
    """Extract section and paragraph text from a valid local HWPX file."""
    input_path = _resolve_path(path, must_exist=True)
    return extract_hwpx_text(input_path)


@mcp.tool()
def analyze_document(path: str) -> dict[str, Any]:
    """Return tables, cells, paragraphs, and image candidates for a local HWPX file."""
    input_path = _resolve_path(path, must_exist=True)
    return analyze_hwpx_document(input_path)


@mcp.tool()
def fill_cells(path: str, output_path: str, edits: list[dict[str, str]]) -> dict[str, Any]:
    """Append confirmed values to HWPX cells and write a new validated file."""
    input_path = _resolve_path(path, must_exist=True)
    destination = _resolve_output_path(output_path, input_path)
    return fill_hwpx_cells(input_path, destination, edits)


@mcp.tool()
def replace_text(path: str, output_path: str, old: str, new: str) -> dict[str, Any]:
    """Replace exact HWPX text into a new output file and revalidate it."""
    input_path = _resolve_path(path, must_exist=True)
    destination = _resolve_output_path(output_path, input_path)
    return replace_hwpx_text(input_path, destination, old, new)


@mcp.tool()
def validate_document(path: str) -> dict[str, Any]:
    """Validate HWPX ZIP/XML parts without changing the document."""
    input_path = _resolve_path(path, must_exist=True)
    return validate_file(input_path)


def main() -> None:
    logger.info("Starting HWPX Editor MCP Server; root=%s", _allowed_root())
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
