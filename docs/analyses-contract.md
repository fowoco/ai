# Analyses Runtime 계약 (AI 소유)

Server `docs/ai-runtime-contract.md`(PR #56)와 맞추기 위한 AI 쪽 계약 요약이다.
Language Agent는 아래 응답 fixture를 임시 입력으로 써도 된다.

## Endpoint

```text
POST /internal/v1/analyses
```

`/api/v1` prefix를 붙이지 않는다. (이전 `/api/v1/internal/v1/analyses` 는 제거)

## 요청 계약 (`analysisInput`)

옛 `maskedInput` / `maskedInstruction`은 사용하지 않는다.

```json
{
  "requestId": "10000000-0000-0000-0000-000000000001",
  "attemptId": "20000000-0000-0000-0000-000000000001",
  "contractVersion": "1.0.0",
  "requiredKnowledgeVersion": "0.2.0",
  "deadlineMs": 10000,
  "analysisInput": {
    "instruction": "가상 근로자 응웬반안(010-1234-5678)의 체류연장 준비",
    "workers": [
      {
        "workerRef": "30000000-0000-0000-0000-000000000001",
        "displayName": "응웬반안",
        "nationalityCode": "VN",
        "preferredLanguage": "vi",
        "workStatus": "ACTIVE",
        "stayExpiryDate": "2026-12-31",
        "contractStartDate": "2026-01-01",
        "contractEndDate": "2026-12-31",
        "requestedFields": {
          "legal_name": "NGUYEN VAN AN",
          "passport_number": "M12345678"
        }
      }
    ],
    "workflowConstraints": [
      {
        "workflowId": "EXPIRY_RENEWAL",
        "allowedSlotKeys": ["stay_expiry_date", "contract_end_date", "monthly_wage"]
      }
    ]
  }
}
```

| 필드 | 의미 |
|---|---|
| `instruction` | HR 원문 (데모는 가상 데이터, `***`/`OOO` 치환 없음) |
| `workers[].requestedFields` | Agent가 요구한 field의 **Server 원본값** 맵 |
| `workflowConstraints` | Workflow·slot allow-list |

요청 `requestedFields`(값 맵)와 #74 응답용 `requestedFields([{key,sourceHint}])`는 **이름이 같고 역할이 다르다**.
현재 Server #56 응답 DTO에는 후보 `requestedFields`가 없으므로 Analyses **응답 와이어에는 넣지 않는다**.

## 응답 계약 (strict JSON)

Server `FAIL_ON_UNKNOWN_PROPERTIES`에 맞춰 **알 수 없는 필드를 넣지 않는다**.
`attemptId`·`evidence`·`caseSignals`·후보 `requestedFields`는 Analyses 응답에 포함하지 않는다.

```json
{
  "requestId": "...",
  "outcome": "NEEDS_INFO | REVIEW_REQUIRED",
  "candidates": [
    {
      "candidateRef": "...",
      "workerRef": "...",
      "workflowId": "EXPIRY_RENEWAL",
      "extractedSlots": {},
      "missingSlots": [],
      "confidence": 0.92
    }
  ],
  "validationErrors": [],
  "versions": { "...": "..." },
  "providerAttemptCount": 1,
  "latencyMs": 245
}
```

`validationErrors` 항목은 `{ "code", "field" }` 객체다.

## workflowId

두 형태를 모두 받는다.

| 형태 | 예 | 언제 |
|---|---|---|
| Intent형 | `EXPIRY_RENEWAL` | Server 계약 fixture / intention projection |
| Catalog형 | `WF-STY-001` | knowledge Workflow Catalog |

- 요청 `workflowConstraints[].workflowId`에 **Intent형**이 있으면, 응답 candidate의
  `workflowId`도 **같은 문자열**을 되돌려 Server 검증을 통과시킨다.
- Catalog형 constraint면 Catalog형 id를 그대로 반환한다.
- constraint가 비어 있으면 내부 분류 결과인 Catalog형 id(`WF-…`)를 반환한다.

내부 Ambiguity/Workflow 검증은 항상 Catalog형 id로 수행한다.

## Step 3 DB 조회용 키 (Analyses → Server)

candidate / slots에서 Server가 worker·company 조회에 쓰는 값:

| 키 | 출처 | 필수 |
|---|---|---|
| `workerRef` / `extractedSlots.worker_id` | 요청 workers[].workerRef | 필수 |
| `extractedSlots.company_id` | workers[].requestedFields.company_id | 권장 |
| `extractedSlots.stay_expiry_date` | workers[] 또는 발화 추출 | 체류 경로 |
| `extractedSlots.contract_end_date` | workers[] 또는 발화 추출 | 계약 경로 |

`worker_id`·`company_id`는 `allowedSlotKeys`와 무관하게 응답 slots에 유지한다.

슬롯 부족 시 `missingSlots`로 알린다. Server 재조회·재호출 키 규약(#74):
[slot-refill-contract.md](slot-refill-contract.md)

## 핸드셰이크 (#8)

`requestId` / `attemptId` / Bearer 토큰: [ai-runtime-handshake.md](ai-runtime-handshake.md)

Server는 `Authorization: Bearer <AI_RUNTIME_SERVICE_CREDENTIAL>`과
`X-Request-Id`(=requestId), 선택적 `traceparent`를 보낸다.
AI는 `FOWOCO_INTERNAL_API_TOKEN`과 동일 값으로 검증한다.

## Versions

`contractVersion=1.0.0`, `requiredKnowledgeVersion=0.2.0` 을 기본으로 둔다.
응답 `versions.workflowCatalogVersion`은 서버 `task.workflow_catalog_version`과 맞출 값이다.
MVP 응답의 model* 필드는 `stub`이다.

## Fixtures

| 파일 | 용도 |
|---|---|
| `examples/analyses/request_expiry_renewal.json` | Server 스타일 요청 |
| `examples/analyses/response_needs_info.json` | 안내문 생성이 필요한 응답 예시 |
| `examples/analyses/response_review_required.json` | HR 검토용 응답 예시 |

## Knowledge 연동 (선택)

기본은 builtin 규칙. `FOWOCO_KNOWLEDGE_ENABLED=true` 이면
`fowoco-knowledge` 패키지에서 required_slots·ambiguity·workflow catalog를 읽는다.

```powershell
pip install -e ..\knowledge\fowoco-knowledge
$env:FOWOCO_KNOWLEDGE_ENABLED="true"
# 선택: $env:FOWOCO_KNOWLEDGE_ROOT="..\knowledge\fowoco-knowledge"
```
