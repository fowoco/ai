from __future__ import annotations

from pathlib import Path
import zipfile

import pytest

from hwp_mcp.hwpx import (
    DocumentError,
    _analyze_xml_document,
    extract_text,
    fill_cells,
    inspect_document,
    replace_text,
    validate_document,
)


NS = {
    "hp": "http://www.hancom.co.kr/hwpml/2011/paragraph",
    "hs": "http://www.hancom.co.kr/hwpml/2011/section",
    "hh": "http://www.hancom.co.kr/hwpml/2011/head",
}


def make_fixture(path: Path, text: str = "안녕하세요 MCP") -> None:
    header = f'''<?xml version="1.0" encoding="UTF-8"?>
<hh:head xmlns:hh="{NS['hh']}" secCnt="1" />'''.encode()
    section = f'''<?xml version="1.0" encoding="UTF-8"?>
<hs:sec xmlns:hs="{NS['hs']}" xmlns:hp="{NS['hp']}">
  <hp:p><hp:run><hp:t>{text}</hp:t></hp:run></hp:p>
</hs:sec>'''.encode()
    content = b'''<?xml version="1.0" encoding="UTF-8"?>
<opf:package xmlns:opf="http://www.idpf.org/2007/opf/" />'''
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", "application/hwp+zip")
        archive.writestr("Contents/content.hpf", content)
        archive.writestr("Contents/header.xml", header)
        archive.writestr("Contents/section0.xml", section)


def make_table_fixture(path: Path, label: str = "업체명") -> None:
    header = f'''<?xml version="1.0" encoding="UTF-8"?>
<hh:head xmlns:hh="{NS['hh']}" secCnt="1" />'''.encode()
    section = f'''<?xml version="1.0" encoding="UTF-8"?>
<hs:sec xmlns:hs="{NS['hs']}" xmlns:hp="{NS['hp']}">
  <hp:tbl>
    <hp:tr>
      <hp:tc><hp:cellAddr colAddr="0" rowAddr="0" /><hp:cellSpan colSpan="1" rowSpan="1" /><hp:p><hp:run><hp:t>{label}</hp:t></hp:run></hp:p></hp:tc>
      <hp:tc><hp:cellAddr colAddr="1" rowAddr="0" /><hp:cellSpan colSpan="1" rowSpan="1" /><hp:p><hp:run><hp:t></hp:t></hp:run></hp:p></hp:tc>
    </hp:tr>
  </hp:tbl>
</hs:sec>'''.encode()
    content = b'''<?xml version="1.0" encoding="UTF-8"?>
<opf:package xmlns:opf="http://www.idpf.org/2007/opf/" />'''
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", "application/hwp+zip")
        archive.writestr("Contents/content.hpf", content)
        archive.writestr("Contents/header.xml", header)
        archive.writestr("Contents/section0.xml", section)


def test_validate_and_extract(tmp_path: Path) -> None:
    source = tmp_path / "sample.hwpx"
    make_fixture(source)

    report = validate_document(source)
    extracted = extract_text(source)

    assert report["valid"] is True
    assert extracted["text"] == "안녕하세요 MCP"
    assert extracted["paragraph_count"] == 1


def test_replace_writes_new_validated_file(tmp_path: Path) -> None:
    source = tmp_path / "sample.hwpx"
    output = tmp_path / "edited.hwpx"
    make_fixture(source)

    result = replace_text(source, output, "MCP", "HWPX MCP")

    assert result["replacements"] == 1
    assert source.exists()
    assert output.exists()
    assert extract_text(output)["text"] == "안녕하세요 HWPX MCP"
    with zipfile.ZipFile(output) as archive:
        assert archive.infolist()[0].filename == "mimetype"
        assert archive.infolist()[0].compress_type == zipfile.ZIP_STORED


def test_replace_requires_new_output(tmp_path: Path) -> None:
    source = tmp_path / "sample.hwpx"
    make_fixture(source)

    with pytest.raises(DocumentError):
        replace_text(source, source, "MCP", "X")


def test_analyze_returns_table_cell_targets(tmp_path: Path) -> None:
    source = tmp_path / "form.hwpx"
    make_table_fixture(source)

    manifest = _analyze_xml_document(source)

    assert manifest["table_count"] == 1
    assert manifest["field_candidates"][0]["label"] == "업체명"
    assert manifest["field_candidates"][0]["target_id"] == "section0.table0.row0.cell1"
    assert manifest["sections"][0]["tables"][0]["row_count"] == 1
    cells = manifest["sections"][0]["tables"][0]["cells"]
    assert cells[0]["id"] == "section0.table0.row0.cell0"
    assert cells[0]["text"] == "업체명"


def test_fill_cells_appends_confirmed_values(tmp_path: Path) -> None:
    source = tmp_path / "form.hwpx"
    output = tmp_path / "filled.hwpx"
    make_table_fixture(source)

    result = fill_cells(
        source,
        output,
        [
            {
                "target_id": "section0.table0.row0.cell1",
                "expected_text": "",
                "value": "ABC",
            }
        ],
    )

    assert result["applied"] == 1
    assert result["validated"] is True
    assert "ABC" in extract_text(output)["text"]


def test_hwp_is_reported_as_unsupported(tmp_path: Path) -> None:
    source = tmp_path / "sample.hwp"
    source.write_bytes(b"not a real hwp")

    metadata = inspect_document(source)

    assert metadata["format"] == "hwp"
    assert metadata["editable"] is False
