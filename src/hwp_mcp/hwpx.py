from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Iterable
import xml.etree.ElementTree as ET
import zipfile

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException

from .fields import infer_field_candidates, infer_field_segments


class DocumentError(ValueError):
    """사용자가 수정할 수 있는 문서 또는 경로 오류입니다."""


class UnsupportedFormatError(DocumentError):
    """요청한 작업을 해당 문서 형식에서 지원하지 않습니다."""


HWPX_MIMETYPE_PREFIX = "application/hwp"
REQUIRED_HWPX_PARTS = {
    "mimetype",
    "Contents/content.hpf",
    "Contents/header.xml",
}
SECTION_RE = re.compile(r"^Contents/section\d+\.xml$")
MAX_DOCUMENT_BYTES = 25 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 10_000
MAX_REPLACEMENT_LENGTH = 10_000
CELL_ID_RE = re.compile(r"^(section\d+)\.table(\d+)\.row(\d+)\.cell(\d+)$")


@dataclass(frozen=True)
class ValidationReport:
    valid: bool
    format: str
    file_count: int
    sections: list[str]
    errors: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "format": self.format,
            "file_count": self.file_count,
            "sections": self.sections,
            "errors": self.errors,
        }


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _is_hwp(path: str | Path) -> bool:
    return Path(path).suffix.lower() == ".hwp"


def _is_hwpx(str_or_path: str | Path) -> bool:
    return Path(str_or_path).suffix.lower() == ".hwpx"



def _require_hwpx(path: Path) -> None:
    if _is_hwp(path):
        raise UnsupportedFormatError(
            "HWP 레거시 바이너리는 현재 직접 편집하지 않습니다. HWPX로 변환한 뒤 다시 시도하세요."
        )
    if not _is_hwpx(path):
        raise DocumentError("지원하는 입력 확장자는 .hwpx입니다.")


def _parse_xml(data: bytes, part_name: str) -> ET.Element:
    try:
        return SafeET.fromstring(data)
    except (ET.ParseError, DefusedXmlException) as exc:
        raise DocumentError(f"XML 파싱 실패: {part_name}: {exc}") from exc


def _read_namespaces(data: bytes) -> dict[str, str]:
    namespaces: dict[str, str] = {}
    for _, (prefix, uri) in SafeET.iterparse(BytesIO(data), events=("start-ns",)):
        namespaces[prefix] = uri
    return namespaces


def _register_namespaces(namespaces: dict[str, str]) -> None:
    for prefix, uri in namespaces.items():
        ET.register_namespace(prefix or "", uri)


def _iter_xml_parts(archive: zipfile.ZipFile) -> Iterable[tuple[str, bytes]]:
    for info in archive.infolist():
        if info.is_dir() or not info.filename.lower().endswith(".xml"):
            continue
        yield info.filename, archive.read(info.filename)


def _validate_archive_name(name: str) -> None:
    path = Path(name)
    if path.is_absolute() or ".." in path.parts:
        raise DocumentError(f"안전하지 않은 ZIP 파트 경로입니다: {name}")


