import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from app.documents.records import (
    DocumentRecordError,
    DocumentRecordGenerationService,
    DocumentRecordParseError,
    TextRecordReader,
)
from app.documents.records.rules import TEMPLATE_RULES

RECORD_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "documents" / "records"
TEMPLATE_IDS = (
    "identity_guaranty_v129",
    "employment_extension_application_v12_3",
    "immigration_integrated_application_v34",
    "standard_labor_contract_v6",
)
ERD_MAPPINGS = {
    "identity_guaranty_v129": {
        "foreign_family_name": "foreign_family_name",
        "foreign_given_name": "foreign_given_name",
        "foreign_name_hanja": "foreign_name_hanja",
        "foreign_birthdate": "foreign_birthdate",
        "foreign_male": "foreign_male",
        "foreign_nationality": "worker.nationality",
        "foreign_passport": "foreign_passport",
        "foreign_korea_address": "foreign_korea_address",
        "foreign_phone": "worker.phone",
        "stay_purpose": "stay_purpose",
        "guarantor_name": "guarantor_name",
        "guarantor_name_hanja": "guarantor_name_hanja",
        "guarantor_nationality": "guarantor_nationality",
        "guarantor_male": "guarantor_male",
        "guarantor_passport_or_birthdate": "guarantor_passport_or_birthdate",
        "guarantor_phone": "guarantor_phone",
        "guarantor_address": "guarantor_address",
        "relationship": "relationship",
        "workplace": "company.name",
        "position": "position",
        "workplace_address": "workplace_address",
        "guarantee_period": "guarantee_period",
        "guarantee_date": "guarantee_date",
        "signature_guarantor_name": "guarantor_name",
    },
    "employment_extension_application_v12_3": {
        "workplace_name": "company.name",
        "workplace_phone": "workplace_phone",
        "workplace_address": "workplace_address",
        "representative": "representative",
        "business_type": "business_type",
        "business_number": "business_number",
        "check_eligible_industry": "check_eligible_industry",
        "check_no_adjustment_dismissal": "check_no_adjustment_dismissal",
        "check_no_unpaid_wages": "check_no_unpaid_wages",
        "check_insurance": "check_insurance",
        "check_departure_guarantee": "check_departure_guarantee",
        "employee_1_serial": "worker.employee_no",
        "employee_1_name": "worker.legal_name",
        "employee_1_resident_number": "employee_1_resident_number",
        "employee_1_nationality": "worker.nationality",
        "employee_1_passport_number": "employee_1_passport_number",
        "employee_1_expiry_date": "worker.stay_expiry",
        "application_date": "application_date",
        "applicant_name": "applicant_name",
        "submission_authority": "submission_authority",
        "consent_applicant_name": "applicant_name",
    },
    "immigration_integrated_application_v34": {
        "family_name": "family_name",
        "given_names": "given_names",
        "birth_year": "birth_year",
        "birth_month": "birth_month",
        "birth_day": "birth_day",
        "nationality": "worker.nationality",
        "passport_number": "passport_number",
        "passport_issue_date": "passport_issue_date",
        "passport_expiry_date": "passport_expiry_date",
        "address_in_korea": "address_in_korea",
        "telephone": "telephone",
        "cell_phone": "worker.phone",
        "home_country_address": "home_country_address",
        "home_country_phone": "home_country_phone",
        "current_workplace": "company.name",
        "current_business_number": "current_business_number",
        "current_workplace_phone": "current_workplace_phone",
        "annual_income": "annual_income",
        "occupation": "occupation",
        "email": "worker.email",
        "application_date": "application_date",
    },
    "standard_labor_contract_v6": {
        "enterprise_name": "company.name",
        "enterprise_phone": "enterprise_phone",
        "enterprise_address": "enterprise_address",
        "employer_name": "employer_name",
        "business_number": "business_number",
        "employee_name": "worker.legal_name",
        "employee_birthdate": "employee_birthdate",
        "employee_home_address": "employee_home_address",
        "industry": "industry",
        "business_description": "business_description",
        "job_description": "job_description",
        "contract_date": "contract_date",
    },
}


