import pytest

from app.agents.language.codes import (
    UnsupportedPreferredLanguageError,
    language_from_nationality,
    normalize_legacy_language_value,
    normalize_preferred_language,
    resolve_target_language,
)
from app.agents.language.contracts import WarningCode


def warning_codes(result):
    return tuple(warning.code for warning in result.warnings)


@pytest.mark.parametrize(
    ("canonical_code", "eps_code"),
    [
        ("en", "01"),
        ("zh-Hans", "02"),
        ("vi", "03"),
        ("th", "04"),
        ("fil", "05"),
        ("id", "06"),
        ("mn", "07"),
        ("si", "08"),
        ("ru", "09"),
        ("uz", "10"),
        ("ky", "11"),
        ("bn", "13"),
        ("ur", "14"),
        ("km", "15"),
        ("tet", "17"),
    ],
)
def test_all_15_canonical_codes_map_to_eps_codes(canonical_code, eps_code):
    result = normalize_preferred_language(canonical_code)

    assert result.canonical_code == canonical_code
    assert result.eps_code == eps_code
    assert result.source == "preferred"
    assert warning_codes(result) == ()


@pytest.mark.parametrize(
    ("nationality_code", "canonical_code"),
    [
        ("CN", "zh-Hans"),
        ("VN", "vi"),
        ("TH", "th"),
        ("PH", "fil"),
        ("ID", "id"),
        ("MN", "mn"),
        ("LK", "si"),
        ("RU", "ru"),
        ("UZ", "uz"),
        ("KG", "ky"),
        ("BD", "bn"),
        ("PK", "ur"),
        ("KH", "km"),
        ("TL", "tet"),
    ],
)
def test_all_supported_nationalities_map_to_languages(nationality_code, canonical_code):
    result = language_from_nationality(nationality_code)

    assert result is not None
    assert result.canonical_code == canonical_code
    assert result.source == "nationality"


def test_preferred_language_wins_over_nationality():
    result = resolve_target_language("vi", "PH")

    assert result.canonical_code == "vi"
    assert result.source == "preferred"
    assert warning_codes(result) == ()


def test_missing_preference_uses_nationality():
    result = resolve_target_language(None, "CN")

    assert result.canonical_code == "zh-Hans"
    assert result.source == "nationality"
    assert warning_codes(result) == (WarningCode.LANGUAGE_INFERRED_FROM_NATIONALITY,)


def test_missing_both_defaults_to_english_with_warning():
    result = resolve_target_language(None, None)

    assert result.canonical_code == "en"
    assert result.eps_code == "01"
    assert result.source == "default"
    assert warning_codes(result) == (WarningCode.LANGUAGE_DEFAULTED_TO_EN,)


def test_invalid_explicit_preference_fails_without_fallback():
    with pytest.raises(UnsupportedPreferredLanguageError) as captured:
        resolve_target_language("not-supported", "PH")

    assert captured.value.code == "UNSUPPORTED_PREFERRED_LANGUAGE"
    assert "not-supported" not in str(captured.value)


def test_legacy_alias_returns_warning():
    result = normalize_legacy_language_value("vn")

    assert result.canonical_code == "vi"
    assert result.eps_code == "03"
    assert result.source == "legacy_preferred"
    assert warning_codes(result) == (WarningCode.LANGUAGE_CODE_NORMALIZED,)


def test_country_code_is_not_lowercased_into_language():
    result = resolve_target_language(None, "TL")

    assert result.canonical_code == "tet"
    assert result.eps_code == "17"
    assert result.canonical_code != "tl"


def test_fil_filters_eps_code_05():
    assert normalize_preferred_language("fil").eps_code == "05"


def test_tet_filters_eps_code_17():
    assert normalize_preferred_language("tet").eps_code == "17"


def test_product_legacy_tl_maps_to_tet_not_fil():
    result = normalize_legacy_language_value("tl")

    assert result.canonical_code == "tet"
    assert result.eps_code == "17"
    assert result.canonical_code != "fil"
