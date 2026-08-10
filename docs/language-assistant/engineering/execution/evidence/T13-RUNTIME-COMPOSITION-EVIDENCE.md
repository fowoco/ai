# Language Assistant Runtime Composition Evidence

```yaml
evidence_version: 1
task: issue-24-runtime-composition
branch: feat/language-assistant-runtime-composition
worktree: /Users/parktaejung/Desktop/workspace/ai/.worktrees/language-assistant-runtime-composition
base_sha: f7058c2ece93e2b3723a715780e6bac5adb3eae1
implementation_commit: 91e08af (runtime/Ollama); this commit (Qdrant/BGE/Docker)
live_ollama_qdrant: success-with-easy-korean-fallback
ollama_model: gemma4:26b-mlx
ollama_structured_output: success
qdrant_endpoint: http://localhost:16333 (isolated compose.test.yml)
qdrant_retrieval: success
```

## Claims

| ID | Claim | Evidence |
|---|---|---|
| C01 | 설정이 유효하면 getter가 실제 `LanguageAssistantService`를 lazy하게 반환한다. | `test_factory_builds_service_from_valid_generation_settings`, `test_endpoint_uses_real_dependency_with_deterministic_ports` |
| C02 | getter의 무조건적인 503 sentinel을 제거하고, 구성 실패 시 HTTP 503을 유지한다. | `test_dependency_returns_service_from_composition_factory`, `test_dependency_returns_503_when_generation_settings_are_missing`, `test_endpoint_returns_503_from_real_dependency_when_settings_are_missing`, `test_endpoint_returns_503_from_real_dependency_when_settings_are_invalid` |
| C03 | 직접 API가 dependency override 없이 실제 getter를 통과하며, 외부 네트워크 없이 결정적 port로 200 응답을 만든다. | `test_endpoint_uses_real_dependency_with_deterministic_ports` |
| C04 | 잘못된 provider/base URL/model 설정은 composition unavailable로 분류된다. | `test_factory_rejects_invalid_generation_settings` |
| C05 | Ollama/Qdrant live 호출 없이도 offline baseline을 재현할 수 있고, secret 파일 변경이 없다. | test commands below; no `.env` or secret file is in the change set |
| C06 | `provider=ollama`은 native `/api/chat` adapter를 사용하고 thinking을 끄며, 실제 모델의 코드펜스 JSON을 정규화해 typed output으로 검증한다. | `test_ollama_adapter_sends_native_schema_contract`, `test_ollama_adapter_disables_thinking_for_structured_generation`, `test_ollama_adapter_parses_single_json_code_fence`, live Ollama/API result below |
| C07 | 유효한 Qdrant 설정은 production `HybridEpsRetriever`를 조립하고, 고정 index contract를 통과한 collection만 검색한다. | `test_factory_selects_hybrid_retriever_when_qdrant_is_configured`, `test_real_store_mock_create_and_verify`, live retrieval result below |
| C08 | 실제 BGE-M3/Qdrant 검색은 5개 reference를 반환하며 retrieval fallback/warning이 없다. | isolated Qdrant/BGE live result below |
| C09 | production Docker image는 `language-retrieval` extra를 설치하고 앱과 retrieval 의존성을 import할 수 있다. | `docker compose build ai` exit `0`; image import smoke result below |

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
- Result: all collected tests passed

### Repository regression excluding unrelated OCR smoke environment tests

```bash
PYTHONPATH=. /opt/homebrew/bin/uv run --frozen \
  --extra dev --extra language-retrieval \
  pytest --ignore=tests/ocr/test_smoke_script.py
```

- Exit code: `0`
- Result: `573 passed, 1 skipped`

### Static checks

```bash
/opt/homebrew/bin/uv run --frozen --extra dev --extra language-retrieval \
ruff check \
app/agents/language/composition.py \
app/agents/language/generation/ollama.py \
app/agents/language/retrieval/encoder.py \
app/agents/language/retrieval/indexer.py \
app/agents/language/retrieval/manifest.py \
app/agents/language/retrieval/qdrant_store.py \
scripts/download_language_models.py \
scripts/index_eps_language.py \
tests/agents/language/test_indexer.py \
tests/agents/language/test_ollama_generation_port.py \
tests/agents/language/test_retrieval_service.py \
tests/integration/language/test_compose_config.py \
tests/integration/language/test_qdrant_retrieval.py \
tests/integration/language/test_runtime_composition.py
/opt/homebrew/bin/uv lock --check
docker compose config --quiet
docker compose -f compose.test.yml config --quiet
git diff --check
```

- Exit code: `0`
- Result: Ruff, lockfile, production/test Compose, diff whitespace checks passed

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

### Actual Language Assistant API with Ollama only

수정 후 실제 설정(`provider=ollama`, base URL, model)을 주입하고 dependency cache를 초기화한 뒤 `POST /internal/v1/language-assistant`를 다시 호출했다.

- HTTP status: `200`
- `generation_status`: `warning` (`failed` 해소)
- component status: standard Korean `success`, easy Korean `warning`, translation `success`
- `requires_human_review`: `true`
- warning codes: `EASY_KOREAN_CONTEXT_PACK_UNAVAILABLE`, `STANDARD_KOREAN_FALLBACK`, `RETRIEVAL_UNAVAILABLE`, `TRANSLATION_FALLBACK_USED`
- `TRANSLATION_GENERATION_FAILED`는 더 이상 발생하지 않음
- 의미: 실제 dependency/API/Ollama structured generation 경로는 성공했고, 남은 warning은 context pack과 retrieval degraded 경로에서 발생함

