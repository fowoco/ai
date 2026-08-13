# Language Assistant Qdrant Production Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 유효한 Qdrant·BGE-M3·EPS index 설정에서 Language Assistant가 `HybridEpsRetriever`를 사용하고, 장애나 contract 불일치 시 기존 typed degraded output을 유지한다.

**Architecture:** Qdrant client와 BGE-M3 모델은 module import/service construction 시 네트워크 또는 모델 로드를 일으키지 않는다. 실제 request에서 index contract를 먼저 검증하고, 검증된 collection에만 dense+sparse query를 실행한다. 인덱싱은 고정된 dataset/model revision으로 새 collection을 만들고 검증 성공 후 `eps_language_phrases_active` alias를 원자적으로 전환한다.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, Qdrant 1.18.3, qdrant-client 1.x, FlagEmbedding BGE-M3, pytest, Docker Compose

## Global Constraints

- 작업 위치: `/Users/parktaejung/Desktop/workspace/ai/.worktrees/language-assistant-runtime-composition`
- 브랜치: `feat/language-assistant-runtime-composition`
- Qdrant production service는 호스트 포트를 공개하지 않는다.
- collection alias는 `eps_language_phrases_active`로 통일한다.
- dataset revision은 `sha256:29106c33d43ccdd8453623ac1a0af44e0201d7c7cc1cc68c3fb438e0ccc61c6d`로 고정한다.
- BGE-M3 revision은 `5617a9f61b028005a4858fdac845db406aefb181`로 고정한다.
- index contract version은 `eps-language-index-v1`을 유지한다.
- module import, `create_app()`, OpenAPI 생성은 Qdrant 호출이나 모델 로드를 하지 않는다.
- `.env`, token, secret은 생성·수정·커밋하지 않는다.
- 기존 untracked `2026-08-10-language-assistant-runtime-composition.md`는 수정하거나 스테이징하지 않는다.

---

### Task 1: Docker Qdrant readiness 계약

**Files:**
- Modify: `compose.yml`
- Modify: `compose.test.yml`
- Test: `tests/integration/language/test_compose_config.py`

**Interfaces:**
- Consumes: Qdrant image `qdrant/qdrant:v1.18.3`
- Produces: 컨테이너 내부 `/readyz`를 검사하는 실행 가능한 healthcheck

- [ ] **Step 1: 사용할 수 없는 `wget`을 거부하는 실패 테스트 작성**

```python
def test_qdrant_healthcheck_uses_available_bash_tcp_probe() -> None:
    data = yaml.safe_load((ROOT / "compose.yml").read_text())
    command = data["services"]["qdrant"]["healthcheck"]["test"]
    assert command[:2] == ["CMD", "/bin/bash"]
    assert "/dev/tcp/127.0.0.1/6333" in command[-1]
    assert "wget" not in " ".join(command)
```

- [ ] **Step 2: RED 확인**

Run: `pytest -q tests/integration/language/test_compose_config.py`
Expected: 기존 healthcheck가 `wget`을 사용해 FAIL

- [ ] **Step 3: production/test Compose healthcheck 교체**

```yaml
healthcheck:
  test:
    - CMD
    - /bin/bash
    - -ec
    - >-
      exec 3<>/dev/tcp/127.0.0.1/6333;
      printf 'GET /readyz HTTP/1.0\r\nHost: localhost\r\n\r\n' >&3;
      grep -q 'all shards are ready' <&3
```

- [ ] **Step 4: GREEN 및 실제 container health 확인**

Run: `pytest -q tests/integration/language/test_compose_config.py`
Run: `docker compose up -d --force-recreate qdrant`
Run: `docker compose ps qdrant`
Expected: tests PASS, Qdrant `healthy`

### Task 2: 고정 index manifest와 QdrantStore contract

**Files:**
- Create: `app/agents/language/retrieval/manifest.py`
- Modify: `app/agents/language/retrieval/qdrant_store.py`
- Modify: `app/agents/language/retrieval/indexer.py`
- Test: `tests/integration/language/test_qdrant_retrieval.py`
- Test: `tests/agents/language/test_indexer.py`

**Interfaces:**
- Produces: `build_expected_index_contract() -> ExpectedIndexContract`
- Produces: `QdrantStore(client, collection_alias="eps_language_phrases_active")`
- Produces: `QdrantStore.verify_collection(...) -> None`

- [ ] **Step 1: alias와 실제 collection 검증 실패 테스트 작성**