@pytest.mark.parametrize("template_id", TEMPLATE_IDS)
def test_generate_hwpx_from_mock_database_txt(
    tmp_path: Path,
    template_id: str,
) -> None:
    reader = TextRecordReader()
    source = RECORD_ROOT / f"{template_id}.txt"
    record = reader.read(source)
    output = tmp_path / f"{template_id}.hwpx"

    result = DocumentRecordGenerationService().generate_from_txt(
        source,
        output,
        template_id=template_id,
    )

    assert result.destination == output.resolve()
    assert result.template_id == template_id
    expected_mapping = dict(ERD_MAPPINGS[template_id])
    for rule in TEMPLATE_RULES[template_id]:
        for record_key in (rule.source_key, *rule.record_keys):
            if record_key in record:
                expected_mapping[rule.source_key] = record_key
                break
    assert set(result.changed_fields) == set(expected_mapping)
    with zipfile.ZipFile(output) as package:
        assert package.testzip() is None
        section_xml = package.read("Contents/section0.xml").decode("utf-8")
    rule_by_source = {
        rule.source_key: rule for rule in TEMPLATE_RULES[template_id]
    }
    for source_key, record_key in expected_mapping.items():
        rule = rule_by_source[source_key]
        if record[record_key].casefold() == "true":
            expected_value = "[v]"
        else:
            expected_value = record[record_key]
            if rule.digits_only:
                expected_value = "".join(
                    character
                    for character in expected_value
                    if character.isdecimal()
                )
            if rule.value_index is not None:
                expected_value = expected_value[rule.value_index]
        assert expected_value in section_xml


def test_identity_guaranty_places_hanja_gender_date_and_signature_name(
    tmp_path: Path,
) -> None:
    source = RECORD_ROOT / "identity_guaranty_v129.txt"
    output = tmp_path / "identity.hwpx"

    DocumentRecordGenerationService().generate_from_txt(
        source,
        output,
        template_id="identity_guaranty_v129",
    )

    with zipfile.ZipFile(output) as package:
        root = ET.fromstring(package.read("Contents/section0.xml"))
    hp = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
    table = next(root.iter(f"{hp}tbl"))
    cells: dict[tuple[int, int], str] = {}
    for cell in table.iter(f"{hp}tc"):
        address = cell.find(f"{hp}cellAddr")
        if address is None:
            continue
        key = (
            int(address.attrib["rowAddr"]),
            int(address.attrib["colAddr"]),
        )
        cells[key] = "".join(text.text or "" for text in cell.iter(f"{hp}t"))

    assert cells[(3, 5)] == "漢字  阮文安"
    assert cells[(4, 7)] == "[v]남   [  ]여"
    assert cells[(10, 5)] == "漢字  金民洙"
    assert cells[(11, 7)] == "[v]남   [  ]여"
    assert cells[(21, 0)] == "2026년 7월 24일"
    assert cells[(22, 4)] == "김민수"


def test_employment_extension_places_facts_authority_and_consent_applicant(
    tmp_path: Path,
) -> None:
    source = RECORD_ROOT / "employment_extension_application_v12_3.txt"
    output = tmp_path / "employment-extension.hwpx"

    DocumentRecordGenerationService().generate_from_txt(
        source,
        output,
        template_id="employment_extension_application_v12_3",
    )

    with zipfile.ZipFile(output) as package:
        root = ET.fromstring(package.read("Contents/section0.xml"))
    hp = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
    table = next(root.iter(f"{hp}tbl"))
    cells: dict[tuple[int, int], str] = {}
    for cell in table.iter(f"{hp}tc"):
        address = cell.find(f"{hp}cellAddr")
        if address is None:
            continue
        key = (
            int(address.attrib["rowAddr"]),
            int(address.attrib["colAddr"]),
        )
        cells[key] = "".join(text.text or "" for text in cell.iter(f"{hp}t"))

    assert cells[(9, 4)].count("[v]") == 5
    assert cells[(20, 0)] == "2026년 7월 24일"
    assert cells[(21, 0)] == "신청인  김민수"
    assert cells[(22, 0)] == "경기지방고용노동청안산지청장 귀하"
    assert cells[(29, 14)] == "김민수"


