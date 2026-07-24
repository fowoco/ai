# Project policy — hwp-editor-mcp

## 프로젝트 개요
로컬 HWPX 문서의 검사, 구조 분석, 본문 추출 및 안전 편집을 수행하는 학습용 MCP Server (`hwp-editor-mcp`) 구축.
데드라인: 이번 주말 내 (2026-07-26). 전체 팀 프로젝트 중 HWP/HWPX MCP Server 모듈 담당.

## 기술 스택
- Core: Python 3.10+ (`uv`) & Rust/WASM (`rhwp`)
- MCP & Framework: `FastMCP` (`mcp[cli]>=1.27,<2`), `FastAPI` Control Plane, `defusedxml`, `Pydantic`, `pytest`
- DB & Storage: 로컬 JSON (양식 프로필 저장), 로컬 HWPX 파일 다이렉트 핸들링

## 핵심 불변 규칙 (항상 적용)

### TDD 및 자동화 검증
- 신규 MCP Tool / XML 파싱 및 치환 로직 작성 시 반드시 `tests/` 아래 파이프라인 검증 테스트 작성 (`uv run pytest`)

### HITL 리스크 기준
- HIGH (사용자 승인 필수): HWPX Edit Plan 실물 적용 (`apply_edit_plan`), 새 출력 파일 최종 생성
- MEDIUM (알림): `rhwp` 렌더링 시각 차이 발생 및 비주얼 diff 감지
- LOW (자동 승인): 문서 검사 (`inspect_document`), 텍스트 추출 (`extract_text`), 미리보기 생성

### 보안 필수 규칙
- 원본 HWPX 덮어쓰기 절대 금지
- 작업 루트 (`HWP_MCP_ROOT`) 외 디렉토리 트래버스(`..`) 및 파일 탈출 금지
- XML 파싱 시 `defusedxml` 사용 필수
- 양식 프로필에 개인정보(이름, 전화번호, 주소 등) 저장 금지

## 컨벤션 참조
- 개요: @wiki/conventions/01-project-overview.md
- 기술 스택: @wiki/conventions/02-tech-stack.md
- 네이밍: @wiki/conventions/03-naming.md
- Git: @wiki/conventions/04-git.md
- 아키텍처: @wiki/conventions/05-architecture.md
- TDD: @wiki/conventions/06-tdd.md
- devlog: @wiki/conventions/07-devlog.md
- HITL 리스크: @wiki/conventions/08-hitl-risk.md
- 대시보드: @wiki/conventions/09-dashboard.md
- 코드리뷰: @wiki/conventions/10-code-review.md
- 에러 핸들링: @wiki/conventions/11-error-handling.md
- 보안: @wiki/conventions/12-security.md
- 의존성: @wiki/conventions/13-dependencies.md

## 스킬 사용법
- /wiki — setup·capture·devlog·ingest·query·lint
- /brief — 현황 브리핑·dashboard·report·handoff
- /review — 컨벤션 기반 변경사항 검토

## Intent Router
- 프로젝트 상태/우선순위 → /brief
- 과거 결정/컨벤션 질문 → /wiki query
- 회의/결정 기록 → /wiki capture
- 작업 세션 기록 → /wiki devlog
- raw 소스 반영/wiki 점검 → /wiki ingest 또는 /wiki lint
- PR전 변경 검토 → /review
