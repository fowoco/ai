from __future__ import annotations

import base64
import json

import pytest

from hwp_mcp.hwpx import DocumentError
from hwp_mcp.integrity import EnvSigningKeyProvider


def _encoded(byte: bytes) -> str:
    return base64.b64encode(byte * 32).decode("ascii")


def test_env_signer_survives_restart_and_supports_rotation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HWP_MCP_ACTIVE_SIGNING_KEY_ID", "v1")
    monkeypatch.setenv(
        "HWP_MCP_SIGNING_KEYS",
        json.dumps({"v1": _encoded(b"a"), "v2": _encoded(b"b")}),
    )
    first = EnvSigningKeyProvider.from_env()
    signature = first.sign(b"approval")

    monkeypatch.setenv("HWP_MCP_ACTIVE_SIGNING_KEY_ID", "v2")
    restarted = EnvSigningKeyProvider.from_env()

    assert signature.key_id == "v1"
    assert restarted.verify(b"approval", signature) is True
    assert restarted.verify(b"changed", signature) is False


def test_env_signer_rejects_missing_or_short_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HWP_MCP_ACTIVE_SIGNING_KEY_ID", raising=False)
    monkeypatch.delenv("HWP_MCP_SIGNING_KEYS", raising=False)

    with pytest.raises(DocumentError, match="서명 키"):
        EnvSigningKeyProvider.from_env()

    monkeypatch.setenv("HWP_MCP_ACTIVE_SIGNING_KEY_ID", "v1")
    monkeypatch.setenv(
        "HWP_MCP_SIGNING_KEYS",
        json.dumps({"v1": base64.b64encode(b"short").decode("ascii")}),
    )
    with pytest.raises(DocumentError, match="32바이트"):
        EnvSigningKeyProvider.from_env()


def test_env_signer_rejects_unknown_verification_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HWP_MCP_ACTIVE_SIGNING_KEY_ID", "v1")
    monkeypatch.setenv(
        "HWP_MCP_SIGNING_KEYS",
        json.dumps({"v1": _encoded(b"a")}),
    )
    signature = EnvSigningKeyProvider.from_env().sign(b"approval")
    monkeypatch.setenv("HWP_MCP_ACTIVE_SIGNING_KEY_ID", "v2")
    monkeypatch.setenv(
        "HWP_MCP_SIGNING_KEYS",
        json.dumps({"v2": _encoded(b"b")}),
    )

    assert EnvSigningKeyProvider.from_env().verify(b"approval", signature) is False
