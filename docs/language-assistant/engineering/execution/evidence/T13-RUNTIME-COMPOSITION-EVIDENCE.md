# Language Assistant Runtime Composition Evidence

```yaml
evidence_version: 1
task: issue-24-runtime-composition
branch: feat/language-assistant-runtime-composition
worktree: /Users/parktaejung/Desktop/workspace/ai/.worktrees/language-assistant-runtime-composition
base_sha: f7058c2ece93e2b3723a715780e6bac5adb3eae1
implementation_commit: not committed
live_ollama_qdrant: partial
ollama_model: gemma4:26b-mlx
ollama_structured_output: success
qdrant_endpoint: http://localhost:6333
```

## Claims

| ID | Claim | Evidence |
|---|---|---|
| C01 | 설정이 유효하면 getter가 실제 `LanguageAssistantService`를 lazy하게 반환한다. | `test_factory_builds_service_from_valid_generation_settings`, `test_endpoint_uses_real_dependency_with_deterministic_ports` |
| C02 | getter의 무조건적인 503 sentinel을 제거하고, 구성 실패 시 HTTP 503을 유지한다. | `test_dependency_returns_service_from_composition_factory`, `test_dependency_returns_503_when_generation_settings_are_missing`, `test_endpoint_returns_503_from_real_dependency_when_settings_are_missing`, `test_endpoint_returns_503_from_real_dependency_when_settings_are_invalid` |
| C03 | 직접 API가 dependency override 없이 실제 getter를 통과하며, 외부 네트워크 없이 결정적 port로 200 응답을 만든다. | `test_endpoint_uses_real_dependency_with_deterministic_ports` |
| C04 | 잘못된 provider/base URL/model 설정은 composition unavailable로 분류된다. | `test_factory_rejects_invalid_generation_settings` |
| C05 | Ollama/Qdrant live 호출 없이도 offline baseline을 재현할 수 있고, secret 파일 변경이 없다. | test commands below; no `.env` or secret file is in the change set |
| C06 | `provider=ollama`은 native `/api/chat` adapter를 사용하며, 실제 모델의 코드펜스 JSON을 정규화해 typed output으로 검증한다. | `test_ollama_adapter_sends_native_schema_contract`, `test_ollama_adapter_parses_single_json_code_fence`, live Ollama/API result below |

## Contract decision

API의 기존 503 detail 계약을 유지한다.

```text
503 LANGUAGE_ASSISTANT_NOT_CONFIGURED
```

내부 composition exception의 code는 `LANGUAGE_ASSISTANT_COMPOSITION_UNAVAILABLE`로 유지하되, FastAPI 경계에서는 기존 detail로 변환한다.

## RED before implementation

초기 sentinel 상태에서 다음 focused command를 실행했다.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=target \
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python \
-m pytest -p no:cacheprovider -q \
tests/agents/language/test_runtime_config.py \
tests/integration/language/test_runtime_composition.py \
tests/api/test_language_endpoint.py
```

- Exit code: `1`
- Result: composition module와 `llm_base_url`이 없어 5개 실패
- Meaning: 구현 전 실패 경계가 설정·factory·dependency에 존재함을 확인

## Verification

### Composition and API focused suite

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=target \
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python \
-m pytest -p no:cacheprovider -q \
tests/integration/language/test_runtime_composition.py \
tests/api/test_language_endpoint.py
```

- Exit code: `0`
- Result: `24 passed`

### Relevant regression suite

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=target \
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python \
-m pytest -p no:cacheprovider -q \
tests/agents/language/test_runtime_config.py \
tests/integration/language/test_runtime_composition.py \
tests/api/test_language_endpoint.py \
tests/agents/test_workflow_bridges.py \
tests/agents/language/test_graph.py \
tests/api/test_workflows_endpoint.py
```

- Exit code: `0`
- Result: `563 passed, 1 skipped`

### Repository regression excluding unrelated OCR smoke environment tests

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=target \
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python \
-m pytest -p no:cacheprovider -q \
--ignore=tests/ocr/test_smoke_script.py
```

- Exit code: `0`
- Result: all collected tests passed

### Static checks

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/ruff check \
app/core/config.py \
app/agents/language/composition.py \
app/agents/language/generation/__init__.py \
app/agents/language/generation/ollama.py \
app/api/dependencies.py \
tests/agents/language/test_runtime_config.py \
tests/agents/language/test_ollama_generation_port.py \
tests/integration/language/test_runtime_composition.py \
tests/api/test_language_endpoint.py
git diff --check
```

- Exit code: `0`
- Result: Ruff passed and no diff whitespace errors

## Live verification

### Ollama availability

```bash
ollama list
curl http://localhost:11434/api/tags
curl http://localhost:11434/v1/models
```

- `ollama list`: `gemma4:26b-mlx` present
- `/api/tags`: HTTP `200`
- `/v1/models`: HTTP `200`, `gemma4:26b-mlx` present

### Direct structured generation before fix

실제 `OpenAICompatibleGenerationPort`를 `http://localhost:11434/v1`와 `gemma4:26b-mlx`로 구성해 `EasyKoreanDraft`를 요청했다.

