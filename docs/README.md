# FOWOCO AI Documentation

이 디렉터리는 현재 실행 계약, 운영 가이드, 구현 과정 기록을 보존합니다.
처음 저장소를 보는 심사위원과 개발자는 아래 추천 순서부터 확인하면 됩니다.

## 추천 읽기 순서

1. [저장소 README](../README.md) — 프로젝트 목표와 전체 기능
2. [Architecture & Code Tour](architecture.md) — 설계 선택과 실제 코드 위치
3. [Analyses Contract](analyses-contract.md) — PLAN·ANALYZE 요청·응답
4. [Workflows Contract](workflows-contract.md) — Renewal Agent 실행 계약
5. [AI Runtime Handshake](ai-runtime-handshake.md) — Server 연결과 인증

## 현재 계약

아래 문서는 현재 Server·AI 연동의 기준입니다.

| 범위 | 문서 |
| --- | --- |
| PLAN·ANALYZE | [analyses-contract.md](analyses-contract.md) |
| Renewal 실행 | [workflows-contract.md](workflows-contract.md) |
| Slot 재보충 | [slot-refill-contract.md](slot-refill-contract.md) |
| Language Assistant JSON Schema | [contracts](contracts) |
| 요청·응답 예시 | [`../examples/analyses`](../examples/analyses), [`../examples/workflows`](../examples/workflows) |

## Provider·운영 가이드

| 범위 | 문서 |
| --- | --- |
| Server–AI 인증과 연결 | [ai-runtime-handshake.md](ai-runtime-handshake.md) |
| Language Assistant 설정·장애 처리 | [language-assistant-operations.md](language-assistant-operations.md) |
| CLOVA OCR 계약 | [clova-ocr-integration.md](clova-ocr-integration.md) |
| HWP·HWPX 변환 검증 | [document-conversion-poc.md](document-conversion-poc.md) |
| Language 품질 기준 | [evaluations/language-assistant-baseline.md](evaluations/language-assistant-baseline.md) |

## 모듈별 상세 문서

| 모듈 | 문서 |
| --- | --- |
| HTTP API | [`../app/api/README.md`](../app/api/README.md) |
| Renewal Agent | [`../app/agents/workflow_graph/README.md`](../app/agents/workflow_graph/README.md) |
| Language Assistant | [`../app/agents/language/README.md`](../app/agents/language/README.md) |
| 문서 처리 | [`../app/documents/README.md`](../app/documents/README.md) |
| HWPX MCP | [`../hwp-editor/README.md`](../hwp-editor/README.md) |

## 구현 과정 기록

다음 디렉터리는 설계·작업·검증 과정을 재현하기 위한 기록입니다. 현재 API 계약을
확인할 때는 위의 **현재 계약** 문서를 우선합니다.

- [`language-assistant/engineering`](language-assistant/engineering) — Language Assistant 설계, 작업, 검증 Evidence
- [`superpowers`](superpowers) — OCR·문서 자동화 설계와 구현 계획

과거 기록은 삭제하지 않습니다. 다만 현재 동작과 충돌할 경우 실행 코드, 테스트,
현재 계약 문서 순으로 판단합니다.
