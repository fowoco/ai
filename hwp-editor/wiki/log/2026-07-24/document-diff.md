---
id: log-2026-07-24-document-diff
type: log
title: "HWPX 문서 버전 비교 Tool 추가"
created: 2026-07-24
updated: 2026-07-24
sources:
  - docs/HWP-HWPX-Form-Agent-MCP-설계-로드맵.md
  - wiki/conventions/05-architecture.md
  - wiki/conventions/06-tdd.md
  - wiki/conventions/08-hitl-risk.md
---

# HWPX 문서 버전 비교 Tool 추가

## 작업 요약

- 두 HWPX 문서의 구조와 렌더 결과를 비교하는 `compare_document_versions`를 추가했다.
- 문단·셀 변경 목록과 문서 개수 차이를 반환한다.
- 페이지별 SVG SHA-256을 비교한다.

## 주요 변경점 & 설계 결정

- 구조 비교는 기존 Manifest를 재사용한다.
- 렌더 비교는 페이지 순서와 SVG SHA-256을 기준으로 한다.
- 출력 폴더는 새 경로로 만들며 실패 시 부분 결과를 삭제한다.
- 픽셀 기반 이미지 diff는 Pillow 도입 전까지 보류한다.

## 테스트 결과

- `uv run pytest`: `10 passed`
- `python -m compileall -q src tests`: 통과
- `.hooks/convention-check.sh`: 통과

## 다음 진행 작업

- 승인된 Edit Plan 모델과 적용 경계를 구현한다.
- 사용자 승인 전 파일 생성 차단을 테스트한다.
- 필요성이 확인되면 SVG를 PNG로 변환해 픽셀 diff를 추가한다.
