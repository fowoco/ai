from datetime import date

from app.ocr.models import DocumentSide, DocumentType, OcrStatus
from app.ocr.normalizer import normalize_clova_response
from app.ocr.template_resolver import TemplateResolver


def field(name: str, text: str, confidence: float = 0.99) -> dict[str, object]:
    return {"name": name, "inferText": text, "inferConfidence": confidence}


def response(
    template_id: int | None,
    fields: list[dict[str, object]],
    *,
    infer_result: str = "SUCCESS",
) -> dict[str, object]:
    image: dict[str, object] = {
        "inferResult": infer_result,
        "fields": fields,
    }
    if template_id is not None:
        image["matchedTemplate"] = {"id": template_id, "name": "synthetic-template"}
    return {"images": [image]}


def passport_required_fields() -> list[dict[str, object]]:
    return [
        field("passport_number", " M 00000000 "),
        field("surname", " TEST "),
        field("given_names", " TEST   USER "),
        field("date_of_birth", "2000.01.02"),
        field("passport_expiry_date", "2030/01/02"),
    ]


def test_normalizes_passport_text_identifiers_and_dates() -> None:
    resolver = TemplateResolver()
    raw = response(
        43019,
        passport_required_fields()
        + [field("passport_issue_date", "2020-01-02"), field("sex", " M ")],
    )

    result = normalize_clova_response(
        raw,
        resolver.resolve(DocumentType.PASSPORT_COPY, "KOR"),
        0.80,
        resolver,
    )

    assert result.status is OcrStatus.SUCCEEDED
    assert result.matched_template_id == 43019
    assert result.document_side is None
    assert result.fields == {
        "passport_number": "M00000000",
        "surname": "TEST",
        "given_names": "TEST USER",
        "date_of_birth": date(2000, 1, 2),
        "passport_expiry_date": date(2030, 1, 2),
        "passport_issue_date": date(2020, 1, 2),
        "sex": "M",
    }
    assert result.error_code is None
    assert result.review_reasons == ()


def test_normalizes_korean_passport_bilingual_dates() -> None:
    resolver = TemplateResolver()
    fields = passport_required_fields()
    fields[3] = field("date_of_birth", "17 2월/FEB 2000")
    fields[4] = field("passport_expiry_date", "24 3월/MAR 2028")
    fields.append(field("passport_issue_date", "24 3월/MAR 2023"))

    result = normalize_clova_response(
        response(43019, fields),
        resolver.resolve(DocumentType.PASSPORT_COPY, "KOR"),
        0.80,
        resolver,
    )

    assert result.status is OcrStatus.SUCCEEDED
    assert result.fields["date_of_birth"] == date(2000, 2, 17)
    assert result.fields["passport_issue_date"] == date(2023, 3, 24)
    assert result.fields["passport_expiry_date"] == date(2028, 3, 24)
    assert result.review_reasons == ()


def test_rejects_korean_passport_date_with_conflicting_months() -> None:
    resolver = TemplateResolver()
    fields = passport_required_fields()
    fields[3] = field("date_of_birth", "17 2월/MAR 2000")

    result = normalize_clova_response(
        response(43019, fields),
        resolver.resolve(DocumentType.PASSPORT_COPY, "KOR"),
        0.80,
        resolver,
    )

    assert result.status is OcrStatus.REVIEW_REQUIRED
    assert result.error_code == "INVALID_DATE"
    assert result.review_reasons == ("invalid_date:date_of_birth",)
    assert "date_of_birth" not in result.fields
    assert "date_of_birth" not in result.field_confidences
    assert set(result.fields) == set(result.field_confidences)


def test_normalizes_arc_front_and_registration_number() -> None:
    resolver = TemplateResolver()
    raw = response(
        43024,
        [
            field("alien_registration_number", " 000000 - 0000000 "),
            field("visa_type", " E-7 "),
        ],
    )

    result = normalize_clova_response(
        raw,
        resolver.resolve(DocumentType.ARC, None),
        0.80,
        resolver,
    )

    assert result.status is OcrStatus.SUCCEEDED
    assert result.document_side is DocumentSide.FRONT
    assert result.fields["alien_registration_number"] == "000000-0000000"
    assert result.fields["visa_type"] == "E-7"


def test_arc_back_succeeds_with_only_one_non_empty_stay_field() -> None:
    resolver = TemplateResolver()
    raw = response(43025, [field("stay_expiration_date", "2028-01-31")])

    result = normalize_clova_response(
        raw,
        resolver.resolve(DocumentType.ARC, None),
        0.80,
        resolver,
    )

    assert result.status is OcrStatus.SUCCEEDED
    assert result.document_side is DocumentSide.BACK
    assert result.fields == {"stay_expiration_date": date(2028, 1, 31)}


def test_arc_back_low_confidence_only_field_requires_review() -> None:
    resolver = TemplateResolver()
    raw = response(
        43025,
        [field("residence_address_1", "TEST ADDRESS", 0.79)],
    )

    result = normalize_clova_response(
        raw,
        resolver.resolve(DocumentType.ARC, None),
        0.80,
        resolver,
    )

    assert result.status is OcrStatus.REVIEW_REQUIRED
    assert result.error_code == "LOW_CONFIDENCE"
    assert result.review_reasons == ("low_confidence:residence_address_1",)


