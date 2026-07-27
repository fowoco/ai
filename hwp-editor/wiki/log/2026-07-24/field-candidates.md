---
id: log-2026-07-24-field-candidates
type: log
title: "HWPX 입력 필드 후보 추출 추가"
created: 2026-07-24
updated: 2026-07-24
sources:
  - docs/HWP-HWPX-Form-Agent-MCP-설계-로드맵.md
  - wiki/conventions/05-architecture.md
  - wiki/conventions/06-tdd.md
---

# HWPX 입력 필드 후보 추출 추가

## 작업 요약

- 문서 Manifest에 입력 후보 목록을 추가했다.
- 인접한 빈 셀과 대표 행정서식 라벨 셀을 후보로 반환한다.
- 후보는 필수값으로 확정하지 않고 `requires_user_confirmation: true`로 표시한다.

## 주요 변경점 & 설계 결정

- 표준근로계약서에서 업체명·전화번호·소재지·사용자 성명·근로자 성명·생년월일·본국주소 7개 후보를 확인했다.
- 라벨 셀 후보는 현재 셀 텍스트를 보존한 채 값을 추가하는 현재 `fill_cells` 동작과 연결된다.
- 제목·서식 안내 문구는 후보에서 제외한다.
- 라벨 인식은 휴리스틱이므로 Agent가 사용자에게 위치와 값을 재확인해야 한다.

## 테스트 결과

- 표준근로계약서 실제 Manifest: 7개 후보 확인
- `uv run pytest`: `18 passed`
- `.hooks/convention-check.sh`: 통과

## 다음 진행 작업

- 후보를 섹션별 Agent 인터뷰 질문으로 묶는다.
- 사용자 답변을 정규화·승인·Edit Plan 생성 흐름에 연결한다.
