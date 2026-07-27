# HWPX 배포 무결성 설계

- 상태: 독립 단일 서버 구현 및 회귀 검증 완료
- 작성일: 2026-07-27
- 범위: 승인, workflow/attempt 상태, 산출물 무결성, Host Vision 전달, 영숫자 값 보존
- 선행 설계: `2026-07-27-workflow-hardening-and-host-vision-review-design.md`

## 1. 배경과 확인된 실패

기존 구현은 plan과 approval receipt의 해시를 비교하지만 receipt 자체를 서버
비밀키로 서명하지 않는다. 같은 로컬 파일 시스템에 접근할 수 있는 Agent가
`approval-receipt.json`과 `workflow-state.json`을 직접 만들면 `APPROVED` 상태를
위조할 수 있다.

attempt 제한도 `workflow-state.json.attempts` 배열을 authoritative source로
사용한다. 배열을 비우면 이미 생성된 실패 attempt가 남아 있어도 2회 제한을
우회할 수 있다.

MCP Sampling 미지원 Host의 Vision fallback은 PNG 경로와 해시만 반환한다. Host가
실제 PNG를 이미지 입력으로 받지 않았어도 `image_input` capability와 필드별
문자열 판정을 제출할 수 있다.

필드 타입 추론은 라벨의 `번호`를 모두 숫자형으로 분류한다. 그 결과
`여권번호 Passport No.`도 숫자형이 되어 `M12345678` 같은 정상 영숫자 값을
거절하고, Agent가 `M`을 제거해 재시도하는 의미 손실이 발생했다.

## 2. 결정

### 2.1 배포 무결성

- 세션마다 바뀌는 HMAC 키를 사용하지 않는다.
- 승인과 Vision 증거 서명은 지속 키를 제공하는 `SigningKeyProvider`를 사용한다.
- workflow 상태와 attempt 횟수는 `WorkflowRepository`가 authoritative source다.
- HWPX, SVG, PNG, JSON 산출물은 `ArtifactStore`에 저장하고 DB의 URI와 SHA-256을
  기준으로 검증한다.
- `workflow-state.json`은 사람과 디버깅을 위한 projection일 뿐 승인·상태 판단에
  사용하지 않는다.

### 2.2 독립 단일 서버 구현

정식 지원 구성:

- `EnvSigningKeyProvider`
  - `HWP_MCP_ACTIVE_SIGNING_KEY_ID`
  - `HWP_MCP_SIGNING_KEYS`: `key_id -> base64 key` JSON
- `SqliteWorkflowRepository`
  - 표준 라이브러리 `sqlite3`
  - 기본 경로는 `HWP_MCP_ROOT/.hwp-mcp/state.sqlite3`
- `LocalArtifactStore`
  - 현재 workspace/attempt 디렉터리를 유지
  - 저장 후 DB에 URI와 SHA-256 기록

이 구성은 FOWOCO나 다른 서비스 DB와 결합하지 않는 독립 서버다. 하나의 MCP 서버
인스턴스가 전용 SQLite, 환경변수 key ring, 로컬 artifact workspace를 소유한다.
프로젝트가 종료되어도 같은 DB·key ring·workspace를 백업하고 복원해 유지할 수
있다.

공유 DB, Secret Manager/KMS, Object Storage는 다중 인스턴스가 실제로 필요해질
때만 같은 protocol의 선택적 adapter로 검토한다. 현재 지원 범위나 배포 완료
조건이 아니다.

## 3. 인터페이스

### 3.1 SigningKeyProvider

```python
class Signature(BaseModel):
    key_id: str
    algorithm: str
    value: str


class SigningKeyProvider(Protocol):
    def sign(self, payload: bytes) -> Signature: ...
    def verify(self, payload: bytes, signature: Signature) -> bool: ...
```

`EnvSigningKeyProvider`는 HMAC-SHA-256을 사용한다. 각 키는 최소 32바이트의
base64 값으로 주입하며 소스, DB, workspace, receipt에 원문을 기록하지 않는다.
active key로 새 서명을 만들고 key ring의 이전 키로 기존 서명을 검증한다. 키가
없거나 잘못된 경우 읽기 전용 분석은 허용하지만 승인, 적용, Vision PASS 수락,
최종화는 fail closed 한다.

