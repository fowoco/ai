from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from test_hwpx import make_fixture


def test_stdio_server_lists_and_calls_tools(tmp_path: Path) -> None:
    source = tmp_path / "sample.hwpx"
    modified = tmp_path / "modified.hwpx"
    make_fixture(source)
    make_fixture(modified, text="변경된 문서")
    asyncio.run(_exercise_server(tmp_path))


async def _exercise_server(root: Path) -> None:
    fake_rhwp = root / "fake-rhwp"
    fake_rhwp.write_text(
        "#!/usr/bin/env python3\n"
        "from pathlib import Path\n"
        "import sys\n"
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
                "replace_text",
                "validate_document",
            } <= tool_names

            result = await session.call_tool(
                "inspect_document",
                arguments={"path": "sample.hwpx"},
            )

            assert result.isError is not True
            assert result.structuredContent["valid"] is True

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
