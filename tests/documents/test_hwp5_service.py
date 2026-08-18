import struct
from pathlib import Path

from PIL import Image, ImageDraw

from app.documents.hwp5 import Hwp5BinaryDocument, Hwp5DocumentService

INTEGRATED_TEMPLATE_ID = "immigration_integrated_application_v34"
LABOR_TEMPLATE_ID = "standard_labor_contract_v6"


def _signature(path: Path) -> None:
    canvas = Image.new("RGBA", (700, 200), (255, 255, 255, 0))
    draw = ImageDraw.Draw(canvas)
    draw.line((20, 150, 220, 40, 430, 155, 680, 30), fill="black", width=12)
    canvas.save(path)


def test_registry_loads_and_identifies_all_bundled_templates() -> None:
    service = Hwp5DocumentService()
    templates = service.templates()

    assert len(templates) == 4
    for template in templates:
        assert service.identify(template.source_path).template_id == template.template_id


def test_generate_standard_labor_contract_body_at_registered_positions(tmp_path: Path) -> None:
    """표준근로계약서 본문 값과 체크는 등록된 한국어 문단에만 반영된다."""
    output = tmp_path / "labor-contract.hwp"
    result = Hwp5DocumentService().generate(
        LABOR_TEMPLATE_ID,
        output,
        values={
            "contract_months": "12",
            "use_probation": True,
            "probation_three_months": True,
            "industry": "제조업",
            "business_description": "자동차 부품 제조 및 조립",
            "job_description": "금속 부품 조립",
            "work_location": "경기도 안산시 단원구 산단로 000",
            "working_hours": "09시 00분 ~ 18시 00분",
            "daily_overtime_hours": "2",
            "daily_overtime_limit": "4",
            "shift_two_two": True,
            "recess_minutes": "60",
            "holiday_sunday": True,
            "holiday_legal": True,
            "holiday_paid": True,
            "holiday_every_saturday": True,
            "monthly_wage": "2,500,000",
            "base_wage": "2,400,000",
            "fixed_allowances": "식대 수당: 100,000원",
            "bonus": "0",
            "probation_wage_detail": "2,250,000원, 3개월 이내 근무기간 2,400,000원",
            "payment_date_detail": (
                "매월 (25)일 또는 매주 (금)요일. 다만, 임금 지급일이 "
                "공휴일인 경우에는 전날에 지급함."
            ),
            "payment_bank": True,
            "accommodation_provided": True,
            "accommodation_workplace_building": True,
            "accommodation_cost": "50,000",
            "meal_breakfast": True,
            "meal_lunch": True,
            "meal_dinner": True,
            "meal_cost": "30,000",
        },
    )

    paragraphs = Hwp5BinaryDocument(output).paragraphs()

    assert result.template_id == LABOR_TEMPLATE_ID
    assert paragraphs[48].text == "09시 00분 ~ 18시 00분"
    assert paragraphs[49].text == (
        "- 1일 평균 시간외 근로시간: 2시간(사업장 사정에 따라 변동 가능: 4시간 이내)"
    )
    assert paragraphs[50].text.startswith("- 교대제 ([√]2조2교대")
    assert paragraphs[60].text == "1일 60분"
    assert "(2,500,000)원" in paragraphs[73].text
    assert paragraphs[87].text.startswith("매월 (25)일")
    assert "[√ ]통장 입금" in paragraphs[92].text
    assert "[√ ]제공" in paragraphs[99].text
    assert "[√]사업장 건물" in paragraphs[101].text
    assert "[√ ]조식" in paragraphs[104].text
    assert "(12)" in paragraphs[29].text
    assert "[√] Included" in paragraphs[31].text
    assert "[√] 3 months" in paragraphs[31].text
    assert paragraphs[34].text == "근로장소: 경기도 안산시 단원구 산단로 000"
    assert paragraphs[36].text == "Place of employment: 경기도 안산시 단원구 산단로 000"
    assert paragraphs[43].text == "- Industry: 제조업"
    assert paragraphs[44].text == "- Business description: 자동차 부품 제조 및 조립"
    assert paragraphs[45].text.startswith("- Job description: 금속 부품 조립")
    assert paragraphs[67].text.startswith("[√]Sunday [√]Legal holiday")
    assert paragraphs[68].text.startswith("[√]Every saturday")
    assert "(2,500,000)won" in paragraphs[80].text
    assert "(2,400,000)won" in paragraphs[81].text
    assert "[√ ]By direct deposit" in paragraphs[95].text
    assert "[√ ]breakfast" in paragraphs[113].text
    assert "[√ ]lunch" in paragraphs[113].text
    assert "[√ ]dinner" in paragraphs[113].text

    paragraph = Hwp5BinaryDocument(output).paragraphs()[49]
    records = Hwp5BinaryDocument(output)._records[0]
    end = next(
        index
        for index in range(paragraph.record_index + 1, len(records))
        if records[index].tag_id == 66
    )
    line_segment = next(
        records[index]
        for index in range(paragraph.record_index + 1, end)
        if records[index].tag_id == 69
    )
    assert [
        struct.unpack_from("<I", line_segment.payload, offset)[0]
        for offset in range(0, len(line_segment.payload), 36)
    ] == [0, 22]


def test_generate_text_checkbox_photo_and_signature(tmp_path: Path) -> None:
    service = Hwp5DocumentService()
    photo = tmp_path / "photo.jpg"
    signature = tmp_path / "signature.png"
    output = tmp_path / "filled.hwp"
    Image.new("RGB", (350, 450), "royalblue").save(photo)
    _signature(signature)

    result = service.generate(
        INTEGRATED_TEMPLATE_ID,
        output,
        values={
            "family_name": "HONG",
            "given_names": "GILDONG",
            "application_stay_extension": True,
        },
        images={
            "photo": photo,
            "applicant_signature": signature,
        },
    )

    assert result.destination == output.resolve()
    assert result.template_id == INTEGRATED_TEMPLATE_ID
    assert result.changed_fields == (
        "family_name",
        "given_names",
        "application_stay_extension",
        "photo",
        "applicant_signature",
    )

    reopened = Hwp5BinaryDocument(output)
    assert reopened.paragraphs()[46].text == "HONG"
    assert reopened.paragraphs()[47].text == "GILDONG"
    assert "[√ " in reopened.paragraphs()[24].text
    assert [image.extension for image in reopened.embedded_images()] == ["jpg", "png"]