def test_integrated_application_places_options_and_split_registration_number(
    tmp_path: Path,
) -> None:
    source = RECORD_ROOT / "immigration_integrated_application_v34.txt"
    output = tmp_path / "integrated-application.hwpx"

    DocumentRecordGenerationService().generate_from_txt(
        source,
        output,
        template_id="immigration_integrated_application_v34",
    )

    with zipfile.ZipFile(output) as package:
        root = ET.fromstring(package.read("Contents/section0.xml"))
    hp = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
    table = next(root.iter(f"{hp}tbl"))
    cells: dict[tuple[int, int], str] = {}
    for cell in table.iter(f"{hp}tc"):
        address = cell.find(f"{hp}cellAddr")
        if address is None:
            continue
        key = (
            int(address.attrib["rowAddr"]),
            int(address.attrib["colAddr"]),
        )
        cells[key] = "".join(text.text or "" for text in cell.iter(f"{hp}t"))

    assert "[v] 체류기간 연장허가" in cells[(7, 0)]
    assert cells[(15, 31)] == "[v]남 M[ ]여 F"
    registration_columns = (9, 11, 15, 16, 19, 21, 24, 26, 29, 31, 33, 35, 38)
    assert "".join(cells[(17, column)] for column in registration_columns) == (
        "9503215000000"
    )
    assert "미취학[v]" in cells[(22, 2)]
    assert "Non-school[v]" in cells[(22, 2)]
    assert cells[(29, 41)] == "NGUYEN VAN AN"
    assert cells[(34, 1)] == "NGUYEN VAN AN"
    assert cells[(25, 12)] == ""
    assert cells[(27, 12)] == ""
    assert cells[(28, 30)] == ""


def test_integrated_application_rejects_short_registration_number(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        DocumentRecordError,
        match="foreign_registration_digit_13.*at least 13 characters",
    ):
        DocumentRecordGenerationService().generate(
            {"foreign_registration_number": "950321-500000"},
            tmp_path / "invalid.hwpx",
            template_id="immigration_integrated_application_v34",
        )


def test_integrated_application_supports_every_application_checkbox(
    tmp_path: Path,
) -> None:
    checkbox_cells = {
        "application_foreign_registration": (4, 0),
        "application_activity_permission": (4, 14),
        "application_card_reissue": (6, 0),
        "application_workplace_change": (6, 14),
        "application_stay_extension": (7, 0),
        "application_reentry": (7, 14),
        "application_status_change": (8, 0),
        "application_address_change": (8, 14),
        "application_status_grant": (10, 0),
        "application_information_change": (10, 14),
    }
    output = tmp_path / "all-application-options.hwpx"

    DocumentRecordGenerationService().generate(
        dict.fromkeys(checkbox_cells, True),
        output,
        template_id="immigration_integrated_application_v34",
    )

    with zipfile.ZipFile(output) as package:
        root = ET.fromstring(package.read("Contents/section0.xml"))
    hp = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
    table = next(root.iter(f"{hp}tbl"))
    cells: dict[tuple[int, int], str] = {}
    for cell in table.iter(f"{hp}tc"):
        address = cell.find(f"{hp}cellAddr")
        if address is not None:
            cells[
                (
                    int(address.attrib["rowAddr"]),
                    int(address.attrib["colAddr"]),
                )
            ] = "".join(text.text or "" for text in cell.iter(f"{hp}t"))

    assert all("[v]" in cells[coordinates] for coordinates in checkbox_cells.values())