```python
def test_store_resolves_active_alias(expected_contract):
    client = MagicMock()
    client.get_aliases.return_value.aliases = [
        MagicMock(alias_name="eps_language_phrases_active", collection_name="versioned")
    ]
    # 1024 cosine, sparse vector, count/provenance fixtures
    handle = QdrantStore(client).verify_contract(expected=expected_contract)
    assert handle.collection_name == "versioned"
```

```python
def test_verify_collection_rejects_wrong_point_count(expected_contract):
    client = MagicMock()
    client.get_collection.return_value.points_count = 0
    with pytest.raises(ValueError, match="RETRIEVAL_UNAVAILABLE"):
        QdrantStore(client).verify_collection(
            "versioned", 100, CollectionSpec(), ("en",), expected_contract
        )
```

- [ ] **Step 2: RED 확인**

Run: `pytest -q tests/integration/language/test_qdrant_retrieval.py tests/agents/language/test_indexer.py`
Expected: hard-coded old alias와 누락된 `verify_collection` 때문에 FAIL

- [ ] **Step 3: manifest 및 store 검증 구현**

```python
QDRANT_COLLECTION_ALIAS = "eps_language_phrases_active"
EPS_DATASET_REVISION = "sha256:29106c33d43ccdd8453623ac1a0af44e0201d7c7cc1cc68c3fb438e0ccc61c6d"
BGE_M3_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"
INDEX_CONTRACT_VERSION = "eps-language-index-v1"
```

`verify_collection`은 vector schema, point count, target language, dataset/model/index provenance count가 모두 일치할 때만 성공한다. Alias 전환은 기존 alias 삭제와 새 alias 생성을 한 요청에 포함한다.

- [ ] **Step 4: GREEN 확인**

Run: `pytest -q tests/integration/language/test_qdrant_retrieval.py tests/agents/language/test_indexer.py`
Expected: PASS

### Task 3: BGE-M3 production backend와 dependency

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `app/agents/language/retrieval/encoder.py`
- Modify: `scripts/download_language_models.py`
- Test: `tests/agents/language/test_retrieval_service.py`
- Test: `tests/agents/language/test_model_cache.py`

**Interfaces:**
- Produces: `FlagEmbeddingBgeM3Backend(model_path: str)` implementing `BGEM3Backend`
- Produces: `RawBgeBatch` with 1024-dimensional dense vectors and integer sparse token weights

- [ ] **Step 1: lazy load 및 output 변환 실패 테스트 작성**

```python
def test_flag_embedding_backend_converts_dense_and_lexical_weights():
    backend = FlagEmbeddingBgeM3Backend("/models/bge-m3")
    backend._model = FakeFlagModel(
        dense_vecs=[[0.1] * 1024],
        lexical_weights=[{"1": 0.5, "9": 0.2}],
    )
    result = backend.encode_queries(("고맙습니다",))
    assert len(result.dense_vectors[0]) == 1024
    assert result.lexical_weights[0] == {1: 0.5, 9: 0.2}
```

- [ ] **Step 2: RED 확인**

Run: `pytest -q tests/agents/language/test_retrieval_service.py`
Expected: production backend가 없어 FAIL

- [ ] **Step 3: lazy backend와 retrieval extra 구현**

`FlagEmbeddingBgeM3Backend`는 첫 `token_count`/`encode_queries` 호출에서만 `BGEM3FlagModel`을 import/load한다. `pyproject.toml`의 `language-retrieval` extra에 `qdrant-client>=1.19,<2`, `FlagEmbedding>=1.3,<2`, `huggingface-hub>=0.36,<2`를 추가하고 lockfile을 갱신한다.

- [ ] **Step 4: GREEN 확인**

Run: `pytest -q tests/agents/language/test_retrieval_service.py tests/agents/language/test_model_cache.py`
Expected: PASS without model load/network

### Task 4: 실제 EPS indexing pipeline

**Files:**
- Modify: `app/agents/language/retrieval/indexer.py`
- Modify: `scripts/index_eps_language.py`
- Test: `tests/agents/language/test_indexer.py`

**Interfaces:**
- Produces: `build_embedded_index_plan(store, encoder, collection_name, records, expected_contract, batch_size, alias_name)`
- Consumes: cleaned EPS records and `DenseSparseEncoder`

- [ ] **Step 1: batch embedding/upsert 및 alias 안전성 실패 테스트 작성**

```python
def test_embedded_index_plan_attaches_real_vectors_before_upsert():
    store = FakeEpsIndexStore()
    encoder = FakeDenseSparseEncoder()
    build_embedded_index_plan(
        store=store,
        encoder=encoder,
        collection_name="versioned",
        records=records,
        expected_contract=contract,
        batch_size=1,
        alias_name="eps_language_phrases_active",
    )
    payload = store.points["versioned"][0]["payload"]
    assert len(payload["dense"]) == 1024
    assert payload["sparse_indices"]
```

