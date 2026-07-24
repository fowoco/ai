---
id: log-2026-07-24-edit-plan
type: log
title: "HWPX Edit Plan 승인 경계 추가"
created: 2026-07-24
updated: 2026-07-24
sources:
  - docs/HWP-HWPX-Form-Agent-MCP-설계-로드맵.md
  - wiki/conventions/05-architecture.md
  - wiki/conventions/06-tdd.md
  - wiki/conventions/08-hitl-risk.md
  - wiki/conventions/12-security.md
---

# HWPX Edit Plan 승인 경계 추가

## 작업 요약

- `create_edit_plan`과 `apply_edit_plan` MCP Tool을 추가했다.
- 계획 생성은 문서 분석과 SHA-256 계산만 수행하며 파일을 만들지 않는다.
- 적용은 명시적 승인, 대상 파일 일치, 원본 지문, 계획 무결성 검증 후 새 파일에만 수행한다.

## 주요 변경점 & 설계 결정

- Edit Plan은 Pydantic 모델로 제한된 셀 텍스트 변경만 표현한다.
- `plan_id`는 대상 파일·원본 지문·작업 목록의 정규화된 JSON으로 계산한다.
- 계획 생성 후 원본이 바뀌면 적용을 차단한다.
- 기존 `fill_cells`를 재사용해 XML 편집 로직을 중복하지 않았다.
- 사용자 승인 자체는 MCP Host의 대화·UI 경계에서 수행하며, Server는 `approved` 입력을 별도 게이트로 확인한다.

## 테스트 결과

- `uv run pytest`: `13 passed`
- `python -m compileall -q src tests`: 통과
- `.hooks/convention-check.sh`: 통과

## 다음 진행 작업

- 승인된 계획의 수정 전·후 렌더 결과를 연결한다.
- 날짜·전화번호 정규화와 표준근로계약서 다중 필드 입력을 추가한다.
