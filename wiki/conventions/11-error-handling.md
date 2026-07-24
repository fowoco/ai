---
title: "에러 핸들링"
type: convention
created: 2026-07-24
updated: 2026-07-24
---

# 에러 핸들링

## 예외 클래스 체계
| 항목 | 내용 |
|---|---|
| **규칙** | 도메인 전용 예외 클래스(`HwpxValidationError`, `HwpxSecurityError`, `EditPlanError`)를 정의하여 사용 |
| **이유** | 일반 `Exception` 캡처로 인한 에러 원인 은폐 방지 및 세분화된 에러 핸들링 |
| **예시** | `raise HwpxSecurityError("허용된 HWP_MCP_ROOT 경계를 벗어났습니다")` |
| **위반 시** | 예외를 안으로 삼키는 백지 `except: pass` 처리 절대 금지 |

## 로깅 정책 및 레벨
| 항목 | 내용 |
|---|---|
| **규칙** | Python 표준 `logging` 모듈 사용. 레벨 기준: `DEBUG`(XML/좌표 세부 파싱), `INFO`(MCP Tool 호출/Plan 생성), `ERROR`(보안 위반/XML 파싱 결함) |
| **이유** | 디버깅 정보 확보 및 프로덕션 관관성 유지 |
| **예시** | `logger.error("Failed to parse section XML: %s", err)` |
| **위반 시** | `print()` 문을 로깅 목적으로 소스 코드에 남기는 행위 금지 |

## 에러 응답 및 차단 정책
| 항목 | 내용 |
|---|---|
| **규칙** | 레이아웃 붕괴, XML 유효성 미통과, 원본 훼손 우려 발생 시 즉시 프로세스를 안전 중단(`BLOCKED`)하고 사유 리포트 반환 |
| **이유** | 손상되거나 비정상적인 HWPX 파일 생성 방지 |
| **예시** | MCP Tool 응답 `isError=True` 및 상세 원인 전달 |
| **위반 시** | 에러가 발생했는데 정상 파일인 것처럼 빈 파일 반환 금지 |
