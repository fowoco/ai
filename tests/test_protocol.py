from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
import zipfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import (
    CreateMessageResult,
    ElicitResult,
    ImageContent,
    SamplingCapability,
    TextContent,
)
import pytest

from test_hwpx import NS, make_fixture, make_table_fixture


def _make_stacked_table_fixture(path: Path) -> None:
    def cell(text: str, row: int, column: int) -> str:
        return (
            f'<hp:tc><hp:cellAddr colAddr="{column}" rowAddr="{row}"/>'
            '<hp:cellSpan colSpan="1" rowSpan="1"/>'
            f"<hp:p><hp:run><hp:t>{text}</hp:t></hp:run></hp:p></hp:tc>"
        )

    section = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<hs:sec xmlns:hs="{NS["hs"]}" xmlns:hp="{NS["hp"]}">'
        "<hp:tbl>"
        f"<hp:tr>{cell('성 Surname', 0, 0)}{cell('명 Given names', 0, 1)}{cell('', 0, 2)}</hp:tr>"
        f"<hp:tr>{cell('', 1, 0)}{cell('', 1, 1)}{cell('', 1, 2)}</hp:tr>"
        "</hp:tbl></hs:sec>"
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", "application/hwp+zip")
        archive.writestr("Contents/content.hpf", '<?xml version="1.0"?><package/>')
        archive.writestr(
            "Contents/header.xml",
            f'<?xml version="1.0"?><hh:head xmlns:hh="{NS["hh"]}" secCnt="1"/>',
        )
        archive.writestr("Contents/section0.xml", section)


@pytest.mark.parametrize(
    "vision_mode",
    [
        "pass",
        "invalid",
        "unsupported",
        "approval_unsupported",
        "overflow",
        "mismatch",
    ],
)
def test_stdio_server_lists_and_calls_tools(
    tmp_path: Path,
    vision_mode: str,
) -> None:
    source = tmp_path / "sample.hwpx"
    modified = tmp_path / "modified.hwpx"
    plan_source = tmp_path / "plan-form.hwpx"
    stacked_source = tmp_path / "stacked-form.hwpx"
    make_fixture(source)
    make_fixture(modified, text="변경된 문서")
    make_table_fixture(plan_source)
    _make_stacked_table_fixture(stacked_source)
    asyncio.run(_exercise_server(tmp_path, vision_mode))


