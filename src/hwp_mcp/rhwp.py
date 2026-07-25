from __future__ import annotations

import os
from pathlib import Path
import shlex
import subprocess
from typing import Any

from .hwpx import DocumentError


DEFAULT_TIMEOUT_SECONDS = 120


class RhwpError(DocumentError):
    """rhwp 실행 또는 출력 검증 오류입니다."""


def _command() -> list[str]:
    env_cmd = os.environ.get("RHWP_COMMAND")
    if env_cmd is not None:
        configured = shlex.split(env_cmd)
        if not configured:
            raise RhwpError("RHWP_COMMAND가 비어 있습니다.")
        return configured

    cargo_rhwp = Path.home() / ".cargo/bin/rhwp"
    if cargo_rhwp.exists():
        return [str(cargo_rhwp)]

    return ["rhwp"]


def render_svg(
    input_path: Path,
    output_dir: Path,
    *,
    debug_overlay: bool = True,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """rhwp로 HWPX 페이지를 SVG로 렌더링합니다."""
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [*_command(), "export-svg", str(input_path), "--output", str(output_dir)]
    if debug_overlay:
        command.append("--debug-overlay")

    info_command = [*_command(), "info", str(input_path)]
    info_completed = _run(info_command, timeout_seconds)
    if info_completed.returncode != 0:
        detail = (info_completed.stderr or info_completed.stdout).strip()
        raise RhwpError(f"rhwp 문서 정보 확인에 실패했습니다: {detail or info_completed.returncode}")

    completed = _run(command, timeout_seconds)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RhwpError(f"rhwp 렌더링에 실패했습니다: {detail or completed.returncode}")

    files = sorted(output_dir.glob("*.svg"))
    if not files:
        raise RhwpError("rhwp가 SVG 페이지를 생성하지 않았습니다.")

    layout_warnings = list(
        dict.fromkeys(
            line.strip()
            for line in (
                info_completed.stdout
                + "\n"
                + info_completed.stderr
                + "\n"
                + completed.stdout
                + "\n"
                + completed.stderr
            ).splitlines()
            if line.strip().startswith("LAYOUT_")
        )
    )
    return {
        "renderer": "rhwp",
        "format": "svg",
        "output_dir": str(output_dir),
        "files": [str(path) for path in files],
        "pages": len(files),
        "debug_overlay": debug_overlay,
        "layout_warnings": layout_warnings,
    }



def _run(command: list[str], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise RhwpError(
            "rhwp 실행 파일을 찾지 못했습니다. RHWP_COMMAND를 설정하세요."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RhwpError(f"rhwp 실행 시간이 제한({timeout_seconds}초)을 초과했습니다.") from exc
    except OSError as exc:
        raise RhwpError(f"rhwp 실행에 실패했습니다: {exc}") from exc

