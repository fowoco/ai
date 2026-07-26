from __future__ import annotations

import asyncio
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from hwp_mcp.api import app

from test_hwpx import make_table_fixture


def test_fastapi_control_plane_uses_same_plan_gate(
    tmp_path: Path, monkeypatch
) -> None:
    import subprocess
    from hwp_mcp import rhwp

    source = tmp_path / "form.hwpx"
    make_table_fixture(source)
    monkeypatch.setenv("HWP_MCP_ROOT", str(tmp_path))
    monkeypatch.setenv("RHWP_COMMAND", "rhwp")

    def fake_run(command, **kwargs):
        if command[1] == "info":
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        output_dir = Path(command[command.index("--output") + 1])
        (output_dir / "page_001.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" width="50" height="50"/>', encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(rhwp.subprocess, "run", fake_run)
    asyncio.run(_exercise_api(tmp_path))


async def _exercise_api(tmp_path: Path) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await _assert_workflow(client, tmp_path)


async def _assert_workflow(client: AsyncClient, tmp_path: Path) -> None:
    analyze = await client.post("/documents/analyze", json={"path": "form.hwpx"})
    assert analyze.status_code == 200
    assert analyze.json()["table_count"] == 1
    field_id = analyze.json()["field_registry"][0]["field_id"]
    confirmed = await client.post(
        "/documents/visual-candidates/confirm",
        json={"path": "form.hwpx", "candidates": []},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["alignment_status"] == "CONSISTENT"

    plan = await client.post(
        "/plans/create",
        json={
            "path": "form.hwpx",
            "edits": [
                {
                    "target_id": "section0.table0.row0.cell1",
                    "expected_text": "",
                    "value": "ABC",
                }
            ],
            "dispositions": {field_id: "provided"},
        },
    )
    assert plan.status_code == 200
    assert plan.json()["status"] == "WAITING_APPROVAL"

    blocked = await client.post(
        "/plans/apply",
        json={
            "path": "form.hwpx",
            "plan": plan.json(),
            "approved": False,
        },
    )
    assert blocked.status_code == 400
    assert not any(tmp_path.glob("*/attempts/*/modified.hwpx"))

    applied = await client.post(
        "/plans/apply",
        json={
            "path": "form.hwpx",
            "plan": plan.json(),
            "approved": True,
        },
    )
    assert applied.status_code == 200
    assert applied.json()["status"] == "PENDING_VISION_REVIEW"
    assert not any(tmp_path.glob("*/final/*.hwpx"))

    compare = await client.post(
        "/compare/versions",
        json={
            "original_path": "form.hwpx",
            "modified_path": str(Path(applied.json()["output_path"]).relative_to(tmp_path)),
            "output_dir": "diffs_api_test",
            "debug_overlay": True,
        },
    )
    assert compare.status_code == 200
    assert "visual" in compare.json()

    finalized = await client.post(
        "/documents/finalize",
        json={
            "path": "form.hwpx",
            "plan_id": plan.json()["plan_id"],
        },
    )
    assert finalized.status_code == 400
    assert "Vision PASS" in finalized.json()["detail"]
    assert not any(tmp_path.glob("*/final/*.hwpx"))
