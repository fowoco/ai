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
    make_fixture(source)
    asyncio.run(_exercise_server(tmp_path))


async def _exercise_server(root: Path) -> None:
    server_parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "hwp_mcp.server"],
        env={**os.environ, "HWP_MCP_ROOT": str(root)},
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
