import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

from app.ocr.models import (
    DocumentSide,
    DocumentType,
    FieldValue,
    NormalizedOcrResult,
    OcrStatus,
    TemplateSelection,
)
from app.ocr.template_resolver import TemplateResolver

DATE_FIELDS = frozenset(
    {
        "date_of_birth",
        "passport_issue_date",
        "passport_expiry_date",
        "stay_expiration_date",
    }
)
PASSPORT_REQUIRED = frozenset(
    {
        "passport_number",
        "surname",
        "given_names",
        "date_of_birth",
        "passport_expiry_date",
    }
)
ARC_FRONT_REQUIRED = frozenset({"alien_registration_number"})
ARC_BACK_PREFIXES = ("stay_", "residence_")
IDENTIFIER_FIELDS = frozenset({"passport_number", "alien_registration_number"})
APPROVED_FIELD_NAMES = frozenset(
    {
        "passport_number",
        "surname",
        "given_names",
        "nationality",
        "date_of_birth",
        "sex",
        "passport_issue_date",
        "passport_expiry_date",
        "alien_registration_number",
        "visa_type",
        "stay_expiration_date",
        "residence_address_1",
    }
)

_DATE_FORMATS = ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d")
_VIETNAMESE_PASSPORT_DATE_FORMATS = (
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%d/%m/%Y",
    "%d %b %Y",
)
_PASSPORT_DATE_PATTERN = re.compile(
    r"^(?P<day>\d{1,2})\s+(?P<numeric_month>\d{1,2})월\s*/\s*"
    r"(?P<english_month>[A-Za-z]{3})\s+(?P<year>\d{4})$"
)
_VNM_TEMPLATE_ID = 43038
_VNM_MRZ_BIRTH_PATTERN = re.compile(r"VNM(?P<birth>\d{6})")
_ENGLISH_MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}
_ERROR_CODES = {
    "multiple_images": "MULTIPLE_IMAGES",
    "template_not_matched": "TEMPLATE_NOT_MATCHED",
    "unexpected_template": "TEMPLATE_NOT_MATCHED",
}


def normalize_clova_response(
    raw: Mapping[str, Any],
    selection: TemplateSelection,
    threshold: float,
    resolver: TemplateResolver,
) -> NormalizedOcrResult:
    images = _mapping_sequence(raw.get("images"))
    if not images:
        return _review_result("template_not_matched")

    review_reasons: list[str] = []
    if len(images) != 1:
        review_reasons.append("multiple_images")

    image = images[0]
    matched_template_id = _matched_template_id(image)
    if image.get("inferResult") != "SUCCESS" or matched_template_id is None:
        review_reasons.append("template_not_matched")
        return _result(
            matched_template_id=None,
            side=None,
            fields={},
            confidences={},
            review_reasons=review_reasons,
        )
    if matched_template_id not in selection.template_ids:
        review_reasons.append("unexpected_template")
        return _result(
            matched_template_id=matched_template_id,
            side=None,
            fields={},
            confidences={},
            review_reasons=review_reasons,
        )

    side = _document_side(selection, matched_template_id, resolver)
    fields: dict[str, FieldValue] = {}
    confidences: dict[str, float] = {}
    recognized_names: set[str] = set()
    vietnamese_full_name: tuple[str, float] | None = None
    vietnamese_mrz: tuple[str, float] | None = None
    for raw_field in _mapping_sequence(image.get("fields")):
        name = raw_field.get("name")
        text = raw_field.get("inferText")
        if (
            matched_template_id == _VNM_TEMPLATE_ID
            and isinstance(name, str)
            and name in {"full_name", "mrz"}
            and isinstance(text, str)
            and text.strip()
        ):
            value = (text.strip(), _confidence(raw_field.get("inferConfidence")))
            if name == "full_name":
                vietnamese_full_name = value
            else:
                vietnamese_mrz = value
            continue
        if not isinstance(name, str) or name not in APPROVED_FIELD_NAMES:
            continue
        if not isinstance(text, str) or not text.strip():
            continue

        recognized_names.add(name)
        confidence = _confidence(raw_field.get("inferConfidence"))
        if name in confidences and confidence < confidences[name]:
            continue
        confidences[name] = confidence

        if name in DATE_FIELDS:
            parsed = _parse_date(
                text.strip(),
                allow_day_first=matched_template_id == _VNM_TEMPLATE_ID,
            )
            if parsed is None:
                fields.pop(name, None)
                confidences.pop(name, None)
                reason = f"invalid_date:{name}"
                if reason not in review_reasons:
                    review_reasons.append(reason)
                continue
            fields[name] = parsed
        elif name in IDENTIFIER_FIELDS:
            fields[name] = re.sub(r"\s+", "", text)
        else:
            fields[name] = " ".join(text.split())

    if matched_template_id == _VNM_TEMPLATE_ID:
        if vietnamese_full_name is not None:
            name_parts = vietnamese_full_name[0].split()
            if len(name_parts) >= 2:
                fields.setdefault("surname", name_parts[0])
                fields.setdefault("given_names", " ".join(name_parts[1:]))
                recognized_names.update({"surname", "given_names"})
                confidences.setdefault("surname", vietnamese_full_name[1])
                confidences.setdefault("given_names", vietnamese_full_name[1])
        if "date_of_birth" not in fields and vietnamese_mrz is not None:
            mrz_birth_date = _parse_vietnamese_mrz_birth_date(vietnamese_mrz[0])
            if mrz_birth_date is not None:
                fields["date_of_birth"] = mrz_birth_date
                recognized_names.add("date_of_birth")
                confidences["date_of_birth"] = vietnamese_mrz[1]
                invalid_reason = "invalid_date:date_of_birth"
                if invalid_reason in review_reasons:
                    review_reasons.remove(invalid_reason)

    required = _required_fields(selection.expected_document_type, side)
    for name in sorted(required):
        if name not in recognized_names:
            review_reasons.append(f"missing_required:{name}")
        elif name not in fields and name not in DATE_FIELDS:
            review_reasons.append(f"missing_required:{name}")

    if selection.expected_document_type is DocumentType.ARC and side is DocumentSide.BACK:
        back_fields = sorted(
            name for name in recognized_names if name.startswith(ARC_BACK_PREFIXES)
        )
        if not back_fields:
            review_reasons.append("missing_required:arc_back_field")
        elif not any(confidences.get(name, 0.0) >= threshold for name in back_fields):
            review_reasons.extend(
                f"low_confidence:{name}" for name in back_fields if name in confidences
            )

    for name in sorted(required):
        confidence = confidences.get(name)
        if confidence is not None and confidence < threshold:
            review_reasons.append(f"low_confidence:{name}")

    return _result(
        matched_template_id=matched_template_id,
        side=side,
        fields=fields,
        confidences=confidences,
        review_reasons=review_reasons,
    )


