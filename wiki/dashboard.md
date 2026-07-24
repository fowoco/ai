---
id: dashboard
type: dashboard
title: 프로젝트 대시보드
created: 2026-07-24
updated: 2026-07-24
sources:
  - wiki/project-status.md
  - AGENT.project.md
---

# 프로젝트 대시보드 (Dashboard)

## 📌 남은 TODO & 마일스톤 (최우선)
- [x] 표준근로계약서 HWPX 2페이지 `rhwp` SVG 렌더링 검증
- [ ] **Phase 0 (진행 중)**: 단순·이미지 포함 샘플 렌더링 및 구조 비교
- [ ] **Phase 1**: `inspect_document` 확장 및 표/셀/문단/이미지 후보 모델 정의
- [ ] **Phase 2**: 사용자/근로자 정보 7개 필드 다중 입력 및 정규화
- [x] **Phase 3 일부**: Edit Plan 승인 대기·원본 지문 검증·새 파일 적용
- [ ] **Phase 3 잔여**: 수정 전/후 캡처 및 구조/이미지 시각 diff 검증
- [ ] **Phase 4**: 양식 프로필 로컬 JSON 저장 및 구조 지문 재사용

## 🎯 현재 목표 (Goal)
로컬 HWPX 문서 검사·분석·추출·편집 MCP Server (`hwp-editor-mcp`) 구축 (데드라인: 2026-07-26 주말 내).

## 💡 주요 이력 & 진행 상황
- [x] 프로젝트 14개 컨벤션 정의 완료 (`wiki/conventions/`)
- [x] `AGENT.project.md` 및 `SOUL.local.md` 설정 완료
- [x] `graphify` 지식 그래프 빌드 완료 (417 nodes, 552 edges)
- [x] Project State 갱신 및 대시보드 동기화 완료
- [x] `render_document` MCP Tool 및 `rhwp` CLI 어댑터 추가
- [x] `compare_document_versions` 구조·SVG 비교 Tool 추가
- [x] `create_edit_plan`·`apply_edit_plan` 승인 경계 추가
- [x] MCP STDIO 통합 테스트 `13 passed`

## ⚠️ 결정 대기 (Decision Queue) & 리스크
- **결정 대기**: `rhwp` 렌더링 엔진 연동 방식 선택 (Rust CLI vs Sidecar)
- **리스크**: HWPX OWPML 레이아웃 복잡도 및 `rhwp` CLI 연동 호환성
