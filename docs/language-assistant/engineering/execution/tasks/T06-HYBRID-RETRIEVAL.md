# T06 Task Packet — Hybrid Retrieval Adapter and Degradation Policy

```yaml
packet_version: 1
wave: W2
task: T06
title: BGE-M3, Qdrant Hybrid Search, Reranking, and Retrieval Degradation
status: sealed
```

## Claims

- BGE-M3 encoder, Qdrant hybrid search, cross-query RRF fusion, and reranker produce top-5 deterministic context.
- Component failures (model missing, Qdrant connection error, timeout, contract mismatch) return typed degradation without crashing the graph.
- Unit tests use fake/mock backends and do not download external model weights or connect to real Qdrant servers.

## Git contract

```yaml
integration_branch: feat/language-assistant
base_sha: 9ccf9c15d48dd4b648ffab6db7726a4c2acb45be
packet_sha: recorded in ledger after sealing
task_branch: task/la-eps-hybrid-retrieval
worktree: /Users/parktaejung/Desktop/workspace/ai-language-assistant-t06-hybrid-retrieval
```

## Scope

### Allowed files

- `app/agents/language/retrieval/encoder.py`
- `app/agents/language/retrieval/qdrant_store.py`
- `app/agents/language/retrieval/reranker.py`
- `app/agents/language/retrieval/service.py`
- `scripts/index_eps_language.py`
- `tests/agents/language/test_retrieval_service.py`
- `tests/integration/language/test_qdrant_retrieval.py`
- `pyproject.toml`
- `uv.lock`

### Forbidden files and behavior

- Do not modify files outside the allowed list.
- Do not download model weights or connect to real external Qdrant servers in unit tests.
- Do not modify existing T01–T05 contracts or tests.

## Stop conditions

- Ambiguity in degradation policy or retrieval service contract.
- Files outside allowed list need modification.
