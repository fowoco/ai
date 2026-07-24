from __future__ import annotations

from pathlib import Path
import subprocess

from hwp_mcp import rhwp


def test_render_svg_returns_generated_pages(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "sample.hwpx"
    output_dir = tmp_path / "rendered"
    source.write_bytes(b"sample")
    output_dir.mkdir()

    def fake_run(command, **kwargs):
        assert command[:2] == ["rhwp", "export-svg"]
        assert command[2] == str(source)
        assert command[3:5] == ["--output", str(output_dir)]
        assert command[5] == "--debug-overlay"
        assert kwargs["check"] is False
        (output_dir / "page_001.svg").write_text("<svg />", encoding="utf-8")
        (output_dir / "page_002.svg").write_text("<svg />", encoding="utf-8")
        return subprocess.CompletedProcess(
            command, 0, stdout="완료", stderr="LAYOUT_OVERFLOW: baseline\n"
        )

    monkeypatch.setenv("RHWP_COMMAND", "rhwp")
    monkeypatch.setattr(rhwp.subprocess, "run", fake_run)

    result = rhwp.render_svg(source, output_dir)

    assert result["renderer"] == "rhwp"
    assert result["pages"] == 2
    assert result["debug_overlay"] is True
    assert result["layout_warnings"] == ["LAYOUT_OVERFLOW: baseline"]


def test_render_svg_rejects_empty_command(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RHWP_COMMAND", "")

    try:
        rhwp.render_svg(tmp_path / "sample.hwpx", tmp_path / "rendered")
    except rhwp.RhwpError as exc:
        assert str(exc) == "RHWP_COMMAND가 비어 있습니다."
    else:
        raise AssertionError("빈 RHWP_COMMAND를 허용했습니다.")
