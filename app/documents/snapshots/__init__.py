"""Document snapshot persistence and XML provenance metadata."""

from .exceptions import (
    DocumentSnapshotError,
    DocumentSnapshotNameConflictError,
    DocumentSnapshotNotFoundError,
)
from .fingerprint import hwpx_layout_fingerprint
from .repository import (
    DocumentSnapshot,
    DocumentSnapshotRepository,
    normalize_template_name,
)
from .xml_metadata import (
    XmlSnapshotMetadata,
    add_snapshot_metadata,
    read_snapshot_metadata,
    strip_snapshot_metadata,
)

__all__ = [
    "DocumentSnapshot",
    "DocumentSnapshotError",
    "DocumentSnapshotNameConflictError",
    "DocumentSnapshotNotFoundError",
    "DocumentSnapshotRepository",
    "XmlSnapshotMetadata",
    "add_snapshot_metadata",
    "hwpx_layout_fingerprint",
    "normalize_template_name",
    "read_snapshot_metadata",
    "strip_snapshot_metadata",
]
