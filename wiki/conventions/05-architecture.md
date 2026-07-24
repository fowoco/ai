---
title: "아키텍처 규칙"
type: convention
created: 2026-07-24
updated: 2026-07-24
---

# 아키텍처 규칙

## 계층 구조 및 레이어 분리
| 항목 | 내용 |
|---|---|
| **규칙** | Interface Layer(`FastMCP`, `FastAPI`), Application Service Layer(비즈니스 조율/세션/Edit Plan), Domain/Engine Layer(`defusedxml`, `rhwp`, Pydantic 스키마)로 3계층 분리 |
| **이유** | MCP 프로토콜 및 HTTP Control Plane의 독립성 확보 및 비즈니스 로직 재사용성 증대 |
| **예시** | `FastMCP`와 `FastAPI`는 모두 동일한 `DocumentService` 메서드를 호출 |
| **위반 시** | Interface 계층(`server.py` 등)에서 직접 XML 파일 다이렉트 수정 금지 |

## 의존성 방향 규칙
| 항목 | 내용 |
|---|---|
| **규칙** | 의존성은 반드시 `Interface` -> `Application Service` -> `Domain/Engine` 단방향으로만 흐름 |
| **이유** | 하위 엔진 변경(예: Python 파서 -> rhwp 통합) 시 상위 프레임워크 코드에 영향 최소화 |
| **예시** | Domain Engine은 FastAPI/FastMCP 패키지를 임포트하지 않음 |
| **위반 시** | 순환 의존성 발생 시 빌드/CI 실패 처리 |

## 데이터 통신 규격
| 항목 | 내용 |
|---|---|
| **규칙** | 레이어 간 데이터 전달은 Pydantic 기반 데이터 모델(`DocumentManifest`, `EditPlan`, `ValidationReport`)로 명시적 수행 |
| **이유** | 데이터 유효성 자동 검증 및 명확한 런타임 타입 보장 |
| **예시** | `service.create_edit_plan(...) -> EditPlan` |
| **위반 시** | 임의의 `dict`나 튜플 기반 데이터 전달 지양 |
