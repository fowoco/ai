from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from .hwpx import DocumentError


class Signature(BaseModel):
    """서명 payload와 분리해 저장하는 검증 정보입니다."""

    model_config = ConfigDict(extra="forbid")

    key_id: str = Field(min_length=1, max_length=100)
    algorithm: Literal["HMAC-SHA256"] = "HMAC-SHA256"
    value: str = Field(min_length=1, max_length=256)


class SigningKeyProvider(Protocol):
    def sign(self, payload: bytes) -> Signature: ...

    def verify(self, payload: bytes, signature: Signature) -> bool: ...


class EnvSigningKeyProvider:
    """환경변수 key ring을 사용하는 단일 서버용 HMAC provider입니다."""

    def __init__(self, active_key_id: str, keys: dict[str, bytes]) -> None:
        if active_key_id not in keys:
            raise DocumentError("활성 서명 키가 key ring에 없습니다.")
        self._active_key_id = active_key_id
        self._keys = dict(keys)

    @classmethod
    def from_env(cls) -> "EnvSigningKeyProvider":
        active_key_id = os.environ.get("HWP_MCP_ACTIVE_SIGNING_KEY_ID", "").strip()
        raw_key_ring = os.environ.get("HWP_MCP_SIGNING_KEYS", "")
        if not active_key_id or not raw_key_ring:
            raise DocumentError(
                "서명 키 환경변수 HWP_MCP_ACTIVE_SIGNING_KEY_ID와 "
                "HWP_MCP_SIGNING_KEYS가 필요합니다."
            )
        try:
            encoded_keys = json.loads(raw_key_ring)
        except json.JSONDecodeError as exc:
            raise DocumentError("HWP_MCP_SIGNING_KEYS는 JSON 객체여야 합니다.") from exc
        if not isinstance(encoded_keys, dict) or not encoded_keys:
            raise DocumentError("HWP_MCP_SIGNING_KEYS는 비어 있지 않은 JSON 객체여야 합니다.")

        keys: dict[str, bytes] = {}
        for key_id, encoded in encoded_keys.items():
            if (
                not isinstance(key_id, str)
                or not key_id.strip()
                or not isinstance(encoded, str)
            ):
                raise DocumentError("서명 key_id와 값은 문자열이어야 합니다.")
            try:
                key = base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise DocumentError(f"서명 키 {key_id!r}가 유효한 base64가 아닙니다.") from exc
            if len(key) < 32:
                raise DocumentError(f"서명 키 {key_id!r}는 최소 32바이트여야 합니다.")
            keys[key_id] = key
        return cls(active_key_id, keys)

    def sign(self, payload: bytes) -> Signature:
        digest = hmac.new(
            self._keys[self._active_key_id],
            payload,
            hashlib.sha256,
        ).digest()
        return Signature(
            key_id=self._active_key_id,
            value=base64.b64encode(digest).decode("ascii"),
        )

    def verify(self, payload: bytes, signature: Signature) -> bool:
        key = self._keys.get(signature.key_id)
        if key is None or signature.algorithm != "HMAC-SHA256":
            return False
        expected = hmac.new(key, payload, hashlib.sha256).digest()
        try:
            supplied = base64.b64decode(signature.value, validate=True)
        except (binascii.Error, ValueError):
            return False
        return hmac.compare_digest(expected, supplied)


def canonical_json_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
