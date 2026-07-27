---
id: log-2026-07-24-edit-review
type: log
title: "HWPX Edit Plan 적용 후 검토·차단 연결"
created: 2026-07-24
updated: 2026-07-24
sources:
  - docs/HWP-HWPX-Form-Agent-MCP-설계-로드맵.md
  - wiki/conventions/06-tdd.md
  - wiki/conventions/08-hitl-risk.md
  - wiki/conventions/11-error-handling.md
---

# HWPX Edit Plan 적용 후 검토·차단 연결

## 작업 요약

- `apply_edit_plan`이 적용 후 원본·수정본 Manifest를 비교한다.
- 승인한 셀 외 변경과 예상 변경 누락을 차단한다.
- `review_output_dir`를 지정하면 원본·수정본 SVG 렌더와 페이지 수를 비교한다.

## 주요 변경점 & 설계 결정

- 정상적인 텍스트 변경으로 SVG 해시가 달라지는 것은 오류로 보지 않는다.
- 페이지 수 변화는 레이아웃 위험으로 보고 결과 파일을 삭제한다.
- 예상 외 변경이나 검토 실패가 발생하면 출력 HWPX와 검토 폴더를 함께 삭제한다.
- PNG 렌더러가 준비되기 전까지 픽셀 단위 비교는 보류한다.

## 테스트 결과

- `uv run pytest`: `17 passed`
- `python -m compileall -q src tests`: 통과
- `.hooks/convention-check.sh`: 통과

## 다음 진행 작업

- 표준근로계약서 7개 필드 후보를 Agent 인터뷰 입력으로 묶는다.
- PNG 렌더링이 가능해지면 픽셀 diff와 변경 영역 표시를 추가한다.
