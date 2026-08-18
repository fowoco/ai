"""Record-aware HWP 5.0 editor without Hancom Office or COM.

The editor modifies ``DocInfo``, ``BinData`` and ``BodyText/SectionN`` records
directly.  It supports plain text, substring replacement, checkboxes, raster
photos/signatures, and a complete CFB rebuild when a stream changes size.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import struct
import tempfile
import zlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

try:
    import olefile
except ImportError:  # pragma: no cover - optional runtime dependency
    olefile = None


HWP5_SIGNATURE = b"HWP Document File"
HWPTAG_PARA_HEADER = 66
HWPTAG_PARA_TEXT = 67
HWPTAG_PARA_CHAR_SHAPE = 68
HWPTAG_PARA_LINE_SEG = 69
HWPTAG_LIST_HEADER = 72
HWPTAG_ID_MAPPINGS = 17
HWPTAG_BIN_DATA = 18
HWPTAG_CTRL_HEADER = 71
HWPTAG_SHAPE_COMPONENT = 76
HWPTAG_SHAPE_COMPONENT_PICTURE = 85


class Hwp5Error(Exception):
    """Base error raised by the binary editor."""


class UnsupportedHwpError(Hwp5Error):
    """The file uses an HWP feature this small editor cannot safely handle."""


class FieldNotFoundError(Hwp5Error):
    """A requested anchor or target paragraph was not found."""


class StreamCapacityError(Hwp5Error):
    """A modified stream no longer fits in its original OLE allocation."""


@dataclass(frozen=True)
class HwpRecord:
    tag_id: int
    level: int
    payload: bytes

    def to_bytes(self) -> bytes:
        size = len(self.payload)
        if size < 0xFFF:
            header = self.tag_id | (self.level << 10) | (size << 20)
            return struct.pack("<I", header) + self.payload
        header = self.tag_id | (self.level << 10) | (0xFFF << 20)
        return struct.pack("<II", header, size) + self.payload


@dataclass(frozen=True)
class TableCell:
    column: int
    row: int
    column_span: int
    row_span: int


@dataclass(frozen=True)
class EmbeddedImage:
    bindata_id: int
    extension: str
    stream_name: str
    stored_size: int


@dataclass(frozen=True)
class Paragraph:
    index: int
    record_index: int
    level: int
    text: str
    has_text_record: bool
    cell: TableCell | None = None

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


@dataclass(frozen=True)
class ParagraphSelector:
    """Locate a paragraph either by index or relative to a text anchor."""

    index: int | None = None
    anchor_text: str | None = None
    paragraph_offset: int = 0
    occurrence: int = 0
    require_empty: bool = True
    cell_row_offset: int | None = None
    cell_column_offset: int = 0

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> ParagraphSelector:
        return cls(
            index=_optional_int(value.get("paragraph_index")),
            anchor_text=_optional_str(value.get("anchor_text")),
            paragraph_offset=int(
                value.get(
                    "paragraph_offset",
                    value.get("target_empty_paragraph_offset", 0),
                )
            ),
            occurrence=int(value.get("occurrence", 0)),
            require_empty=bool(value.get("require_empty", True)),
            cell_row_offset=_optional_int(value.get("cell_row_offset")),
            cell_column_offset=int(value.get("cell_column_offset", 0)),
        )


def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def parse_records(data: bytes) -> list[HwpRecord]:
    records: list[HwpRecord] = []
    offset = 0
    while offset < len(data):
        if len(data) - offset < 4:
            raise Hwp5Error(f"truncated record header at offset {offset}")
        header = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        tag_id = header & 0x3FF
        level = (header >> 10) & 0x3FF
        size = (header >> 20) & 0xFFF
        if size == 0xFFF:
            if len(data) - offset < 4:
                raise Hwp5Error(f"truncated extended record size at offset {offset}")
            size = struct.unpack_from("<I", data, offset)[0]
            offset += 4
        end = offset + size
        if end > len(data):
            raise Hwp5Error(
                f"record payload at offset {offset} exceeds section size "
                f"({size} bytes requested, {len(data) - offset} available)"
            )
        records.append(HwpRecord(tag_id, level, data[offset:end]))
        offset = end
    return records


def serialize_records(records: Iterable[HwpRecord]) -> bytes:
    return b"".join(record.to_bytes() for record in records)


def decode_para_text(payload: bytes) -> str:
    """Return searchable text from a PARA_TEXT payload.

    HWP inline controls occupy more than one UTF-16 code unit.  For anchor
    matching we only need their textual surroundings, so control characters
    and their non-text parameters are discarded conservatively.
    """

    if len(payload) % 2:
        raise Hwp5Error("PARA_TEXT payload has an odd byte length")

    units = struct.unpack(f"<{len(payload) // 2}H", payload) if payload else ()
    chars: list[str] = []
    index = 0
    while index < len(units):
        code = units[index]
        if code == 13:
            index += 1
            continue
        if code < 32:
            # HWP's extended controls occupy 8 UTF-16 units.  A few controls
            # are one-unit characters; skipping 8 only when available avoids
            # leaking control identifiers into anchor text.
            index += 8 if code not in (0, 10, 13) and index + 8 <= len(units) else 1
            continue
        chars.append(chr(code))
        index += 1
    return "".join(chars)


def paragraphs_from_records(records: Sequence[HwpRecord]) -> list[Paragraph]:
    paragraphs: list[Paragraph] = []
    current_cell: TableCell | None = None
    current_cell_level: int | None = None
    for record_index, record in enumerate(records):
        if record.tag_id == HWPTAG_LIST_HEADER and len(record.payload) >= 38:
            column, row, column_span, row_span = struct.unpack_from("<4H", record.payload, 8)
            current_cell = TableCell(column, row, column_span, row_span)
            current_cell_level = record.level
            continue
        if record.tag_id != HWPTAG_PARA_HEADER:
            continue
        if current_cell_level is not None and record.level < current_cell_level:
            current_cell = None
            current_cell_level = None
        texts: list[str] = []
        has_text_record = False
        next_index = record_index + 1
        while next_index < len(records) and records[next_index].tag_id != HWPTAG_PARA_HEADER:
            child = records[next_index]
            if child.tag_id == HWPTAG_PARA_TEXT and child.level > record.level:
                has_text_record = True
                texts.append(decode_para_text(child.payload))
            next_index += 1
        paragraphs.append(
            Paragraph(
                index=len(paragraphs),
                record_index=record_index,
                level=record.level,
                text="".join(texts),
                has_text_record=has_text_record,
                cell=current_cell,
            )
        )
    return paragraphs


def _normalise_anchor(value: str) -> str:
    return "".join(value.split()).casefold()


def _plain_text_payload(text: str) -> bytes:
    if "\r" in text or "\n" in text:
        raise ValueError("paragraph text must not contain CR or LF")
    return (text + "\r").encode("utf-16-le")


def _is_plain_para_payload(payload: bytes) -> bool:
    if len(payload) % 2:
        return False
    units = struct.unpack(f"<{len(payload) // 2}H", payload) if payload else ()
    return all(code >= 32 or code == 13 for code in units)


def _is_text_with_line_breaks_payload(payload: bytes) -> bool:
    """Allow a soft line break while rejecting opaque inline HWP controls."""

    if len(payload) % 2:
        return False
    units = struct.unpack(f"<{len(payload) // 2}H", payload) if payload else ()
    return all(code >= 32 or code in (10, 13) for code in units)


def _set_header_character_count(payload: bytes, count: int) -> bytes:
    if len(payload) < 4:
        raise Hwp5Error("PARA_HEADER payload is too short")
    old_count = struct.unpack_from("<I", payload)[0]
    # Bit 31 is a paragraph property in observed HWP 5 documents.  The lower
    # 31 bits contain the character count, including the terminating CR.
    new_count = (old_count & 0x80000000) | count
    return struct.pack("<I", new_count) + payload[4:]


def _set_header_control_mask(payload: bytes, control_code: int) -> bytes:
    if len(payload) < 8:
        raise Hwp5Error("PARA_HEADER payload is too short for a control mask")
    mask = struct.unpack_from("<I", payload, 4)[0] | (1 << control_code)
    return payload[:4] + struct.pack("<I", mask) + payload[8:]


def _utf16_units(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def _adjust_char_shape_positions(
    records: list[HwpRecord],
    first_child: int,
    last_child: int,
    start: int,
    end: int,
    replacement_end: int,
) -> None:
    """Move character-style run offsets after a plain-text replacement."""

    delta = replacement_end - end
    for index in range(first_child, last_child):
        record = records[index]
        if record.tag_id != HWPTAG_PARA_CHAR_SHAPE:
            continue
        if len(record.payload) % 8:
            raise UnsupportedHwpError("PARA_CHAR_SHAPE has an invalid payload size")
        runs = [
            struct.unpack_from("<II", record.payload, offset)
            for offset in range(0, len(record.payload), 8)
        ]
        adjusted: list[tuple[int, int]] = []
        for position, shape_id in runs:
            if position <= start:
                new_position = position
            elif position < end:
                old_width = end - start
                new_width = replacement_end - start
                new_position = start + round((position - start) * new_width / old_width)
            else:
                new_position = position + delta
            adjusted.append((new_position, shape_id))
        payload = b"".join(struct.pack("<II", *run) for run in adjusted)
        records[index] = HwpRecord(record.tag_id, record.level, payload)


def _adjust_line_segment_positions(
    records: list[HwpRecord],
    first_child: int,
    last_child: int,
    start: int,
    end: int,
    replacement_end: int,
) -> None:
    """Move cached line-start offsets after a text replacement."""

    if end == start:
        return
    delta = replacement_end - end
    old_width = end - start
    new_width = replacement_end - start
    for index in range(first_child, last_child):
        record = records[index]
        if record.tag_id != HWPTAG_PARA_LINE_SEG:
            continue
        if len(record.payload) % 36:
            raise UnsupportedHwpError("PARA_LINE_SEG has an invalid payload size")
        payload = bytearray(record.payload)
        for offset in range(0, len(payload), 36):
            position = struct.unpack_from("<I", payload, offset)[0]
            if position <= start:
                adjusted = position
            elif position < end:
                adjusted = start + round((position - start) * new_width / old_width)
            else:
                adjusted = position + delta
            struct.pack_into("<I", payload, offset, adjusted)
        records[index] = HwpRecord(record.tag_id, record.level, bytes(payload))


def _encode_chid(value: str) -> bytes:
    if len(value) != 4 or not value.isascii():
        raise ValueError("HWP control IDs must contain four ASCII characters")
    return value[::-1].encode("ascii")


def _extended_control_payload(chid: str) -> bytes:
    return b"\x0b\x00" + _encode_chid(chid) + (b"\x00" * 8) + b"\x0b\x00"


def _identity_matrix() -> bytes:
    # HWP matrix order: a, c, e, b, d, f.
    return struct.pack("<6d", 1.0, 0.0, 0.0, 0.0, 1.0, 0.0)


def _mm_to_hwpunit(value: float) -> int:
    return max(1, round(value * 7200 / 25.4))


def _best_raw_deflate(data: bytes) -> bytes:
    candidates: list[bytes] = []
    strategies = (zlib.Z_DEFAULT_STRATEGY, zlib.Z_FILTERED, zlib.Z_HUFFMAN_ONLY)
    for level in (9, 8, 7, 6, 5, 4, 3, 2, 1):
        for strategy in strategies:
            compressor = zlib.compressobj(level, zlib.DEFLATED, -15, 9, strategy)
            compressed = compressor.compress(data) + compressor.flush()
            candidates.append(compressed)
    return min(candidates, key=len)


def _compress_raw_deflate(data: bytes, capacity: int) -> bytes:
    compressed = _best_raw_deflate(data)
    if len(compressed) > capacity:
        raise StreamCapacityError(
            f"modified DEFLATE stream needs {len(compressed)} bytes; "
            f"the OLE stream has {capacity} bytes"
        )
    padded = compressed + (b"\x00" * (capacity - len(compressed)))
    if zlib.decompress(padded, -15) != data:
        raise Hwp5Error("internal DEFLATE verification failed")
    return padded


class Hwp5BinaryDocument:
    """In-memory editor for unencrypted HWP 5.0 body text streams."""

    def __init__(self, source_path: os.PathLike[str] | str):
        if olefile is None:
            raise ImportError("olefile is required (pip install olefile)")
        self.source_path = Path(source_path).resolve()
        if not self.source_path.is_file():
            raise FileNotFoundError(self.source_path)

        with olefile.OleFileIO(str(self.source_path)) as ole:
            if not ole.exists("FileHeader"):
                raise UnsupportedHwpError("not an HWP 5.0 OLE document: FileHeader is missing")
            file_header = ole.openstream("FileHeader").read()
            if not file_header.startswith(HWP5_SIGNATURE):
                raise UnsupportedHwpError("FileHeader does not contain the HWP 5.0 signature")
            if len(file_header) < 40:
                raise UnsupportedHwpError("truncated HWP FileHeader")
            flags = struct.unpack_from("<I", file_header, 36)[0]
            self.file_version = tuple(reversed(file_header[32:36]))
            self.compressed = bool(flags & 0x01)
            if flags & 0x02:
                raise UnsupportedHwpError("password-encrypted HWP files are not supported")
            if flags & 0x04:
                raise UnsupportedHwpError("distribution HWP files are not supported")

            section_names = sorted(
                "/".join(entry)
                for entry in ole.listdir(streams=True)
                if len(entry) == 2 and entry[0] == "BodyText" and entry[1].startswith("Section")
            )
            if not section_names:
                raise UnsupportedHwpError("the document has no BodyText/SectionN stream")

            self._container_streams = {
                "/".join(entry): ole.openstream(entry).read()
                for entry in ole.listdir(streams=True, storages=False)
            }
            self._original_streams = {name: ole.openstream(name).read() for name in section_names}
            self._original_doc_info = ole.openstream("DocInfo").read()

        self._section_names = section_names
        self._records = {}
        for section_index, name in enumerate(section_names):
            stream = self._original_streams[name]
            body = zlib.decompress(stream, -15) if self.compressed else stream
            self._records[section_index] = parse_records(body)
        self._modified_sections: set[int] = set()
        doc_info = (
            zlib.decompress(self._original_doc_info, -15)
            if self.compressed
            else self._original_doc_info
        )
        self._doc_info_records = parse_records(doc_info)
        self._doc_info_modified = False
        self._stream_replacements: dict[str, bytes] = {}
        self._stream_additions: dict[str, bytes] = {}

    @property
    def sha256(self) -> str:
        digest = hashlib.sha256()
        with self.source_path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @property
    def section_count(self) -> int:
        return len(self._section_names)

    def paragraphs(self, section: int = 0) -> list[Paragraph]:
        return paragraphs_from_records(self._get_records(section))

    def find_paragraphs(self, text: str, section: int = 0) -> list[Paragraph]:
        needle = _normalise_anchor(text)
        if not needle:
            raise ValueError("anchor text must not be empty")
        return [
            paragraph
            for paragraph in self.paragraphs(section)
            if needle in _normalise_anchor(paragraph.text)
        ]

    def resolve_selector(self, selector: ParagraphSelector, section: int = 0) -> Paragraph:
        paragraphs = self.paragraphs(section)
        if selector.index is not None:
            target_index = selector.index
        elif selector.anchor_text:
            matches = self.find_paragraphs(selector.anchor_text, section)
            if not matches:
                raise FieldNotFoundError(f"anchor text not found: {selector.anchor_text!r}")
            if selector.occurrence < 0 or selector.occurrence >= len(matches):
                raise FieldNotFoundError(
                    f"anchor occurrence {selector.occurrence} is out of range "
                    f"for {selector.anchor_text!r} ({len(matches)} match(es))"
                )
            anchor = matches[selector.occurrence]
            if selector.cell_row_offset is not None:
                if anchor.cell is None:
                    raise FieldNotFoundError(
                        f"anchor is not in a parsed table cell: {selector.anchor_text!r}"
                    )
                target_column = anchor.cell.column + selector.cell_column_offset
                target_row = anchor.cell.row + selector.cell_row_offset
                cell_matches = [
                    paragraph
                    for paragraph in paragraphs
                    if paragraph.cell is not None
                    and paragraph.cell.column == target_column
                    and paragraph.cell.row == target_row
                ]
                if not cell_matches:
                    raise FieldNotFoundError(
                        f"target table cell was not found at column {target_column}, "
                        f"row {target_row}"
                    )
                target_index = cell_matches[0].index + selector.paragraph_offset
            else:
                target_index = anchor.index + selector.paragraph_offset
        else:
            raise ValueError("selector needs paragraph_index or anchor_text")

        if target_index < 0 or target_index >= len(paragraphs):
            raise FieldNotFoundError(f"target paragraph index is out of range: {target_index}")
        target = paragraphs[target_index]
        if selector.require_empty and not target.is_empty:
            raise Hwp5Error(f"target paragraph {target.index} is not empty: {target.text!r}")
        return target

    def set_text(
        self,
        selector: ParagraphSelector | Mapping[str, object],
        text: str,
        section: int = 0,
    ) -> Paragraph:
        if isinstance(selector, Mapping):
            selector = ParagraphSelector.from_mapping(selector)
        target = self.resolve_selector(selector, section)
        records = self._get_records(section)
        header = records[target.record_index]
        payload = _plain_text_payload(text)

        next_header_index = target.record_index + 1
        while (
            next_header_index < len(records)
            and records[next_header_index].tag_id != HWPTAG_PARA_HEADER
        ):
            next_header_index += 1

        text_indices = [
            index
            for index in range(target.record_index + 1, next_header_index)
            if records[index].tag_id == HWPTAG_PARA_TEXT and records[index].level > header.level
        ]
        if len(text_indices) > 1:
            raise UnsupportedHwpError(f"paragraph {target.index} has multiple PARA_TEXT records")
        if text_indices:
            text_index = text_indices[0]
            old_text_record = records[text_index]
            if not _is_plain_para_payload(old_text_record.payload):
                raise UnsupportedHwpError(f"paragraph {target.index} contains inline controls")
            old_units = max(0, len(old_text_record.payload) // 2 - 1)
            new_units = max(0, len(payload) // 2 - 1)
            _adjust_char_shape_positions(
                records,
                target.record_index + 1,
                next_header_index,
                0,
                old_units,
                new_units,
            )
            _adjust_line_segment_positions(
                records,
                target.record_index + 1,
                next_header_index,
                0,
                old_units,
                new_units,
            )
            records[text_index] = HwpRecord(HWPTAG_PARA_TEXT, old_text_record.level, payload)
        else:
            records.insert(
                target.record_index + 1,
                HwpRecord(HWPTAG_PARA_TEXT, header.level + 1, payload),
            )

        records[target.record_index] = HwpRecord(
            header.tag_id,
            header.level,
            _set_header_character_count(header.payload, len(payload) // 2),
        )
        self._modified_sections.add(section)

        changed = self.paragraphs(section)[target.index]
        if changed.text != text:
            raise Hwp5Error(
                f"paragraph verification failed: expected {text!r}, got {changed.text!r}"
            )
        return changed

    def replace_text(
        self,
        selector: ParagraphSelector | Mapping[str, object],
        old: str,
        new: str,
        *,
        occurrence: int = 0,
        section: int = 0,
    ) -> Paragraph:
        """Replace one substring in a plain paragraph and preserve style runs."""

        if not old:
            raise ValueError("old text must not be empty")
        if "\r" in new or "\n" in new:
            raise ValueError("replacement text must not contain CR or LF")
        if isinstance(selector, Mapping):
            selector = ParagraphSelector.from_mapping(selector)
        target = self.resolve_selector(selector, section)
        records = self._get_records(section)
        header = records[target.record_index]
        next_header_index = target.record_index + 1
        while (
            next_header_index < len(records)
            and records[next_header_index].tag_id != HWPTAG_PARA_HEADER
        ):
            next_header_index += 1
        text_indices = [
            index
            for index in range(target.record_index + 1, next_header_index)
            if records[index].tag_id == HWPTAG_PARA_TEXT and records[index].level > header.level
        ]
        if len(text_indices) != 1:
            raise UnsupportedHwpError(
                f"paragraph {target.index} must have exactly one PARA_TEXT record"
            )
        text_index = text_indices[0]
        text_record = records[text_index]
        if not _is_text_with_line_breaks_payload(text_record.payload):
            raise UnsupportedHwpError(f"paragraph {target.index} contains inline controls")
        source_text = text_record.payload.decode("utf-16-le")
        if not source_text.endswith("\r"):
            raise Hwp5Error(f"paragraph {target.index} has no terminating CR")
        source_text = source_text[:-1]
        starts = [match.start() for match in re.finditer(re.escape(old), source_text)]
        if occurrence < 0 or occurrence >= len(starts):
            raise FieldNotFoundError(
                f"text occurrence {occurrence} is out of range for {old!r} "
                f"in paragraph {target.index}"
            )
        start_chars = starts[occurrence]
        end_chars = start_chars + len(old)
        result = source_text[:start_chars] + new + source_text[end_chars:]
        start_units = _utf16_units(source_text[:start_chars])
        end_units = _utf16_units(source_text[:end_chars])
        replacement_end = start_units + _utf16_units(new)
        _adjust_char_shape_positions(
            records,
            target.record_index + 1,
            next_header_index,
            start_units,
            end_units,
            replacement_end,
        )
        _adjust_line_segment_positions(
            records,
            target.record_index + 1,
            next_header_index,
            start_units,
            end_units,
            replacement_end,
        )
        payload = (result + "\r").encode("utf-16-le")
        records[text_index] = HwpRecord(text_record.tag_id, text_record.level, payload)
        records[target.record_index] = HwpRecord(
            header.tag_id,
            header.level,
            _set_header_character_count(header.payload, len(payload) // 2),
        )
        self._modified_sections.add(section)
        changed = self.paragraphs(section)[target.index]
        if changed.text != result.replace("\n", ""):
            raise Hwp5Error(
                f"paragraph verification failed: expected {result!r}, got {changed.text!r}"
            )
        return changed

    def set_checkbox(
        self,
        selector: ParagraphSelector | Mapping[str, object],
        *,
        checked: bool = True,
        occurrence: int = 0,
        section: int = 0,
    ) -> Paragraph:
        """Check or clear a square/bracket checkbox in a plain paragraph."""

        if isinstance(selector, Mapping):
            selector = ParagraphSelector.from_mapping(selector)
        target = self.resolve_selector(selector, section)
        candidates = list(re.finditer(r"\[[ \u00a0√✓xX]*\]|[□☐☑]", target.text))
        if occurrence < 0 or occurrence >= len(candidates):
            raise FieldNotFoundError(
                f"checkbox occurrence {occurrence} is out of range in paragraph {target.index}"
            )
        match = candidates[occurrence]
        token = match.group(0)
        token_occurrence = sum(
            candidate.group(0) == token for candidate in candidates[:occurrence]
        )
        if token in {"□", "☐", "☑"}:
            replacement = "☑" if checked else "☐"
        else:
            inner_width = len(token) - 2
            marker = "√" if checked else ""
            replacement = "[" + marker + (" " * (inner_width - len(marker))) + "]"
        return self.replace_text(
            ParagraphSelector(index=target.index, require_empty=False),
            token,
            replacement,
            occurrence=token_occurrence,
            section=section,
        )

    def apply_fields(
        self,
        fields: Mapping[str, Mapping[str, object]],
        values: Mapping[str, str] | None = None,
        images: Mapping[str, os.PathLike[str] | str] | None = None,
    ) -> list[str]:
        changed: list[str] = []
        for field_name, value in (values or {}).items():
            if field_name not in fields:
                raise FieldNotFoundError(f"field is not present in the template map: {field_name}")
            field = fields[field_name]
            field_type = str(field.get("type", "text"))
            if field_type == "checkbox":
                normalised = str(value).strip().casefold()
                if normalised not in {"1", "0", "true", "false", "yes", "no", "on", "off"}:
                    raise ValueError(
                        f"checkbox field {field_name!r} expects true/false, got {value!r}"
                    )
                checked = normalised in {"1", "true", "yes", "on"}
                self.set_checkbox(
                    field,
                    checked=checked,
                    occurrence=int(field.get("checkbox_occurrence", 0)),
                    section=int(field.get("section", 0)),
                )
                changed.append(field_name)
                continue
            if field_type != "text":
                raise Hwp5Error(f"field {field_name!r} is {field_type!r}; provide it as an image")
            section = int(field.get("section", 0))
            if "replace_text" in field:
                replacement = str(field.get("replacement_format", "{value}")).format(value=value)
                self.replace_text(
                    field,
                    str(field["replace_text"]),
                    replacement,
                    occurrence=int(field.get("replace_occurrence", 0)),
                    section=section,
                )
            else:
                self.set_text(field, str(value), section)
            changed.append(field_name)
        for field_name, image_path in (images or {}).items():
            if field_name not in fields:
                raise FieldNotFoundError(f"field is not present in the template map: {field_name}")
            field = fields[field_name]
            field_type = str(field.get("type", "image"))
            if field_type not in {"image", "photo", "signature"}:
                raise Hwp5Error(f"field {field_name!r} is {field_type!r}; provide it as text")
            self.insert_image(
                field,
                image_path,
                width_mm=float(field["width_mm"]),
                height_mm=float(field["height_mm"]),
                kind=field_type,
                section=int(field.get("section", 0)),
            )
            changed.append(field_name)
        return changed

    def embedded_images(self) -> list[EmbeddedImage]:
        images: list[EmbeddedImage] = []
        for record in self._doc_info_records:
            if record.tag_id != HWPTAG_BIN_DATA or len(record.payload) < 6:
                continue
            flags, bindata_id, ext_len = struct.unpack_from("<3H", record.payload)
            if (flags & 0x0F) != 1:
                continue
            end = 6 + ext_len * 2
            if end > len(record.payload):
                raise Hwp5Error("truncated embedded BinData record")
            extension = record.payload[6:end].decode("utf-16-le")
            prefix = f"BinData/BIN{bindata_id:04X}."
            stream_name = next(
                (name for name in self._container_streams if name.startswith(prefix)),
                f"{prefix}{extension}",
            )
            stored = self._stream_replacements.get(
                stream_name,
                self._stream_additions.get(
                    stream_name, self._container_streams.get(stream_name, b"")
                ),
            )
            images.append(EmbeddedImage(bindata_id, extension, stream_name, len(stored)))
        return images

    def insert_image(
        self,
        selector: ParagraphSelector | Mapping[str, object],
        image_path: os.PathLike[str] | str,
        *,
        width_mm: float,
        height_mm: float,
        kind: str = "image",
        section: int = 0,
    ) -> EmbeddedImage:
        from .image_processing import prepare_image

        if isinstance(selector, Mapping):
            selector = ParagraphSelector.from_mapping(selector)
        target = self.resolve_selector(selector, section)
        if target.has_text_record:
            raise Hwp5Error(
                f"image target paragraph {target.index} already has a text/control record"
            )
        prepared = prepare_image(
            image_path,
            kind=kind,
            target_width_mm=width_mm,
            target_height_mm=height_mm,
        )
        embedded = self._add_bindata(prepared.data, prepared.extension)
        self._insert_picture_records(
            target,
            section,
            embedded.bindata_id,
            _mm_to_hwpunit(width_mm),
            _mm_to_hwpunit(height_mm),
        )
        return embedded

    def replace_image(
        self,
        bindata_id: int,
        image_path: os.PathLike[str] | str,
        *,
        width_mm: float,
        height_mm: float,
        kind: str = "image",
    ) -> EmbeddedImage:
        from .image_processing import prepare_image

        image = next(
            (item for item in self.embedded_images() if item.bindata_id == bindata_id),
            None,
        )
        if image is None:
            raise FieldNotFoundError(f"embedded image ID was not found: {bindata_id}")
        prepared = prepare_image(
            image_path,
            kind=kind,
            target_width_mm=width_mm,
            target_height_mm=height_mm,
            extension=image.extension,
        )
        stored = _best_raw_deflate(prepared.data) if self.compressed else prepared.data
        if image.stream_name in self._stream_additions:
            self._stream_additions[image.stream_name] = stored
        else:
            self._stream_replacements[image.stream_name] = stored
        return EmbeddedImage(bindata_id, image.extension, image.stream_name, len(stored))

    def _add_bindata(self, image_data: bytes, extension: str) -> EmbeddedImage:
        existing = self.embedded_images()
        bindata_id = max((image.bindata_id for image in existing), default=0) + 1
        stream_name = f"BinData/BIN{bindata_id:04X}.{extension}"
        if stream_name in self._container_streams or stream_name in self._stream_additions:
            raise Hwp5Error(f"generated BinData stream already exists: {stream_name}")

        id_mapping_index = next(
            (
                index
                for index, record in enumerate(self._doc_info_records)
                if record.tag_id == HWPTAG_ID_MAPPINGS
            ),
            None,
        )
        if id_mapping_index is None:
            raise UnsupportedHwpError("DocInfo has no ID_MAPPINGS record")
        mapping = self._doc_info_records[id_mapping_index]
        if len(mapping.payload) < 4:
            raise Hwp5Error("ID_MAPPINGS payload is too short")
        count = struct.unpack_from("<I", mapping.payload)[0]
        mapping_payload = struct.pack("<I", count + 1) + mapping.payload[4:]
        self._doc_info_records[id_mapping_index] = HwpRecord(
            mapping.tag_id, mapping.level, mapping_payload
        )

        extension_bytes = extension.encode("utf-16-le")
        bindata_payload = struct.pack("<3H", 0x0001, bindata_id, len(extension))
        bindata_payload += extension_bytes
        insert_index = id_mapping_index + 1
        while (
            insert_index < len(self._doc_info_records)
            and self._doc_info_records[insert_index].tag_id == HWPTAG_BIN_DATA
        ):
            insert_index += 1
        self._doc_info_records.insert(insert_index, HwpRecord(HWPTAG_BIN_DATA, 1, bindata_payload))
        self._doc_info_modified = True

        stored = _best_raw_deflate(image_data) if self.compressed else image_data
        self._stream_additions[stream_name] = stored
        return EmbeddedImage(bindata_id, extension, stream_name, len(stored))

    def _insert_picture_records(
        self,
        target: Paragraph,
        section: int,
        bindata_id: int,
        width: int,
        height: int,
    ) -> None:
        records = self._get_records(section)
        header = records[target.record_index]
        control_text = _extended_control_payload("gso ") + "\r".encode("utf-16-le")
        records.insert(
            target.record_index + 1,
            HwpRecord(HWPTAG_PARA_TEXT, header.level + 1, control_text),
        )
        header_payload = _set_header_character_count(header.payload, len(control_text) // 2)
        header_payload = _set_header_control_mask(header_payload, 11)
        records[target.record_index] = HwpRecord(header.tag_id, header.level, header_payload)

        boundary = target.record_index + 2
        while boundary < len(records) and records[boundary].level > header.level:
            boundary += 1

        seed = self.sha256.encode("ascii") + struct.pack("<III", section, target.index, bindata_id)
        instance_id = int.from_bytes(hashlib.sha256(seed).digest()[:4], "little") or 1
        common_flags = 0x042A6311  # inline picture; line spacing follows object
        control_payload = _encode_chid("gso ") + struct.pack(
            "<Iiiii2h4hIhH",
            common_flags,
            0,
            0,
            width,
            height,
            0,
            0,
            0,
            0,
            0,
            0,
            instance_id,
            0,
            0,
        )

        matrices = _identity_matrix() * 3  # translation, scaler, rotator
        shape_payload = (
            _encode_chid("$pic")
            + _encode_chid("$pic")
            + struct.pack(
                "<iiHHiiiiIHiiH",
                0,
                0,
                0,
                1,
                width,
                height,
                width,
                height,
                0x20000000,
                0,
                width // 2,
                height // 2,
                1,
            )
            + matrices
        )

        picture_payload = struct.pack(
            "<IiI8i4i4hbbBH",
            0,
            0,
            0,
            0,
            0,
            width,
            0,
            width,
            height,
            0,
            height,
            0,
            0,
            width,
            height,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            bindata_id,
        )
        if self.file_version >= (5, 0, 2, 2):
            picture_payload += b"\x00"
        if self.file_version >= (5, 0, 2, 5):
            picture_payload += struct.pack("<I", (instance_id + 1) & 0xFFFFFFFF)
        if self.file_version >= (5, 0, 3, 4):
            picture_payload += struct.pack("<I", 0)

        records[boundary:boundary] = [
            HwpRecord(HWPTAG_CTRL_HEADER, header.level + 1, control_payload),
            HwpRecord(HWPTAG_SHAPE_COMPONENT, header.level + 2, shape_payload),
            HwpRecord(
                HWPTAG_SHAPE_COMPONENT_PICTURE,
                header.level + 3,
                picture_payload,
            ),
        ]
        self._modified_sections.add(section)

    def save(self, destination_path: os.PathLike[str] | str) -> Path:
        destination = Path(destination_path).resolve()
        if destination == self.source_path:
            raise ValueError("destination must differ from the source HWP")
        destination.parent.mkdir(parents=True, exist_ok=True)

        body_streams: dict[str, bytes] = {}
        requires_rebuild = bool(
            self._doc_info_modified or self._stream_replacements or self._stream_additions
        )
        for section in self._modified_sections:
            name = self._section_names[section]
            body = serialize_records(self._records[section])
            original = self._original_streams[name]
            if self.compressed:
                compressed = _best_raw_deflate(body)
                body_streams[name] = compressed
                if len(compressed) > len(original):
                    requires_rebuild = True
            else:
                if len(body) != len(original):
                    requires_rebuild = True
                body_streams[name] = body

        replacements = dict(self._stream_replacements)
        replacements.update(body_streams)
        if self._doc_info_modified:
            doc_info = serialize_records(self._doc_info_records)
            replacements["DocInfo"] = _best_raw_deflate(doc_info) if self.compressed else doc_info

        if requires_rebuild:
            from .compound_file import rebuild_cfb

            rebuild_cfb(
                self.source_path,
                destination,
                replacements=replacements,
                additions=self._stream_additions,
            )
            self._validate_saved_document(destination)
            return destination

        fixed_replacements = {}
        for name, data in replacements.items():
            original_size = len(self._original_streams[name])
            if self.compressed and name.startswith("BodyText/"):
                fixed_replacements[name] = data + b"\x00" * (original_size - len(data))
            elif len(data) == original_size:
                fixed_replacements[name] = data
            else:
                raise StreamCapacityError(
                    f"stream {name} changed size without enabling a CFB rebuild"
                )

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix="hwp5-edit-", suffix=".hwp", dir=destination.parent, delete=False
            ) as temporary:
                temporary_path = Path(temporary.name)
            shutil.copy2(self.source_path, temporary_path)
            with olefile.OleFileIO(str(temporary_path), write_mode=True) as ole:
                for name, data in fixed_replacements.items():
                    ole.write_stream(name, data)

            # Reopen and validate every modified stream before publishing it.
            self._validate_saved_document(temporary_path)
            os.replace(temporary_path, destination)
            temporary_path = None
            return destination
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

    def _get_records(self, section: int) -> list[HwpRecord]:
        try:
            return self._records[section]
        except KeyError as exc:
            raise IndexError(f"section index is out of range: {section}") from exc

    def _validate_saved_document(self, path: Path) -> None:
        with olefile.OleFileIO(str(path)) as ole:
            for section in self._modified_sections:
                name = self._section_names[section]
                stored = ole.openstream(name).read()
                body = zlib.decompress(stored, -15) if self.compressed else stored
                reparsed = parse_records(body)
                if serialize_records(reparsed) != serialize_records(self._records[section]):
                    raise Hwp5Error(f"saved stream verification failed: {name}")
            if self._doc_info_modified:
                stored = ole.openstream("DocInfo").read()
                doc_info = zlib.decompress(stored, -15) if self.compressed else stored
                if parse_records(doc_info) != self._doc_info_records:
                    raise Hwp5Error("saved DocInfo verification failed")
            for name, expected in self._stream_replacements.items():
                if ole.openstream(name).read() != expected:
                    raise Hwp5Error(f"saved stream replacement verification failed: {name}")
            for name, expected in self._stream_additions.items():
                if not ole.exists(name) or ole.openstream(name).read() != expected:
                    raise Hwp5Error(f"saved added stream verification failed: {name}")


# Backwards-compatible extraction helper retained for existing experiments.
def extract_streams(hwp_path: str, outdir: str) -> list[tuple[str, bytes]]:
    if olefile is None:
        raise ImportError("olefile is required (pip install olefile)")
    output = Path(outdir)
    output.mkdir(parents=True, exist_ok=True)
    streams: list[tuple[str, bytes]] = []
    with olefile.OleFileIO(hwp_path) as ole:
        for entry in ole.listdir(streams=True):
            data = ole.openstream(entry).read()
            name = "/".join(entry)
            streams.append((name, data))
            safe_name = name.replace("/", "_2f")
            (output / safe_name).write_bytes(data)
    return streams


__all__ = [
    "EmbeddedImage",
    "FieldNotFoundError",
    "Hwp5BinaryDocument",
    "Hwp5Error",
    "HwpRecord",
    "Paragraph",
    "ParagraphSelector",
    "StreamCapacityError",
    "TableCell",
    "UnsupportedHwpError",
    "decode_para_text",
    "extract_streams",
    "paragraphs_from_records",
    "parse_records",
    "serialize_records",
]
