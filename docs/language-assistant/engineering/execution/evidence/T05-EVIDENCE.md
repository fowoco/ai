# T05 EPS Index Plan Evidence Pack

```yaml
evidence_version: 1
wave: W2
task: T05
packet_version: 1
base_sha: d847dfea435a442f8734601f3e3a9dc3b34e0d92
packet_sha: d07b36bd32e341f22b6ba0c99a5cd51b4a291827
implementation_sha: 81f955f6fe22bee80a7046108ba185f271265a25
branch: task/la-t05-eps-index-plan
worktree: /Users/parktaejung/Desktop/workspace/ai-language-assistant-t05-eps-index-plan
clean_worktree_at_implementation: true
```

## Claims

| ID | Claim | Evidence |
|---|---|---|
| T05-C01 | EPS 데이터 정제가 재현 가능하며, 17,925개 원본 레코드 중 공백 한국어(0개), 공백 번역(10개), 중복(13개)을 제거해 정확히 17,902개 유효 레코드를 확정한다. | `test_full_eps_dry_run`, `test_indexer_drops_blank_translation`, `test_indexer_drops_blank_korean`, `test_indexer_deduplicates_exact_records` |
| T05-C02 | Point ID(UUID5) 및 collection name 생성이 결정적이며 데이터셋 SHA와 인코더 리비전으로부터 도출된다. | `test_point_ids_are_deterministic`, `test_payload_has_dataset_and_content_hash`, `generate_collection_name` 단위 테스트 |
| T05-C03 | Vendor-neutral index plan이 fake store 기반 build-verify-alias-switch 수명주기를 강제한다. | `test_new_collection_is_verified_before_alias_switch`, `test_failed_verification_keeps_old_alias`, `test_expected_count_must_match`, `test_reindex_is_idempotent` |
| T05-C04 | Payload에 발음 필드가 제외되며 모든 포인트에 정확한 인덱스 출처 프로비넌스가 저장된다. | `test_payload_has_no_pronunciation`, `test_payload_has_exact_encoder_and_index_contract_provenance`, `test_index_verification_requires_one_exact_provenance_for_every_point` |

## RED before implementation

구현 전 packet SHA(`d07b36bd32e341f22b6ba0c99a5cd51b4a291827`)에서 다음 focused 명령을 실행했다.

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest tests/agents/language/test_indexer.py -q
```

- Exit code: `2`
- 결과: `ImportError: cannot import name 'EpsIndexStore' from 'app.agents.language.ports'`
- 의미: T05 retrieval indexer 및 `EpsIndexStore` Protocol이 존재하지 않아 발생한 RED다.

## Implementation verification

모든 명령은 implementation SHA `81f955f6fe22bee80a7046108ba185f271265a25`에서 실행했다.

### Focused test

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest tests/agents/language/test_indexer.py -q
```

- Exit code: `0`
- 결과: `17 passed`

### Language regression

```bash
PYTEST_ADDOPTS='' /Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest -o addopts='' --disable-warnings -ra tests/agents/language
```

- Exit code: `0`
- 결과: `142 passed` in 0.21s

### Repository regression

```bash
PYTEST_ADDOPTS='' /Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest -o addopts='' --disable-warnings -q
```

- Exit code: `0`
- 결과: `280 passed, 1 skipped` in 1.34s

### Ruff

```bash
RUFF_CACHE_DIR=/private/tmp/la-t05-ruff-cache /Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/ruff check \
  app/agents/language/ports.py \
  app/agents/language/retrieval/indexer.py \
  app/agents/language/retrieval/models.py \
  tests/agents/language/test_indexer.py
```

- Exit code: `0`
- 결과: `All checks passed!`

### Diff and scope

```bash
git diff --check
git diff --name-status d847dfea435a442f8734601f3e3a9dc3b34e0d92..81f955f6fe22bee80a7046108ba185f271265a25
```

- Exit code: `0`
- 변경 파일은 Packet 허용 파일 5개에 한정되었다.

```text
M  app/agents/language/ports.py
A  app/agents/language/retrieval/indexer.py
M  app/agents/language/retrieval/models.py
A  tests/agents/language/test_indexer.py
A  tests/fixtures/language/eps_minimal.json
```

## Scope audit

```yaml
implementation_allowed_files_only: true
unexpected_implementation_files: []
vendor_imports_in_retrieval_domain: []
evidence_artifact: docs/language-assistant/engineering/execution/evidence/T05-EVIDENCE.md
```

## Unrun and unverified

- 실 Qdrant 서버 생성/연결 및 인덱스 생성을 수행하지 않았다.
- FlagEmbedding / BGE-M3 실 임베딩 모델 추론 및 벡터화 계산을 실행하지 않았다.
- T06 Hybrid retrieval adapter 연결을 실행하지 않았다.

## Rollback

- Safe point: `d847dfea435a442f8734601f3e3a9dc3b34e0d92`
