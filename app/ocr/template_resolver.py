from app.ocr.models import (
    DocumentSide,
    DocumentType,
    TemplateResolutionError,
    TemplateSelection,
)

PASSPORT_TEMPLATE_IDS = {
    "KOR": 43019,
    "PHL": 43021,
    "JPN": 43022,
    "CHN": 43023,
    "VNM": 43038,
}
PASSPORT_COUNTRY_ALIASES = {
    "KR": "KOR",
    "PH": "PHL",
    "JP": "JPN",
    "CN": "CHN",
    "VN": "VNM",
}
DEFAULT_PASSPORT_COUNTRY = "VNM"
ARC_TEMPLATE_IDS = (43024, 43025)
ARC_TEMPLATE_SIDES = {
    43024: DocumentSide.FRONT,
    43025: DocumentSide.BACK,
}


class TemplateResolver:
    def resolve(
        self,
        document_type: DocumentType,
        country_code: str | None,
    ) -> TemplateSelection:
        if document_type is DocumentType.ARC:
            return TemplateSelection(
                template_ids=ARC_TEMPLATE_IDS,
                expected_document_type=DocumentType.ARC,
            )

        normalized_country = (country_code or "").strip().upper()
        if not normalized_country:
            normalized_country = DEFAULT_PASSPORT_COUNTRY
        normalized_country = PASSPORT_COUNTRY_ALIASES.get(
            normalized_country,
            normalized_country,
        )

        template_id = PASSPORT_TEMPLATE_IDS.get(normalized_country)
        if template_id is None:
            raise TemplateResolutionError("unsupported passport country")
        return TemplateSelection(
            template_ids=(template_id,),
            expected_document_type=DocumentType.PASSPORT_COPY,
        )

    def side_for_template(self, template_id: int) -> DocumentSide:
        try:
            return ARC_TEMPLATE_SIDES[template_id]
        except KeyError as exc:
            raise TemplateResolutionError("unexpected matched template") from exc
