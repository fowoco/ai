"""Rebuild Microsoft CFB/OLE containers with variable-sized streams.

``olefile`` is excellent for reading HWP containers, but its writer requires
replacement streams to keep their original byte length.  This module rebuilds
the complete container with ``ms-cfb`` so body streams may grow and new
``BinData`` streams may be added.
"""

from __future__ import annotations

import hashlib
import os
import struct
import tempfile
import threading
import warnings
from collections.abc import Mapping
from pathlib import Path

import olefile

try:
    from ms_cfb.Models.Directories.storage_directory import StorageDirectory
    from ms_cfb.Models.Directories.stream_directory import StreamDirectory
    from ms_cfb.ole_file import OleFile
except ImportError:  # pragma: no cover - optional until variable-size writes
    StorageDirectory = None
    StreamDirectory = None
    OleFile = None


class CfbRebuildError(RuntimeError):
    pass


# ms-cfb 0.0.6 uses process-relative scratch filenames internally.  Serialise
# this small critical section.  A future HTTP service should call this module
# from its document-worker process, which also isolates the process cwd.
_BUILD_LOCK = threading.Lock()


def _write_built_cfb(cfb: object, destination: Path, scratch: Path) -> None:
    """Write all FAT sectors; ms-cfb 0.0.6 only writes the first one."""

    cfb.build_file()
    fat = cfb._fat_chain
    sector_size = fat.get_sector_size()
    sector_data_path = scratch / "sector-data.bin"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ResourceWarning)
        fat.write_streams(str(sector_data_path))
    sector_data = bytearray(sector_data_path.read_bytes())

    chain = fat.get_chain()
    fat_sector_numbers = cfb.get_fat_sectors()
    entries_per_sector = sector_size // 4
    required_entries = len(fat_sector_numbers) * entries_per_sector
    chain.extend([0xFFFFFFFF] * (required_entries - len(chain)))
    fat_bytes = struct.pack(f"<{required_entries}I", *chain[:required_entries])
    for index, sector_number in enumerate(fat_sector_numbers):
        start = sector_number * sector_size
        end = start + sector_size
        sector_data[start:end] = fat_bytes[index * sector_size : (index + 1) * sector_size]

    header = bytearray(cfb.header())
    # csectFat is the number of FAT sectors, not the number of 512-byte data
    # sectors.  Correct the upstream calculation for containers > 128 sectors.
    struct.pack_into("<I", header, 44, len(fat_sector_numbers))
    with destination.open("wb") as output:
        output.write(header)
        output.write(sector_data)


def read_all_streams(source_path: os.PathLike[str] | str) -> dict[str, bytes]:
    source = Path(source_path)
    with olefile.OleFileIO(str(source)) as ole:
        return {
            "/".join(entry): ole.openstream(entry).read()
            for entry in ole.listdir(streams=True, storages=False)
        }


def rebuild_cfb(
    source_path: os.PathLike[str] | str,
    destination_path: os.PathLike[str] | str,
    replacements: Mapping[str, bytes] | None = None,
    additions: Mapping[str, bytes] | None = None,
) -> Path:
    """Rebuild *source_path* while replacing or adding named streams."""

    if OleFile is None or StorageDirectory is None or StreamDirectory is None:
        raise ImportError("ms-cfb is required for variable-size OLE writes")

    source = Path(source_path).resolve()
    destination = Path(destination_path).resolve()
    if source == destination:
        raise ValueError("destination must differ from source")
    if not source.is_file():
        raise FileNotFoundError(source)

    streams = read_all_streams(source)
    for name, data in (replacements or {}).items():
        if name not in streams:
            raise KeyError(f"cannot replace missing OLE stream: {name}")
        streams[name] = bytes(data)
    for name, data in (additions or {}).items():
        if name in streams:
            raise KeyError(f"OLE stream already exists: {name}")
        streams[name] = bytes(data)

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hwp-cfb-") as temp_name:
        temp_dir = Path(temp_name)
        cfb = OleFile()
        cfb.version = 3
        storages: dict[tuple[str, ...], object] = {(): cfb.root_directory}

        storage_paths = {
            tuple(parts[:index])
            for stream_name in streams
            for parts in [stream_name.split("/")]
            for index in range(1, len(parts))
        }
        for storage_path in sorted(storage_paths, key=lambda value: (len(value), value)):
            parent_path = storage_path[:-1]
            storage = StorageDirectory(storage_path[-1])
            storages[parent_path].add_directory(storage)
            storages[storage_path] = storage

        for number, (stream_name, data) in enumerate(sorted(streams.items())):
            parts = stream_name.split("/")
            blob_path = temp_dir / f"stream-{number:04d}.bin"
            blob_path.write_bytes(data)
            stream = StreamDirectory(parts[-1], str(blob_path))
            storages[tuple(parts[:-1])].add_directory(stream)

        temporary_output = temp_dir / "rebuilt.ole"
        with _BUILD_LOCK:
            previous_cwd = Path.cwd()
            try:
                os.chdir(temp_dir)
                _write_built_cfb(cfb, temporary_output, temp_dir)
            finally:
                os.chdir(previous_cwd)

        rebuilt_streams = read_all_streams(temporary_output)
        if rebuilt_streams != streams:
            missing = sorted(set(streams) - set(rebuilt_streams))
            extra = sorted(set(rebuilt_streams) - set(streams))
            changed = sorted(
                name
                for name in set(streams) & set(rebuilt_streams)
                if streams[name] != rebuilt_streams[name]
            )
            changed_details = {
                name: {
                    "expected_size": len(streams[name]),
                    "actual_size": len(rebuilt_streams[name]),
                    "expected_sha256": hashlib.sha256(streams[name]).hexdigest(),
                    "actual_sha256": hashlib.sha256(rebuilt_streams[name]).hexdigest(),
                }
                for name in changed
            }
            raise CfbRebuildError(
                f"rebuilt CFB validation failed; missing={missing}, "
                f"extra={extra}, changed={changed_details}"
            )
        os.replace(temporary_output, destination)
    return destination


__all__ = ["CfbRebuildError", "read_all_streams", "rebuild_cfb"]