def _validate_archive(path: Path) -> ValidationReport:
    errors: list[str] = []
    sections: list[str] = []

    if path.stat().st_size > MAX_DOCUMENT_BYTES:
        errors.append(f"문서 크기가 제한({MAX_DOCUMENT_BYTES} bytes)을 초과했습니다.")

    if not zipfile.is_zipfile(path):
        return ValidationReport(False, "unknown", 0, [], ["ZIP 기반 HWPX 파일이 아닙니다."])

    try:
        with zipfile.ZipFile(path, "r") as archive:
            if len(archive.infolist()) > MAX_ARCHIVE_ENTRIES:
                errors.append(f"ZIP 파트 수가 제한({MAX_ARCHIVE_ENTRIES})를 초과했습니다.")
            total_uncompressed = 0
            for info in archive.infolist():
                try:
                    _validate_archive_name(info.filename)
                except DocumentError as exc:
                    errors.append(str(exc))
                total_uncompressed += info.file_size
            if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
                errors.append(
                    f"압축 해제 후 크기가 제한({MAX_UNCOMPRESSED_BYTES} bytes)를 초과했습니다."
                )
            names = set(archive.namelist())
            missing = sorted(REQUIRED_HWPX_PARTS - names)
            if missing:
                errors.append(f"필수 파트가 없습니다: {', '.join(missing)}")

            sections = sorted(name for name in names if SECTION_RE.match(name))
            if not sections:
                errors.append("Contents/sectionN.xml 본문 구역이 없습니다.")

            mimetype = archive.read("mimetype").decode("utf-8", errors="replace").strip() if "mimetype" in names else ""
            if mimetype and not mimetype.startswith(HWPX_MIMETYPE_PREFIX):
                errors.append(f"HWPX mimetype가 아닙니다: {mimetype}")

            if not errors:
                for part_name, data in _iter_xml_parts(archive):
                    try:
                        _parse_xml(data, part_name)
                    except DocumentError as exc:
                        errors.append(str(exc))
    except (OSError, zipfile.BadZipFile) as exc:
        errors.append(f"ZIP 읽기 실패: {exc}")

    return ValidationReport(not errors, "hwpx", len(names) if "names" in locals() else 0, sections, errors)


def validate_document(path: str | Path) -> dict[str, Any]:
    """변경 없이 HWPX 패키지를 검증합니다."""
    path = Path(path)
    if _is_hwp(path):
        return {
            "valid": False,
            "format": "hwp",
            "file_count": 0,
            "sections": [],
            "errors": ["HWP 레거시 바이너리는 현재 직접 검증·편집 대상이 아닙니다."],
        }
    _require_hwpx(path)
    return _validate_archive(path).as_dict()


def inspect_document(path: str | Path) -> dict[str, Any]:
    """문서의 안전한 메타데이터와 검증 결과를 반환합니다."""
    path = Path(path)
    if _is_hwp(path):
        return {
            "format": "hwp",
            "editable": False,
            "reason": "legacy_binary_format",
            "next_step": "convert_to_hwpx",
            "size_bytes": path.stat().st_size,
        }
    report = validate_document(path)
    return {
        "format": "hwpx",
        "editable": report["valid"],
        "size_bytes": path.stat().st_size,
        **report,
    }


def extract_text(path: Path) -> dict[str, Any]:
    """유효한 HWPX 패키지에서 구역과 문단 텍스트를 추출합니다."""
    _require_hwpx(path)
    report = _validate_archive(path)
    if not report.valid:
        raise DocumentError("유효하지 않은 HWPX입니다: " + " | ".join(report.errors))

    sections: list[dict[str, Any]] = []
    with zipfile.ZipFile(path, "r") as archive:
        for section_name in report.sections:
            root = _parse_xml(archive.read(section_name), section_name)
            paragraphs: list[str] = []
            for element in root.iter():
                if _local_name(element.tag) != "p":
                    continue
                text = "".join(
                    (child.text or "")
                    for child in element.iter()
                    if _local_name(child.tag) == "t"
                )
                paragraphs.append(text)
            sections.append(
                {
                    "name": section_name,
                    "paragraphs": paragraphs,
                    "text": "\n".join(paragraphs),
                }
            )

    return {
        "format": "hwpx",
        "sections": sections,
        "text": "\n".join(section["text"] for section in sections),
        "paragraph_count": sum(len(section["paragraphs"]) for section in sections),
    }


def _element_text(element: ET.Element) -> str:
    return "".join(child.text or "" for child in element.iter() if _local_name(child.tag) == "t")


