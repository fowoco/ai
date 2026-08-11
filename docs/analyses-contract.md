# Analyses Runtime 계약 (AI 소유)

Server PR #138의 `AiRuntimeHttpRequest`와 맞춘 계약이다. 계약 버전은 **1.0.0**이며,
MVP에서는 발화 하나당 대표 Intent와 canonical Workflow 한 쌍만 처리한다.

## Endpoint와 흐름

```text
POST /internal/v1/analyses

PLAN    → Intent 모델 1회 → CONTEXT_REQUIRED
        → Server가 대표 Intent/Workflow 저장 + DB 조회
ANALYZE → PLAN 결정 재사용(모델 0회) → NEEDS_INFO | REVIEW_REQUIRED
```

## PLAN 요청

```json
{
  "requestId": "10000000-0000-0000-0000-000000000001",
  "phase": "PLAN",
  "analysisInput": {
    "instruction": "응웬반안 체류연장 준비해줘"
  }
}
```

PLAN에는 `plannedIntent`, `plannedWorkflowId`, Worker context를 보내지 않는다.

## CONTEXT_REQUIRED 응답

```json
{
  "requestId": "10000000-0000-0000-0000-000000000001",
  "outcome": "CONTEXT_REQUIRED",
  "contextRequirement": {
    "detectedIntent": "EXPIRY_RENEWAL",
    "workflowId": "WF-STY-001",
    "evidence": "체류연장 준비해줘",
    "confidence": null,
    "confidenceSource": "UNAVAILABLE",
    "bertRoutingScore": 0.3088,
    "targetDisplayName": "응웬반안",
    "extractedSlots": {},
    "requiredFieldKeys": [
      "worker_id",
      "stay_expiry_date",
      "passport_status",
      "arc_status"
    ]
  },
  "questions": [],
  "candidates": [],
  "validationErrors": [],
  "versions": {
    "agentVersion": "0.1.0",
    "modelProvider": "huggingface",
    "modelName": "skt/A.X-4.0-Light",
    "modelVersion": "AX",
    "promptVersion": "knowledge-25e778ad",
    "contextPackVersion": "0.2.0",
    "workflowCatalogVersion": "0.2.0",
    "contractVersion": "1.0.0"
  },
  "providerAttemptCount": 1,
  "latencyMs": 120
}
```

규칙:

- `workflowId`는 `WF-STY-001` 같은 Knowledge canonical ID다.
- A.X는 확률을 제공하지 않으므로 `confidence=null`, `confidenceSource=UNAVAILABLE`이다.
- BERT가 최종 분류기이면 `confidenceSource=BERT`이고 confidence를 반환한다.
- 고정 규칙 fallback은 `confidenceSource=MODEL`을 사용한다.
- `bertRoutingScore`는 A.X 선택 전 참고값이며 A.X confidence가 아니다.
- `evidence`는 A.X의 원문 substring이다. BERT와 OUT_OF_SCOPE에서는 null일 수 있다.
- evidence는 Slot이 아니므로 `extractedSlots`에 `evidence:*` key를 만들지 않는다.
- A.X가 여러 Intent를 반환해도 MVP 응답은 원문 등장 순서의 첫 Intent만 사용한다.

## ANALYZE 요청

```json
{
  "requestId": "10000000-0000-0000-0000-000000000001",
  "phase": "ANALYZE",
  "analysisInput": {
    "instruction": "응웬반안 체류연장 준비해줘",
    "plannedIntent": "EXPIRY_RENEWAL",
    "plannedWorkflowId": "WF-STY-001",
    "requestedFieldKeys": [
      "worker_id",
      "stay_expiry_date",
      "passport_status",
      "arc_status"
    ],
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

규칙:

- `plannedIntent`, `plannedWorkflowId`는 모두 필수다. 하나라도 없으면 422로 거부한다.
- AI는 이 값을 신뢰하여 Intent 모델을 다시 호출하지 않고 Slot/Context만 검사한다.
- `providerAttemptCount=0`은 ANALYZE에서 모델 호출이 없었음을 뜻한다.
- `requestedFieldKeys`는 PLAN에서 요청한 전체 key다.
- `workers[].requestedFields`에는 Server DB에서 실제로 찾은 값만 담는다.
- MVP는 Worker 한 명과 대표 Intent/Workflow 한 쌍만 처리한다.

## ANALYZE 응답

### NEEDS_INFO

- `contextRequirement`: null
- `candidates`: []
- `questions`: 한 개 이상

### REVIEW_REQUIRED

```json
{
  "candidateRef": "candidate-1",
  "workerRef": "30000000-0000-0000-0000-000000000001",
  "workflowId": "WF-STY-001",
  "extractedSlots": {
    "worker_id": "30000000-0000-0000-0000-000000000001",
    "stay_expiry_date": "2026-12-31"
  },
  "missingSlots": [],
  "confidence": null
}
```

Candidate의 `workflowId`는 `plannedWorkflowId`와 반드시 같아야 한다. ANALYZE는 모델을
재호출하지 않고 Server가 confidence를 다시 보내지 않으므로 AI는 새 점수를 만들지 않는다.

## Server #138 확인·대기 항목

PR #138은 A.X의 nullable confidence, nullable evidence, ANALYZE의
`providerAttemptCount=0`을 이미 허용한다. 따라서 A.X 대표 Intent 경로는 이 계약과 맞는다.

남은 경계 사례는 BERT 경로다. Server는 ANALYZE Candidate confidence가 PLAN confidence와
같기를 요구하지만, HTTP 요청에는 `plannedIntent`, `plannedWorkflowId`만 보내므로 AI가 PLAN의
BERT 점수를 알 수 없다. AI는 재분류하거나 점수를 만들지 않고 Candidate confidence를 null로
유지한다. Server는 BERT 경로에서 Candidate confidence 비교를 제거하거나, 별도 계약 합의 후
PLAN confidence를 ANALYZE에 전달해야 한다.

## Intent 운영 설정

| 설정 | 동작 |
|---|---|
| `FOWOCO_INTENT_MODEL_ENABLED=false` | `EXPIRY_RENEWAL` 고정 규칙 |
| `FOWOCO_INTENT_MODEL_ENABLED=true` | HF BERT와 선택적 A.X 하이브리드 |

A.X 사용 이미지는 `intent-ax` extra를 설치한다. 운영 장치에 맞춰
`FOWOCO_INTENT_DEVICE`를 설정하고 private HF Token은 Kubernetes Secret으로 주입한다.
BERT/Base/Adapter의 `*_REVISION`은 immutable Hugging Face commit SHA로 고정한다.

`GET /internal/v1/intent/status`에서 모델 설정, lazy-load 상태, BERT/A.X 가용성과
`promptVersion`을 확인한다. 배포 smoke PLAN 후 `axAvailable=true`,
`promptVersion=knowledge-25e778ad`를 확인한다.

## Fixtures

| 파일 | 용도 |
|---|---|
| `examples/analyses/request_plan.json` | PLAN 요청 |
| `examples/analyses/response_context_required.json` | CONTEXT_REQUIRED |
| `examples/analyses/request_analyze.json` | ANALYZE 요청 |
| `examples/analyses/response_needs_info.json` | NEEDS_INFO |
| `examples/analyses/response_review_required.json` | REVIEW_REQUIRED |