KMS adapter는 같은 인터페이스에서 비대칭 서명 또는 관리형 MAC을 사용할 수 있다.
receipt에는 `key_id`와 `algorithm`을 기록한다. 회전 후에도 이전 `key_id`의
검증 키를 보존하는 동안 기존 receipt를 검증할 수 있다.

### 3.2 WorkflowRepository

```python
class WorkflowRepository(Protocol):
    def get_document(self, document_id: str) -> DocumentRecord: ...
    def create_plan(self, plan: PlanRecord) -> None: ...
    def approve_plan(self, approval: ApprovalRecord) -> None: ...
    def reserve_attempt(self, document_id: str, plan_id: str) -> AttemptRecord: ...
    def complete_attempt(self, attempt: AttemptRecord) -> None: ...
    def record_vision_delivery(self, delivery: VisionDeliveryRecord) -> None: ...
    def record_vision_review(self, review: VisionReviewRecord) -> None: ...
    def finalize(self, document_id: str, plan_id: str) -> DocumentRecord: ...
```

쓰기 메서드는 `BEGIN IMMEDIATE` 트랜잭션을 사용한다. `version`은 상태 변경
감사 카운터이며 다중 인스턴스 optimistic lock으로 사용하지 않는다. 상태 전이는
repository가 검증하며 호출자가 임의 status 문자열로 덮어쓸 수 없다.

최소 레코드:

- `documents`: document ID, original hash, status, current plan, version
- `plans`: plan ID, document ID, edit-plan hash, status, 생성 시각
- `approvals`: plan ID, approver subject, 서명, 승인·폐기 시각
- `attempts`: 순번, plan ID, 상태, modified/report hash
- `vision_deliveries`: delivery ID, review ID, 이미지 manifest hash, 서명
- `vision_reviews`: review ID, plan ID, verdict, review hash
- `artifacts`: owner ID, kind, URI, SHA-256, 크기

### 3.3 ArtifactStore

```python
class ArtifactStore(Protocol):
    def put(self, owner_id: str, kind: str, source: Path) -> ArtifactRecord: ...
    def open_verified(self, artifact: ArtifactRecord) -> BinaryIO: ...
```

`open_verified`는 실제 bytes의 SHA-256과 DB 레코드를 대조한다. 파일이 없거나
해시가 다르면 workflow를 진행하지 않고 `ARTIFACT_TAMPERED`로 중단한다.

## 4. 승인 흐름

1. `create_edit_plan`이 plan을 파일에 저장하고 SHA-256을 계산한다.
2. repository transaction이 새 plan을 `current_plan_id`로 설정한다.
3. 같은 문서의 기존 미폐기 승인은 모두 폐기한다.
4. `approve_edit_plan`이 MCP elicitation으로 현재 plan 전체를 보여준다.
5. 승인한 주체, document ID/hash, plan ID/hash, 승인 시각을 canonical JSON으로
   만들고 `SigningKeyProvider`로 서명한다.
6. approval record와 receipt artifact를 같은 논리 transaction에 기록한다.
7. `apply_edit_plan`은 DB의 current plan, active approval, signature, artifact
   hash가 모두 일치할 때만 attempt를 예약한다.

승인 payload:

```json
{
  "version": 2,
  "document_id": "...",
  "document_sha256": "...",
  "plan_id": "...",
  "edit_plan_sha256": "...",
  "approver_subject": "...",
  "source": "mcp_elicitation",
  "approved_at": "...",
  "key_id": "...",
  "algorithm": "HMAC-SHA-256"
}
```

로컬 stdio MCP에는 인증된 사용자 ID가 없다. 이 경우
`approver_subject=local-interactive-user`는 MCP elicitation을 누른 로컬 사용자라는
감사 표식이며 암호학적 신원 증명이 아니다. 배포 환경에서는 인증 transport가
제공한 principal만 허용해야 한다. Agent가 tool 인자로 전달한 사용자 ID는
신뢰하지 않는다.

