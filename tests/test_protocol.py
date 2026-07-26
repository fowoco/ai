from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import (
    CreateMessageResult,
    ImageContent,
    SamplingCapability,
    TextContent,
)
import pytest

from test_hwpx import make_fixture, make_table_fixture


@pytest.mark.parametrize("vision_mode", ["pass", "invalid", "unsupported"])
def test_stdio_server_lists_and_calls_tools(
    tmp_path: Path,
    vision_mode: str,
) -> None:
    source = tmp_path / "sample.hwpx"
    modified = tmp_path / "modified.hwpx"
    plan_source = tmp_path / "plan-form.hwpx"
    make_fixture(source)
    make_fixture(modified, text="변경된 문서")
    make_table_fixture(plan_source)
    asyncio.run(_exercise_server(tmp_path, vision_mode))


async def _exercise_server(root: Path, vision_mode: str) -> None:
    fake_rhwp = root / "fake-rhwp"
    fake_rhwp.write_text(
        "#!/usr/bin/env python3\n"
        "from pathlib import Path\n"
        "import sys\n"
        "if sys.argv[1] == 'info':\n"
        "    raise SystemExit(0)\n"
        "output = Path(sys.argv[sys.argv.index('--output') + 1])\n"
        "output.mkdir(parents=True, exist_ok=True)\n"
        "(output / 'page_001.svg').write_text('<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"50\" height=\"50\"/>', encoding='utf-8')\n",
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
        assert len([item for item in content if isinstance(item, ImageContent)]) == 3
        response = (
            '{"verdict":"PASS","summary":"의도한 셀에만 입력됨","fields":[]}'
            if vision_mode == "invalid"
            else (
                '{"verdict":"PASS","summary":"의도한 셀에만 입력됨",'
                '"fields":[{"field_id":"section0.table0.row0.cell1.blank",'
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

    session_kwargs = (
        {
            "sampling_callback": sample_vision,
            "sampling_capabilities": SamplingCapability(),
        }
        if vision_mode != "unsupported"
        else {}
    )
    async with stdio_client(server_parameters) as (read_stream, write_stream):
        async with ClientSession(
            read_stream,
            write_stream,
            **session_kwargs,
        ) as session:
            await session.initialize()
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
                "apply_edit_plan",
                "confirm_visual_candidates",
                "review_document_vision",
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
            assert analyzed_result.structuredContent["field_candidates"][0]["label"] == "업체명"
            field_id = analyzed_result.structuredContent["field_registry"][0]["field_id"]
            confirmed_result = await session.call_tool(
                "confirm_visual_candidates",
                arguments={"path": "plan-form.hwpx", "candidates": []},
            )
            assert confirmed_result.isError is not True
            assert confirmed_result.structuredContent["alignment_status"] == "CONSISTENT"

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

            apply_result = await session.call_tool(
                "apply_edit_plan",
                arguments={
                    "path": "plan-form.hwpx",
                    "output_path": None,
                    "plan": plan,
                    "approved": True,
                },
            )

            assert apply_result.isError is not True
            assert apply_result.structuredContent["status"] == "PENDING_VISION_REVIEW"
            assert apply_result.structuredContent["review"]["expected_changes"]["passed"] is True
            assert apply_result.structuredContent["review"]["visual"]["layout_warnings_preserved"] is True

            vision_result = await session.call_tool(
                "review_document_vision",
                arguments={
                    "path": "plan-form.hwpx",
                    "plan_id": plan["plan_id"],
                },
            )
            assert vision_result.isError is not True
            expected_verdict = "PASS" if vision_mode == "pass" else "NEEDS_HUMAN"
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
            if vision_mode == "pass":
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