def analyze_document(path: str | Path) -> dict[str, Any]:
    """양식 대상 지정을 위한 간단한 구조 Manifest를 반환합니다."""
    path = Path(path)
    _require_hwpx(path)
    report = _validate_archive(path)
    if not report.valid:
        raise DocumentError("유효하지 않은 HWPX입니다: " + " | ".join(report.errors))

    sections: list[dict[str, Any]] = []
    with zipfile.ZipFile(path, "r") as archive:
        for section_name in report.sections:
            root = _parse_xml(archive.read(section_name), section_name)
            section_id = Path(section_name).stem
            paragraphs = [
                {
                    "id": f"{section_id}.paragraph{index}",
                    "text": _element_text(element),
                }
                for index, element in enumerate(
                    element for element in root.iter() if _local_name(element.tag) == "p"
                )
            ]
            tables: list[dict[str, Any]] = []
            for table_index, table in enumerate(
                element for element in root.iter() if _local_name(element.tag) == "tbl"
            ):
                rows = [element for element in table if _local_name(element.tag) == "tr"]
                cells: list[dict[str, Any]] = []
                for row_index, row in enumerate(rows):
                    for cell_index, cell in enumerate(
                        element for element in row if _local_name(element.tag) == "tc"
                    ):
                        cell_addr = next(
                            (
                                element
                                for element in cell
                                if _local_name(element.tag) == "cellAddr"
                            ),
                            None,
                        )
                        cell_span = next(
                            (
                                element
                                for element in cell
                                if _local_name(element.tag) == "cellSpan"
                            ),
                            None,
                        )
                        cells.append(
                            {
                                "id": (
                                    f"{section_id}.table{table_index}."
                                    f"row{row_index}.cell{cell_index}"
                                ),
                                "row": row_index,
                                "column": cell_index,
                                "row_addr": int(cell_addr.attrib.get("rowAddr", row_index))
                                if cell_addr is not None
                                else row_index,
                                "column_addr": int(cell_addr.attrib.get("colAddr", cell_index))
                                if cell_addr is not None
                                else cell_index,
                                "row_span": int(cell_span.attrib.get("rowSpan", 1))
                                if cell_span is not None
                                else 1,
                                "column_span": int(cell_span.attrib.get("colSpan", 1))
                                if cell_span is not None
                                else 1,
                                "text": _element_text(cell),
                            }
                        )
                tables.append(
                    {
                        "id": f"{section_id}.table{table_index}",
                        "row_count": len(rows),
                        "cell_count": len(cells),
                        "cells": cells,
                    }
                )
            images = [
                {
                    "id": f"{section_id}.object{index}",
                    "kind": _local_name(element.tag),
                }
                for index, element in enumerate(root.iter())
                if _local_name(element.tag) in {"pic", "img", "image"}
            ]
            sections.append(
                {
                    "name": section_name,
                    "paragraph_count": len(paragraphs),
                    "paragraphs": paragraphs,
                    "table_count": len(tables),
                    "tables": tables,
                    "image_count": len(images),
                    "images": images,
                }
            )

    manifest = {
        "format": "hwpx",
        "valid": True,
        "sections": sections,
        "paragraph_count": sum(section["paragraph_count"] for section in sections),
        "table_count": sum(section["table_count"] for section in sections),
        "image_count": sum(section["image_count"] for section in sections),
    }
    manifest["field_candidates"] = infer_field_candidates(manifest)
    manifest["field_segments"] = infer_field_segments(manifest)
    return manifest


def _safe_output_path(input_path: Path, output_path: Path) -> Path:
    if output_path == input_path:
        raise DocumentError("원본 파일을 덮어쓸 수 없습니다. 다른 출력 경로를 지정하세요.")
    if output_path.suffix.lower() != ".hwpx":
        raise DocumentError("출력 확장자는 .hwpx여야 합니다.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_parent = output_path.parent.resolve()
    if not resolved_parent.is_dir():
        raise DocumentError("출력 폴더가 유효하지 않습니다.")
    return output_path


def _write_entries(
    entries: list[tuple[zipfile.ZipInfo, bytes]], output_path: Path
) -> dict[str, Any]:
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".hwpx", dir=output_path.parent, delete=False
        ) as temporary:
            temporary_path = temporary.name
        with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_DEFLATED) as destination:
            mimetype_entries = [entry for entry in entries if entry[0].filename == "mimetype"]
            other_entries = [entry for entry in entries if entry[0].filename != "mimetype"]
            for info, data in mimetype_entries + other_entries:
                output_info = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                output_info.compress_type = (
                    zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED
                )
                output_info.comment = info.comment
                output_info.create_system = info.create_system
                output_info.external_attr = info.external_attr
                output_info.extra = info.extra
                destination.writestr(output_info, data)
        os.replace(temporary_path, output_path)
        temporary_path = None
    finally:
        if temporary_path:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass

    output_report = _validate_archive(output_path)
    if not output_report.valid:
        try:
            output_path.unlink()
        except FileNotFoundError:
            pass
        raise DocumentError("수정 후 검증에 실패했습니다: " + " | ".join(output_report.errors))
    return output_report.as_dict()