async def _exercise_server(root: Path, vision_mode: str) -> None:
    fake_rhwp = root / "fake-rhwp"
    fake_rhwp.write_text(
        "#!/usr/bin/env python3\n"
        "from html import escape\n"
        "from pathlib import Path\n"
        "import sys\n"
        "import zipfile\n"
        "from xml.etree import ElementTree as ET\n"
        f"force_overflow = {vision_mode == 'overflow'!r}\n"
        f"force_mismatch = {vision_mode == 'mismatch'!r}\n"
        "if sys.argv[1] == 'info':\n"
        "    raise SystemExit(0)\n"
        "source = Path(sys.argv[2])\n"
        "output = Path(sys.argv[sys.argv.index('--output') + 1])\n"
        "output.mkdir(parents=True, exist_ok=True)\n"
        "with zipfile.ZipFile(source) as archive:\n"
        "    root = ET.fromstring(archive.read('Contents/section0.xml'))\n"
        "cells = [node for node in root.iter() if node.tag.rsplit('}', 1)[-1] == 'tc']\n"
        "if force_mismatch:\n"
        "    cells = cells[:-1]\n"
        "texts = [''.join(node.text or '' for node in cell.iter() if node.tag.rsplit('}', 1)[-1] == 't') for cell in cells]\n"
        "clips = []\n"
        "groups = []\n"
        "for index, (cell, value) in enumerate(zip(cells, texts), start=1):\n"
        "    address = next((node for node in cell if node.tag.rsplit('}', 1)[-1] == 'cellAddr'), None)\n"
        "    row = int(address.attrib.get('rowAddr', 0)) if address is not None else 0\n"
        "    column = int(address.attrib.get('colAddr', index - 1)) if address is not None else index - 1\n"
        "    x = column * 100\n"
        "    y = row * 30\n"
        "    clips.append(f'<clipPath id=\"cell-clip-{index}\"><rect x=\"{x}\" y=\"{y}\" width=\"100\" height=\"30\"/></clipPath>')\n"
        "    rendered = escape(value)\n"
        "    text_length = 150 if force_overflow and value == '계획 값' else max(len(value) * 8, 1)\n"
        "    text = f'<text transform=\"translate({x + 5},{y + 20})\" font-size=\"12\" textLength=\"{text_length}\">{rendered}</text>' if value else ''\n"
        "    groups.append(f'<g clip-path=\"url(#cell-clip-{index})\">{text}</g>')\n"
        "svg = '<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"200\" height=\"900\"><defs>' + ''.join(clips) + '</defs>' + ''.join(groups) + '</svg>'\n"
        "(output / 'page_001.svg').write_text(svg, encoding='utf-8')\n",
        encoding="utf-8",
    )
    fake_rhwp.chmod(0o755)
    server_parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "hwp_mcp.server"],
        env={
            **os.environ,
            "HWP_MCP_ROOT": str(root),
            "RHWP_COMMAND": str(fake_rhwp),
        },
    )

    async def sample_vision(_context, params):
        content = params.messages[0].content_as_list
        assert len([item for item in content if isinstance(item, ImageContent)]) == 6
        assert any(
            isinstance(item, TextContent) and "detail band" in item.text
            for item in content
        )
        response = (
            '{"verdict":"PASS","summary":"의도한 셀에만 입력됨","fields":[]}'
            if vision_mode == "invalid"
            else (
                '{"verdict":"PASS","summary":"의도한 셀에만 입력됨",'
                f'"fields":[{{"field_id":"{field_id}",'
                '"verdict":"PASS","reason":"셀 경계 안에 정상 배치"}]}'
            )
        )
        return CreateMessageResult(
            role="assistant",
            content=TextContent(
                type="text",
                text=response,
            ),
            model="test-vision",
        )

    async def approve_plan(_context, params):
        assert "계획 값" in params.message
        return ElicitResult(
            action="accept",
            content={"approved": True},
        )

    session_kwargs = {
        **(
            {"elicitation_callback": approve_plan}
            if vision_mode != "approval_unsupported"
            else {}
        ),
        **(
            {
            "sampling_callback": sample_vision,
            "sampling_capabilities": SamplingCapability(),
            }
            if vision_mode != "unsupported"
            else {}
        ),
    }
    async with stdio_client(server_parameters) as (read_stream, write_stream):
        async with ClientSession(
            read_stream,
            write_stream,
            **session_kwargs,
        ) as session:
            initialize_result = await session.initialize()
            assert "analysis_contract.version: 2" in (initialize_result.instructions or "")
            assert "hwp_mcp.hwpx" in (initialize_result.instructions or "")
            assert "submit_host_vision_review" in (
                initialize_result.instructions or ""
            )
            assert "이미지 입력" in (initialize_result.instructions or "")
            tools = await session.list_tools()
            tool_names = {tool.name for tool in tools.tools}
            assert {
                "inspect_document",
                "extract_text",
                "analyze_document",
                "render_document",
                "compare_document_versions",
                "fill_cells",
                "create_edit_plan",
                "approve_edit_plan",
                "apply_edit_plan",
                "confirm_visual_candidates",
                "review_document_vision",
                "submit_host_vision_review",
                "finalize_document",
                "normalize_field_value",
                "replace_text",
                "validate_document",
            } <= tool_names

            result = await session.call_tool(
                "inspect_document",
                arguments={"path": "sample.hwpx"},
            )

            assert result.isError is not True
            assert result.structuredContent["valid"] is True

            analyzed_result = await session.call_tool(
                "analyze_document",
                arguments={"path": "plan-form.hwpx"},
            )
            assert analyzed_result.isError is not True
            assert "field_candidates" not in analyzed_result.structuredContent
            assert "field_segments" not in analyzed_result.structuredContent
            assert analyzed_result.structuredContent["svg_analysis"]["method"] == "rhwp_svg_geometry"
            if vision_mode == "mismatch":
                assert analyzed_result.structuredContent["svg_analysis"]["status"] == "NEEDS_HUMAN"
                assert analyzed_result.structuredContent["analysis_contract"] == {
                    "version": 2,
                    "stage": "XML_SVG_NEEDS_HUMAN",
                    "registry_source": None,
                    "interview_ready": False,
                }
                assert analyzed_result.structuredContent["field_registry"] == []
                return
            assert analyzed_result.structuredContent["svg_analysis"]["status"] == "MAPPED"
            assert analyzed_result.structuredContent["analysis_contract"] == {
                "version": 2,
                "stage": "XML_SVG_MAPPED",
                "registry_source": "rhwp_svg",
                "interview_ready": False,
            }
            assert analyzed_result.structuredContent["interview_ready"] is False
            assert (
                analyzed_result.structuredContent["next_action"]
                == "confirm_visual_candidates"
            )
            assert "xml_field_candidates" not in analyzed_result.structuredContent
            assert analyzed_result.structuredContent["field_registry"][0]["visual_regions"]
            assert all(
                field["constraints"]["visual_source"] == "rhwp_svg"
                for field in analyzed_result.structuredContent["field_registry"]
            )
            field_id = analyzed_result.structuredContent["field_registry"][0]["field_id"]
            stacked_result = await session.call_tool(
                "analyze_document",
                arguments={"path": "stacked-form.hwpx"},
            )
            assert stacked_result.isError is not True
            stacked_registry = stacked_result.structuredContent["field_registry"]
            assert next(
                field for field in stacked_registry if field["label"] == "성 Surname"
            )["target_id"] == "section0.table0.row1.cell0"
            assert next(
                field for field in stacked_registry if field["label"] == "명 Given names"
            )["target_id"] == "section0.table0.row1.cell1"
            confirmed_result = await session.call_tool(
                "confirm_visual_candidates",
                arguments={"path": "plan-form.hwpx", "candidates": []},
            )
            assert confirmed_result.isError is not True
            assert confirmed_result.structuredContent["alignment_status"] == "CONSISTENT"
            assert confirmed_result.structuredContent["interview_ready"] is True
            assert (
                confirmed_result.structuredContent["next_action"]
                == "collect_field_values"
            )

            render_result = await session.call_tool(
                "render_document",
                arguments={"path": "sample.hwpx", "output_dir": "rendered"},
            )

            assert render_result.isError is not True
            assert render_result.structuredContent["pages"] == 1

            compare_result = await session.call_tool(
                "compare_document_versions",
                arguments={
                    "original_path": "sample.hwpx",
                    "modified_path": "modified.hwpx",
                    "output_dir": "comparison",
                },
            )

            assert compare_result.isError is not True
            assert compare_result.structuredContent["structure"]["changed_paragraphs"]

            plan_result = await session.call_tool(
                "create_edit_plan",
                arguments={
                    "path": "plan-form.hwpx",
                    "edits": [
                        {
                            "target_id": "section0.table0.row0.cell1",
                            "expected_text": "",
                            "value": "계획 값",
                            "label": "업체명",
                        }
                    ],
                    "dispositions": {field_id: "provided"},
                },
            )

            assert plan_result.isError is not True
            plan = plan_result.structuredContent
            assert plan["status"] == "WAITING_APPROVAL"

            approval_result = await session.call_tool(
                "approve_edit_plan",
                arguments={
                    "path": "plan-form.hwpx",
                    "plan_id": plan["plan_id"],
                },
            )
            if vision_mode == "approval_unsupported":
                assert approval_result.isError is True
                assert "elicitation" in str(approval_result.content)
                assert not list(root.glob("*/attempts/*/modified.hwpx"))
                return
            assert approval_result.isError is not True
            assert approval_result.structuredContent["status"] == "APPROVED"

            apply_result = await session.call_tool(
                "apply_edit_plan",
                arguments={
                    "path": "plan-form.hwpx",
                    "plan_id": plan["plan_id"],
                },
            )

            if vision_mode == "overflow":
                assert apply_result.isError is True
                assert "rhwp SVG geometry" in str(apply_result.content)
                return
            assert apply_result.isError is not True
            assert apply_result.structuredContent["status"] == "PENDING_VISION_REVIEW"
            assert apply_result.structuredContent["review"]["expected_changes"]["passed"] is True
            assert apply_result.structuredContent["review"]["visual"]["layout_warnings_preserved"] is True
            assert apply_result.structuredContent["review"]["visual"]["svg_geometry"]["passed"] is True
            assert apply_result.structuredContent["review"]["visual"]["svg_geometry"]["field_checks"][0]["rendered_value_present"] is True

            vision_result = await session.call_tool(
                "review_document_vision",
                arguments={
                    "path": "plan-form.hwpx",
                    "plan_id": plan["plan_id"],
                },
            )
            assert vision_result.isError is not True
            if vision_mode == "unsupported":
                request = vision_result.structuredContent
                assert request["status"] == "VISION_REVIEW_REQUIRED"
                assert request["next_action"] == "submit_host_vision_review"
                evidence_view_ids = [
                    view["view_id"]
                    for view in request["views"]
                    if field_id in view["field_ids"]
                ]
                host_result = await session.call_tool(
                    "submit_host_vision_review",
                    arguments={
                        "path": "plan-form.hwpx",
                        "plan_id": plan["plan_id"],
                        "review_id": request["review_id"],
                        "reviewer": {
                            "provider": "test-host",
                            "model": "test-vision",
                            "capabilities": ["image_input"],
                        },
                        "decision": {
                            "verdict": "PASS",
                            "summary": "원본 대비 올바른 셀에 배치됨",
                            "fields": [
                                {
                                    "field_id": field_id,
                                    "verdict": "PASS",
                                    "reason": "업체명 라벨 오른쪽 셀 경계 안에 배치됨",
                                    "evidence_view_ids": evidence_view_ids,
                                }
                            ],
                        },
                    },
                )
                assert host_result.isError is not True
                assert host_result.structuredContent["verdict"] == "PASS"
                assert (
                    host_result.structuredContent["source"]
                    == "host_vision_submission"
                )
            else:
                expected_verdict = (
                    "PASS" if vision_mode == "pass" else "NEEDS_HUMAN"
                )
                assert vision_result.structuredContent["verdict"] == expected_verdict
            if vision_mode == "pass":
                assert vision_result.structuredContent["model"] == "test-vision"

            finalize_result = await session.call_tool(
                "finalize_document",
                arguments={
                    "path": "plan-form.hwpx",
                    "plan_id": plan["plan_id"],
                },
            )
            if vision_mode in {"pass", "unsupported"}:
                assert finalize_result.isError is not True
                assert finalize_result.structuredContent["status"] == "VERIFIED_FINAL"
            else:
                assert finalize_result.isError is True
                assert not list(root.glob("*/final/*.hwpx"))

            normalized_result = await session.call_tool(
                "normalize_field_value",
                arguments={
                    "request": {
                        "field_type": "phone",
                        "value": "01012345678",
                    }
                },
            )

            assert normalized_result.isError is not True
            assert normalized_result.structuredContent["normalized"] == "010-1234-5678"