def _mapping_sequence(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _matched_template_id(image: Mapping[str, Any]) -> int | None:
    matched = image.get("matchedTemplate")
    if not isinstance(matched, Mapping):
        return None
    template_id = matched.get("id")
    if isinstance(template_id, bool) or not isinstance(template_id, int):
        return None
    return template_id


def _document_side(
    selection: TemplateSelection,
    template_id: int,
    resolver: TemplateResolver,
) -> DocumentSide | None:
    if selection.expected_document_type is DocumentType.PASSPORT_COPY:
        return None
    return resolver.side_for_template(template_id)


def _required_fields(
    document_type: DocumentType,
    side: DocumentSide | None,
) -> frozenset[str]:
    if document_type is DocumentType.PASSPORT_COPY:
        return PASSPORT_REQUIRED
    if side is DocumentSide.FRONT:
        return ARC_FRONT_REQUIRED
    return frozenset()


def _parse_date(value: str, *, allow_day_first: bool = False):
    date_formats = _DATE_FORMATS
    if allow_day_first:
        date_formats += _VIETNAMESE_PASSPORT_DATE_FORMATS
    for date_format in date_formats:
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue

    match = _PASSPORT_DATE_PATTERN.fullmatch(value)
    if match is None:
        return None
    numeric_month = int(match.group("numeric_month"))
    english_month = _ENGLISH_MONTHS.get(match.group("english_month").upper())
    if english_month != numeric_month:
        return None
    try:
        return datetime(
            int(match.group("year")),
            numeric_month,
            int(match.group("day")),
        ).date()
    except ValueError:
        return None


def _parse_vietnamese_mrz_birth_date(value: str) -> date | None:
    match = _VNM_MRZ_BIRTH_PATTERN.search(re.sub(r"\s+", "", value).upper())
    if match is None:
        return None
    compact = match.group("birth")
    year = 2000 + int(compact[:2])
    today = date.today()
    if year > today.year:
        year -= 100
    try:
        parsed = date(year, int(compact[2:4]), int(compact[4:6]))
    except ValueError:
        return None
    if parsed > today:
        return None
    return parsed


def _confidence(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return max(0.0, min(1.0, float(value)))


def _review_result(reason: str) -> NormalizedOcrResult:
    return _result(
        matched_template_id=None,
        side=None,
        fields={},
        confidences={},
        review_reasons=[reason],
    )


def _result(
    *,
    matched_template_id: int | None,
    side: DocumentSide | None,
    fields: Mapping[str, FieldValue],
    confidences: Mapping[str, float],
    review_reasons: list[str],
) -> NormalizedOcrResult:
    status = OcrStatus.REVIEW_REQUIRED if review_reasons else OcrStatus.SUCCEEDED
    return NormalizedOcrResult(
        status=status,
        matched_template_id=matched_template_id,
        document_side=side,
        fields=dict(fields),
        field_confidences=dict(confidences),
        error_code=_primary_error_code(review_reasons),
        review_reasons=tuple(review_reasons),
    )


def _primary_error_code(review_reasons: list[str]) -> str | None:
    if not review_reasons:
        return None
    reason = review_reasons[0]
    if reason.startswith("invalid_date:"):
        return "INVALID_DATE"
    if reason.startswith("missing_required:"):
        return "MISSING_REQUIRED_FIELD"
    if reason.startswith("low_confidence:"):
        return "LOW_CONFIDENCE"
    return _ERROR_CODES.get(reason, "OCR_REVIEW_REQUIRED")