def _find_cell(root: ET.Element, target_id: str) -> ET.Element:
    match = CELL_ID_RE.fullmatch(target_id)
    if match is None:
        raise DocumentError(f"지원하지 않는 셀 대상 ID입니다: {target_id}")
    section_id, table_index, row_index, cell_index = match.groups()
    root_section_id = next(
        (part for part in target_id.split(".") if part.startswith("section")), ""
    )
    if root_section_id != section_id:
        raise DocumentError(f"문서 구역이 대상과 다릅니다: {target_id}")
    tables = [element for element in root.iter() if _local_name(element.tag) == "tbl"]
    try:
        rows = [
            element
            for element in tables[int(table_index)]
            if _local_name(element.tag) == "tr"
        ]
        cells = [
            element
            for element in rows[int(row_index)]
            if _local_name(element.tag) == "tc"
        ]
        return cells[int(cell_index)]
    except (IndexError, ValueError) as exc:
        raise DocumentError(f"셀 대상을 찾지 못했습니다: {target_id}") from exc


def fill_cells(path: str | Path, output_path: str | Path, edits: list[dict[str, str]]) -> dict[str, Any]:
    """확인된 셀에 값을 추가하고 검증된 새 HWPX 패키지를 작성합니다."""
    path = Path(path)
    output_path = Path(output_path)
    _require_hwpx(path)
    if not edits:
        raise DocumentError("edits는 비어 있을 수 없습니다.")
    if len(edits) > 100:
        raise DocumentError("한 번에 최대 100개 셀까지 수정할 수 있습니다.")
    output_path = _safe_output_path(path, output_path)
    report = _validate_archive(path)
    if not report.valid:
        raise DocumentError("유효하지 않은 HWPX입니다: " + " | ".join(report.errors))

    by_section: dict[str, list[dict[str, str]]] = {}
    for edit in edits:
        target_id = edit.get("target_id", "")
        expected_text = edit.get("expected_text", edit.get("old_value", ""))
        value = edit.get("value", edit.get("new_value", ""))
        edit["expected_text"] = expected_text
        edit["value"] = value
        if not target_id or "expected_text" not in edit or not value:
            raise DocumentError("각 edit에 target_id, expected_text(또는 old_value), value(또는 new_value)가 필요합니다.")
        if len(value) > MAX_REPLACEMENT_LENGTH:
            raise DocumentError(f"입력값은 {MAX_REPLACEMENT_LENGTH}자 이하이어야 합니다.")
        match = CELL_ID_RE.fullmatch(target_id)
        if match is None:
            raise DocumentError(f"지원하지 않는 셀 대상 ID입니다: {target_id}")
        by_section.setdefault(match.group(1), []).append(edit)

    entries: list[tuple[zipfile.ZipInfo, bytes]] = []
    applied = 0
    with zipfile.ZipFile(path, "r") as source:
        for info in source.infolist():
            data = source.read(info.filename)
            if SECTION_RE.match(info.filename):
                section_id = Path(info.filename).stem
                section_edits = by_section.get(section_id, [])
                if section_edits:
                    namespaces = _read_namespaces(data)
                    _register_namespaces(namespaces)
                    root = _parse_xml(data, info.filename)
                    seen_targets: set[str] = set()
                    for edit in section_edits:
                        target_id = edit["target_id"]
                        if target_id in seen_targets:
                            raise DocumentError(f"같은 셀을 중복 수정할 수 없습니다: {target_id}")
                        seen_targets.add(target_id)
                        cell = _find_cell(root, target_id)
                        current_text = _element_text(cell)
                        if current_text != edit["expected_text"]:
                            raise DocumentError(
                                f"셀 내용이 예상과 다릅니다: {target_id}: {current_text!r}"
                            )
                        # ponytail: anchor나 기존 텍스트가 있으면 덧붙이지 않고 t 노드를 직접 치환합니다.
                        anchor = edit.get("anchor")
                        t_elems = [e for e in cell.iter() if _local_name(e.tag) == "t"]
                        replaced = False

                        if anchor:
                            for t in t_elems:
                                if t.text and anchor in t.text:
                                    t.text = t.text.replace(anchor, edit["value"])
                                    replaced = True
                                    break
                        elif t_elems:
                            # 체크박스 정교화: [  ] 또는 [ ] (공백 1~2칸) 패턴을 [V]로 정교 교체
                            if edit["value"] in ("[V]", "[■]", "V"):
                                import re
                                for t in t_elems:
                                    if t.text and re.search(r"\[\s+\]", t.text):
                                        t.text = re.sub(r"\[\s+\]", "[V]", t.text, count=1)
                                        replaced = True
                                        break
                            if not replaced:
                                target_t = t_elems[-1]
                                if not target_t.text:
                                    target_t.text = edit["value"]
                                    replaced = True
                                elif edit["expected_text"] and edit["expected_text"] in target_t.text:
                                    target_t.text = target_t.text.replace(edit["expected_text"], edit["value"])
                                    replaced = True

                        if not replaced:
                            paragraphs = [
                                element for element in cell.iter() if _local_name(element.tag) == "p"
                            ]
                            if not paragraphs:
                                raise DocumentError(f"셀에 문단이 없습니다: {target_id}")
                            paragraph = paragraphs[-1]
                            runs = [element for element in paragraph if _local_name(element.tag) == "run"]
                            char_pr_id = runs[-1].attrib.get("charPrIDRef", "0") if runs else "0"
                            run = ET.SubElement(paragraph, paragraph.tag.rsplit("}", 1)[0] + "}run")
                            run.set("charPrIDRef", char_pr_id)
                            text = ET.SubElement(run, run.tag.rsplit("}", 1)[0] + "}t")
                            text.text = edit["value"]

                        applied += 1
                    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            entries.append((info, data))

    validation = _write_entries(entries, output_path)
    return {
        "format": "hwpx",
        "output_path": str(output_path),
        "applied": applied,
        "validated": True,
        "validation": validation,
    }


