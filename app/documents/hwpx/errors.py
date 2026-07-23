"""HWPX parsing, editing, and packaging errors."""


class HwpxError(RuntimeError):
    """The HWPX package is malformed or cannot be edited safely."""


__all__ = ["HwpxError"]