def test_arc_back_invalid_date_requires_review_without_confidence() -> None:
    resolver = TemplateResolver()
    raw = response(43025, [field("stay_expiration_date", "31-01-2030")])

    result = normalize_clova_response(
        raw,
        resolver.resolve(DocumentType.ARC, None),
        0.80,
        resolver,
    )

    assert result.status is OcrStatus.REVIEW_REQUIRED
    assert result.error_code == "INVALID_DATE"
    assert result.review_reasons == ("invalid_date:stay_expiration_date",)
    assert "stay_expiration_date" not in result.fields
    assert "stay_expiration_date" not in result.field_confidences


def test_removed_arc_back_fields_are_ignored() -> None:
    resolver = TemplateResolver()
    raw = response(
        43025,
        [
            field("stay_permit_date", "2025/02/03"),
            field("residence_report_date_1", "2025/02/04"),
            field("residence_confirmation_1", "CONFIRM"),
            field("residence_address_2", "SECOND ADDRESS"),
            field("residence_address_1", " FIRST ADDRESS "),
        ],
    )

    result = normalize_clova_response(
        raw,
        resolver.resolve(DocumentType.ARC, None),
        0.80,
        resolver,
    )

    assert result.status is OcrStatus.SUCCEEDED
    assert result.fields == {"residence_address_1": "FIRST ADDRESS"}
    assert set(result.field_confidences) == {"residence_address_1"}


def test_low_confidence_required_field_requires_review() -> None:
    resolver = TemplateResolver()
    fields = passport_required_fields()
    fields[0] = field("passport_number", "M00000000", 0.79)

    result = normalize_clova_response(
        response(43019, fields),
        resolver.resolve(DocumentType.PASSPORT_COPY, "KOR"),
        0.80,
        resolver,
    )

    assert result.status is OcrStatus.REVIEW_REQUIRED
    assert result.error_code == "LOW_CONFIDENCE"
    assert result.review_reasons == ("low_confidence:passport_number",)


def test_missing_required_field_requires_review() -> None:
    resolver = TemplateResolver()
    fields = [item for item in passport_required_fields() if item["name"] != "surname"]

    result = normalize_clova_response(
        response(43019, fields),
        resolver.resolve(DocumentType.PASSPORT_COPY, "KOR"),
        0.80,
        resolver,
    )

    assert result.status is OcrStatus.REVIEW_REQUIRED
    assert result.error_code == "MISSING_REQUIRED_FIELD"
    assert result.review_reasons == ("missing_required:surname",)


def test_invalid_recognized_date_requires_review_and_is_not_stored() -> None:
    resolver = TemplateResolver()
    fields = passport_required_fields()
    fields[-1] = field("passport_expiry_date", "31-01-2030")

    result = normalize_clova_response(
        response(43019, fields),
        resolver.resolve(DocumentType.PASSPORT_COPY, "KOR"),
        0.80,
        resolver,
    )

    assert result.status is OcrStatus.REVIEW_REQUIRED
    assert result.error_code == "INVALID_DATE"
    assert result.review_reasons == ("invalid_date:passport_expiry_date",)
    assert "passport_expiry_date" not in result.fields
    assert "passport_expiry_date" not in result.field_confidences
    assert set(result.fields) == set(result.field_confidences)


def test_no_matched_template_requires_review() -> None:
    resolver = TemplateResolver()

    result = normalize_clova_response(
        response(None, []),
        resolver.resolve(DocumentType.PASSPORT_COPY, "KOR"),
        0.80,
        resolver,
    )

    assert result.status is OcrStatus.REVIEW_REQUIRED
    assert result.error_code == "TEMPLATE_NOT_MATCHED"
    assert result.review_reasons == ("template_not_matched",)


def test_unexpected_template_requires_review_without_parsing_fields() -> None:
    resolver = TemplateResolver()

    result = normalize_clova_response(
        response(43021, passport_required_fields()),
        resolver.resolve(DocumentType.PASSPORT_COPY, "KOR"),
        0.80,
        resolver,
    )

    assert result.status is OcrStatus.REVIEW_REQUIRED
    assert result.error_code == "TEMPLATE_NOT_MATCHED"
    assert result.review_reasons == ("unexpected_template",)
    assert result.fields == {}


def test_unknown_fields_are_not_returned_or_scored() -> None:
    resolver = TemplateResolver()

    result = normalize_clova_response(
        response(43019, passport_required_fields() + [field("raw_secret", "do-not-store")]),
        resolver.resolve(DocumentType.PASSPORT_COPY, "KOR"),
        0.80,
        resolver,
    )

    assert result.status is OcrStatus.SUCCEEDED
    assert "raw_secret" not in result.fields
    assert "raw_secret" not in result.field_confidences


def test_multiple_images_requires_review_and_uses_only_first_image() -> None:
    resolver = TemplateResolver()
    raw = response(43019, passport_required_fields())
    raw["images"].append(  # type: ignore[union-attr]
        response(43019, passport_required_fields())["images"][0]  # type: ignore[index]
    )

    result = normalize_clova_response(
        raw,
        resolver.resolve(DocumentType.PASSPORT_COPY, "KOR"),
        0.80,
        resolver,
    )

    assert result.status is OcrStatus.REVIEW_REQUIRED
    assert result.error_code == "MULTIPLE_IMAGES"
    assert result.review_reasons == ("multiple_images",)
    assert result.fields["passport_number"] == "M00000000"