def replace_text(path: Path, output_path: Path, old: str, new: str) -> dict[str, Any]:
    """텍스트 노드를 정확히 치환하고 검증된 새 HWPX 패키지를 작성합니다."""
    _require_hwpx(path)
    if not old:
        raise DocumentError("old 텍스트는 비어 있을 수 없습니다.")
    if len(old) > MAX_REPLACEMENT_LENGTH or len(new) > MAX_REPLACEMENT_LENGTH:
        raise DocumentError(f"치환 문자열은 {MAX_REPLACEMENT_LENGTH}자 이하이어야 합니다.")

    report = _validate_archive(path)
    if not report.valid:
        raise DocumentError("유효하지 않은 HWPX입니다: " + " | ".join(report.errors))
    output_path = _safe_output_path(path, output_path)

    replacements = 0
    with zipfile.ZipFile(path, "r") as source:
        entries: list[tuple[zipfile.ZipInfo, bytes]] = []
        for info in source.infolist():
            data = source.read(info.filename)
            if SECTION_RE.match(info.filename):
                namespaces = _read_namespaces(data)
                _register_namespaces(namespaces)
                root = _parse_xml(data, info.filename)
                changed = False
                for element in root.iter():
                    if _local_name(element.tag) != "t" or not element.text or old not in element.text:
                        continue
                    count = element.text.count(old)
                    element.text = element.text.replace(old, new)
                    replacements += count
                    changed = True
                if changed:
                    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            entries.append((info, data))

    if replacements == 0:
        raise DocumentError("치환할 텍스트를 찾지 못했습니다. 원본은 생성하지 않았습니다.")

    output_report = _write_entries(entries, output_path)

    return {
        "format": "hwpx",
        "output_path": str(output_path),
        "replacements": replacements,
        "validated": True,
        "validation": output_report,
    }
