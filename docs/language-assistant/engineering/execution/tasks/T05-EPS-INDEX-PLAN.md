# T05 Task Packet — EPS Index Plan

```yaml
packet_version: 1
wave: W2
task: T05
title: Reproducible EPS cleaning and vendor-neutral index plan
status: sealed
```

## Claims

- EPS cleaning is reproducible, NFC-normalizes text, drops blank translations/Korean, and dedupes exact records to exactly 17,902 usable unique records from 17,925 source rows.
- Point IDs (UUID5 with constant namespace) and versioned collection names are deterministic and derived from dataset SHA and encoder revision.
- The vendor-neutral index plan enforces build-verify-alias-switch semantics with a fake store without importing Qdrant or model packages.
- Pronunciation fields are excluded from payloads, and every point payload stores exact index provenance (dataset revision, encoder repo/revision, index contract version).

## Source authority

- Design: `docs/language-assistant/engineering/specs/2026-08-02-language-assistant-graph-design.md`
- Implementation plan: `docs/language-assistant/engineering/plans/2026-08-02-language-assistant-graph.md`, Task 5
- Control Tower protocol: `docs/language-assistant/engineering/specs/2026-08-02-language-assistant-control-tower-design.md`
- Current integrated base: `d847dfea435a442f8734601f3e3a9dc3b34e0d92`

## Git contract

```yaml
integration_branch: feat/language-assistant
base_sha: d847dfea435a442f8734601f3e3a9dc3b34e0d92
packet_sha: recorded in the Control Tower ledger after sealing
task_branch: task/la-t05-eps-index-plan
worktree: /Users/parktaejung/Desktop/workspace/ai-language-assistant-t05-eps-index-plan
```

The Builder must start from the packet commit. The Builder must not modify the packet or the Control Tower ledger.

## Dependencies

- T02 integrated: `550fc47c329f2d049985df9ec552d981cbf53aaf`
- T04 integrated: `d847dfea435a442f8734601f3e3a9dc3b34e0d92`
- User Gate: `진행` recorded for W2 on 2026-08-04

## Scope

### Allowed files

- `app/agents/language/ports.py`
- `app/agents/language/retrieval/indexer.py`
- `app/agents/language/retrieval/models.py`
- `tests/fixtures/language/eps_minimal.json`
- `tests/agents/language/test_indexer.py`

### Forbidden files and behavior

- Do not modify files outside the allowed list, including `control-tower.md`, existing T01–T04 Evidence Packs, API/runtime files, and T06 files.
- Do not import Qdrant, FlagEmbedding, FastAPI, LangGraph, or external provider SDKs.
- Do not connect to a real Qdrant server or download embedding models in T05 unit tests.
- Do not modify existing T01–T04 contracts or tests.

## Required domain contract

- `EpsIndexStore` Protocol in `ports.py` with `create_collection`, `ensure_payload_indexes`, `upsert_batch`, `verify_collection`, and `swap_alias`.
- `CollectionSpec` dataclass/model (`dense_vector_name="korean_dense"`, `dense_vector_size=1024`, `dense_distance="cosine"`, `sparse_vector_name="korean_sparse"`).
- Pure cleaning and normalization function in `indexer.py`:
  - Input: raw EPS JSON rows.
  - Normalization: trim and NFC normalize `korean_text` and `translated_text`.
  - Drop rules: drop blank Korean, drop blank foreign translation, reject unknown EPS language code, reject non-positive integer page.
  - Deduplication: dedupe key `(eps_language_code, korean_text, translated_text)`, retaining the smallest numeric `source_page`.
  - Deterministic Point ID: `UUID5(constant_namespace, content_hash)` where `content_hash = sha256(json.dumps([eps_code, korean, translation], ensure_ascii=False, separators=(",", ":")).encode("utf-8"))`.
  - Collection name format: `eps_language_phrases_<dataset_sha_first_12>_<encoder_revision_first_12>`.
  - Payload fields: `eps_reference` payload attributes, `embedding_model_repo="BAAI/bge-m3"`, full `embedding_model_revision`, `index_contract_version="eps-language-index-v1"`, dataset revision SHA-256. No pronunciation fields in payload.
- Build-verify-alias-switch index plan pipeline (`build_index_plan`). Alias switch occurs only if `switch_alias=True` and only after `verify_collection` passes.

## Required tests

Write the following tests before implementation and record initial failures:

- Minimal fixture cleaning tests (`eps_minimal.json`): drop blank translation, drop blank korean, deduplicate exact records, reject unknown eps code, reject invalid page.
- Deterministic point IDs and payload provenance (dataset revision, content hash, index contract version, no pronunciation).
- Idempotency and collection lifecycle with a fake store: `reindex_is_idempotent`, `new_collection_is_verified_before_alias_switch`, `failed_verification_keeps_old_alias`, `expected_count_must_match`.
- Current-data dry-run test: 17,925 source rows -> 10 blank translations dropped, 13 duplicates dropped -> 17,902 usable unique records across 15 languages (without model inference).

## Required verification commands

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest tests/agents/language/test_indexer.py -q
RUFF_CACHE_DIR=/private/tmp/la-t05-ruff-cache /Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/ruff check \
  app/agents/language/ports.py \
  app/agents/language/retrieval/indexer.py \
  app/agents/language/retrieval/models.py \
  tests/agents/language/test_indexer.py
git diff --check
```

## Evidence required

- RED output before implementation
- implementation SHA and changed-file list
- focused and regression test commands with exit codes
- changed-area Ruff and `git diff --check` results
- exact scope audit and clean worktree result
- unrun/unverified list
- rollback safe point: `d847dfea435a442f8734601f3e3a9dc3b34e0d92`

## Stop conditions

- A retrieval/indexing contract is ambiguous or conflicts with T02/T04.
- An allowed file outside this Packet must change.
- External services, model downloads, or Qdrant connections are required in T05 tests.
- On any stop condition, report to the Control Tower.
