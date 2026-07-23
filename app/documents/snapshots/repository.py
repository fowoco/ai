"""File-backed HWPX document snapshots with normalized filename aliases."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

from app.documents.hwpx import HwpxPackage

from .exceptions import (
    DocumentSnapshotNameConflictError,
    DocumentSnapshotNotFoundError,
)
from .fingerprint import hwpx_layout_fingerprint


@dataclass(frozen=True)
class DocumentSnapshot:
    snapshot_ref: str
    document_hash: str
    layout_fingerprint: str
    template_name: str
    section: int
    package_path: Path


class DocumentSnapshotRepository:
    """Persist immutable packages and a single-layout alias for each form name."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.packages_dir = self.root / "packages"
        self.metadata_dir = self.root / "metadata"
        self.aliases_dir = self.root / "aliases"
        for directory in (self.packages_dir, self.metadata_dir, self.aliases_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def store(
        self,
        source_hwpx: str | Path,
        *,
        template_name: str,
        section: int = 0,
    ) -> DocumentSnapshot:
        source_path = Path(source_hwpx).resolve()
        HwpxPackage(source_path).section_name(section)
        normalized_name = normalize_template_name(template_name)
        if not normalized_name:
            raise ValueError("template name is empty after normalization")
        document_hash = _file_sha256(source_path)
        layout_fingerprint = hwpx_layout_fingerprint(source_path, section=section)
        snapshot_ref = document_hash
        package_path = self.packages_dir / f"{snapshot_ref}.hwpx"
        metadata_path = self.metadata_dir / f"{snapshot_ref}.json"
        alias_path = self.aliases_dir / f"{_alias_key(normalized_name)}.json"

        existing_alias = _read_json(alias_path)
        if (
            existing_alias is not None
            and existing_alias.get("layout_fingerprint") != layout_fingerprint
        ):
            raise DocumentSnapshotNameConflictError(
                f"template name {template_name!r} is already assigned to a different layout"
            )

        if not package_path.is_file():
            _atomic_copy(source_path, package_path)
        snapshot = DocumentSnapshot(
            snapshot_ref=snapshot_ref,
            document_hash=document_hash,
            layout_fingerprint=layout_fingerprint,
            template_name=normalized_name,
            section=section,
            package_path=package_path,
        )
        metadata = asdict(snapshot)
        metadata["package_path"] = package_path.name
        _atomic_json(metadata_path, metadata)
        _atomic_json(
            alias_path,
            {
                "template_name": normalized_name,
                "layout_fingerprint": layout_fingerprint,
                "snapshot_ref": snapshot_ref,
            },
        )
        return snapshot

    def get(self, snapshot_ref: str) -> DocumentSnapshot:
        normalized_ref = snapshot_ref.strip().casefold()
        if len(normalized_ref) != 64 or any(
            character not in "0123456789abcdef" for character in normalized_ref
        ):
            raise DocumentSnapshotNotFoundError("invalid document snapshot reference")
        metadata = _read_json(self.metadata_dir / f"{normalized_ref}.json")
        package_path = self.packages_dir / f"{normalized_ref}.hwpx"
        if metadata is None or not package_path.is_file():
            raise DocumentSnapshotNotFoundError(
                f"document snapshot was not found: {normalized_ref}"
            )
        return DocumentSnapshot(
            snapshot_ref=normalized_ref,
            document_hash=str(metadata["document_hash"]),
            layout_fingerprint=str(metadata["layout_fingerprint"]),
            template_name=str(metadata["template_name"]),
            section=int(metadata["section"]),
            package_path=package_path,
        )

    def resolve_name(self, template_name: str) -> DocumentSnapshot:
        normalized_name = normalize_template_name(template_name)
        alias = _read_json(self.aliases_dir / f"{_alias_key(normalized_name)}.json")
        if alias is None or alias.get("template_name") != normalized_name:
            raise DocumentSnapshotNotFoundError(
                f"no document snapshot matches template name: {template_name!r}"
            )
        return self.get(str(alias["snapshot_ref"]))


def normalize_template_name(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value).strip().casefold()
    return " ".join(normalized.split())


def _alias_key(normalized_name: str) -> str:
    return hashlib.sha256(normalized_name.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, object] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        raise DocumentSnapshotNotFoundError(f"invalid snapshot metadata: {path}") from exc
    if not isinstance(value, dict):
        raise DocumentSnapshotNotFoundError(f"invalid snapshot metadata: {path}")
    return value


def _atomic_copy(source: Path, destination: Path) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".snapshot-",
            suffix=".hwpx",
            dir=destination.parent,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
        shutil.copy2(source, temporary_path)
        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _atomic_json(destination: Path, payload: dict[str, object]) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".snapshot-",
            suffix=".json",
            dir=destination.parent,
            mode="w",
            encoding="utf-8",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(payload, temporary, ensure_ascii=False, sort_keys=True)
        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


__all__ = [
    "DocumentSnapshot",
    "DocumentSnapshotRepository",
    "normalize_template_name",
]
