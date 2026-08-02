from dataclasses import dataclass
from typing import Literal

from .contracts import (
    EpsLanguageCode,
    FrozenContract,
    SupportedLanguage,
    WarningCode,
    WarningItem,
)

LanguageResolutionSource = Literal[
    "preferred",
    "legacy_preferred",
    "nationality",
    "default",
]


class UnsupportedPreferredLanguageError(ValueError):
    """Stable, data-free error for an unsupported explicit language."""

    code = "UNSUPPORTED_PREFERRED_LANGUAGE"

    def __init__(self) -> None:
        super().__init__("unsupported preferred language")


class LanguageResolution(FrozenContract):
    canonical_code: SupportedLanguage
    eps_code: EpsLanguageCode
    source: LanguageResolutionSource
    warnings: tuple[WarningItem, ...] = ()


@dataclass(frozen=True)
class _LanguageRow:
    canonical_code: SupportedLanguage
    display_name_ko: str
    eps_code: EpsLanguageCode
    nationality_codes: tuple[str, ...] = ()
    legacy_product_aliases: tuple[str, ...] = ()


_LANGUAGE_ROWS = (
    _LanguageRow("en", "영어", "01"),
    _LanguageRow("zh-Hans", "중국어 간체", "02", ("CN",)),
    _LanguageRow("vi", "베트남어", "03", ("VN",), ("vn",)),
    _LanguageRow("th", "태국어", "04", ("TH",)),
    _LanguageRow("fil", "필리핀어/따갈로그어", "05", ("PH",), ("ph",)),
    _LanguageRow("id", "인도네시아어", "06", ("ID",)),
    _LanguageRow("mn", "몽골어", "07", ("MN",)),
    _LanguageRow("si", "싱할라어", "08", ("LK",), ("lk",)),
    _LanguageRow("ru", "러시아어", "09", ("RU",)),
    _LanguageRow("uz", "우즈베크어", "10", ("UZ",)),
    _LanguageRow("ky", "키르기스어", "11", ("KG",), ("kg",)),
    _LanguageRow("bn", "방글라어", "13", ("BD",), ("bd",)),
    _LanguageRow("ur", "우르두어", "14", ("PK",), ("pk",)),
    _LanguageRow("km", "크메르어", "15", ("KH",), ("kh",)),
    _LanguageRow("tet", "테툼어", "17", ("TL",), ("tl",)),
)

_BY_CANONICAL = {row.canonical_code: row for row in _LANGUAGE_ROWS}
_BY_NATIONALITY = {
    nationality: row
    for row in _LANGUAGE_ROWS
    for nationality in row.nationality_codes
}
_BY_LEGACY_ALIAS = {
    alias: row
    for row in _LANGUAGE_ROWS
    for alias in row.legacy_product_aliases
}


def _warning(code: WarningCode, message: str) -> WarningItem:
    return WarningItem(component="language_normalization", code=code, message=message)


def _resolve_row(
    row: _LanguageRow,
    *,
    source: LanguageResolutionSource,
    warnings: tuple[WarningItem, ...] = (),
) -> LanguageResolution:
    return LanguageResolution(
        canonical_code=row.canonical_code,
        eps_code=row.eps_code,
        source=source,
        warnings=warnings,
    )


def _unsupported() -> UnsupportedPreferredLanguageError:
    return UnsupportedPreferredLanguageError()


def normalize_preferred_language(value: str) -> LanguageResolution:
    row = _BY_CANONICAL.get(value.strip())
    if row is None:
        raise _unsupported()
    return _resolve_row(row, source="preferred")


def normalize_legacy_language_value(value: str) -> LanguageResolution:
    row = _BY_LEGACY_ALIAS.get(value.strip())
    if row is None:
        raise _unsupported()
    return _resolve_row(
        row,
        source="legacy_preferred",
        warnings=(
            _warning(
                WarningCode.LANGUAGE_CODE_NORMALIZED,
                "A legacy language code was normalized.",
            ),
        ),
    )


def language_from_nationality(value: str) -> LanguageResolution | None:
    row = _BY_NATIONALITY.get(value.strip().upper())
    if row is None:
        return None
    return _resolve_row(
        row,
        source="nationality",
        warnings=(
            _warning(
                WarningCode.LANGUAGE_INFERRED_FROM_NATIONALITY,
                "Target language was inferred from nationality.",
            ),
        ),
    )


def resolve_target_language(
    preferred_language: str | None,
    nationality_code: str | None,
) -> LanguageResolution:
    if preferred_language is not None:
        try:
            return normalize_preferred_language(preferred_language)
        except UnsupportedPreferredLanguageError:
            if preferred_language.strip() in _BY_LEGACY_ALIAS:
                return normalize_legacy_language_value(preferred_language)
            raise _unsupported() from None

    if nationality_code is not None:
        inferred = language_from_nationality(nationality_code)
        if inferred is not None:
            return inferred

    return _resolve_row(
        _BY_CANONICAL["en"],
        source="default",
        warnings=(
            _warning(
                WarningCode.LANGUAGE_DEFAULTED_TO_EN,
                "Target language defaulted to English.",
            ),
        ),
    )


__all__ = [
    "LanguageResolution",
    "UnsupportedPreferredLanguageError",
    "language_from_nationality",
    "normalize_legacy_language_value",
    "normalize_preferred_language",
    "resolve_target_language",
]
