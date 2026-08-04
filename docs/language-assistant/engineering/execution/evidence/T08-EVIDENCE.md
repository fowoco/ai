# T08 Validation and Bounded Correction Evidence Pack

```yaml
evidence_version: 1
wave: W3
task: T08
packet_version: 1
base_sha: e732df0c7c34d3efb0790ce0e556488d575c3efc
packet_sha: 09153e086aae9da445c3d8988937680ceb87f1ae
implementation_sha: 350f2a6b08016093fea27336ce784576c635d867
branch: task/la-generation-adapter
worktree: /Users/parktaejung/Desktop/workspace/ai-language-assistant-t08-generation-adapter
clean_worktree_at_implementation: true
```

## Claims

| ID | Claim | Evidence |
|---|---|---|
| T08-C01 | 결정적 검증기(Deterministic Validator)는 날짜, 금액/수량, 기계 토큰, 항목 수(cardinality)를 `request_context` 기반으로 정규화하여 검증한다. | `test_date_surface_forms_normalize_to_same_date`, `test_changed_date_fails`, `test_missing_or_added_number_fails`, `test_amount_currency_and_unit_are_preserved`, `test_url_email_and_phone_are_preserved`, `test_requested_item_cardinality_is_preserved`, `test_extra_requested_item_fails`, `test_same_number_in_two_paths_is_not_collapsed` |
| T08-C02 | 의미적 검증기(Semantic Validator)는 동등성, 양태(modality), 개체 보존을 검증하며, 검증기 비가용 시 false pass 대신 typed `inconclusive`를 반환한다. | `test_semantic_validator_receives_request_context_and_candidate_only`, `test_semantic_validator_excludes_parent_context`, `test_semantic_validator_checks_reason_items_action_and_modality`, `test_semantic_validator_checks_names_places_documents_and_legal_terms_in_fields`, `test_semantic_validator_can_return_inconclusive`, `test_unavailable_validator_never_marks_success` |
| T08-C03 | 재시도 제한 제어기(`BoundedCorrectionController`)는 최대 2회 수정 재시도를 준수하고 `LanguageExecutionPolicy` 시계열 예산(monotonic clock) 초과 시 추가 호출을 스케줄링하지 않고 기존 후보를 보존한다. | `test_initial_plus_two_corrections_only`, `test_successful_first_attempt_has_zero_retries`, `test_retry_exhaustion_returns_last_candidate`, `test_retry_exhaustion_sets_human_review`, `test_hard_generation_failure_has_no_candidate`, `test_branch_budget_uses_monotonic_clock`, `test_expired_budget_schedules_no_new_provider_call`, `test_policy_retry_override_zero_disables_corrections` |

## RED before implementation

구현 전 packet SHA(`09153e086aae9da445c3d8988937680ceb87f1ae`)에서 다음 focused 명령을 실행했다.

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest tests/agents/language/test_validation.py -q
```

- Exit code: `2`
- 결과: `ImportError: cannot import name 'LanguageExecutionPolicy' from 'app.agents.language.contracts'`
- 의미: T08 validation 및 execution policy 모듈이 작성되지 않아 예상대로 RED 발생.

## Implementation verification

모든 명령은 implementation SHA `350f2a6b08016093fea27336ce784576c635d867`에서 실행했다.

### Focused test

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest tests/agents/language/test_validation.py -q
```

- Exit code: `0`
- 결과: `28 passed`

### Language regression

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest tests/agents/language/ -q
```

- Exit code: `0`
- 결과: `206 passed`

### Repository regression

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest -q
```

- Exit code: `0`
- 결과: `348 passed`

### Ruff

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/ruff check app/agents/language/validation.py app/agents/language/contracts.py app/agents/language/generation/models.py tests/agents/language/test_validation.py
```

- Exit code: `0`
- 결과: `All checks passed!`

### Diff and scope

```bash
git diff --check
git diff --name-status 09153e086aae9da445c3d8988937680ceb87f1ae..350f2a6b08016093fea27336ce784576c635d867
```

- Exit code: `0`
- 변경 파일은 허용 파일 범위 4개 한정:

```text
M  app/agents/language/contracts.py
A  app/agents/language/validation.py
A  tests/agents/language/test_validation.py
```

## Scope audit

```yaml
implementation_allowed_files_only: true
unexpected_implementation_files: []
vendor_imports_in_validation_domain: []
evidence_artifact: docs/language-assistant/engineering/execution/evidence/T08-EVIDENCE.md
```

## Unrun and unverified

- 단위 테스트 중 외부 실 LLM API 및 Qdrant 데이터베이스 통신은 수행하지 않았다 (fake/mock validator 사용).
- T09 Easy Korean Subgraph 및 T10 Translation Subgraph 조립은 시작하지 않았다.

## Rollback

- Safe point: `09153e086aae9da445c3d8988937680ceb87f1ae`
