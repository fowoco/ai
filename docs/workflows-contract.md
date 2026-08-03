# Renewal Workflow Runtime 계약 (AI 소유)

Server가 재갱신 LangGraph를 호출할 때 쓰는 Internal API 요약이다.

## 역할 분리

| 주체 | 책임 |
|---|---|
| **AI (휘)** | Shared State·슈퍼바이저·서브그래프·`outcome`/`status`/`caseSignals`/`progressEvents`·서류 초안 |
| **Server** | Case/Task **생성**, worker·company·task 일괄 조회, UI 상태·WebSocket 반영 |

AI는 Workflow/Task 행을 만들지 않는다. 판단 신호만 주고 Server가 반영한다.

## Endpoint

```text
POST /internal/v1/workflows/renewal/run
```

## 흐름

1. Server → AI: `instruction` + ids + 일괄 스냅샷
2. AI: `load_context` → **Language 서브그래프** → **Supervisor** → OCR/Document/대기 분기
3. AI → Server: 판단 신호 + `progressEvents` (호출 단위 진행 로그)

실시간 전광판(WebSocket)은 Server가 `progressEvents`/`status`를 중계한다.

## 판단 신호

| 필드 | 의미 |
|---|---|
| `outcome` / `status` | 상태 |
| `scenario` | `ask_hr`(담당자 화면 입력) · `ask_worker`(근로자 서류) · `generate`(초안) · `ocr` · `out_of_scope` |
| `phase` / `step` | PHASE_1~4 / STEP_* |
| `caseSignals` | 예: `REQUEST_ALIEN_REGISTRATION`, `GENERATE_DRAFTS` |
| `documentValidation` | `{passport, alienRegistration, combo}` |
| `progressEvents` | `[{phase, step, message, subgraph}, …]` |
| `evidence` | Intent·서류 근거 |
| `supervisorSource` | `rules` \| `llm` |

### combo (Step4)

`both_present` · `passport_only` · `alien_only` · `both_missing` · `partial_unknown`

| scenario | outcome | 쉬운 말 | 다음 Server 행동 |
|---|---|---|---|
| `ask_worker` | `WAITING_WORKER` | 근로자에게 서류 달라 | 서류 모아 `documents`로 재호출 |
| `ask_hr` | `NEEDS_INFO` | 담당자가 화면에 입력 | `slots` 채워 재호출 |
| `generate` | `REVIEW_REQUIRED` | 초안 나옴 | 미리보기·승인 |
| `out_of_scope` | `OUT_OF_SCOPE` | 범위 밖 | 재시작 |

## 설정

- `FOWOCO_SUPERVISOR_MODE=rules` (기본) \| `llm`
- LLM 모드: `FOWOCO_LLM_PROVIDER`, `FOWOCO_LLM_API_KEY`, `FOWOCO_LLM_MODEL`

## Fixtures

| 파일 | 용도 |
|---|---|
| `examples/workflows/request_renewal_full_entities.json` | 사람·기업·업무 ERD 풀컬럼 일괄 요청 |
| `examples/workflows/response_renewal_review_required.json` | 초안 4종·REVIEW_REQUIRED 응답 |
| `examples/workflows/request_renewal_waiting_worker.json` | 최초 요청 (최소) |
| `examples/workflows/request_renewal_with_ocr.json` | OCR 재개 |
| `examples/workflows/response_needs_info.json` | 담당자 입력 예 |

노드 교체: [app/agents/workflow_graph/README.md](../app/agents/workflow_graph/README.md)
