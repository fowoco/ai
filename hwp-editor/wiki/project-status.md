---
id: project-status
type: project-status
title: Project Status
created: 2026-07-24
updated: 2026-07-26
sources:
  - AGENT.project.md
  - wiki/conventions/*
---

# Project Status

> 사람이 선언하는 현재 목표입니다. Git 관찰로 이 내용을 자동 덮어쓰지 않습니다.

## Goal

로컬 HWPX 문서의 검사, 구조 분석, 본문 추출, 정확한 세그먼트 단위 안전 편집을 수행하는 MCP Server (`hwp-editor-mcp`) 구축 (데드라인: 2026-07-26).

## Why

HWPX 필드 세그먼트 탐색 및 정교한 텍스트 치환 연산 개선이 완료되었습니다. 다음 병목인 PNG 렌더러 기반 시각 검증 및 양식 프로필 연동을 해결해야 합니다.

## Focus

- Phase 3 마일스톤: 필드 세그먼트 단위 치환 및 승인된 Edit Plan 안전 적용

## Priorities

- 1단계: 표준근로계약서 2페이지 SVG 렌더링 확인 완료
- 2단계: Downloads HWPX 4종 SVG 렌더링 확인 완료
- 3단계: 문서 구조·SVG SHA-256 비교 Tool 완료
- 4단계: 승인 대기 Edit Plan 생성·적용 경계 완료
- 5단계: 날짜·전화번호 정규화 결과 Tool 완료
- 5.5단계: 표준근로계약서 7개 입력 후보 추출 완료
- 6단계: 승인된 셀 외 변경·페이지 수 변화 차단 완료
- 7단계: FastAPI Control Plane 최소 골격 완료
- 8단계: 필드 세그먼트(`FieldSegment`) 모델 및 정교한 탐색기(`infer_field_segments`) 구현 완료 (사업자번호, 날짜, 체크박스, 서명 영역)
- 9단계: `fill_cells` exact `t` 요소 텍스트 치환 연산 개선 완료 (라벨 뒤 무분별한 부착 현상 고침)
- 10단계: `resvg-py` 기반 PNG 렌더러 및 Pillow 빨간색 바운딩 박스 Visual Diff 하이라이트 구현 완료
- 11단계: FastAPI Control Plane `POST /compare/versions` HTTP API 및 테스트 연동 완료
- 12단계: TDD 테스트 23개 100% 통과 완료

## Deferred

- Streamable HTTP Transport 및 웹 인증 연동
- HWP 바이너리 직접 편집

## Decision queue

- `rhwp` PNG 렌더러 추가 확정을 위한 라이브러리/sidecar 연동 방식 선택

## Risks

- HWPX OWPML 레이아웃 복잡도 및 다양한 서식 내 텍스트 node 쪼개짐 현상

## Next actions

- PNG 렌더러 확보 후 픽셀 기반 렌더 비교 연결.
- 양식 프로필 저장(`save_form_profile`) 및 세션 인터뷰 연동.
- FastAPI 파일 업로드·세션·인증 연동.
- 원본 `rhwp` `LAYOUT_OVERFLOW` 경고 2건은 기준선으로 기록하고 신규 경고만 차단.