새 plan의 ID나 hash가 달라지면 기존 승인은 자동 폐기되며 반드시 재승인한다.

## 5. attempt와 상태

`workflow-state.json.attempts`는 더 이상 제한 판단에 사용하지 않는다.

`reserve_attempt`는 하나의 DB transaction에서 다음을 확인한다.

1. document의 current plan이 요청 plan과 같다.
2. plan 상태가 `APPROVED`다.
3. active approval의 서명과 plan artifact hash가 유효하다.
4. 소비된 attempt가 2개 미만이다.
5. 다음 순번을 유일하게 예약한다.

실제 `modified.hwpx`가 생성된 뒤 자동 검증을 수행한 attempt만 소비한다.
입력 preflight, 승인 거절, Sampling capability 미지원은 attempt를 소비하지 않는다.
수정본 생성 후 SVG geometry 또는 의미 검증이 실패하면 실패 attempt로 보존한다.
동시 실행에서는 `RESERVED` 상태도 두 개의 slot 제한에 포함한다. 수정본 생성 전에
실패하면 transaction으로 `ABORTED_NO_OUTPUT` 처리해 slot을 반환한다. 서버가
중단된 채 남은 `RESERVED` attempt는 재시작 시 ArtifactStore를 대조해, 수정본이
없으면 `ABORTED_NO_OUTPUT`, 있으면 소비된 복구 대상 attempt로 전환한다.

DB의 attempt 레코드와 파일/Object Storage 산출물이 불일치하면 횟수를 줄이지 않고
tamper 오류로 중단한다. JSON projection을 삭제하거나 수정해도 DB 상태에는 영향이
없다.

## 6. Host Vision 이미지 전달

Sampling 지원 Host는 기존과 같이 `create_message`에 원본·수정·diff
`ImageContent`를 넣는다.

Sampling 미지원 Host에서는 `review_document_vision` Tool 결과를
`CallToolResult`로 반환한다.

- `structuredContent`: review ID, field/view 관계, 이미지 hash, 제출 계약
- `content`: 설명 `TextContent`와 실제 PNG `ImageContent`

같은 응답에 일회성 `delivery_id`를 포함한다. repository에는 review ID, plan ID,
모든 이미지 hash의 canonical manifest, 전달 방식, 만료 시각을 기록하고
`SigningKeyProvider` 서명을 결합한다.

`submit_host_vision_review`는 다음을 모두 요구한다.

- 현재 plan/review와 일치하는 active delivery
- 유효한 delivery 서명과 만료 시각
- 현재 ArtifactStore bytes와 이미지 manifest hash 일치
- 기존의 full/detail evidence 및 field별 고유 reason 검증

이 방식은 모델 내부 attention을 증명하지 않는다. 다만 Host에 이미지 bytes가
포함된 Tool 결과를 발행하지 않은 상태에서 문자열만으로 PASS를 제출하는 경로는
차단한다.

이미지 payload가 제한을 초과하거나 Host가 이미지 Tool 결과를 처리하지 못하면
`NEEDS_HUMAN`으로 중단한다. 경로만 반환하는 fallback은 제거한다.

## 7. 값 손실 방지

`_guess_field_type`은 일반 `번호` 규칙보다 `여권`, `passport`를 먼저 판정한다.
여권번호는 값이 영숫자일 수 있으므로 원문을 그대로 보존하는 text field로
생성한다.

- `M12345678`을 plan과 HWPX에 그대로 기록한다.
- `number` preflight를 통과시키기 위해 문자를 삭제하거나 자동 변환하지 않는다.
- 타입과 값이 충돌하면 값 수정이 아니라 field registry 추론 오류로 보고한다.
- 사업자등록번호, 외국인등록번호 character grid, 금액, 날짜의 기존 typed 검증은
  유지한다.

별도 `alphanumeric` 타입은 현재 추가하지 않는다. 허용 문자 정책이 국가별
여권 규칙을 과도하게 제한할 수 있으므로, 이번 범위에서는 손실 없는 text가 더
안전하다.

