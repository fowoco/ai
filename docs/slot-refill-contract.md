# Slot 조회·재호출 계약 (#74) — AI 소유 초안

Server가 Agent `missingSlots`/`requestedFields`를 보고 DB에서 값을 채워 **다시 Agent를 호출**할 때의 키 규약이다.
Knowledge `required_slots`와 builtin Ambiguity 목록을 기준으로 맞춘다.

## 왕복 흐름

```text
1) Server → AI  (analyses 또는 renewal/run)
2) AI → Server  missingSlots + requestedFields
3) Server      DB/화면에서 값 조회·보완
4) Server → AI  같은 requestId(+attemptId)로 slots 채워 재호출
5) 충분하면     outcome=REVIEW_REQUIRED 등 / 부족하면 2) 반복
```

중복 Intent·Task 남발은 피하고, **같은 requestId 계열의 재시도(attempt)** 로 슬롯만 채운다.

## requestedFields 항목

| JSON 필드 | 의미 |
|---|---|
| `key` | 슬롯 키 (snake_case, Knowledge/AI 공통) |
| `sourceHint` | Server가 어디서 찾을지 힌트 |

### sourceHint

| 값 | Server 행동 |
|---|---|
| `WORKER_DB` | `worker` 테이블·관련 문서 메타에서 조회 |
| `COMPANY_DB` | `company` 테이블에서 조회 |
| `TASK_BUSINESS_DATA` | `task.business_data_json`에서 조회 |
| `USER_INPUT` | HR 화면 입력 요청 (DB에 없음) |
| `DOCUMENT_OCR` | 서류 업로드·OCR 후 재호출 |
| `REQUEST` | 이미 요청에 있어야 하는 식별자 (`worker_id` 등) |

## 대표 워크플로 Slot ↔ sourceHint

Knowledge 0.3.1의 `required`와 `resolvable_from_context`를 구분한다. PLAN은
Context 조회 대상을 내려주고, AI는 그중 필수 Slot이 없을 때만 HR 질문을 만든다.

| workflowId | key | 구분 | sourceHint |
|---|---|---|---|
| `WF-STY-001` | `worker_id` | 필수 | `REQUEST` |
| `WF-STY-001` | `due_at` | 필수 | `TASK_BUSINESS_DATA` 또는 `USER_INPUT` |
| `WF-STY-001` | `stay_expiry_date` | 선택 Context | `WORKER_DB` |
| `WF-STY-001` | `passport_status` | 선택 Context | `WORKER_DB` |
| `WF-STY-001` | `arc_status` | 선택 Context | `WORKER_DB` |
| `WF-CON-001` | `worker_id` | 필수 | `REQUEST` |
| `WF-CON-001` | `due_at` | 필수 | `TASK_BUSINESS_DATA` 또는 `USER_INPUT` |
| `WF-CON-001` | `contract_end_date` | 선택 Context | `WORKER_DB` |

### 재갱신(EXPIRY_RENEWAL) 추가 슬롯 (시나리오)

| key | sourceHint | 시나리오 |
|---|---|---|
| `passport_number` | `DOCUMENT_OCR` | 2 |
| `alien_registration_number` | `DOCUMENT_OCR` | 2 |
| `nationality` | `WORKER_DB` 또는 `DOCUMENT_OCR` | 2 |
| `full_name` | `WORKER_DB` (`display_name`) 또는 OCR | 2 |
| `date_of_birth` | `DOCUMENT_OCR` | 2 |
| `wage` | `USER_INPUT` | 1 |
| `working_hours` | `USER_INPUT` | 1 |
| `job_description` | `USER_INPUT` | 1 |
| `work_location` | `USER_INPUT` | 1 |
| `lodging` | `USER_INPUT` | 1 |
| `contract_period` | `USER_INPUT` | 1 |
| `company_id` | `REQUEST` / `WORKER_DB` | 공통 |

## 응답 예 (Analyses candidate)

Server #56 Analyses 응답 와이어에는 `missingSlots`만 실는다.
아래 `requestedFields` 리스트는 #74 재조회 orchestration용 규약이며,
현재 Server `AiCandidate` strict JSON에는 아직 없다.

```json
{
  "missingSlots": ["due_at"],
  "requestedFields": [
    { "key": "due_at", "sourceHint": "USER_INPUT" }
  ]
}
```

요청의 `workers[].requestedFields`는 **값 맵**(원본 업무 데이터)이고,
여기 응답/재조회용 `requestedFields`는 **`[{key,sourceHint}]` 리스트**다.

## 재호출 요청 (Server → AI)

- **같은** `requestId` 유지
- `attemptId`는 시도마다 새 UUID (또는 서버 AI Run attempt)
- `extractedSlots` / `slots`에 찾은 값만 병합해 전달
- `WORKER_DB`·`COMPANY_DB` 값은 가능하면 worker/company **일괄 스냅샷**으로도 같이 보냄 ([workflows-contract.md](workflows-contract.md))

## AI / Server 책임

| AI | Server |
|---|---|
| `missingSlots`·`requestedFields` 산출 | DB·화면에서 값 조회 |
| 재호출 시 slots 병합·재검사 | attempt 증가·중복 Run 방지 (#24) |
| Knowledge 0.3.1의 필수·선택 Slot 구분 유지 | 없는 필수값만 HR 입력으로 전환 |

구현 코드: `app/agents/slot_catalog.py`
