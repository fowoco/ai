import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_mac_run_script_has_valid_shell_syntax() -> None:
    result = subprocess.run(
        ["sh", "-n", str(ROOT / "scripts" / "run_mac_agent.sh")],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_mac_run_script_is_loopback_single_worker() -> None:
    script = (ROOT / "scripts" / "run_mac_agent.sh").read_text(encoding="utf-8")
    assert "--host 127.0.0.1" in script
    assert "--workers 1" in script
    assert "caffeinate -dimsu" in script


def test_mac_profile_requires_auth_warmup_and_mps() -> None:
    profile = (ROOT / ".env.mac.example").read_text(encoding="utf-8")
    assert "FOWOCO_INTERNAL_API_AUTH_REQUIRED=true" in profile
    assert "FOWOCO_INTERNAL_API_TOKEN=\n" in profile
    assert "FOWOCO_INTENT_MODEL_ENABLED=true" in profile
    assert "FOWOCO_INTENT_ENABLE_AX=true" in profile
    assert "FOWOCO_INTENT_DEVICE=mps" in profile
    assert "FOWOCO_INTENT_WARMUP_REQUIRED=true" in profile