## 8. 오류와 복구

- signing key 없음/알 수 없는 `key_id`: 승인·적용·PASS·최종화 중단
- DB unavailable: mutation 중단, 읽기 전용 분석만 허용
- DB/artifact hash 불일치: `ARTIFACT_TAMPERED`
- stale/new plan approval: `WAITING_APPROVAL`
- attempt 2회 소비: `NEEDS_HUMAN`
- Vision 이미지 전달 불가: `NEEDS_HUMAN`
- 서버 재시작: 환경변수 키와 SQLite DB가 유지되므로 기존 유효 승인을 검증 가능
- 키 회전: 이전 verification key가 남아 있는 동안 기존 receipt 검증 가능

DB를 복구하지 못했거나 필요한 검증 키가 없으면 JSON/파일만으로 상태를
재구성해 자동 승인하지 않는다.

## 9. 코드 배치

- `integrity.py`: signature 모델, canonical payload, provider protocol과 env 구현
- `state.py`: repository protocol, SQLite 구현, 상태 전이와 transaction
- `artifacts.py`: artifact 모델/protocol, local 구현과 hash 대조
- `plans.py`: approval payload와 typed plan 검증
- `server.py`: MCP Context, repository/provider/store 조율
- `vision.py`: delivery manifest와 Host/Sampling 판정 검증
- `workspace.py`: 로컬 디렉터리와 JSON projection

FastMCP 타입은 `server.py` 밖으로 내리지 않는다. DB, KMS, Object Storage
provider는 domain 모델에 FastMCP를 의존시키지 않는다.

## 10. TDD와 인수 조건

### 승인

- 서명 없는/위조된 receipt 거절
- plan 파일 변경 후 기존 receipt 거절
- 다른 plan/document 승인 재사용 거절
- 새 plan 생성 시 기존 approval 폐기
- 서버 프로세스 재시작을 모사해도 같은 key/DB에서 승인 유지
- 다른 key로 시작하면 기존 receipt 거절
- 이전 `key_id` 검증 키가 있으면 회전 전 receipt 허용

### 상태와 attempt

- `workflow-state.json`의 status와 attempts를 조작해도 DB 판정 유지
- 두 서버 connection이 동시에 attempt를 예약해도 순번 중복 없음
- 실제 수정본 생성 전 실패는 attempt 미소비
- 수정본 생성 후 SVG 실패는 attempt 소비
- DB와 artifact hash가 다르면 fail closed

### Vision

- Sampling 미지원 응답에 실제 `ImageContent` 포함
- ImageContent 없이 delivery 생성 불가
- delivery 없이 Host PASS 제출 거절
- 변조·만료·다른 review delivery 거절
- payload 제한 초과 시 `NEEDS_HUMAN`

### 값 보존

- `여권번호 Passport No.`는 text로 추론
- `M12345678`이 plan과 HWPX에 동일하게 남음
- 사업자등록번호 숫자 검증 회귀 없음

### 전체 인수 조건

- 전체 `pytest` 통과
- 원본 HWPX hash 불변
- 현재 통합신청서에서 receipt/state 수동 조작 재현이 모두 차단
- 로컬 서버 재시작 후 유효 승인 복구
- DB/키/이미지 문제가 있을 때 `VERIFIED_FINAL` 생성 안 됨

## 11. 독립 배포 게이트

정식 지원 범위는 단일 MCP 서버 인스턴스다.

- 전용 SQLite는 `HWP_MCP_ROOT` 내부에 둔다.
- HMAC active key와 key ring은 환경변수로 주입한다.
- 이전 승인 검증에 필요한 과거 `key_id`는 회전 후에도 key ring에 남긴다.
- SQLite, key ring, workspace artifact를 하나의 복구 단위로 백업한다.
- 같은 SQLite를 여러 MCP 서버 프로세스가 동시에 소유하는 구성은 지원하지 않는다.
- 인증되지 않은 원격 공개 endpoint는 지원하지 않는다.

다중 인스턴스가 필요해지면 별도 설계로 공유 DB·KMS·Object Storage adapter와
인증 transport를 추가한다.
