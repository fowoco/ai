# T07 Structured Generation Resources Evidence Pack

```yaml
evidence_version: 1
wave: W3
task: T07
packet_version: 1
base_sha: 305125d213cf856931af63297d2385c7ed74f56e
packet_sha: 5e4f05b1f721278c6604fa934d998e1bffb1aeb3
implementation_sha: 45e25759cdb174fbff4a64a0171881bdd21c2882
branch: task/la-generation-resources
worktree: /Users/parktaejung/Desktop/workspace/ai-language-assistant-t07-generation-resources
clean_worktree_at_implementation: true
```

## Claims

| ID | Claim | Evidence |
|---|---|---|
| T07-C01 | 생성 인터페이스는 Pydantic draft 모델(`EasyKoreanDraft`, `TranslationDraft`, `SemanticValidationDraft`)을 사용하는 `StructuredGenerator` Protocol 뒤에 은닉된다. | `test_easy_korean_draft_valid`, `test_easy_korean_draft_rejects_extra_fields`, `test_translation_draft_valid_and_bounds`, `test_semantic_validation_draft_contract` |
| T07-C02 | 시스템 프롬프트 및 알기 쉬운 한국어 규칙은 SHA-256 무결성 검증을 거치는 패키지 리소스(`importlib.resources`)로 관리된다. | `test_pack_has_semver_and_source_metadata`, `test_context_pack_checksum_changes_with_content`, `test_context_pack_is_included_in_package_data`, `test_production_loader_rejects_draft_unreviewed_or_checksum_invalid_pack` |
| T07-C03 | HTTP generation 어댑터는 단위 테스트에서 `httpx.MockTransport`를 사용하며 외부 실 LLM API 네트워크 호출을 엄격히 차단한다. | `test_adapter_sends_versioned_system_prompt`, `test_adapter_sends_json_schema_response_contract`, `test_adapter_parses_valid_json`, `test_adapter_rejects_trailing_non_json_text`, `test_adapter_rejects_response_over_one_mebibyte`, `test_adapter_maps_429_5xx_and_timeout_to_typed_errors`, `test_adapter_retries_transport_once_only`, `test_adapter_never_logs_api_key_or_raw_response` |

## RED before implementation

구현 전 packet SHA(`5e4f05b1f721278c6604fa934d998e1bffb1aeb3`)에서 다음 focused 명령을 실행했다.

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest tests/agents/language/test_generation_port.py tests/agents/language/test_context_pack.py -q
```

- Exit code: `2`
- 결과: `ModuleNotFoundError: No module named 'app.agents.language.generation'` 및 `No module named 'app.agents.language.context_pack'`
- 의미: T07 generation models, adapter, context pack 모듈이 작성되지 않아 예상대로 RED 발생.

## Implementation verification

모든 명령은 implementation SHA `45e25759cdb174fbff4a64a0171881bdd21c2882`에서 실행했다.

### Focused test

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest tests/agents/language/test_generation_port.py tests/agents/language/test_context_pack.py -q
```

- Exit code: `0`
- 결과: `24 passed`

### Language regression

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest tests/agents/language/ -q
```

- Exit code: `0`
- 결과: `178 passed`

### Repository regression

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest -q
```

- Exit code: `0`
- 결과: `320 passed`

### Ruff

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/ruff check app/agents/language/generation app/agents/language/context_pack.py app/agents/language/resources tests/agents/language/test_generation_port.py tests/agents/language/test_context_pack.py pyproject.toml
```

- Exit code: `0`
- 결과: `All checks passed!`

### Diff and scope

```bash
git diff --check
git diff --name-status 5e4f05b1f721278c6604fa934d998e1bffb1aeb3..45e25759cdb174fbff4a64a0171881bdd21c2882
```

- Exit code: `0`
- 변경 파일은 허용 파일 범위 15개 한정:

```text
M  pyproject.toml
A  app/agents/language/context_pack.py
A  app/agents/language/generation/__init__.py
A  app/agents/language/generation/models.py
A  app/agents/language/generation/openai_compatible.py
A  app/agents/language/resources/__init__.py
A  app/agents/language/resources/easy_korean_rules.v1.json
A  app/agents/language/resources/easy_korean_rules.v1.sha256
A  app/agents/language/resources/prompts/__init__.py
A  app/agents/language/resources/prompts/correction.v1.md
A  app/agents/language/resources/prompts/easy_korean.v1.md
A  app/agents/language/resources/prompts/semantic_validation.v1.md
A  app/agents/language/resources/prompts/translation.v1.md
A  tests/agents/language/test_context_pack.py
A  tests/agents/language/test_generation_port.py
```

## Scope audit

```yaml
implementation_allowed_files_only: true
unexpected_implementation_files: []
vendor_imports_in_generation_domain: []
evidence_artifact: docs/language-assistant/engineering/execution/evidence/T07-EVIDENCE.md
```

## Unrun and unverified

- OpenAI/Anthropic 등 실제 외부 LLM API 런타임 통신은 단위 테스트에서 실행하지 않았다 (`httpx.MockTransport`로 검증).
- T08 검증 엔진 및 후속 Graph 컨트롤러 조립은 시작하지 않았다.

## Rollback

- Safe point: `5e4f05b1f721278c6604fa934d998e1bffb1aeb3`
