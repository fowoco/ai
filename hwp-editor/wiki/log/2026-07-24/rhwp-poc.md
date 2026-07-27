---
id: log-2026-07-24-rhwp-poc
type: log
title: "rhwp Phase 0 렌더링 PoC"
created: 2026-07-24
updated: 2026-07-24
sources:
  - docs/HWP-HWPX-Form-Agent-MCP-설계-로드맵.md
  - wiki/project-status.md
  - wiki/conventions/02-tech-stack.md
  - wiki/conventions/06-tdd.md
---

# rhwp Phase 0 렌더링 PoC

## 작업 요약

- 공식 `rhwp v0.7.19` macOS ARM64 CLI를 임시 환경에서 검증했다.
- 표준근로계약서 HWPX를 2페이지 SVG로 렌더링했다.
- Debug Overlay 옵션이 동작하는 것을 확인했다.
- 저장소에는 바이너리를 추가하지 않았다.

## 주요 변경점 & 설계 결정

- `RHWP_COMMAND` 환경변수로 외부 `rhwp` 실행 파일 경로를 주입한다.
- `render_document` MCP Tool은 페이지별 SVG와 출력 경로를 반환한다.
- 출력 폴더는 허용된 작업 루트 안에 있어야 하며 비어 있어야 한다.
- PNG 렌더링은 공식 바이너리의 native-skia 조건 때문에 후속 작업으로 보류했다.

## 테스트 결과

- `uv run pytest`: `9 passed`
- `python -m compileall -q src tests`: 통과
- `.hooks/convention-check.sh`: 통과
- 실제 표준근로계약서 렌더링: 2페이지 SVG 생성

## 다음 진행 작업

- 단순 문서·이미지 포함 HWPX 샘플을 추가로 렌더링한다.
- Python Manifest와 `rhwp info` 결과를 비교한다.
- 수정 전·후 SVG 및 구조 diff 설계를 시작한다.
