---
id: log-2026-07-24-fastapi-control-plane
type: log
title: "FastAPI Control Plane 최소 골격 추가"
created: 2026-07-24
updated: 2026-07-24
sources:
  - docs/HWP-HWPX-Form-Agent-MCP-설계-로드맵.md
  - wiki/conventions/05-architecture.md
  - wiki/conventions/06-tdd.md
  - wiki/conventions/12-security.md
---

# FastAPI Control Plane 최소 골격 추가

## 작업 요약

- MCP와 같은 로컬 문서 기능을 HTTP로 호출하는 FastAPI 앱을 추가했다.
- `/health`, `/documents/analyze`, `/plans/create`, `/plans/apply`를 제공한다.
- FastAPI에 XML 편집 로직을 복제하지 않고 기존 MCP 함수와 보안 경계를 재사용한다.

## 주요 변경점 & 설계 결정

- 실행 명령은 `hwp-editor-api`이며 `HWP_MCP_ROOT`를 공유한다.
- HTTP에서도 승인 없는 적용은 400으로 차단된다.
- 파일 업로드·세션 저장·인증은 로컬 MCP 흐름을 먼저 검증한 뒤 추가한다.
- FastAPI를 MCP 대체물이 아니라 Control Plane으로 한정했다.

## 테스트 결과

- `uv run pytest`: `18 passed`
- `python -m compileall -q src tests`: 통과
- `.hooks/convention-check.sh`: 통과

## 다음 진행 작업

- 표준근로계약서 7개 필드 인터뷰를 Host Agent 흐름과 연결한다.
- 파일 업로드·세션 상태·미리보기 Endpoint 필요성을 실제 사용으로 검증한다.
