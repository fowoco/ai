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

- Phase 0 마일스톤: `rhwp` 렌더링 연동 및 표준근로계약서 HWPX 검증

## Priorities

- 1단계: HWPX 샘플 3종(단순·표·이미지) 준비 및 `rhwp` 렌더링 검증
- 2단계: 문단 추가 Tool 분리 및 FastAPI Control Plane 설계
- 3단계: 표 편집 OWPML 구조 학습 및 설계

## Deferred

- Streamable HTTP Transport 및 웹 인증 연동
- HWP 바이너리 직접 편집

## Decision queue

- `rhwp` 렌더링 엔진 연동 방식 선택 (Rust CLI vs Sidecar)

## Risks

- HWPX OWPML 레이아웃 복잡도 및 `rhwp` CLI 연동 호환성

## Next actions

- 표준근로계약서 HWPX 샘플 준비 및 `rhwp` 렌더링/구조 파싱 연동 검증.
