---
title: "네이밍 컨벤션"
type: convention
created: 2026-07-24
updated: 2026-07-24
---

# 네이밍 컨벤션

## 식별자 네이밍 표기법
| 항목 | 내용 |
|---|---|
| **규칙** | 변수·함수·메서드: `snake_case`. 클래스·Pydantic 스키마: `PascalCase`. 상수: `UPPER_SNAKE_CASE` |
| **이유** | PEP 8 Python 표준 네이밍 규칙 준수 및 코드 가독성 보장 |
| **예시** | `inspect_document()`, `class DocumentManifest:`, `MAX_FILE_SIZE_MB = 50` |
| **위반 시** | camelCase 변수명이나 mixedCase 클래스명 사용 시 리팩토링 요청 |

## 파일 및 모듈 네이밍
| 항목 | 내용 |
|---|---|
| **규칙** | 모든 Python 소스 파일과 테스트 파일은 소문자 `snake_case`로 작성 |
| **이유** | 대소문자 구별 OS 환경 간 파이썬 임포트 충돌 방지 |
| **예시** | `server.py`, `hwpx_parser.py`, `test_hwpx.py` |
| **위반 시** | 케밥 케이스(`-`)나 대문자 포함 파일명 수정 |

## 디렉토리 및 모듈 구조
| 항목 | 내용 |
|---|---|
| **규칙** | Python 모듈은 `src/hwp_mcp/` 아래 위치시키며 `src layout` 구조 준수. 테스트는 `tests/` 폴더 분리 |
| **이유** | 파이썬 표준 패키지 빌드(Hatchling) 및 개발/테스트 격리 |
| **예시** | `src/hwp_mcp/server.py`, `tests/test_protocol.py` |
| **위반 시** | `src/` 외부에 메인 소스 모듈 직접 작성 금지 |
