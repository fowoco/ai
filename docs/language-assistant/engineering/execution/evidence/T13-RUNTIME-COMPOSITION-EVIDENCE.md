# Language Assistant Runtime Composition Evidence

```yaml
evidence_version: 1
task: issue-24-runtime-composition
branch: feat/language-assistant-runtime-composition
worktree: /Users/parktaejung/Desktop/workspace/ai/.worktrees/language-assistant-runtime-composition
base_sha: 8837c5efcf1f161442e0adab8584488e0a656c0f
implementation_commit: 177e695 (runtime/Ollama); 7c56654 (Qdrant/BGE/Docker); 8e227211 (reranker composition); d43e163 (model-baked Docker contract); this commit (Task 4 evidence)
live_ollama_qdrant: success-with-easy-korean-fallback
ollama_model: gemma4:26b-mlx
ollama_structured_output: success
qdrant_endpoint: fowoco-qdrant:6333 (production volume; temporary localhost:26333 proxy removed after verification)
qdrant_retrieval: success
docker_baked_model_build: failed-before-model-download
docker_baked_model_failure: ModuleNotFoundError for app in download_language_models.py
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
| C08 | production Qdrant volume에 실제 BGE-M3 index를 생성하고, 검색에서 5개 reference를 반환하며 retrieval fallback/warning이 없다. | production Qdrant/BGE live result below |
| C09 | production Docker image는 `language-retrieval` extra를 포함해 빌드된다. | `docker compose build ai` exit `0`; image metadata below |
| C10 | feature HEAD는 검수 시점의 최신 `origin/develop`을 포함한다. | `git merge-base --is-ancestor origin/develop HEAD` exit `0`; base `8837c5e` |
| C11 | production retriever는 고정 revision의 BGE reranker를 lazy하게 조립하고 실패 시 기존 degraded 계약을 유지한다. | `test_factory_wires_fixed_revision_reranker_when_qdrant_is_configured`, Task 2 focused suite `23 passed`; 실제 container reranking은 아래 Task 4 build 실패로 미검증 |

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
- Result: `576 passed, 1 skipped, 1164 warnings in 2.18s`

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
- isolated `fowoco-qdrant-test`: 이전 격리 검증에서 `healthy`; OrbStack 재시작 후 중지 상태
- production Qdrant 검증용 임시 proxy `localhost:26333`: 검증 후 제거
- host `6333`, `26333`: 모두 비공개/연결 거부 상태
- production Compose의 host port 비공개 계약 유지

### Actual BGE-M3 indexing and production Qdrant retrieval

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
- production collection status: `green`, optimizer status: `ok`
- production alias: `eps_language_phrases_active` → `eps_language_phrases_29106c33d43c_5617a9f61b02`
- provenance payload indexes: 각 `17,902` points
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
- post-rebase production-Qdrant run elapsed: `65.51`초
- retrieval dataset version: `sha256:29106c33d43ccdd8453623ac1a0af44e0201d7c7cc1cc68c3fb438e0ccc61c6d`
- retrieval reference count: `5`
- retrieval reference IDs: `ef4b8686-5a53-5133-9ca2-df615070af86`, `b9f625d6-4bcd-5758-85df-3f700ad8e25b`, `497d29fd-ea15-569e-9419-f4bc0dd87af0`, `8be7ab57-92d5-5148-9e31-00b21f8a37c1`, `fa19ac87-d641-5da7-ba60-4c85171ea8ac`
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
- application platform manifest: `sha256:08af20ea1794e4eadf53e75158e6d7dd92b4edec81ea2113d26b4e403b54f319`
- architecture: `arm64`
- image size: `3,506,131,198` bytes
- installed retrieval packages: `qdrant-client==1.19.0`, `FlagEmbedding==1.4.0`, `torch==2.13.0`
- BuildKit attestation 때문에 `latest` manifest-list digest는 빌드마다 달라질 수 있어 재현성 기준으로 사용하지 않음
- latest image one-shot smoke: Python 시작이 두 차례 장시간 정지해 중단했으며, OrbStack 재시작 후 Qdrant 데이터 영속성을 재확인함
- 주의: Linux Torch가 CUDA 계열 wheel을 포함해 이미지가 3.51 GB다. 빌드는 성공했지만 이미지 경량화는 별도 최적화 대상이다.

위 결과는 BGE-M3와 reranker를 이미지에 직접 포함하기 전 image의 기록이다. 모델 bake를 추가한 `d43e163`에서 2026-08-10에 다음 Task 4 검증을 별도로 수행했다.

### Model-baked production Docker Task 4 attempt

Preflight:

- branch: `feat/language-assistant-runtime-composition`
- HEAD: `d43e163d998657e2a2fe3cbcbb206493b6933776`
- `git status --short`: 사용자 소유 untracked 계획 문서 1개만 존재
- `fowoco-qdrant`: `running`, `healthy`
- Qdrant collection, alias, point, volume 변경: 없음

Build:

```bash
docker compose build ai
```

- Exit code: `1`
- Python retrieval dependency 설치: 성공 (`FlagEmbedding==1.4.0`, `torch==2.13.0`, `qdrant-client==1.19.0` 포함)
- 모델 bake command 진입: 성공
- 실패 command: `/app/.venv/bin/python scripts/download_language_models.py --cache-dir /opt/fowoco/language-models`
- 실패 원인: `ModuleNotFoundError: No module named 'app'`
- 실패 위치: `download_language_models.py`가 `app.agents.language.retrieval.manifest`를 import하는 시점
- BGE-M3/reranker model download 시작: 하지 못함

Build가 model download 전에 실패했으므로 다음 항목은 성공으로 주장하지 않는다.

- model-baked image platform manifest/size: 생성되지 않음
- 두 모델의 `config.json` image 내부 존재: 미검증
- 최신 image health 및 `/openapi.json`: 미검증
- 최신 image one-shot `create_app()`: 미검증
- 실제 Qdrant hybrid retrieval + BGE reranker JSON assert: 미검증

실패 후 `fowoco-qdrant`가 계속 `running`, `healthy`임을 재확인했다. AI service는 시작되지 않았으므로 stop 대상이 없었고, Qdrant는 중지·삭제·재색인하지 않았다. 외부 LLM/Ollama/OpenAI 호출과 provider 설정 변경도 수행하지 않았다.

## Not yet verified

- model-baked production image의 실제 BGE reranker 성공 경로; build가 model download 전에 실패함
- model-baked production image의 manifest/size, model `config.json`, health/OpenAPI, one-shot `create_app()`
- actual OpenAI API structured-output compatibility; 현재 작업 범위에서 명시적으로 제외함

현재 production composition은 Qdrant URL이 없으면 typed degraded fallback을 사용하고, 유효한 URL에서는 lazy BGE-M3 backend, `HybridEpsRetriever`, lazy BGE reranker를 조립한다. production Qdrant volume의 실제 BGE-M3 indexing·retrieval과 Ollama 결합 API 호출은 이전 단계에서 검증됐다. 다만 model-baked image build가 downloader import 오류로 중단되어, 최신 image의 reranker·health·one-shot 성공은 주장하지 않는다.

## Known unrelated environment failures

전체 suite를 `tests/ocr/test_smoke_script.py`까지 포함해 실행하면 기존 OCR smoke 테스트 2건이 macOS 환경 제약으로 실패한다.

- PowerShell executable(`powershell`/`pwsh`) 미설치
- sandbox에서 loopback HTTP server bind가 `PermissionError`로 차단

## Secret and scope audit

- `.env`, API token, secret 값은 생성·수정·커밋하지 않았다.
- 변경 범위는 runtime composition, Ollama adapter, Qdrant/BGE retrieval, indexing, Docker readiness, dependency, 관련 테스트와 Evidence 문서다.
- 기존 untracked implementation plan은 보존했으며 수정하지 않았다.
