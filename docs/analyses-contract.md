# Analyses Runtime 계약 (AI 소유)

Server PR #138의 `AiRuntimeHttpRequest`와 맞춘 계약이다. 계약 버전은 **1.1.0**이며,
MVP에서는 발화 하나당 대표 Intent와 canonical Workflow 한 쌍만 처리한다.

## Endpoint와 흐름

```text
POST /internal/v1/analyses

PLAN    → Intent 모델 1회 → CONTEXT_REQUIRED | OUT_OF_SCOPE
        → CONTEXT_REQUIRED: Server가 대표 Intent/Workflow 저장 + DB 조회
        → OUT_OF_SCOPE: Workflow/DB/ANALYZE 없이 종료
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
    "agentTarget": "renewal-agent",
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
    "contractVersion": "1.1.0"
  },
  "providerAttemptCount": 1,
  "latencyMs": 120
}
```

규칙:

- `workflowId`는 `WF-STY-001` 같은 Knowledge canonical ID다.
- `agentTarget`은 `renewal-agent` 같은 논리 실행 Agent ID다. `MAC`/`K8S` 같은
  배포 위치가 아니며, 물리 Endpoint는 Server의 `FOWOCO_AI_BASE_URL`이 결정한다.
- A.X는 확률을 제공하지 않으므로 `confidence=null`, `confidenceSource=UNAVAILABLE`이다.
- BERT가 최종 분류기이면 `confidenceSource=BERT`이고 confidence를 반환한다.
- 고정 규칙 fallback은 `confidenceSource=MODEL`을 사용한다.
- `bertRoutingScore`는 A.X 선택 전 참고값이며 A.X confidence가 아니다.
- `evidence`는 A.X의 원문 substring이다. BERT와 OUT_OF_SCOPE에서는 null일 수 있다.
- evidence는 Slot이 아니므로 `extractedSlots`에 `evidence:*` key를 만들지 않는다.
- A.X가 여러 Intent를 반환해도 MVP 응답은 원문 등장 순서의 첫 Intent만 사용한다.
- 같은 Intent에 여러 Knowledge Workflow가 있으면 발화/evidence의 업무 신호로 선택한다.
- `EXPIRY_RENEWAL`의 체류 신호는 `WF-STY-001`, 계약·재계약·취업활동기간 연장·고용허가기간 연장 신호는 `WF-CON-001`이다.

## OUT_OF_SCOPE 응답

실행할 Workflow가 없는 발화는 DB context를 요청하지 않고 PLAN에서 즉시 종료한다.

```json
{
  "requestId": "10000000-0000-0000-0000-000000000001",
  "outcome": "OUT_OF_SCOPE",
  "contextRequirement": null,
  "questions": [],
  "candidates": [],
  "validationErrors": [],
  "providerAttemptCount": 1
}
```

Server는 `OUT_OF_SCOPE`에서 Workflow 검증·DB 조회·ANALYZE 호출을 수행하지 않는다.

## ANALYZE 요청

```json
{
  "requestId": "10000000-0000-0000-0000-000000000001",
  "phase": "ANALYZE",
  "analysisInput": {
    "instruction": "응웬반안 체류연장 준비해줘",
    "plannedIntent": "EXPIRY_RENEWAL",
    "plannedWorkflowId": "WF-STY-001",
    "agentTarget": "renewal-agent",
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
- `agentTarget`은 전환 기간의 선택 필드다. PLAN에서 값이 반환되었다면 Server가 그대로
  보존해 ANALYZE에 전달하며, 현재 허용값은 `renewal-agent`다.
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

## Server #138 확정 정책

- PLAN의 confidence는 Intent 분류 결과다.
- Server는 PLAN의 BERT confidence, confidenceSource, bertRoutingScore를 실행 이력에 보존한다.
- ANALYZE 요청에는 `plannedIntent`, `plannedWorkflowId`와 PLAN에서 반환된 선택적
  `agentTarget`만 결정 메타데이터로 전달한다.
- AI는 Intent 모델을 재호출하지 않고 Candidate confidence를 null로 반환한다.
- Server는 Candidate confidence와 PLAN confidence를 비교하지 않으며 nullable을 허용한다.
- Candidate의 workflowId는 plannedWorkflowId와 반드시 같아야 한다.
- PLAN 결정을 재사용한 ANALYZE의 providerAttemptCount는 0이다.

## Intent 운영 설정

| 설정 | 동작 |
|---|---|
| `FOWOCO_INTENT_MODEL_ENABLED=false` | `EXPIRY_RENEWAL` 고정 규칙 |
| `FOWOCO_INTENT_MODEL_ENABLED=true` | HF BERT와 선택적 A.X 하이브리드 |
| `FOWOCO_INTENT_WARMUP_ON_START=true` | startup에서 BERT/A.X 로딩·첫 추론 |
| `FOWOCO_INTENT_WARMUP_REQUIRED=true` | warmup 실패 시 애플리케이션 startup 실패 |

A.X 사용 이미지는 `intent-ax` extra를 설치한다. 운영 장치에 맞춰
`FOWOCO_INTENT_DEVICE`를 설정하고 private HF Token은 Kubernetes Secret으로 주입한다.
BERT/Base/Adapter의 `*_REVISION`은 immutable Hugging Face commit SHA로 고정한다.

`GET /internal/v1/intent/status`에서 모델 설정, lazy-load 상태, BERT/A.X 가용성과
`promptVersion`을 확인한다. Kubernetes readiness는
`GET /internal/v1/intent/readiness`의 200 응답을 사용한다. 운영에서는 warmup 후
`ready=true`, `axAvailable=true`, `promptVersion=knowledge-25e778ad`를 확인한다.

## Fixtures

| 파일 | 용도 |
|---|---|
| `examples/analyses/request_plan.json` | PLAN 요청 |
| `examples/analyses/response_context_required.json` | CONTEXT_REQUIRED |
| `examples/analyses/request_analyze.json` | ANALYZE 요청 |
| `examples/analyses/response_needs_info.json` | NEEDS_INFO |
| `examples/analyses/response_review_required.json` | REVIEW_REQUIRED |
| `examples/analyses/response_out_of_scope.json` | OUT_OF_SCOPE |
