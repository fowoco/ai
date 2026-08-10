# Language Assistant Reranker Docker Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 고정 revision BGE-M3와 BGE reranker를 production Docker image에 포함하고, production retrieval composition에서 실제 reranker를 사용한다.

**Architecture:** 모델 repo/revision은 retrieval manifest를 단일 소스로 사용한다. Docker build가 두 모델을 `/opt/fowoco/language-models`에 내려받고, production composition은 같은 경로 규칙으로 lazy encoder와 reranker를 조립한다. 외부 모델·Qdrant 실검증은 자동 테스트와 분리해 Evidence에 기록한다.

**Tech Stack:** Python 3.12, FastAPI, Qdrant 1.18.3, qdrant-client 1.19.x, FlagEmbedding 1.4.x, Hugging Face Hub, pytest, Ruff, Docker Compose

## Global Constraints

- OpenAI API·provider 설정은 변경하거나 호출하지 않는다.
- Encoder revision은 `5617a9f61b028005a4858fdac845db406aefb181`이다.
- Reranker revision은 `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`이다.
- 모델은 Docker build 중 다운로드하고 request 처리 중 다운로드하지 않는다.
- 모델 volume이나 별도 init service를 추가하지 않는다.
- 모델 누락·reranker 실패 시 기존 cross-query RRF fallback 계약을 유지한다.
- `.env`, API key, token, secret을 생성하거나 커밋하지 않는다.
- 기존 미추적 `docs/language-assistant/engineering/plans/2026-08-10-language-assistant-runtime-composition.md`는 수정·스테이징하지 않는다.

---

### Task 1: Reranker revision 단일화

**Files:**
- Modify: `app/agents/language/retrieval/manifest.py`
- Modify: `scripts/download_language_models.py`
- Modify: `tests/agents/language/test_model_cache.py`

**Interfaces:**
- Produces: `BGE_RERANKER_MODEL_REPO: str`, `BGE_RERANKER_REVISION: str`
- Consumes: 기존 `BGE_M3_MODEL_REPO`, `BGE_M3_REVISION`

- [ ] **Step 1: 잘못된 revision을 잡는 실패 테스트 작성**

```python
def test_manifest_constants_defined() -> None:
    from app.agents.language.retrieval.manifest import (
        BGE_M3_REVISION,
        BGE_RERANKER_MODEL_REPO,
        BGE_RERANKER_REVISION,
    )
    from scripts.download_language_models import MODEL_SPECS

    assert BGE_M3_REVISION == "5617a9f61b028005a4858fdac845db406aefb181"
    assert BGE_RERANKER_MODEL_REPO == "BAAI/bge-reranker-v2-m3"
    assert BGE_RERANKER_REVISION == "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
    assert MODEL_SPECS[1]["revision"] == BGE_RERANKER_REVISION
```

- [ ] **Step 2: RED 확인**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest \
  tests/agents/language/test_model_cache.py::TestModelManifest::test_manifest_constants_defined
```

Expected: manifest에 reranker 상수가 없어 FAIL.

- [ ] **Step 3: manifest 상수를 추가하고 스크립트의 중복 상수 제거**

```python
BGE_RERANKER_MODEL_REPO = "BAAI/bge-reranker-v2-m3"
BGE_RERANKER_REVISION = "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
```

`MODEL_SPECS`는 두 값을 `manifest.py`에서 import해 사용한다.

- [ ] **Step 4: GREEN 확인**

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/agents/language/test_model_cache.py
.venv/bin/ruff check app/agents/language/retrieval/manifest.py \
  scripts/download_language_models.py tests/agents/language/test_model_cache.py
```

- [ ] **Step 5: 커밋**

```bash
git add app/agents/language/retrieval/manifest.py \
  scripts/download_language_models.py tests/agents/language/test_model_cache.py
git commit -m "fix(language): reranker 모델 revision 단일화"
```

### Task 2: Production reranker composition 연결

**Files:**
- Modify: `app/agents/language/retrieval/reranker.py`
- Modify: `app/agents/language/composition.py`
- Modify: `tests/integration/language/test_runtime_composition.py`

**Interfaces:**
- Consumes: Task 1의 `BGE_RERANKER_REVISION`
- Produces: `HybridEpsRetriever.reranker: FlagEmbeddingReranker`

- [ ] **Step 1: production composition 실패 테스트 작성**