- [ ] **Step 2: RED 확인**

Run: `pytest -q tests/agents/language/test_indexer.py`
Expected: embedded plan이 없어 FAIL

- [ ] **Step 3: batch pipeline과 CLI 구현**

CLI는 source SHA를 검증하고, BGE-M3 backend/Qdrant client/store를 생성한 뒤 `build_embedded_index_plan`을 실행한다. 성공 메시지는 collection 검증과 alias 전환이 완료된 뒤에만 출력한다. `--dry-run`은 기존처럼 모델/Qdrant를 건드리지 않는다.

- [ ] **Step 4: GREEN 확인**

Run: `pytest -q tests/agents/language/test_indexer.py`
Run: `python scripts/index_eps_language.py --dry-run`
Expected: PASS, dry-run reports 17,902 usable records

### Task 5: Production runtime composition

**Files:**
- Modify: `app/core/config.py`
- Modify: `.env.example`
- Modify: `app/agents/language/composition.py`
- Test: `tests/agents/language/test_runtime_config.py`
- Test: `tests/integration/language/test_runtime_composition.py`
- Test: `tests/api/test_language_endpoint.py`

**Interfaces:**
- Consumes: `Settings.qdrant_url`, `Settings.qdrant_api_key`, `Settings.model_cache_dir`
- Produces: Qdrant configured -> `HybridEpsRetriever`; Qdrant absent -> `_UnavailableRetriever`

- [ ] **Step 1: actual retriever selection 실패 테스트 작성**

```python
def test_factory_selects_hybrid_retriever_when_qdrant_is_configured():
    _, retriever, _, _, _ = _build_production_ports(
        Settings(
            llm_provider="ollama",
            llm_base_url="http://localhost:11434/v1",
            llm_model="gemma4:26b-mlx",
            qdrant_url="http://qdrant:6333",
        )
    )
    assert isinstance(retriever, HybridEpsRetriever)
```

- [ ] **Step 2: RED 확인**

Run: `pytest -q tests/integration/language/test_runtime_composition.py`
Expected: 현재 `_UnavailableRetriever`가 반환되어 FAIL

- [ ] **Step 3: lazy production composition 구현**

`QdrantClient(check_compatibility=False)`, `QdrantStore`, `FlagEmbeddingBgeM3Backend`, `BgeM3Encoder`, `build_expected_index_contract()`, `HybridEpsRetriever(reranker=None)`를 조립한다. Constructor 단계에서 Qdrant 요청이나 모델 로드를 하지 않는다.

- [ ] **Step 4: GREEN 및 import safety 확인**

Run: `pytest -q tests/integration/language/test_runtime_composition.py tests/api/test_language_endpoint.py`
Run: `python -c 'from app.main import app; app.openapi()'`
Expected: PASS without Qdrant/model access

### Task 6: Offline regression, live index, API evidence

**Files:**
- Modify: `docs/language-assistant/engineering/execution/evidence/T13-RUNTIME-COMPOSITION-EVIDENCE.md`

**Interfaces:**
- Consumes: running local Qdrant, cached pinned BGE-M3, `data/eps_language_db.json`
- Produces: non-empty active alias and actual API retrieval metadata

- [ ] **Step 1: offline verification**

Run: `ruff check <changed Python files>`
Run: `pytest -q --ignore=tests/ocr/test_smoke_script.py`
Run: `git diff --check`
Expected: zero failures

- [ ] **Step 2: model cache 준비**

Run: `python scripts/download_language_models.py --cache-dir .model-cache`
Expected: pinned BGE-M3 revision cache present. 다운로드 권한이 필요한 경우 실행 직전에 승인을 요청한다.

- [ ] **Step 3: 실제 index 생성**

Run: `python scripts/index_eps_language.py --source data/eps_language_db.json --qdrant-url <reachable-local-url> --embedding-model-path .model-cache/bge-m3/5617a9f61b028005a4858fdac845db406aefb181 --switch-alias`
Expected: 17,902 points, active alias switched only after verification

- [ ] **Step 4: 실제 retrieval/API 확인**

Run: configured `POST /internal/v1/language-assistant`
Expected: HTTP 200, retrieval metadata has dataset revision/reference ids, warning codes exclude `RETRIEVAL_UNAVAILABLE`

- [ ] **Step 5: Evidence 기록 및 최종 검증**

Evidence에 commands, exit codes, collection/alias/point count, API status와 남은 미검증 범위를 기록한다. `.env`, token, secret이 변경 파일에 없음을 확인한다.
