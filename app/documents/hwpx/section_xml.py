"""HWPX section XML parsing and form-oriented mutations."""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from pathlib import Path

from .errors import HwpxError
from .package import MAX_UNCOMPRESSED_BYTES

HP_NAMESPACE = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HS_NAMESPACE = "http://www.hancom.co.kr/hwpml/2011/section"
HP = f"{{{HP_NAMESPACE}}}"


def _normalise_label(value: str) -> tuple[str, str]:
    return re.sub(r"[^가-힣]", "", value), re.sub(r"[^a-zA-Z]", "", value).casefold()


def _label_matches(key: str, text: str) -> bool:
    key_hangul, key_english = _normalise_label(key)
    text_hangul, text_english = _normalise_label(text)
    return bool(
        (key_hangul and text_hangul == key_hangul)
        or (key_english and text_english == key_english)
    )


def _cell_text(cell: ET.Element) -> str:
    return "".join(text.text for text in cell.iter(f"{HP}t") if text.text)


def _get_or_create_text_element(cell: ET.Element) -> ET.Element:
    sublist = cell.find(f"{HP}subList")
    if sublist is None:
        sublist = ET.SubElement(cell, f"{HP}subList")
    paragraph = sublist.find(f"{HP}p")
    if paragraph is None:
        paragraph = ET.SubElement(sublist, f"{HP}p")
    run = paragraph.find(f"{HP}run")
    if run is None:
        run = ET.SubElement(paragraph, f"{HP}run")
    text = run.find(f"{HP}t")
    if text is None:
        text = ET.SubElement(run, f"{HP}t")
    return text


def _register_namespaces(xml_data: bytes) -> None:
    for _, (prefix, uri) in ET.iterparse(io.BytesIO(xml_data), events=("start-ns",)):
        if prefix not in {"xml", "xmlns"}:
            ET.register_namespace(prefix, uri)


def _parse_section(xml_data: bytes, *, location: str = "section XML") -> ET.Element:
    if len(xml_data) > MAX_UNCOMPRESSED_BYTES:
        raise HwpxError("section XML exceeds the size limit")
    upper_xml = xml_data.upper().replace(b"\x00", b"")
    if b"<!DOCTYPE" in upper_xml or b"<!ENTITY" in upper_xml:
        raise HwpxError("DTD and entity declarations are not allowed in section XML")
    try:
        _register_namespaces(xml_data)
        root = ET.fromstring(xml_data)
    except (ET.ParseError, ValueError) as exc:
        raise HwpxError(f"invalid HWPX section XML: {location}") from exc
    if root.tag != f"{{{HS_NAMESPACE}}}sec":
        raise HwpxError(
            "section XML root must be "
            f"{{{HS_NAMESPACE}}}sec, got {root.tag!r}"
        )
    return root


class HwpxSection:
    """One parsed HWPX section with lossless bytes until it is modified."""

    def __init__(self, xml_data: bytes, *, location: str = "section XML"):
        self._root = _parse_section(xml_data, location=location)
        self._original_data = xml_data
        self._dirty = False

    def apply_values(self, values: Mapping[str, object]) -> tuple[str, ...]:
        changed: list[str] = []
        down_fields = {"성", "명", "년", "월", "일"}
        for table in self._root.iter(f"{HP}tbl"):
            cell_map: dict[tuple[int, int], ET.Element] = {}
            for cell in table.iter(f"{HP}tc"):
                address = cell.find(f"{HP}cellAddr")
                if address is not None:
                    row = int(address.attrib.get("rowAddr", 0))
                    column = int(address.attrib.get("colAddr", 0))
                    cell_map[(row, column)] = cell

            for (row, column), cell in cell_map.items():
                text = _cell_text(cell)
                for key, value in values.items():
                    if key in changed or not _label_matches(key, text):
                        continue
                    key_hangul, _ = _normalise_label(key)
                    if key_hangul == "성별":
                        marker = str(value)
                        for text_element in cell.iter(f"{HP}t"):
                            if text_element.text and marker in text_element.text:
                                text_element.text = text_element.text.replace(
                                    "[ ]", "[v]"
                                ).replace("[  ]", "[v]")
                                changed.append(key)
                                break
                        continue

                    target = None
                    if key_hangul in down_fields:
                        target = next(
                            (
                                cell_map[(next_row, column)]
                                for next_row in range(row + 1, 100)
                                if (next_row, column) in cell_map
                            ),
                            None,
                        )
                    else:
                        target = next(
                            (
                                cell_map[(row, next_column)]
                                for next_column in range(column + 1, 100)
                                if (row, next_column) in cell_map
                            ),
                            None,
                        )
                    if target is not None:
                        _get_or_create_text_element(target).text = str(value)
                        changed.append(key)
        self._dirty = self._dirty or bool(changed)
        return tuple(changed)

    def apply_application_options(
        self,
        options: Mapping[str, object],
    ) -> tuple[str, ...]:
        changed: list[str] = []
        for table in self._root.iter(f"{HP}tbl"):
            for row in table.iter(f"{HP}tr"):
                cells = list(row.iter(f"{HP}tc"))
                for index, cell in enumerate(cells):
                    cell_text = _cell_text(cell)
                    for label, value in options.items():
                        if label in changed or not _label_matches(label, cell_text):
                            continue
                        marked = False
                        for text_element in cell.iter(f"{HP}t"):
                            if text_element.text and "[" in text_element.text:
                                updated = text_element.text.replace(
                                    "[ ]", "[v]"
                                ).replace("[  ]", "[v]")
                                marked = marked or updated != text_element.text
                                text_element.text = updated
                        if isinstance(value, str) and value:
                            status_updated = False
                            for next_cell in cells[index:]:
                                for text_element in next_cell.iter(f"{HP}t"):
                                    if (
                                        text_element.text
                                        and "희망 자격" in text_element.text
                                    ):
                                        text_element.text = re.sub(
                                            r"희망\s*자격\s*:\s*[^)]*",
                                            f"희망 자격 : {value}",
                                            text_element.text,
                                        )
                                        marked = True
                                        status_updated = True
                                        break
                                if status_updated:
                                    break
                        if marked:
                            changed.append(label)
        self._dirty = self._dirty or bool(changed)
        return tuple(changed)

    def replace(self, xml_source: str | Path | bytes) -> None:
        if isinstance(xml_source, bytes):
            xml_data = xml_source
        else:
            xml_path = Path(xml_source)
            if not xml_path.is_file():
                raise FileNotFoundError(xml_path)
            if xml_path.stat().st_size > MAX_UNCOMPRESSED_BYTES:
                raise HwpxError("section XML exceeds the size limit")
            xml_data = xml_path.read_bytes()
        self._root = _parse_section(xml_data)
        self._original_data = xml_data
        self._dirty = False

    def to_bytes(self) -> bytes:
        if not self._dirty:
            return self._original_data
        return ET.tostring(self._root, encoding="utf-8", xml_declaration=True)


__all__ = [
    "HP_NAMESPACE",
    "HS_NAMESPACE",
    "HwpxSection",
]
