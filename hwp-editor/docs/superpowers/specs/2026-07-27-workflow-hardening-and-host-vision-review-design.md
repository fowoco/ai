# HWPX 작성 흐름 강화 및 범용 Host Vision 검토 설계

- 상태: 1차 구현 완료, 배포 무결성 설계로 일부 대체
- 작성일: 2026-07-27
- 범위: HWP Editor MCP v2 작성·승인·시각 검토·최종화 흐름

> 승인 서명, authoritative workflow 상태, attempt 계산, Host Vision 이미지 전달은
> `2026-07-27-deployment-workflow-integrity-design.md`가 이 문서보다 우선한다.

## 1. 문제

현재 XML/SVG 자동 검증은 실제로 수행되지만 다음 경로가 남아 있다.

1. `apply_edit_plan(approved=true)`를 Agent가 직접 제출할 수 있다.
2. Agent가 attempt 수정본을 `samples/`로 복사해 final gate를 우회할 수 있다.
3. MCP Client가 `sampling/createMessage`를 지원하지 않으면, Host에서 실행 중인
   멀티모달 LLM이 이미지를 볼 수 있어도 최종 Vision 검토를 제출할 방법이 없다.
4. 날짜·checkbox 등 타입 오류가 적용 단계에서 발견되어 attempt를 소모한다.
5. 분석 응답의 `interview_ready`와 실제 workflow 상태가 어긋난다.
6. `prefix_unit` 금액 필드에 단위가 포함된 값이 들어가도 통과한다.
7. “예시 작성”에서 Agent가 임의 개인정보를 만든 뒤 승인 없이 적용할 수 있다.

구조·페이지·SVG geometry 통과만으로 의미상 올바른 배치를 보장할 수 없다. 최종
성공은 모든 편집 필드에 대한 이미지 기반 의미 검토까지 통과해야 한다.

## 2. 목표

- MCP Sampling과 Host의 네이티브 이미지 입력을 모두 지원한다.
- 특정 제품이나 모델명에 의존하지 않는다.
- 원본·수정본·diff·상세 band와 판정을 해시로 결합한다.
- 모든 편집 필드의 위치·경계·중복·가독성 판정을 강제한다.
- 사용자 승인, 자동 검증, Vision PASS 없이는 `VERIFIED_FINAL`을 만들지 않는다.
- 타입 오류는 적용 전에 반환하며 실제 적용 attempt만 횟수에 포함한다.
- 특정 관공서 양식의 행·셀 좌표를 코드나 테스트에 고정하지 않는다.

## 3. 비목표와 신뢰 경계

- 서버는 LLM 내부의 실제 시각 attention을 암호학적으로 증명할 수 없다.
- 서버 밖에서 Agent가 실행하는 임의 `cp`, `rm` 명령 자체를 MCP 코드가 차단할 수
  없다. 공식 최종본은 `finalize_document`가 반환한 `final_path`만 인정한다.
- 외부 Vision API, 모델 SDK, API key, 새 저장소는 추가하지 않는다.
- 모델의 브랜드나 허용 목록을 관리하지 않는다.

서버가 강제하는 것은 **현재 attempt의 이미지 해시를 인용한 필드별 판정**이다.
Host 정책은 이미지 입력을 실제 호출해야 하며, 이미지를 열 수 없는 모델은
`NEEDS_HUMAN`으로 중단해야 한다.

## 4. 검토 방식 비교

### A. MCP Sampling만 유지

- 장점: 서버가 요청과 응답을 한 호출 안에서 관리한다.
- 단점: `sampling/createMessage` 미지원 Client에서는 실행할 수 없다.
- 결론: 호환성 요구를 충족하지 못해 제외한다.

### B. Sampling + 해시 결합 Host Vision 제출

- Sampling 지원 시 기존 경로를 사용한다.
- Sampling 미지원 시 Host의 멀티모달 LLM이 동일 이미지 묶음을 직접 검토하고
  필드별 판정을 MCP Tool로 제출한다.
- 서버는 plan, 수정본, 검증 보고서, 이미지 묶음, 필드 증거를 다시 검증한다.
- 결론: 선택한다. 새 모델 SDK 없이 현재 Host 능력을 사용한다.