```python
def test_factory_wires_fixed_revision_reranker_when_qdrant_is_configured(
    tmp_path: Path,
) -> None:
    from app.agents.language.composition import _build_production_ports
    from app.agents.language.retrieval.manifest import BGE_RERANKER_REVISION
    from app.agents.language.retrieval.reranker import FlagEmbeddingReranker

    _, retriever, _, _, _ = _build_production_ports(
        Settings(
            llm_provider="ollama",
            llm_base_url="http://localhost:11434/v1",
            llm_model="gemma4:26b-mlx",
            qdrant_url="http://qdrant:6333",
            model_cache_dir=tmp_path,
        )
    )

    assert isinstance(retriever, HybridEpsRetriever)
    assert isinstance(retriever.reranker, FlagEmbeddingReranker)
    assert retriever.reranker.model_path == str(
        tmp_path / "bge-reranker-v2-m3" / BGE_RERANKER_REVISION
    )
    assert retriever.reranker.use_fp16 is False
```

- [ ] **Step 2: RED 확인**

```bash
PYTHONPATH=. .venv/bin/python -m pytest \
  tests/integration/language/test_runtime_composition.py::test_factory_wires_fixed_revision_reranker_when_qdrant_is_configured
```

Expected: `retriever.reranker is None`으로 FAIL.

- [ ] **Step 3: 기존 adapter를 최소 연결**

`FlagEmbeddingReranker`에 `use_fp16: bool = False`를 저장하고 model 생성에 전달한다. `_build_retriever()`는 다음 경로로 adapter를 만든다.

```python
reranker_path = (
    settings.model_cache_dir
    / "bge-reranker-v2-m3"
    / BGE_RERANKER_REVISION
)
reranker = FlagEmbeddingReranker(
    model_path=str(reranker_path),
    expected_revision=BGE_RERANKER_REVISION,
    use_fp16=False,
)
```

`HybridEpsRetriever(..., reranker=reranker, ...)`로 주입한다. constructor에서 모델을 로드하거나 네트워크를 호출하지 않는다.

- [ ] **Step 4: GREEN과 fallback 회귀 확인**

```bash
PYTHONPATH=. .venv/bin/python -m pytest \
  tests/integration/language/test_runtime_composition.py \
  tests/agents/language/test_retrieval_service.py
.venv/bin/ruff check app/agents/language/composition.py \
  app/agents/language/retrieval/reranker.py \
  tests/integration/language/test_runtime_composition.py
```

- [ ] **Step 5: 커밋**

```bash
git add app/agents/language/composition.py \
  app/agents/language/retrieval/reranker.py \
  tests/integration/language/test_runtime_composition.py
git commit -m "feat(language): production reranker 검색 경로 연결"
```

### Task 3: 모델을 production Docker image에 포함

**Files:**
- Modify: `Dockerfile`
- Modify: `.dockerignore`
- Modify: `compose.yml`
- Modify: `tests/integration/language/test_compose_config.py`

**Interfaces:**
- Consumes: `scripts/download_language_models.py --cache-dir PATH`
- Produces: image model root `/opt/fowoco/language-models`

- [ ] **Step 1: Docker 계약 실패 테스트 작성**

```python
def test_production_image_bakes_language_models() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()
    dockerignore = (ROOT / ".dockerignore").read_text().splitlines()

    assert "COPY scripts/download_language_models.py ./scripts/" in dockerfile
    assert "/app/.venv/bin/python scripts/download_language_models.py" in dockerfile
    assert "--cache-dir /opt/fowoco/language-models" in dockerfile
    assert "FOWOCO_MODEL_CACHE_DIR=/opt/fowoco/language-models" in dockerfile
    assert "scripts/*" in dockerignore
    assert "!scripts/download_language_models.py" in dockerignore
    assert "scripts" not in dockerignore


def test_ai_service_uses_baked_model_path() -> None:
    import yaml

    data = yaml.safe_load((ROOT / "compose.yml").read_text())
    assert data["services"]["ai"]["environment"]["FOWOCO_MODEL_CACHE_DIR"] \
        == "/opt/fowoco/language-models"
```

- [ ] **Step 2: RED 확인**

```bash
PYTHONPATH=. .venv/bin/python -m pytest \
  tests/integration/language/test_compose_config.py::test_production_image_bakes_language_models \
  tests/integration/language/test_compose_config.py::test_ai_service_uses_baked_model_path
```

Expected: Dockerfile script copy/download와 baked path가 없어 FAIL.

- [ ] **Step 3: Dockerfile과 Compose 최소 수정**

`.dockerignore`에서 `scripts`를 `scripts/*`로 바꾸고 다운로드 스크립트만 re-include한다. Dockerfile은 app과 script를 복사한 뒤 다음을 실행한다.

