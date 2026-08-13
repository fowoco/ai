# Internal API Bearer 인증 (#8)

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Header, HTTPException, status

from app.core.config import get_settings


# Authorization Bearer가 설정 토큰과 일치하는지 검사 (미설정 시 통과)
async def verify_internal_bearer(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    expected = get_settings().internal_api_token
    if not expected:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization Bearer token",
        )
    token = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal API token",
        )