### C. 서버 전용 외부 Vision Provider 추가

- 장점: Host 기능 차이를 숨길 수 있다.
- 단점: 의존성·인증·개인정보 전송·Provider 추상화가 추가된다.
- 결론: 현재 범위에는 과하다.

## 5. 상태 흐름

```text
ANALYZED
  → VISUAL_CANDIDATES_REQUIRED
  → READY_FOR_INTERVIEW
  → WAITING_APPROVAL
  → APPROVED
  → PENDING_VISION_REVIEW
      ├─ MCP Sampling PASS
      ├─ Host Vision PASS
      └─ FAIL / NEEDS_HUMAN
  → VERIFIED_FINAL
```

- 시각 후보가 없거나 자동으로 모두 확정된 문서는 `ANALYZED`에서
  `READY_FOR_INTERVIEW`로 바로 간다.
- 후보 확인이 필요하면 `interview_ready=false`와
  `next_action=confirm_visual_candidates`를 반환한다.
- Sampling 미지원은 실패 attempt가 아니다. `PENDING_VISION_REVIEW`를 유지하고
  `next_action=submit_host_vision_review`를 반환한다.
- 유효한 Vision `FAIL` 또는 `NEEDS_HUMAN` 판정은 terminal review로 보존하며 Host
  제출로 덮어쓸 수 없다.

## 6. 사용자 승인

`approved: bool` 입력을 삭제한다.

1. `create_edit_plan`이 서버 workspace에 immutable plan을 저장한다.
2. `approve_edit_plan(path, plan_id, ctx)`가 전체 변경값과 disposition 요약을 MCP
   elicitation으로 사용자에게 표시한다.
3. Client가 elicitation을 지원하지 않거나 사용자가 거절·취소하면 승인 receipt를
   만들지 않는다.
4. 수락 시 서버가 `approval-receipt.json`을 기록한다.
5. `apply_edit_plan(path, plan_id)`은 저장된 plan과 receipt의 plan/document hash가
   모두 일치할 때만 실행한다.

receipt에는 `plan_id`, `document_sha256`, `edit_plan_sha256`, `source=mcp_elicitation`,
`approved_at`만 저장한다. 승인 화면에 표시한 개인정보 값은 receipt에 복제하지
않는다.

MCP elicitation은 Host가 사용자 입력으로 취급한다는 신뢰를 전제로 한다. 현재
프로토콜 안에서 Agent가 제출하는 단순 boolean보다 강한 경계이며, 별도 인증 UI는
이번 범위에 추가하지 않는다.

## 7. 범용 Host Vision 계약

### 7.1 검토 요청 생성

`review_document_vision`은 Sampling 호출 전에 항상
`vision-review-request.json`을 만든다.

```json
{
  "version": 1,
  "review_id": "canonical payload sha256",
  "plan_id": "...",
  "original_sha256": "...",
  "modified_sha256": "...",
  "verification_report_sha256": "...",
  "expected_field_ids": ["..."],
  "views": [
    {
      "view_id": "page-001-full",
      "page": 1,
      "kind": "full",
      "bbox": null,
      "field_ids": ["..."],
      "original": {"path": "...", "sha256": "..."},
      "modified": {"path": "...", "sha256": "..."},
      "diff": {"path": "...", "sha256": "..."}
    },
    {
      "view_id": "page-001-band-002",
      "page": 1,
      "kind": "detail",
      "bbox": [0, 396, 1240, 840],
      "field_ids": ["..."],
      "original": {"path": "...", "sha256": "..."},
      "modified": {"path": "...", "sha256": "..."},
      "diff": {"path": "...", "sha256": "..."}
    }
  ],
  "prompt": "..."
}
```

- 경로는 현재 attempt 내부 파일만 허용한다.
- 각 view는 원본·수정·diff 3장을 묶는다.
- `review_id`는 `review_id` 필드를 제외한 canonical JSON의 SHA-256이다.
- 전체 페이지는 항상 포함한다.
- 편집 필드가 있는 상세 band만 포함하며 최대 band 수는 기존 제한을 유지한다.
- 좌표가 아니라 `visual_regions`와 field-view 교차 관계로 증거를 구성한다.

