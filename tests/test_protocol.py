from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from test_hwpx import make_fixture, make_table_fixture


def test_stdio_server_lists_and_calls_tools(tmp_path: Path) -> None:
    source = tmp_path / "sample.hwpx"
    modified = tmp_path / "modified.hwpx"
    plan_source = tmp_path / "plan-form.hwpx"
    make_fixture(source)
    make_fixture(modified, text="변경된 문서")
    make_table_fixture(plan_source)
    asyncio.run(_exercise_server(tmp_path))


async def _exercise_server(root: Path) -> None:
    fake_rhwp = root / "fake-rhwp"
    fake_rhwp.write_text(
        "#!/usr/bin/env python3\n"
        "from pathlib import Path\n"
        "import sys\n"
        "if sys.argv[1] == 'info':\n"
        "    raise SystemExit(0)\n"
        "output = Path(sys.argv[sys.argv.index('--output') + 1])\n"
        "output.mkdir(parents=True, exist_ok=True)\n"
        "(output / 'page_001.svg').write_text('<svg />', encoding='utf-8')\n",
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

    async with stdio_client(server_parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
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
                },
            )

            assert plan_result.isError is not True
            plan = plan_result.structuredContent
            assert plan["status"] == "WAITING_APPROVAL"

            apply_result = await session.call_tool(
                "apply_edit_plan",
                arguments={
                    "path": "plan-form.hwpx",
                    "output_path": "planned.hwpx",
                    "plan": plan,
                    "approved": True,
                    "review_output_dir": "planned-review",
                },
            )

            assert apply_result.isError is not True
            assert apply_result.structuredContent["status"] == "APPLIED"
            assert apply_result.structuredContent["review"]["expected_changes"]["passed"] is True
            assert apply_result.structuredContent["review"]["visual"]["layout_warnings_preserved"] is True

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
