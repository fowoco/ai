"""Common document formats shared by APIs and conversion services."""

from enum import StrEnum


class DocumentFormat(StrEnum):
    HWP = "hwp"
    HWPX = "hwpx"
    PDF = "pdf"
    XML = "xml"


__all__ = ["DocumentFormat"]
