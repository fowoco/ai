"""Bundled HWP5 template discovery and SHA-256 based identification."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .exceptions import Hwp5TemplateError, Hwp5TemplateNotFoundError


def file_sha256(path: str | Path) -> str:
    """Return a lowercase SHA-256 digest without loading the whole file."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class Hwp5Template:
    """Validated metadata and source file for one supported HWP form."""

    template_id: str
    template_hash: str
    fields: Mapping[str, Mapping[str, object]]
    map_path: Path
    source_path: Path


class Hwp5TemplateRegistry:
    """Load bundled form maps and identify HWP files by content hash."""

    def __init__(self, template_dir: str | Path | None = None):
        self.template_dir = (
            Path(template_dir).resolve()
            if template_dir is not None
            else Path(__file__).resolve().parent / "templates"
        )
        self._by_id: dict[str, Hwp5Template] = {}
        self._by_hash: dict[str, Hwp5Template] = {}
        self._load()

    def _load(self) -> None:
        if not self.template_dir.is_dir():
            raise Hwp5TemplateError(f"HWP5 template directory does not exist: {self.template_dir}")

        source_by_hash: dict[str, Path] = {}
        for source_path in sorted(self.template_dir.glob("*.hwp")):
            digest = file_sha256(source_path)
            if digest in source_by_hash:
                raise Hwp5TemplateError(
                    f"duplicate HWP5 source hash in template directory: {digest}"
                )
            source_by_hash[digest] = source_path

        for map_path in sorted(self.template_dir.glob("*.json")):
            try:
                data = json.loads(map_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise Hwp5TemplateError(f"invalid template map: {map_path}") from exc
            template_id = str(data.get("template_id", "")).strip()
            template_hash = str(data.get("template_hash", "")).strip().casefold()
            fields = data.get("fields")
            if not template_id or len(template_hash) != 64 or not isinstance(fields, dict):
                raise Hwp5TemplateError(
                    f"template map needs template_id, SHA-256 template_hash, and fields: {map_path}"
                )
            if template_id in self._by_id:
                raise Hwp5TemplateError(f"duplicate template_id: {template_id}")
            if template_hash in self._by_hash:
                raise Hwp5TemplateError(f"duplicate template_hash: {template_hash}")
            try:
                source_path = source_by_hash[template_hash]
            except KeyError as exc:
                raise Hwp5TemplateError(
                    f"no bundled HWP source matches {map_path.name}: {template_hash}"
                ) from exc
            template = Hwp5Template(
                template_id=template_id,
                template_hash=template_hash,
                fields=fields,
                map_path=map_path,
                source_path=source_path,
            )
            self._by_id[template_id] = template
            self._by_hash[template_hash] = template

        if not self._by_id:
            raise Hwp5TemplateError(f"no HWP5 template maps were found in {self.template_dir}")

    def list(self) -> tuple[Hwp5Template, ...]:
        return tuple(self._by_id[key] for key in sorted(self._by_id))

    def get(self, template_id: str) -> Hwp5Template:
        try:
            return self._by_id[template_id]
        except KeyError as exc:
            raise Hwp5TemplateNotFoundError(f"unknown HWP5 template_id: {template_id}") from exc

    def identify(self, source: str | Path) -> Hwp5Template:
        digest = file_sha256(source)
        try:
            return self._by_hash[digest]
        except KeyError as exc:
            raise Hwp5TemplateNotFoundError(
                f"no HWP5 template matches source SHA-256: {digest}"
            ) from exc


__all__ = ["Hwp5Template", "Hwp5TemplateRegistry", "file_sha256"]
