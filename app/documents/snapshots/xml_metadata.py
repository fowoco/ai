"""Embed and read an opaque document snapshot reference in section XML."""

from __future__ import annotations

import re
from dataclasses import dataclass

PROCESSING_INSTRUCTION = re.compile(rb"<\?fowoco\s+([^?]+)\?>")
ATTRIBUTE = re.compile(rb'([a-z][a-z0-9-]*)="([^"]*)"')
XML_DECLARATION = re.compile(rb"^\s*<\?xml[^?]*\?>")


@dataclass(frozen=True)
class XmlSnapshotMetadata:
    snapshot_ref: str
    section: int


def add_snapshot_metadata(
    xml_data: bytes,
    *,
    snapshot_ref: str,
    section: int,
) -> bytes:
    clean_xml = strip_snapshot_metadata(xml_data)
    instruction = (
        f'<?fowoco snapshot-ref="{snapshot_ref}" section="{section}"?>'.encode()
    )
    declaration = XML_DECLARATION.match(clean_xml)
    if declaration is None:
        return instruction + clean_xml
    end = declaration.end()
    return clean_xml[:end] + instruction + clean_xml[end:]


def read_snapshot_metadata(xml_data: bytes) -> XmlSnapshotMetadata | None:
    match = PROCESSING_INSTRUCTION.search(xml_data[:4096])
    if match is None:
        return None
    attributes = {
        key.decode("ascii"): value.decode("utf-8")
        for key, value in ATTRIBUTE.findall(match.group(1))
    }
    snapshot_ref = attributes.get("snapshot-ref", "").strip().casefold()
    if not snapshot_ref:
        return None
    try:
        section = int(attributes.get("section", "0"))
    except ValueError:
        return None
    if section < 0:
        return None
    return XmlSnapshotMetadata(snapshot_ref, section)


def strip_snapshot_metadata(xml_data: bytes) -> bytes:
    return PROCESSING_INSTRUCTION.sub(b"", xml_data, count=1)


__all__ = [
    "XmlSnapshotMetadata",
    "add_snapshot_metadata",
    "read_snapshot_metadata",
    "strip_snapshot_metadata",
]
