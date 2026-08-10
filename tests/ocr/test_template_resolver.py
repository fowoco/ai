import pytest

from app.ocr.models import DocumentSide, DocumentType, TemplateResolutionError
from app.ocr.template_resolver import TemplateResolver


@pytest.mark.parametrize(
    ("country", "template_id"),
    [
        ("KOR", 43019),
        ("PHL", 43021),
        ("JPN", 43022),
        ("CHN", 43023),
        ("VNM", 43038),
    ],
)
def test_resolves_each_supported_passport_country(
    country: str,
    template_id: int,
) -> None:
    selection = TemplateResolver().resolve(DocumentType.PASSPORT_COPY, country)

    assert selection.template_ids == (template_id,)
    assert selection.expected_document_type is DocumentType.PASSPORT_COPY


def test_normalizes_passport_country_case_and_outer_whitespace() -> None:
    selection = TemplateResolver().resolve(DocumentType.PASSPORT_COPY, "  kor  ")

    assert selection.template_ids == (43019,)


def test_resolves_arc_candidates_and_matched_side() -> None:
    resolver = TemplateResolver()

    selection = resolver.resolve(DocumentType.ARC, None)

    assert selection.template_ids == (43024, 43025)
    assert selection.expected_document_type is DocumentType.ARC
    assert resolver.side_for_template(43024) is DocumentSide.FRONT
    assert resolver.side_for_template(43025) is DocumentSide.BACK


def test_arc_ignores_country_code() -> None:
    selection = TemplateResolver().resolve(DocumentType.ARC, "unexpected")

    assert selection.template_ids == (43024, 43025)


def test_rejects_missing_passport_country() -> None:
    with pytest.raises(TemplateResolutionError, match="passport country"):
        TemplateResolver().resolve(DocumentType.PASSPORT_COPY, None)


def test_rejects_blank_passport_country() -> None:
    with pytest.raises(TemplateResolutionError, match="passport country"):
        TemplateResolver().resolve(DocumentType.PASSPORT_COPY, "  ")


def test_rejects_unsupported_passport_country_without_echoing_input() -> None:
    with pytest.raises(TemplateResolutionError, match="unsupported passport country") as exc:
        TemplateResolver().resolve(DocumentType.PASSPORT_COPY, "SECRET-VALUE")

    assert "SECRET-VALUE" not in str(exc.value)


def test_rejects_unexpected_matched_template_id() -> None:
    with pytest.raises(TemplateResolutionError, match="unexpected matched template"):
        TemplateResolver().side_for_template(99999)