### 7.2 Sampling capability 분기

`ctx.session.check_client_capability(ClientCapabilities(sampling=...))`로 호출 전에
판단한다.

- 지원: 현재 `create_message` 경로를 실행하고 같은 요청 묶음에 판정을 결합한다.
- 미지원: `create_message`를 호출하지 않고 검토 요청 경로·내용과
  `next_action=submit_host_vision_review`를 반환한다.
- capability가 지원된다고 광고했지만 transport 단계에서 실패한 경우에도 검토
  요청은 보존하고 Host fallback을 허용한다.
- Sampling이 유효한 `FAIL`/`NEEDS_HUMAN`을 반환했거나 응답 형식이 잘못된 경우에는
  fallback으로 PASS를 덮어쓰지 않는다.

따라서 미지원 Client에서 발생하던 확률적 예외 의존을 제거한다.

### 7.3 Host 제출 Tool

새 Tool:

```text
submit_host_vision_review(
  path,
  plan_id,
  review_id,
  reviewer,
  decision
)
```

`reviewer`:

```json
{
  "provider": "informational string",
  "model": "informational string",
  "capabilities": ["image_input"]
}
```

`decision.fields[]`:

```json
{
  "field_id": "...",
  "verdict": "PASS|FAIL|NEEDS_HUMAN",
  "reason": "라벨과 원본 대비 위치 관계를 포함한 필드 고유 근거",
  "evidence_view_ids": ["page-001-full", "page-001-band-002"]
}
```

모델명은 판정 조건이 아니다. Gemini, GPT, Claude, 로컬 VLM 등 어떤 모델도 동일한
계약을 사용한다.

### 7.4 서버 검증

서버는 제출값을 신뢰하지 않고 다음을 재계산한다.

1. workflow가 현재 `PENDING_VISION_REVIEW`이고 plan이 일치한다.
2. 저장된 review request hash와 `review_id`가 일치한다.
3. 원본·수정본·verification report·모든 PNG hash가 request와 일치한다.
4. 자동 검증 보고서가 `PENDING_VISION_REVIEW` 상태다.
5. `capabilities`에 `image_input`이 있다.
6. 모든 편집 `field_id`가 정확히 한 번 존재한다.
7. 각 필드는 해당 필드가 매핑된 full view를 인용한다.
8. 해당 필드의 detail view가 있으면 최소 하나를 함께 인용한다.
9. 존재하지 않거나 다른 필드에만 매핑된 view를 인용할 수 없다.
10. 여러 필드에 동일 reason을 반복할 수 없다.
11. 전체 verdict는 필드 verdict의 최악값과 일치한다.

검증 후 서버가 정규화한 `vision-review.json`만 저장한다. 호출자가 파일 경로나
해시를 임의로 대체할 수 없다.

### 7.5 최종화

`finalize_document`가 허용하는 source:

- `mcp_sampling`
- `host_vision_submission`

두 source 모두 다음 값이 일치해야 한다.

- `plan_id`
- `review_id`
- `original_sha256`
- `modified_sha256`
- `verification_report_sha256`
- `vision-review.json` 자체 hash
- `verdict=PASS`

하나라도 다르면 final 디렉터리를 만들지 않는다.

## 8. 나머지 흐름 보완

### 8.1 타입 preflight

- 날짜, checkbox, character grid, phone, number, amount를 plan 생성 시 검증한다.
- 입력 오류는 state와 attempt 횟수를 변경하지 않는다.
- 실제 `modified.hwpx`가 생성되고 자동 검증에 실패한 경우만 apply attempt로 센다.
- Sampling 미지원, 승인 거절, plan 입력 오류는 attempt를 소모하지 않는다.

### 8.2 금액 정규화

- `prefix_unit` 필드는 숫자와 허용된 자릿수 구분자만 입력받는다.
- `만원`, `원`, 영문 단위가 값에 포함되면 plan 생성 단계에서 거절한다.
- 렌더 후에는 숫자 값과 기존 anchor 단위를 각각 확인한다.
- `4000만원 만원`처럼 단위가 중복되면 semantic 검증이 실패한다.

### 8.3 분석 next action