def test_standard_labor_contract_places_all_example_working_conditions(
    tmp_path: Path,
) -> None:
    source = RECORD_ROOT / "standard_labor_contract_v6.txt"
    output = tmp_path / "standard-labor-contract.hwpx"

    DocumentRecordGenerationService().generate_from_txt(
        source,
        output,
        template_id="standard_labor_contract_v6",
    )

    with zipfile.ZipFile(output) as package:
        root = ET.fromstring(package.read("Contents/section0.xml"))
    hp = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
    tables = list(root.iter(f"{hp}tbl"))

    def cell_text(table_index: int, row: int, column: int) -> str:
        for cell in tables[table_index].iter(f"{hp}tc"):
            address = cell.find(f"{hp}cellAddr")
            if address is not None and (
                int(address.attrib["rowAddr"]),
                int(address.attrib["colAddr"]),
            ) == (row, column):
                return "".join(text.text or "" for text in cell.iter(f"{hp}t"))
        raise AssertionError(f"missing cell: {table_index}:{row},{column}")

    contract_period = cell_text(0, 11, 2)
    assert "2026-09-16" in contract_period
    assert "2027-09-15" in contract_period
    assert "[v]미활용" in contract_period
    assert "경기도 안산시 단원구 산단로 000" in cell_text(0, 13, 2)
    workplace_cell = next(
        cell
        for cell in tables[0].iter(f"{hp}tc")
        if (address := cell.find(f"{hp}cellAddr")) is not None
        and (
            int(address.attrib["rowAddr"]),
            int(address.attrib["colAddr"]),
        )
        == (13, 2)
    )
    line_break = next(workplace_cell.iter(f"{hp}lineBreak"))
    assert line_break.tail == (
        "※ 근로자를 이 계약서에서 정한 장소 외에서 근로하게 해서는 안 됨."
    )
    assert "09:00" in cell_text(0, 17, 2)
    assert "18:00" in cell_text(0, 17, 2)
    assert "1일 60분" == cell_text(0, 19, 2)
    assert cell_text(0, 21, 2).count("[v]") == 4

    payment = cell_text(1, 1, 1)
    assert "2,500,000" in payment
    assert "2,300,000" in payment
    assert "식대 수당: 200,000원" in payment
    assert "[v]통장 입금" in cell_text(1, 5, 1)

    accommodations = cell_text(1, 7, 1)
    assert "[v]제공" in accommodations
    assert "[v]사업장 건물" in accommodations
    assert "[v]중식" in accommodations
    assert "매월 100,000원" in accommodations

    signatures = cell_text(1, 15, 0)
    assert "사용자: 김민수" in signatures
    assert "근로자: NGUYEN VAN AN" in signatures


def test_text_record_reader_rejects_duplicate_keys(tmp_path: Path) -> None:
    source = tmp_path / "duplicate.txt"
    source.write_text("name=first\nname=second\n", encoding="utf-8")

    with pytest.raises(DocumentRecordParseError, match="duplicate key"):
        TextRecordReader().read(source)


def test_record_generation_requires_at_least_one_mapped_field(
    tmp_path: Path,
) -> None:
    with pytest.raises(DocumentRecordError, match="no fields supported"):
        DocumentRecordGenerationService().generate(
            {"record_id": "unmapped-only"},
            tmp_path / "output.hwpx",
            template_id="identity_guaranty_v129",
        )


def test_document_specific_value_overrides_erd_projection(
    tmp_path: Path,
) -> None:
    output = tmp_path / "override.hwpx"

    DocumentRecordGenerationService().generate(
        {
            "worker.nationality": "DB-NATIONALITY",
            "nationality": "CONFIRMED-NATIONALITY",
        },
        output,
        template_id="immigration_integrated_application_v34",
    )

    with zipfile.ZipFile(output) as package:
        section_xml = package.read("Contents/section0.xml").decode("utf-8")
    assert "CONFIRMED-NATIONALITY" in section_xml
    assert "DB-NATIONALITY" not in section_xml
