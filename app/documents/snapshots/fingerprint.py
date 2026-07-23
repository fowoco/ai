"""Stable HWPX layout fingerprints that ignore entered text and binary payloads."""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path

from app.documents.hwpx import HwpxError, HwpxPackage


def hwpx_layout_fingerprint(source: str | Path, *, section: int = 0) -> str:
    """Hash package structure while excluding entered text and image bytes."""

    package = HwpxPackage(source)
    digest = hashlib.sha256()
    for name in ("Contents/header.xml", "Content/header.xml", "settings.xml"):
        try:
            payload = package.read(name)
        except HwpxError:
            continue
        digest.update(name.encode("utf-8"))
        digest.update(_normalized_xml(payload, clear_text_nodes=False))

    section_name = package.section_name(section)
    digest.update(section_name.encode("utf-8"))
    digest.update(_normalized_xml(package.read(section_name), clear_text_nodes=True))
    return digest.hexdigest()


def _normalized_xml(payload: bytes, *, clear_text_nodes: bool) -> bytes:
    root = ET.fromstring(payload)
    for element in root.iter():
        if clear_text_nodes and element.tag.endswith("}t"):
            element.text = ""
        elif element.text is not None and not element.text.strip():
            element.text = None
        if element.tail is not None and not element.tail.strip():
            element.tail = None
    return ET.tostring(root, encoding="utf-8")


__all__ = ["hwpx_layout_fingerprint"]
