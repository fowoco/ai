---
title: "기술 스택"
type: convention
created: 2026-07-24
updated: 2026-07-24
---

# 기술 스택

## 주 언어 및 실행 환경
| 항목 | 내용 |
|---|---|
| **규칙** | 메인 애플리케이션: Python 3.10+ (패키지 매니저 `uv`). 문단/페이지 렌더링 및 디버그 오버레이: Rust/WASM 엔진 (`rhwp`) |
| **이유** | 빠른 MCP/Control Plane 개발(Python)과 고성능 HWP/HWPX 파싱/렌더링 엔진(Rust `rhwp`)의 조합 |
| **예시** | `uv run hwp-editor-mcp`로 stdio 서버 실행, 내부적으로 `rhwp` CLI/sidecar 호출 |
| **위반 시** | 허용되지 않은 외부 언어 런타임 도입 금지 |

## 핵심 프레임워크 및 라이브러리
| 항목 | 내용 |
|---|---|
| **규칙** | MCP: Official Python SDK `FastMCP` (`mcp[cli]>=1.27,<2`). Control Plane: `FastAPI`. XML 파싱: `defusedxml`. 스키마: `Pydantic`. 이미지 시각 비교: `Pillow`. 테스트: `pytest` |
| **이유** | MCP 표준 규격 준수, 세션/미리보기 Control Plane과 MCP 서버 역할 분리, 안전한 XML 처리 |
| **예시** | `FastMCP`는 Tool/Resource/Prompt 노출 및 stdio/HTTP Transport 전담, `FastAPI`는 세션/미리보기 API 담당 |
| **위반 시** | FastMCP의 본래 역할 외 세션 상태 및 렌더링 가공 로직을 커플링하지 말 것 |

## 저장소 및 외부 연동
| 항목 | 내용 |
|---|---|
| **규칙** | 데이터베이스: 로컬 JSON (양식 프로필 저장). 추후 SQLite 확장 가능. 외부 엔진: `rhwp` (`https://github.com/edwardkim/rhwp` CLI/sidecar). 외부 API 연동은 없음 (로컬 전용) |
| **이유** | 외부 네트워크 의존성 없는 로컬 전용 처리 및 HWPX 양식 재사용성 보장 |
| **예시** | `save_form_profile`로 필드 위치 지문을 로컬 JSON에 기록 |
| **위반 시** | 양식 프로필에 성명, 전화번호 등 개인정보 저장 금지 |
