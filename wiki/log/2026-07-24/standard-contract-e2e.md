---
id: log-2026-07-24-standard-contract-e2e
type: log
title: "표준근로계약서 7개 필드 End-to-End 검증"
created: 2026-07-24
updated: 2026-07-24
sources:
  - docs/HWP-HWPX-Form-Agent-MCP-설계-로드맵.md
  - wiki/conventions/06-tdd.md
  - wiki/conventions/08-hitl-risk.md
  - wiki/conventions/12-security.md
---

# 표준근로계약서 7개 필드 End-to-End 검증

## 작업 요약

- Downloads의 표준근로계약서 원본을 임시 작업 폴더로 복사했다.
- Manifest의 7개 입력 후보에서 Edit Plan을 만들고 승인 후 새 HWPX를 생성했다.

## 주요 변경점 & 설계 결정

- 대상: 업체명, 전화번호, 소재지, 사용자 성명, 근로자 성명, 생년월일, 본국주소
- Edit Plan 작업 수: 7개
- 구조 검토: 승인한 셀 7개만 변경되어 통과
- 렌더 검토: 수정 전·후 2페이지 유지, 원본 레이아웃 경고 기준선 유지
- 보존 검토: 원본 파일 유지, 새 출력 파일 생성
- 검증 결과는 `/private/tmp` 임시 폴더에서만 만들었으며 Downloads 원본은 수정하지 않았다.

## 테스트 결과

- 실제 표준근로계약서 적용 흐름: 통과
- 수정본 HWPX 재검증: 통과
- `uv run pytest`: `18 passed`
- `.hooks/convention-check.sh`: 통과

## 다음 진행 작업

- Agent가 후보를 섹션별 질문으로 묶고 사용자 답변을 수집하는 대화 흐름을 연결한다.
- 실제 긴 값 입력에서 신규 레이아웃 경고·셀 넘침 차단을 검증한다.
