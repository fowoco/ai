---
title: "TDD 규칙"
type: convention
created: 2026-07-24
updated: 2026-07-24
---

# TDD 규칙

## 테스트 프레임워크 및 실행 명령
| 항목 | 내용 |
|---|---|
| **규칙** | 테스트 프레임워크는 `pytest` 사용. 실행 명령: `uv run pytest` |
| **이유** | 패키지 격리 환경에서의 일관된 자동화 테스트 실행 보장 |
| **예시** | `uv run pytest tests/test_hwpx.py` |
| **위반 시** | 테스트 커맨드 미작동 시 수리 전 커밋 금지 |

## 테스트 위치 및 명명 규격
| 항목 | 내용 |
|---|---|
| **규칙** | 테스트 파일은 `tests/` 디렉토리에 위치시키며 `test_*.py` 형식 준수. 테스트 함수는 `test_*()` 형식 사용 |
| **이유** | Pytest 테스트 러너의 자동 탐색(Discovery) 규칙 준수 |
| **예시** | `tests/test_protocol.py::test_inspect_document()` |
| **위반 시** | test_ 접두사가 없는 테스트 파일 추가 금지 |

## TDD 검증 범위 및 원칙
| 항목 | 내용 |
|---|---|
| **규칙** | MCP Tool, XML 검증/치환 파싱, Edit Plan 생성 및 보안 검증 로직 구현 시 반드시 `tests/`에 해당하는 파이프라인 검증 테스트 작성 |
| **이유** | HWPX 파일 훼손 방지 및 리그레션 결함 방지 |
| **예시** | `test_apply_edit_plan_does_not_overwrite_original()` |
| **위반 시** | 핵심 로직 단위 테스트 미작성 PR 승인 불가 |
