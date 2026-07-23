"""Safe ZIP-container access and atomic HWPX repackaging."""

from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from .errors import HwpxError

MAX_ARCHIVE_ENTRIES = 1_024
MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024


class HwpxPackage:
    """Validated in-memory representation of an HWPX ZIP package."""

    def __init__(self, source: str | Path):
        self.source = Path(source).resolve()
        if not self.source.is_file():
            raise FileNotFoundError(self.source)
        self._entries = self._read()
        self._by_name = {info.filename: data for info, data in self._entries}

    def section_name(self, section: int) -> str:
        for candidate in (f"Contents/section{section}.xml", f"Content/section{section}.xml"):
            if candidate in self._by_name:
                return candidate
        raise HwpxError(f"HWPX package has no section XML for section {section}")

    def read(self, name: str) -> bytes:
        try:
            return self._by_name[name]
        except KeyError as exc:
            raise HwpxError(f"HWPX package has no entry: {name}") from exc

    def save(self, destination: str | Path) -> Path:
        """Write a normalized package, including an uncompressed mimetype entry."""

        return self._save({}, destination)

    def save_replacing(
        self,
        name: str,
        payload: bytes,
        destination: str | Path,
    ) -> Path:
        if name not in self._by_name:
            raise HwpxError(f"HWPX package has no entry: {name}")
        return self._save({name: payload}, destination)

    def _save(
        self,
        replacements: dict[str, bytes],
        destination: str | Path,
    ) -> Path:
        destination_path = Path(destination).resolve()
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix="hwpx-edit-",
                suffix=".hwpx",
                dir=destination_path.parent,
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
            with zipfile.ZipFile(temporary_path, "w") as output:
                for info, data in self._entries:
                    entry_payload = replacements.get(info.filename, data)
                    if info.filename == "mimetype":
                        info.compress_type = zipfile.ZIP_STORED
                    output.writestr(info, entry_payload)
            with zipfile.ZipFile(temporary_path, "r") as saved:
                invalid_entry = saved.testzip()
                if invalid_entry is not None:
                    raise HwpxError(
                        f"saved HWPX package failed CRC validation: {invalid_entry}"
                    )
            os.replace(temporary_path, destination_path)
            temporary_path = None
            return destination_path
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

    def _read(self) -> list[tuple[zipfile.ZipInfo, bytes]]:
        entries: list[tuple[zipfile.ZipInfo, bytes]] = []
        seen: set[str] = set()
        total_size = 0
        try:
            archive = zipfile.ZipFile(self.source, "r")
        except (OSError, zipfile.BadZipFile) as exc:
            raise HwpxError(f"invalid HWPX ZIP package: {self.source}") from exc
        with archive:
            infos = archive.infolist()
            if len(infos) > MAX_ARCHIVE_ENTRIES:
                raise HwpxError(f"HWPX package has too many entries: {len(infos)}")
            for info in infos:
                path = PurePosixPath(info.filename)
                if (
                    not info.filename
                    or info.filename in seen
                    or path.is_absolute()
                    or ".." in path.parts
                    or "\\" in info.filename
                ):
                    raise HwpxError(f"unsafe or duplicate HWPX entry: {info.filename!r}")
                if info.flag_bits & 0x1:
                    raise HwpxError(f"encrypted HWPX entry is not supported: {info.filename}")
                seen.add(info.filename)
                total_size += info.file_size
                if total_size > MAX_UNCOMPRESSED_BYTES:
                    raise HwpxError("HWPX package exceeds the uncompressed size limit")
                entries.append((info, archive.read(info)))
        if "mimetype" not in seen:
            raise HwpxError("HWPX package has no mimetype entry")
        return entries


__all__ = [
    "MAX_ARCHIVE_ENTRIES",
    "MAX_UNCOMPRESSED_BYTES",
    "HwpxPackage",
]