### Qdrant readiness after fix

기존 `wget` healthcheck는 Qdrant 이미지에 실행 파일이 없어 false `unhealthy`를 만들었다. 이미지에 실제 존재하는 `/bin/bash`와 `/dev/tcp`로 `/readyz`를 검사하도록 production/test Compose를 수정했다.

- production `fowoco-qdrant`: `healthy`
- isolated `fowoco-qdrant-test`: `healthy`
- `http://localhost:16333/readyz`: HTTP `200`, `all shards are ready`
- production Compose의 host port 비공개 계약 유지

### Actual BGE-M3 indexing and Qdrant retrieval

- model: `BAAI/bge-m3@5617a9f61b028005a4858fdac845db406aefb181`
- source: `data/eps_language_db.json`
- source rows: `17,925`
- usable/indexed points: `17,902`
- collection: `eps_language_phrases_29106c33d43c_5617a9f61b02`
- alias: `eps_language_phrases_active`
- dense vector: `korean_dense`, 1024 dimensions, cosine
- sparse vector: `korean_sparse`
- dataset/model/index provenance verification: 성공
- full indexing CLI idempotent rerun: exit `0`, `17,902` points
- actual `HybridEpsRetriever`: contexts `5`, fallback `false`, warnings `[]`

live 인덱싱 중 qdrant-client 1.19 compatibility 오류 두 건을 재현하고 수정했다.

- `PayloadSchema.KEYWORD` → `PayloadSchemaType.KEYWORD`
- `update_collection_aliases(change_aliases=...)` → `change_aliases_operations=...`

### Actual Language Assistant API with Ollama and Qdrant

- 최초 실패 재현: 동일 translation 요청이 기본 timeout `60`초에서 두 번 `ReadTimeout`되어 `120.64`초 후 typed failure로 변환됨
- 원인: Qdrant payload/schema 오류가 아니라 로컬 `gemma4:26b-mlx` 응답 시간이 기본 timeout을 초과함
- 동일 schema/payload를 `think=false`로 직접 호출: HTTP `200`, typed `TranslationDraft` 성공, `81.92`초와 `105.10`초
- adapter 수정: native Ollama 요청에 `think: false` 명시
- 실제 API 검증 설정: 테스트 프로세스에만 `FOWOCO_LLM_TIMEOUT_SECONDS=180` 주입; `.env`와 전역 Provider 설정은 변경하지 않음
- HTTP status: `200`
- elapsed: `94.56`초
- retrieval dataset version: `sha256:29106c33d43ccdd8453623ac1a0af44e0201d7c7cc1cc68c3fb438e0ccc61c6d`
- retrieval reference count: `5`
- retrieval fallback: `false`
- `RETRIEVAL_UNAVAILABLE`: 발생하지 않음
- translation status: `success`
- translated text: 존재
- overall `generation_status`: `warning`
- warning codes: `EASY_KOREAN_CONTEXT_PACK_UNAVAILABLE`, `STANDARD_KOREAN_FALLBACK`
- `TRANSLATION_GENERATION_FAILED`: 발생하지 않음
- 의미: 실제 dependency → BGE-M3 → Qdrant → Ollama structured translation 경로가 끝까지 성공했다. 전체 warning은 승인된 Easy Korean Context Pack 부재에 따른 기존 fallback 계약이다.

### Production Docker image build

- command: `docker compose build ai`
- exit: `0`
- image: `fowoco-ai:latest`
- image id: `sha256:81de153f32fdcb7222af1281352ef4759c7c91a82c1f78c55c7f481e6a86b291`
- architecture: `arm64`
- image size: `3,506,302,676` bytes
- installed retrieval packages: `qdrant-client==1.19.0`, `FlagEmbedding==1.4.0`, `torch==2.13.0`
- production execution path smoke: `docker run --rm fowoco-ai:latest uv run python -c ...` → `FastAPI`
- 주의: Linux Torch가 CUDA 계열 wheel을 포함해 이미지가 3.51 GB다. 빌드는 성공했지만 이미지 경량화는 별도 최적화 대상이다.

## Not yet verified

- production Qdrant volume indexing; live data는 격리된 test volume에 생성함
- BGE reranker 연결; 현재 production composition은 cross-query RRF fallback을 사용함
- actual OpenAI API structured-output compatibility

현재 production composition은 Qdrant URL이 없으면 typed degraded fallback을 사용하고, 유효한 URL에서는 lazy BGE-M3 backend와 `HybridEpsRetriever`를 조립한다. 실제 BGE-M3/Qdrant indexing·retrieval과 Ollama 결합 API 호출은 검증됐으며, reranker와 실제 OpenAI API 호환성은 주장하지 않는다.

## Known unrelated environment failures

전체 suite를 `tests/ocr/test_smoke_script.py`까지 포함해 실행하면 기존 OCR smoke 테스트 2건이 macOS 환경 제약으로 실패한다.

- PowerShell executable(`powershell`/`pwsh`) 미설치
- sandbox에서 loopback HTTP server bind가 `PermissionError`로 차단

## Secret and scope audit

- `.env`, API token, secret 값은 생성·수정·커밋하지 않았다.
- 변경 범위는 runtime composition, Ollama adapter, Qdrant/BGE retrieval, indexing, Docker readiness, dependency, 관련 테스트와 Evidence 문서다.
- 기존 untracked implementation plan은 보존했으며 수정하지 않았다.