```dockerfile
COPY scripts/download_language_models.py ./scripts/
RUN /app/.venv/bin/python scripts/download_language_models.py \
    --cache-dir /opt/fowoco/language-models
ENV FOWOCO_MODEL_CACHE_DIR=/opt/fowoco/language-models
```

Compose의 `FOWOCO_MODEL_CACHE_DIR`도 `/opt/fowoco/language-models`로 바꾼다.

- [ ] **Step 4: GREEN과 구성 검증**

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/integration/language/test_compose_config.py
docker compose config --quiet
.venv/bin/ruff check tests/integration/language/test_compose_config.py
git diff --check
```

- [ ] **Step 5: 커밋**

```bash
git add Dockerfile .dockerignore compose.yml \
  tests/integration/language/test_compose_config.py
git commit -m "feat(language): Docker 이미지에 검색 모델 포함"
```

### Task 4: 실제 모델·Qdrant·Docker 검증과 Evidence

**Files:**
- Modify: `docs/language-assistant/engineering/execution/evidence/T13-RUNTIME-COMPOSITION-EVIDENCE.md`

**Interfaces:**
- Consumes: Task 1~3의 final HEAD, production `fowoco-qdrant`, local Ollama
- Produces: reranker live 결과와 Docker runtime evidence

- [ ] **Step 1: 자동 회귀 검증**

```bash
PYTHONPATH=. /opt/homebrew/bin/uv run --frozen \
  --extra dev --extra language-retrieval \
  pytest --ignore=tests/ocr/test_smoke_script.py
/opt/homebrew/bin/uv run --frozen --extra dev --extra language-retrieval ruff check \
  app/agents/language/composition.py \
  app/agents/language/retrieval/manifest.py \
  app/agents/language/retrieval/reranker.py \
  scripts/download_language_models.py \
  tests/agents/language/test_model_cache.py \
  tests/integration/language/test_runtime_composition.py \
  tests/integration/language/test_compose_config.py
/opt/homebrew/bin/uv lock --check
docker compose config --quiet
docker compose -f compose.test.yml config --quiet
git diff --check
```

Expected: 모두 exit `0`.

- [ ] **Step 2: 모델 내장 image build**

```bash
docker compose build ai
```

Expected: 두 고정 revision 다운로드와 image export 성공. build 시간, image 크기, platform manifest를 기록한다.

- [ ] **Step 3: image 내부 모델과 one-shot 확인**

```bash
docker run --rm --entrypoint /bin/sh fowoco-ai:latest -ec \
  'test -f /opt/fowoco/language-models/bge-m3/5617a9f61b028005a4858fdac845db406aefb181/config.json && test -f /opt/fowoco/language-models/bge-reranker-v2-m3/953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e/config.json'
docker run --rm fowoco-ai:latest uv run python -c \
  'from app.main import create_app; print(type(create_app()).__name__)'
```

Expected: 두 command exit `0`, second output에 `FastAPI`.

- [ ] **Step 4: production Qdrant와 실제 reranker 검색**

production Docker network에서 baked image의 `_build_production_ports()`를 사용해 세 `SearchQuery`를 검색한다. 결과는 다음을 모두 만족해야 한다.

```text
len(contexts) == 5
all(context.selected_by == "reranker" for context in contexts)
"reranker" not in degraded_components
fallback_used == false
```

- [ ] **Step 5: Compose AI service 기동 확인**

```bash
docker compose up -d ai
docker inspect fowoco-ai --format '{{.State.Health.Status}}'
curl -fsS http://localhost:8000/openapi.json
docker compose stop ai
```

Expected: health `healthy`, OpenAPI HTTP `200`. Qdrant service와 production volume은 유지한다.

- [ ] **Step 6: Evidence 갱신·검토**

Evidence에 final SHA lineage, 실제 revision, reranker 결과, Docker build/runtime 결과, image 크기, build 시간, OpenAI 제외를 기록한다. 이전 one-shot 정지는 재현되지 않은 OrbStack 일시 상태로 수정한다.

- [ ] **Step 7: Evidence 커밋**

```bash
git add docs/language-assistant/engineering/execution/evidence/T13-RUNTIME-COMPOSITION-EVIDENCE.md
git commit -m "docs(language): reranker 및 Docker 실검증 기록"
```

- [ ] **Step 8: 깨끗한 detached worktree 최종 검증**

final HEAD를 `/private/tmp`의 detached worktree에서 다시 checkout하고 Step 1의 자동 검증을 반복한다. `git status --short`가 비어 있고 `origin/develop` ancestry가 유지되는지 확인한다.
