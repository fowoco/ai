---
id: log-2026-07-24-value-normalization
type: log
title: "HWPX 날짜·전화번호 정규화 Tool 추가"
created: 2026-07-24
updated: 2026-07-24
sources:
  - docs/HWP-HWPX-Form-Agent-MCP-설계-로드맵.md
  - wiki/conventions/05-architecture.md
  - wiki/conventions/06-tdd.md
---

# HWPX 날짜·전화번호 정규화 Tool 추가

## 작업 요약

- `normalize_field_value` MCP Tool을 추가했다.
- 날짜와 전화번호의 변환안을 원본과 함께 반환한다.
- 정규화 Tool은 파일을 만들거나 값을 자동 적용하지 않는다.

## 주요 변경점 & 설계 결정

- 날짜는 유효한 날짜인지 확인한 뒤 `YYYY년 M월 D일` 형식으로 제안한다.
- 전화번호는 국내 일반 형식과 `+82`·`0082` 입력을 지원한다.
- 실제 적용은 사용자가 변환안을 확인한 뒤 `create_edit_plan`에 넣는 흐름으로 제한한다.
- 별도 라이브러리 없이 표준 라이브러리와 기존 Pydantic 모델을 사용했다.

## 테스트 결과

- `uv run pytest`: `16 passed`
- `python -m compileall -q src tests`: 통과
- `.hooks/convention-check.sh`: 통과

## 다음 진행 작업

- 표준근로계약서 7개 필드 후보를 섹션별 입력 흐름으로 묶는다.
- 승인된 계획의 수정 전·후 렌더 비교와 예상 외 변경 차단을 연결한다.
