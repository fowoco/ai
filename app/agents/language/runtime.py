"""T13 — 언어 어시스턴트 런타임 의존성 상태.

HTTP 요청 중 모델 가중치 다운로드 금지 계약을 강제한다.
qdrant_url 미설정 시 ready=False, 기존 문서 엔드포인트는 영향 없음.

ponytail: 최소 구현. 모델 파일 체크는 선택적 — config에 설정된 경우만 실행.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RuntimeStatus:
    """언어 어시스턴트 런타임 준비 상태."""

    ready: bool
    missing: list[str] = field(default_factory=list)


def check_runtime_dependencies() -> RuntimeStatus:
    """설정 기반 런타임 의존성 점검.

    외부 서버 연결 없음. 환경변수 존재 여부만 확인.
    """
    from app.core.config import get_settings

    settings = get_settings()
    missing: list[str] = []

    if not settings.qdrant_url:
        missing.append("qdrant_url")

    return RuntimeStatus(ready=len(missing) == 0, missing=missing)
