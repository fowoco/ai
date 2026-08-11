# Analyses Runtime 계약 (AI 소유)

Server `docs/ai-runtime-contract.md` + `AiRuntimeHttpRequest` (fowoco/server main)과 맞춘다.
계약 버전은 **1.1.0**이다. `attemptId` / deadline / `workflowConstraints`는 Server 내부에만
두며, PLAN에서 확정한 Intent 결정은 ANALYZE 요청에 되돌려 보내 재분류를 막는다.

## Endpoint

```text
POST /internal/v1/analyses
```

## 흐름

```text
PLAN  → Intent/A.X 1회 → CONTEXT_REQUIRED (intentDecisions + requiredFieldKeys)
      → Server DB 조회
ANALYZE → PLAN 결정 재사용(모델 0회) → NEEDS_INFO (questions) | REVIEW_REQUIRED (candidates)
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
    "workflowId": "WF-STY-001",
    "confidence": null,
    "confidenceSource": "UNAVAILABLE",
    "bertRoutingScore": 0.3088,
    "intentDecisions": [
      {
        "detectedIntent": "EXPIRY_RENEWAL",
        "workflowId": "WF-STY-001",
        "evidence": "체류연장 준비해줘",
        "confidence": null,
        "confidenceSource": "UNAVAILABLE",
        "bertRoutingScore": 0.3088,
        "modelProvider": "huggingface",
        "modelName": "skt/A.X-4.0-Light",
        "modelVersion": "AX",
        "promptVersion": "knowledge-25e778ad"
      }
    ],
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
| `confidence` | BERT/RULES는 0.0~1.0. A.X는 score가 없으므로 `null` |
| `confidenceSource` | `BERT`, `RULES`, `UNAVAILABLE` 중 하나 |
| `bertRoutingScore` | A.X 선택 전 라우팅 참고값. A.X confidence로 해석하면 안 됨 |
| `intentDecisions` | 복합 Intent를 원문 순서대로 보존. 각 항목은 canonical `workflowId` 포함 |

## 3) ANALYZE 요청 (Server → AI)

```json
{
  "requestId": "10000000-0000-0000-0000-000000000001",
  "phase": "ANALYZE",
  "analysisInput": {
    "instruction": "응웬반안 체류연장 준비해줘",
    "plannedIntent": "EXPIRY_RENEWAL",
    "plannedWorkflowId": "WF-STY-001",
    "plannedIntentDecisions": [
      {
        "detectedIntent": "EXPIRY_RENEWAL",
        "workflowId": "WF-STY-001",
        "evidence": "체류연장 준비해줘",
        "confidence": null,
        "confidenceSource": "UNAVAILABLE",
        "bertRoutingScore": 0.3088,
        "modelProvider": "huggingface",
        "modelName": "skt/A.X-4.0-Light",
        "modelVersion": "AX",
        "promptVersion": "knowledge-25e778ad"
      }
    ],
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
| `plannedIntentDecisions` | PLAN 응답의 `intentDecisions`를 변경 없이 전달. 복합 Intent 권장 계약 |
| `plannedIntent` / `plannedWorkflowId` | 단일 Intent 호출자의 최소 재사용 계약 |
| DB 미조회 키 | `requestedFieldKeys − requestedFields.keys` → HR 질문 후보 |
| MVP | Worker **1명** |
| HTTP에 안 실림 | `extractedSlots`, `workflowConstraints`, attemptId, versions, deadline |

`plannedIntentDecisions`가 있으면 배열이 단일 필드보다 우선한다. 두 계약이 모두 없을 때만
1.0 하위호환을 위해 Intent 모델을 다시 호출하며, 이 경로는 Server 전환 후 제거할 수 있다.

## 4) ANALYZE 응답

### NEEDS_INFO

- `contextRequirement`: null  
- `candidates`: []  
- `questions`: **1개 이상** `{ "slotKey", "prompt" }`

### REVIEW_REQUIRED

- `contextRequirement`: null  
- `questions`: []  
- `candidates`: **1개 이상** (기존 AiCandidate 필드)
- `detectedIntent`는 `EXPIRY_RENEWAL` 같은 업무 종류이며, 후보의 `workflowId`는 `WF-STY-001` 같은 구체적인 Workflow Catalog ID다.
- `workflowId`에 Intent 코드를 다시 넣지 않는다.

```json
{
  "candidateRef": "candidate-1",
  "workerRef": "30000000-0000-0000-0000-000000000001",
  "detectedIntent": "EXPIRY_RENEWAL",
  "workflowId": "WF-STY-001",
  "extractedSlots": {
    "worker_id": "30000000-0000-0000-0000-000000000001",
    "stay_expiry_date": "2026-12-31",
    "full_name": "NGUYEN VAN AN"
  },
  "missingSlots": [],
  "confidence": null,
  "confidenceSource": "UNAVAILABLE",
  "bertRoutingScore": 0.3088
}
```

`missingSlots`는 REVIEW 직전 필수 슬롯이 모두 채워졌을 때 **빈 배열**이다.  
남은 HR 입력은 `NEEDS_INFO.questions`로 보낸다.

공통 응답 필드: `validationErrors`, `versions`, `providerAttemptCount`, `latencyMs`.

### versions (응답 필수)

Server가 내부 요청의 `contractVersion` / `requiredKnowledgeVersion` 과  
응답 `versions.contractVersion` / `versions.workflowCatalogVersion` 을 대조한다.  
HTTP 요청에 version이 없어도 AI는 기본값 **`1.1.0` / `0.2.0`** 을 맞춰야 한다.

---

## 우리(AI) 구현 상태

| 항목 | Server HTTP | AI (`schemas` / `pipeline`) |
|---|---|---|
| `phase` PLAN/ANALYZE | 필수 | **반영** |
| `CONTEXT_REQUIRED` | 있음 | **반영** |
| `questions` | NEEDS_INFO | **반영** |
| ANALYZE `requestedFieldKeys` | 있음 | **반영** |
| PLAN 결정 재사용 | plannedIntent(s) | **반영** (ANALYZE providerAttemptCount=0) |
| 복합 Intent | intentDecisions[] | **반영** (Intent별 candidate) |
| A.X confidence | score 없음 | **null + BERT routing score 분리** |
| workers 최소 필드 | workerRef + requestedFields | **반영** (추가 필드는 선택) |
| attemptId 등 | HTTP 미전송 | **요청에서 제거** |
| 슬롯 기준 | Knowledge | Ambiguity/Workflow catalog |
| versions | 응답 필수 | `1.1.0` / `0.2.0` 고정 |

## Intent 분류기

| 설정 | 동작 |
|---|---|
| `FOWOCO_INTENT_MODEL_ENABLED=false` (기본) | `EXPIRY_RENEWAL` 고정 stub |
| `FOWOCO_INTENT_MODEL_ENABLED=true` | HF BERT(+선택 A.X) 하이브리드 |

필요 시 BERT만: `pip install -e ".[intent]"` (Windows CPU 권장).  
A.X까지: `pip install -e ".[intent-ax]"` (Linux/CUDA; Windows에선 `bitsandbytes` 실패 흔함).  
`.env`에 `FOWOCO_HF_TOKEN` 또는 `HF_TOKEN`,  
`FOWOCO_INTENT_BERT_MODEL_DIR=fowoco/klue-roberta-base-intent-classifier`.  
로컬 CPU는 `FOWOCO_INTENT_ENABLE_AX=false` 권장. 운영은 실제 추론 장치에 맞춰
`FOWOCO_INTENT_DEVICE`를 설정하고 private 모델 토큰은 Kubernetes Secret으로만 주입한다.
BERT/Base/Adapter의 `*_REVISION`은 배포 전에 immutable Hugging Face commit SHA로 고정한다.

`GET /internal/v1/intent/status`에서 설정 활성화, lazy-load 완료 여부, BERT/A.X 가용성과
`promptVersion`을 확인한다. 상태 조회는 모델을 강제로 로드하지 않으므로 배포 smoke PLAN 후
`axAvailable=true`, `promptVersion=knowledge-25e778ad`를 확인한다.

## Fixtures

| 파일 | 용도 |
|---|---|
| `examples/analyses/request_plan.json` | PLAN 요청 |
| `examples/analyses/response_context_required.json` | CONTEXT_REQUIRED |
| `examples/analyses/request_analyze.json` | ANALYZE 요청 |
| `examples/analyses/response_needs_info.json` | NEEDS_INFO |
| `examples/analyses/response_review_required.json` | REVIEW_REQUIRED |

## 핸드셰이크 (#8)

[ai-runtime-handshake.md](ai-runtime-handshake.md) — Bearer, `X-Request-Id` = requestId.
