# T04 Task Packet — Retrieval Domain

```yaml
packet_version: 1
wave: W2
task: T04
title: Retrieval domain models, ports, and deterministic cross-query RRF
status: sealed
```

## Claims

- Retrieval domain models enforce the vector, EPS reference, index-contract, ranking, fusion, and selected-context invariants without importing Qdrant or FlagEmbedding.
- Cross-query Reciprocal Rank Fusion (RRF) is deterministic, deduplicates by EPS point ID, uses all query rankings, and applies the specified tie-break order.
- The reranker/source pairing is represented as a discriminated union, so impossible score and `selected_by` combinations are rejected.
- Every retrieval port has a deterministic fake that can be used by later graph and retry tests without external services.

## Source authority

- Design: `docs/language-assistant/engineering/specs/2026-08-02-language-assistant-graph-design.md`
- Implementation plan: `docs/language-assistant/engineering/plans/2026-08-02-language-assistant-graph.md`, Task 4
- Control Tower protocol: `docs/language-assistant/engineering/specs/2026-08-02-language-assistant-control-tower-design.md`
- Current integrated base: `f13487f540fed74cd336be4aa9df5802aedf7a57`

## Git contract

```yaml
integration_branch: feat/language-assistant
base_sha: f13487f540fed74cd336be4aa9df5802aedf7a57
packet_sha: recorded in the Control Tower ledger after sealing
task_branch: task/la-t04-retrieval-domain
worktree: /Users/parktaejung/Desktop/workspace/ai-language-assistant-t04-retrieval-domain
```

The Builder must start from the packet commit. The Builder must not modify the packet or the Control Tower ledger.

## Dependencies

- T02 integrated: `550fc47c329f2d049985df9ec552d981cbf53aaf`
- T03 integrated: `2ddb84cc3600fe2b7cd03577e5fa364174f19133`
- User Gate: `진행` recorded for W2 on 2026-08-04

## Scope

### Allowed files

- `app/agents/language/ports.py`
- `app/agents/language/retrieval/__init__.py`
- `app/agents/language/retrieval/models.py`
- `app/agents/language/retrieval/fusion.py`
- `tests/agents/language/fakes.py`
- `tests/agents/language/test_fusion.py`

### Forbidden files and behavior

- Do not modify files outside the allowed list, including `control-tower.md`, existing T01–T03 Evidence Packs, API/runtime files, and T05/T06 files.
- Do not import Qdrant, FlagEmbedding, FastAPI, LangGraph, or external provider SDKs into the retrieval domain or graph code.
- Do not connect to Qdrant, download models, ingest EPS data, or claim production retrieval behavior in T04.
- Do not alter the `request_context` authority or add DB-derived facts to query inputs.
- Do not weaken existing T01–T03 tests or contracts.

## Required domain contract

Implement the exact domain fields and invariants from the approved plan:

- `HybridVector`: dense dimension exactly `1024`; sparse indices sorted, unique, non-negative; sparse values finite and equal in length to indices.
- `EpsReference`: point ID, source record ID, Korean and translated text, canonical target language, EPS language code, source page, dataset revision, content hash, quality status, `source="EPS"`, and source URL.
- `RankedCandidate`, `PerQueryRanking`, `FusedCandidate`, `RerankedCandidate` with zero-based ranks and deterministic metadata.
- `RerankerSelectedContext | FusionSelectedContext` as a discriminated `SelectedContext` union. Reranker selection requires a float score; cross-query fallback requires `reranker_score=None`.
- `ExpectedIndexContract` and `VerifiedCollectionHandle` with exact dataset, encoder revision, index contract version, and verified positive point count.
- `RetrievalResult` with verified-or-`None` dataset version, query strategies, selected contexts, warnings, fallback flag, and degraded components.

Use the existing language code and request/query contracts. Vendor-specific types must not cross the port boundary.

## Required ports

Define synchronous protocols with these signatures:

```text
DenseSparseEncoder.encode_queries(texts: Sequence[str]) -> tuple[HybridVector, ...]
HybridSearchStore.search_many(queries, *, target_language, collection) -> tuple[PerQueryRanking, ...]
HybridSearchStore.verify_contract(*, expected: ExpectedIndexContract) -> VerifiedCollectionHandle
CandidateReranker.rerank(query: str, candidates: Sequence[FusedCandidate]) -> tuple[RerankedCandidate, ...]
StructuredGenerationPort.generate(*, operation, payload, response_model) -> DraftT
SemanticValidationPort.validate(*, component, request_context, target_language, candidate) -> SemanticValidationDecision
EpsRetriever.retrieve(*, queries, standard_korean_text, target_language) -> RetrievalResult
TraceSink.emit(event: TraceEvent) -> None
```

Apply the approved list/status invariants. `SemanticValidationDecision.unavailable=True` must imply `status="inconclusive"`. Add a no-op trace sink so later Tasks have a safe default.

## Deterministic RRF contract

- Defaults: `rrf_k=60`, `weights=(1.0, 1.0, 1.0)`, `candidate_limit=30`.
- Aggregate by `point_id` across every query ranking.
- Score: `weight / (rrf_k + zero_based_rank)`.
- Sort by `fusion_score DESC`, then `best_rank ASC`, then `point_id ASC`.
- Preserve reference payload without leaking vectors in public fused output.

## Required tests

Write the following tests before implementation and record the initial failures:

- dimension mismatch, sparse ordering/uniqueness/non-negative values, finite sparse values
- point-ID deduplication, use of all rankings, stable tie-break, empty rankings
- reference payload preservation without vectors
- valid reranker and fusion-fallback serialization
- rejection of both impossible score/source pairings
- deterministic fakes: success, typed failure, call capture, barrier/event, scripted sequence, and verified/mismatched/schema-invalid store outcomes

## Required verification commands

```bash
.venv/bin/python -m pytest tests/agents/language/test_fusion.py -q
RUFF_CACHE_DIR=/private/tmp/la-t04-ruff-cache .venv/bin/ruff check \
  app/agents/language/ports.py \
  app/agents/language/retrieval \
  tests/agents/language/fakes.py \
  tests/agents/language/test_fusion.py
git diff --check
```

The Builder must also run the repository's applicable regression tests and report any pre-existing baseline failures separately.

## Evidence required

- RED output before implementation
- implementation SHA and changed-file list
- focused and regression test commands with exit codes
- changed-area Ruff and `git diff --check` results
- exact scope audit and clean worktree result
- unrun/unverified list, including all external Qdrant/EPS/model behavior
- rollback safe point: `f13487f540fed74cd336be4aa9df5802aedf7a57`

## Stop conditions

- A retrieval-domain contract is ambiguous or conflicts with T02/T03.
- An allowed file outside this Packet must change.
- External services, model downloads, or production credentials are required.
- Existing unrelated dirty changes appear in the Task worktree.
- A test can pass only by weakening an existing contract.

On any stop condition, do not broaden scope. Report the exact conflict to the Control Tower.
