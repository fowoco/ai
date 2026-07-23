"""Errors raised by persistent document snapshot lookup."""


class DocumentSnapshotError(RuntimeError):
    """Base error for snapshot persistence and resolution."""


class DocumentSnapshotNotFoundError(DocumentSnapshotError):
    """No snapshot matches the embedded reference or filename alias."""


class DocumentSnapshotNameConflictError(DocumentSnapshotError):
    """One normalized name was assigned to structurally different forms."""


__all__ = [
    "DocumentSnapshotError",
    "DocumentSnapshotNameConflictError",
    "DocumentSnapshotNotFoundError",
]
