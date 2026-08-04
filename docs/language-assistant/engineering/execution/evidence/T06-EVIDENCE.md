# T06 Hybrid Retrieval Evidence Pack

```yaml
evidence_version: 1
wave: W2
task: T06
packet_version: 1
base_sha: 9ccf9c15d48dd4b648ffab6db7726a4c2acb45be
packet_sha: 658dc29e3c0fce0e585fa84f12f4e3dfd5bff676
implementation_sha: 268e1f921b73286bc745be7c7e9e5ef5b41406b1
branch: task/la-eps-hybrid-retrieval
worktree: /Users/parktaejung/Desktop/workspace/ai-language-assistant-t06-hybrid-retrieval
clean_worktree_at_implementation: true
```

## Claims

| ID | Claim | Evidence |
|---|---|---|
| T06-C01 | BGE-M3 인코더, Qdrant Hybrid RRF 검색, Cross-Query Fusion, Reranker 통합으로 결정적 상위 5개 컨텍스트를 생성한다. | `test_success_returns_five_contexts`, `test_encoder_returns_1024_dense_dimensions`, `test_real_store_mock_search_many` |
| T06-C02 | 구성요소 장애(Qdrant 연결 오류, 인코더 실패, 토큰 제한 초과, 스키마/프로비넌스 불일치) 발생 시 typed degradation 경고를 반환하고 Graph 실행을 중단하지 않는다. | `test_qdrant_failure_returns_empty_context_and_unavailable_warning`, `test_encoder_failure_returns_empty_context_and_encoder_warning`, `test_query_too_long_returns_empty_context_without_truncation`, `test_reranker_failure_uses_cross_query_order` |
| T06-C03 | 단원 단위 unit test는 fake/mock backend를 사용해 실서버 연결 및 외부 모델 가중치 다운로드 없이 결정적으로 동작한다. | `tests/agents/language/test_retrieval_service.py` mock 백엔드 테스트 15개 |

## RED before implementation

구현 전 packet SHA(`658dc29e3c0fce0e585fa84f12f4e3dfd5bff676`)에서 다음 focused 명령을 실행했다.

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest tests/agents/language/test_retrieval_service.py -q
```

- Exit code: `2`
- 결과: `ModuleNotFoundError: No module named 'app.agents.language.retrieval.encoder'`
- 의미: T06 retrieval adapter 및 retrieval service 모듈이 아직 존재하지 않아 발생한 RED다.

## Implementation verification

모든 명령은 implementation SHA `268e1f921b73286bc745be7c7e9e5ef5b41406b1`에서 실행했다.

### Focused test

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest tests/agents/language/test_retrieval_service.py tests/integration/language/test_qdrant_retrieval.py -q
```

- Exit code: `0`
- 결과: `15 passed`

### Language regression

```bash
PYTEST_ADDOPTS='' /Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest -o addopts='' --disable-warnings -ra tests/agents/language
```

- Exit code: `0`
- 결과: `155 passed` in 0.24s

### Repository regression

```bash
PYTEST_ADDOPTS='' /Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest -o addopts='' --disable-warnings -q
```

- Exit code: `0`
- 결과: `295 passed, 1 skipped` in 1.32s

### Ruff

```bash
RUFF_CACHE_DIR=/private/tmp/la-t06-ruff-cache /Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/ruff check \
  app/agents/language/retrieval/encoder.py \
  app/agents/language/retrieval/qdrant_store.py \
  app/agents/language/retrieval/reranker.py \
  app/agents/language/retrieval/service.py \
  scripts/index_eps_language.py \
  tests/agents/language/test_retrieval_service.py \
  tests/integration/language/test_qdrant_retrieval.py
```

- Exit code: `0`
- 결과: `All checks passed!`

### Diff and scope

```bash
git diff --check
git diff --name-status 658dc29e3c0fce0e585fa84f12f4e3dfd5bff676..268e1f921b73286bc745be7c7e9e5ef5b41406b1
```

- Exit code: `0`
- 변경 파일은 허용 파일 범위 내 7개 한정.

```text
A  app/agents/language/retrieval/encoder.py
A  app/agents/language/retrieval/qdrant_store.py
A  app/agents/language/retrieval/reranker.py
A  app/agents/language/retrieval/service.py
A  scripts/index_eps_language.py
A  tests/agents/language/test_retrieval_service.py
A  tests/integration/language/test_qdrant_retrieval.py
```

## Scope audit

```yaml
implementation_allowed_files_only: true
unexpected_implementation_files: []
vendor_imports_in_retrieval_domain: []
evidence_artifact: docs/language-assistant/engineering/execution/evidence/T06-EVIDENCE.md
```

## Unrun and unverified

- 실 Qdrant 서버 런타임 연결 및 운영 환경 배포는 실행하지 않았다.
- FlagEmbedding HuggingFace 실 모델 런타임 다운로드 및 GPU 추론은 unit test에서 실행하지 않았다.
- T07 세대 자원 모듈 및 후속 W3 Graph 조립은 시작하지 않았다.

## Rollback

- Safe point: `9ccf9c15d48dd4b648ffab6db7726a4c2acb45be`