- HTTP transport/model reachability: 성공
- Typed response validation: 실패
- 모델 응답 key: `easy_korean_text`
- 현재 `EasyKoreanDraft` 요구 key: `request_reason`, `requested_items`, `submission_method`
- 결과: `GenerationSchemaError`

필드명을 system prompt에 직접 명시하고 동일한 `response_format.json_schema`를 보낸 재시험도 수행했다.

- HTTP status: `200`
- JSON parse: 실패(`JSONDecodeError`)
- 결론: OpenAI-compatible `response_format` 경로에서 schema 준수성이 확인되지 않음

### Ollama native structured generation after fix

`provider=ollama` composition이 native `/api/chat` adapter를 선택하도록 수정했다. adapter는 `format=<JSON schema>`를 전달하고, schema의 required fields를 system prompt에 추가하며, 응답 전체를 감싼 단일 JSON 코드펜스를 제거한 뒤 Pydantic validation을 수행한다.

- HTTP status: `200`
- 응답 key: `request_reason`, `requested_items`, `submission_method` — 기대 구조와 일치
- 실제 typed result: `EasyKoreanDraft` validation 성공
- 코드펜스 응답: adapter의 제한적 정규화 후 validation 성공
- 잘못된 `easy_korean_text` schema: `GenerationSchemaError` 유지

### Actual Language Assistant API

수정 후 실제 설정(`provider=ollama`, base URL, model)을 주입하고 dependency cache를 초기화한 뒤 `POST /internal/v1/language-assistant`를 다시 호출했다.

- HTTP status: `200`
- `generation_status`: `warning` (`failed` 해소)
- component status: standard Korean `success`, easy Korean `warning`, translation `success`
- `requires_human_review`: `true`
- warning codes: `EASY_KOREAN_CONTEXT_PACK_UNAVAILABLE`, `STANDARD_KOREAN_FALLBACK`, `RETRIEVAL_UNAVAILABLE`, `TRANSLATION_FALLBACK_USED`
- `TRANSLATION_GENERATION_FAILED`는 더 이상 발생하지 않음
- 의미: 실제 dependency/API/Ollama structured generation 경로는 성공했고, 남은 warning은 context pack과 retrieval degraded 경로에서 발생함

### Qdrant availability

```bash
curl http://localhost:6333/readyz
curl http://localhost:6333/collections
```

- 최초 host `localhost:6333` 확인: connection failed (`HTTP_STATUS=000`)
- 원인: 당시 OrbStack/Docker daemon이 실행되지 않았고 Compose는 host port를 공개하지 않음
- OrbStack 시작 후 `qdrant/qdrant:v1.18.3` 컨테이너 기동: Qdrant HTTP server listening 확인
- 컨테이너 IP `http://192.168.97.2:6333/readyz`: HTTP `200`, `all shards are ready`
- 컨테이너 IP `/collections`: HTTP `200`, collections `[]`
- Compose health: `unhealthy`; 이미지에 `wget`이 없어 현재 healthcheck가 실행되지 않음
- `eps_language_phrases` collection/index contract: 아직 없음/확인하지 못함

## Not yet verified

- Qdrant live request or EPS index contract verification
- Compose Qdrant healthcheck correction and `healthy` transition
- BGE-M3/reranker model loading or download

현재 production composition은 Qdrant/BGE concrete backend가 없는 환경에서 retrieval을 typed degraded fallback으로 조립한다. 이 Evidence는 service/dependency/API composition과 실제 Ollama structured generation 성공 및 Qdrant server 도달성을 검증하며, live RAG 성공은 주장하지 않는다.

## Known unrelated environment failures

전체 suite를 `tests/ocr/test_smoke_script.py`까지 포함해 실행하면 기존 OCR smoke 테스트 2건이 macOS 환경 제약으로 실패한다.

- PowerShell executable(`powershell`/`pwsh`) 미설치
- sandbox에서 loopback HTTP server bind가 `PermissionError`로 차단
- Qdrant Compose healthcheck가 존재하지 않는 `wget` 바이너리를 호출함

## Secret and scope audit

- `.env`, API token, secret 값은 생성·수정·커밋하지 않았다.
- 변경 범위는 runtime composition, dependency, 설정, 관련 테스트, 이 Evidence 문서다.
- 기존 untracked implementation plan은 보존했으며 수정하지 않았다.