모든 workflow 응답은 `status`, `next_action`, `interview_ready`를 서로 일관되게
반환한다. `READY_FOR_INTERVIEW`가 아니면 인터뷰나 plan 생성을 시작하지 않는다.

### 8.4 예시 작성

- 사용자 입력값과 예시값을 구분해 plan에 `value_origin=user|example`을 기록한다.
- 예시값은 명백한 합성값만 허용하고 실제 사람처럼 보이는 개인정보를 만들지 않는다.
- 적용 전 승인 화면에 모든 예시값과 `value_origin=example`을 표시한다.
- “예시대로”라는 요청도 승인 단계를 생략하지 않는다.

### 8.5 workspace 경계

- `apply_edit_plan`의 `output_path`, `review_output_dir` 호환 인자를 제거한다.
- 수정본과 모든 검토 산출물은 서버가 정한 attempt 경로에만 쓴다.
- 안내문은 `workflow-state.status=VERIFIED_FINAL`과 서버 반환 `final_path` 외 파일을
  완료본으로 부르지 못하게 한다.
- 테스트는 실패·미지원·거절 경로에서 `final/`이 생성되지 않음을 확인한다.

### 8.6 코드 배치

- `server.py`: MCP Context capability 확인과 Tool 입출력 조율
- `plans.py`: 타입 preflight, plan/approval receipt hash 검증
- `vision.py`: review request 생성, Host/Sampling 판정 스키마와 검증
- `workspace.py`: 상태 전이와 final gate

FastMCP/FastAPI 타입을 domain 검증 코드로 내리지 않는다. 기존 파일 안에서 해결하고
새 Provider 계층이나 모델 adapter는 만들지 않는다.

## 9. 오류 처리

- 기존 도메인 예외와 구체적인 메시지로 입력·승인·capability·Vision 오류를
  구분한다. 새 오류 프레임워크는 만들지 않는다.
- 모든 실패 attempt와 검증 보고서는 보존한다.
- Sampling 미지원은 `NEEDS_HUMAN`이 아니라 `VISION_REVIEW_REQUIRED` 응답이다.
- Host가 이미지를 열지 못했거나 text-only 모델이면
  `submit_host_vision_review`를 호출하지 않고 `NEEDS_HUMAN`으로 보고한다.
- 유효한 Vision 실패 판정 뒤에는 새 plan을 만들어야 하며 기존 review를 덮어쓰지
  않는다.

## 10. 테스트

### 단위 테스트

- Sampling capability 없음: `create_message` 미호출, request 생성, 상태 유지
- 임의 모델명 3종: 동일 Host 제출 계약 통과
- text-only capability, 누락 필드, 중복 필드, 반복 reason 거절
- 잘못된 plan/review/image/report hash 거절
- 다른 필드 view 인용, detail view 누락 거절
- 유효한 Sampling FAIL을 Host PASS로 덮어쓰기 거절
- 단위 포함 금액과 잘못된 날짜를 plan 단계에서 거절하며 attempt 미증가
- example origin이 승인 요약에 포함됨

### 프로토콜 테스트

- Sampling 지원 Client: 기존 Sampling PASS → finalize
- Sampling 미지원 Client: request → Host 이미지 판정 제출 → finalize
- Sampling 미지원 + text-only Host: final 미생성
- approval elicitation 거절/미지원: apply 미실행
- 승인 receipt·수정본·PNG 변조: final 미생성

### 회귀 테스트 원칙

- 실제 관공서 양식의 행·셀 좌표를 assertion하지 않는다.
- 합성 XML/SVG fixture에서 label, field type, geometry, collision, view-field 매핑을
  검증한다.
- 실제 양식은 소수 통합 테스트로 두되 의미 배치와 전체 편집 필드를 확인한다.

## 11. 구현 순서

1. 실패 테스트: 타입 preflight와 amount normalization
2. 실패 테스트: approval receipt와 apply gate
3. 실패 테스트: review request manifest와 capability 분기
4. 실패 테스트: 범용 Host 제출 검증과 final gate
5. 상태·next action·example origin 계약 정리
6. 프로토콜/통합 회귀 테스트
7. 안내문·README 갱신

각 단계는 기능 브랜치에서 테스트·커밋 후 `main`에 merge commit으로 합친다.
