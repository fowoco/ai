# Analyses Runtime 계약 (AI 소유)

Server `docs/ai-runtime-contract.md` + `AiRuntimeHttpRequest` (fowoco/server main)과 맞춘다.  
**HTTP 와이어**는 최소 페이로드다. `attemptId` / version / deadline / `extractedSlots` /
`workflowConstraints` 는 Server 내부 `AiAnalysisRequest`에만 있고 **요청 JSON에 실리지 않는다**.

## Endpoint

```text
POST /internal/v1/analyses
```

## 흐름

```text
PLAN  → CONTEXT_REQUIRED (requiredFieldKeys)
      → Server DB 조회
ANALYZE → NEEDS_INFO (questions) | REVIEW_REQUIRED (candidates)
```

`CONTEXT_REQUIRED` / `NEEDS_INFO` / `REVIEW_REQUIRED` 는 모두 **성공 outcome** 이다 (`FAILED` 아님).

---

## 1) PLAN 요청 (Server → AI)

```json
{
  "requestId": "10000000-0000-0000-0000-000000000001",
  "phase": "PLAN",
  "analysisInput": {
    "instruction": "응웬반안 체류연장 준비해줘"
  }
}
```

| 필드 | 규칙 |
|---|---|
| `requestId` | 필수. 응답에 그대로 에코 |
| `phase` | `"PLAN"` |
| `analysisInput.instruction` | HR 발화 **원문만** (Intent 태그·코드 미부착, Issue #6) |
| workers / requestedFieldKeys | **보내지 않음** (PLAN) |
| `intentHint` | **없음** (폐기) |
| attemptId / contractVersion / deadlineMs 등 | HTTP에 **없음** (Server 내부) |

## 2) CONTEXT_REQUIRED 응답 (AI → Server)

```json
{
  "requestId": "10000000-0000-0000-0000-000000000001",
  "outcome": "CONTEXT_REQUIRED",
  "contextRequirement": {
    "detectedIntent": "EXPIRY_RENEWAL",
    "confidence": 0.94,
    "targetDisplayName": "응웬반안",
    "extractedSlots": {},
    "requiredFieldKeys": ["worker_id", "stay_expiry_date"]
  },
  "questions": [],
  "candidates": [],
  "validationErrors": [],
  "versions": { "...": "..." },
  "providerAttemptCount": 1,
  "latencyMs": 120
}
```

| 규칙 | 내용 |
|---|---|
| `requiredFieldKeys` | 비어 있으면 Server 거부. Knowledge canonical key만 (`worker_id` 포함) |
| `questions` / `candidates` | 비움 |
| `confidence` | 0.0 ~ 1.0 |

## 3) ANALYZE 요청 (Server → AI)

```json
{
  "requestId": "10000000-0000-0000-0000-000000000001",
  "phase": "ANALYZE",
  "analysisInput": {
    "instruction": "응웬반안 체류연장 준비해줘",
    "requestedFieldKeys": ["worker_id", "stay_expiry_date"],
    "workers": [
      {
        "workerRef": "30000000-0000-0000-0000-000000000001",
        "requestedFields": {
          "worker_id": "30000000-0000-0000-0000-000000000001",
          "stay_expiry_date": "2026-12-31"
        }
      }
    ]
  }
}
```

| 필드 | 규칙 |
|---|---|
| `requestedFieldKeys` | PLAN에서 Agent가 요청한 **전체** key (DB 미조회여도 목록 유지) |
| `workers[].requestedFields` | Server가 **실제로 찾은 값만** |
| DB 미조회 키 | `requestedFieldKeys − requestedFields.keys` → HR 질문 후보 |
| MVP | Worker **1명** |
| HTTP에 안 실림 | `extractedSlots`, `workflowConstraints`, attemptId, versions, deadline |

> 이슈 댓글의 ANALYZE `extractedSlots` 와이어 추가는 **최종 HTTP 계약에서 제외**됨  
> (`AiRuntimeHttpRequest` 주석·직렬화 기준).

## 4) ANALYZE 응답

### NEEDS_INFO

- `contextRequirement`: null  
- `candidates`: []  
- `questions`: **1개 이상** `{ "slotKey", "prompt" }`

### REVIEW_REQUIRED

- `contextRequirement`: null  
- `questions`: []  
- `candidates`: **1개 이상** (기존 AiCandidate 필드)

```json
{
  "candidateRef": "candidate-1",
  "workerRef": "30000000-0000-0000-0000-000000000001",
  "workflowId": "EXPIRY_RENEWAL",
  "extractedSlots": { "stay_expiry_date": "2026-12-31" },
  "missingSlots": ["contract_end_date", "monthly_wage"],
  "confidence": 0.92
}
```

공통 응답 필드: `validationErrors`, `versions`, `providerAttemptCount`, `latencyMs`.

### versions (응답 필수)

Server가 내부 요청의 `contractVersion` / `requiredKnowledgeVersion` 과  
응답 `versions.contractVersion` / `versions.workflowCatalogVersion` 을 대조한다.  
HTTP 요청에 version이 없어도 AI는 기본값 **`1.0.0` / `0.2.0`** 을 맞춰야 한다.

---

## 우리(AI) 구현 상태

| 항목 | Server HTTP | AI (`schemas` / `pipeline`) |
|---|---|---|
| `phase` PLAN/ANALYZE | 필수 | **반영** |
| `CONTEXT_REQUIRED` | 있음 | **반영** |
| `questions` | NEEDS_INFO | **반영** |
| ANALYZE `requestedFieldKeys` | 있음 | **반영** |
| workers 최소 필드 | workerRef + requestedFields | **반영** (추가 필드는 선택) |
| attemptId 등 | HTTP 미전송 | **요청에서 제거** |
| 슬롯 기준 | Knowledge | Ambiguity/Workflow catalog |
| versions | 응답 필수 | `1.0.0` / `0.2.0` 고정 |

## Intent 분류기

| 설정 | 동작 |
|---|---|
| `FOWOCO_INTENT_MODEL_ENABLED=false` (기본) | `EXPIRY_RENEWAL` 고정 stub |
| `FOWOCO_INTENT_MODEL_ENABLED=true` | HF BERT(+선택 A.X) 하이브리드 |

필요 시: `pip install -e ".[intent]"`, `.env`에 `FOWOCO_HF_TOKEN` 또는 `HF_TOKEN`,  
`FOWOCO_INTENT_BERT_MODEL_DIR=fowoco/klue-roberta-base-intent-classifier`.  
로컬 CPU는 `FOWOCO_INTENT_ENABLE_AX=false` 권장.

## Fixtures

| 파일 | 용도 |
|---|---|
| `examples/analyses/request_plan.json` | PLAN 요청 |
| `examples/analyses/response_context_required.json` | CONTEXT_REQUIRED |
| `examples/analyses/request_analyze.json` | ANALYZE 요청 |
| `examples/analyses/response_needs_info.json` | NEEDS_INFO (신계약) |
| `examples/analyses/response_review_required.json` | REVIEW_REQUIRED |
| `examples/analyses/request_expiry_renewal.json` | **구계약** 참고용 (폐기 예정) |

## 핸드셰이크 (#8)

[ai-runtime-handshake.md](ai-runtime-handshake.md) — Bearer, `X-Request-Id` = requestId.
