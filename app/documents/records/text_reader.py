"""DB 레코드를 대신하는 UTF-8 ``key=value`` TXT 리더."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from .errors import DocumentRecordParseError


class RecordReader(Protocol):
    """TXT, DB 등 외부 데이터 소스가 구현할 최소 계약."""

    def read(self, source: str | Path) -> Mapping[str, object]: ...


class TextRecordReader:
    """한 줄에 하나의 ``key=value``를 갖는 테스트 레코드를 읽는다."""

    def read(self, source: str | Path) -> dict[str, str]:
        source_path = Path(source)
        try:
            text = source_path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            raise DocumentRecordParseError(
                "TXT record must be encoded as UTF-8"
            ) from exc
        except OSError as exc:
            raise DocumentRecordParseError(
                f"could not read TXT record: {source_path}"
            ) from exc

        if "\x00" in text:
            raise DocumentRecordParseError("TXT record must not contain NUL bytes")

        values: dict[str, str] = {}
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                raise DocumentRecordParseError(
                    f"TXT record line {line_number} must use key=value"
                )
            raw_key, raw_value = line.split("=", 1)
            key = raw_key.strip()
            if not key:
                raise DocumentRecordParseError(
                    f"TXT record line {line_number} has an empty key"
                )
            if key in values:
                raise DocumentRecordParseError(
                    f"TXT record has a duplicate key: {key}"
                )
            values[key] = raw_value.strip()

        if not values:
            raise DocumentRecordParseError("TXT record does not contain any values")
        return values


__all__ = ["RecordReader", "TextRecordReader"]
