---
id: project-status
type: project-status
title: Project Status
created: 2026-07-24
updated: 2026-07-24
sources:
  - AGENT.project.md
  - wiki/conventions/*
---

# Project Status

> 사람이 선언하는 현재 목표입니다. Git 관찰로 이 내용을 자동 덮어쓰지 않습니다.

## Goal

로컬 HWPX 문서의 검사, 구조 분석, 본문 추출 및 안전 편집을 수행하는 MCP Server (`hwp-editor-mcp`) 구축 (데드라인: 2026-07-26).

## Why

HWPX 파싱/편집 모듈 기반이 마련되었습니다. 다음 병목인 Rust `rhwp` 파싱/렌더링 연동과 HWPX 구조 검증을 해결해야 합니다.

## Focus

- Phase 3 마일스톤: 승인된 Edit Plan과 안전한 결과 생성

## Priorities

- 1단계: 표준근로계약서 2페이지 SVG 렌더링 확인 완료
- 2단계: 단순·이미지 포함 HWPX 샘플 추가 렌더링 검증
- 3단계: 문서 구조·SVG SHA-256 비교 Tool 완료
- 4단계: 승인 대기 Edit Plan 생성·적용 경계 완료
- 5단계: 날짜·전화번호 정규화 결과 Tool 완료
- 6단계: 수정 전·후 렌더 비교와 예상 외 변경 차단

## Deferred

- Streamable HTTP Transport 및 웹 인증 연동
- HWP 바이너리 직접 편집

## Decision queue

- `rhwp` 렌더링 엔진 연동 방식 선택 (Rust CLI vs Sidecar)

## Risks

- HWPX OWPML 레이아웃 복잡도 및 `rhwp` CLI 연동 호환성

## Next actions

- 단순·이미지 포함 HWPX 샘플의 `rhwp` 렌더링 검증.
- 현재 Manifest와 `rhwp info` 결과 비교.
- 승인된 Edit Plan에 렌더 비교와 결과 차단 연결.
- 7개 필드 입력을 Agent 인터뷰와 연결.
