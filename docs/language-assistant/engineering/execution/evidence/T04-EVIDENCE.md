# T04 Retrieval Domain Evidence Pack

~~~yaml
evidence_version: 1
wave: W2
task: T04
packet_version: 1
base_sha: f13487f540fed74cd336be4aa9df5802aedf7a57
packet_sha: 2b76b8979efab7cddbe1e6d82f76227a46c2e2ea
implementation_sha: a68e05f0d94e0f625434e0b932e7e339cd8f616a
branch: task/la-t04-retrieval-domain
worktree: /Users/parktaejung/Desktop/workspace/ai-language-assistant-t04-retrieval-domain
clean_worktree_at_implementation: true
~~~

## Claims

| ID | Claim | Evidence |
|---|---|---|
| T04-C01 | Retrieval domain 모델이 vector, EPS reference, ranking, fusion, index provenance, selected-context 불변조건을 검증한다. | `tests/agents/language/test_fusion.py`의 dimension/sparse, serialization, impossible pairing 테스트와 Pydantic 모델 |
| T04-C02 | Cross-query RRF가 모든 query ranking을 사용하고 point ID를 deduplicate하며 `fusion_score DESC → best_rank ASC → point_id ASC`로 결정적으로 정렬한다. | `test_rrf_deduplicates_by_point_id`, `test_rrf_uses_all_query_rankings`, `test_rrf_stable_tie_break`, `test_empty_rankings_return_empty_candidates` |
| T04-C03 | Retrieval port가 동기 domain 타입만 노출하고 vendor SDK를 import하지 않는다. | `app/agents/language/ports.py` Protocol signatures, changed-area Ruff, vendor import scope audit |
| T04-C04 | 이후 Graph/retry 테스트가 사용할 deterministic fake가 success, typed failure, call capture, barrier/event, scripted sequence, contract outcome, verified physical handle을 지원한다. | `tests/agents/language/fakes.py` 및 fake capability 테스트 |

## RED before implementation

구현 전 packet SHA에서 다음 focused 명령을 실행했다.

~~~bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest tests/agents/language/test_fusion.py -q
~~~

- Exit code: `2`
- 결과: `ModuleNotFoundError: No module named 'app.agents.language.retrieval'`
- 의미: T04 retrieval domain package가 아직 존재하지 않아 발생한 feature-missing RED다.

Task worktree에는 local `.venv`가 없어 Packet이 지정한 중앙 환경을 사용했다.

## Implementation verification

모든 명령은 implementation SHA `a68e05f0d94e0f625434e0b932e7e339cd8f616a`에서 새 프로세스로 실행했다.

### Focused test

~~~bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest tests/agents/language/test_fusion.py -q
~~~

- Exit code: `0`
- 결과: `23 passed`
- 비실패 경고: LangGraph pending-deprecation 및 isolated worktree pytest cache write warning

### Language regression

~~~bash
PYTEST_ADDOPTS='' /Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest -o addopts='' --disable-warnings -ra tests/agents/language
~~~

- Exit code: `0`
- 결과: `125 passed`

### Repository regression

~~~bash
PYTEST_ADDOPTS='' /Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest -o addopts='' --disable-warnings -q
~~~

- Exit code: `0`
- 결과: `263 passed, 1 skipped`
- 출력에 3개 warning이 있었으며 test failure는 아니었다.

### Ruff

~~~bash
RUFF_CACHE_DIR=/private/tmp/la-t04-ruff-cache /Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/ruff check \
  app/agents/language/ports.py \
  app/agents/language/retrieval \
  tests/agents/language/fakes.py \
  tests/agents/language/test_fusion.py
~~~

- Exit code: `0`
- 결과: `All checks passed!`

### Diff and scope

~~~bash
git diff --check
git diff --check 2b76b8979efab7cddbe1e6d82f76227a46c2e2ea..a68e05f0d94e0f625434e0b932e7e339cd8f616a
git diff --name-status 2b76b8979efab7cddbe1e6d82f76227a46c2e2ea..a68e05f0d94e0f625434e0b932e7e339cd8f616a
~~~

- 두 `git diff --check` 명령: exit code `0`
- implementation 변경은 Packet 허용 파일 6개에 한정되었다.

~~~text
A  app/agents/language/ports.py
A  app/agents/language/retrieval/__init__.py
A  app/agents/language/retrieval/fusion.py
A  app/agents/language/retrieval/models.py
A  tests/agents/language/fakes.py
A  tests/agents/language/test_fusion.py
~~~

## Changed files

- `app/agents/language/ports.py`
- `app/agents/language/retrieval/__init__.py`
- `app/agents/language/retrieval/models.py`
- `app/agents/language/retrieval/fusion.py`
- `tests/agents/language/fakes.py`
- `tests/agents/language/test_fusion.py`

## Scope audit

~~~yaml
implementation_allowed_files_only: true
unexpected_implementation_files: []
vendor_imports_in_retrieval_domain: []
evidence_artifact: docs/language-assistant/engineering/execution/evidence/T04-EVIDENCE.md
~~~

Evidence Pack 자체는 implementation SHA 확정 후 별도 docs-only commit으로 추가한다. Control Tower ledger와 T04 Packet은 수정하지 않았다.

## Unrun and unverified

- 독립 Luna Verifier의 별도 세션 재현 verdict는 아직 없다.
- 실제 Qdrant Server/collection/alias/schema와의 연결은 실행하지 않았다.
- EPS ingest, index 생성, point payload 검증은 실행하지 않았다.
- FlagEmbedding/BGE-M3 encoder와 reranker 모델 다운로드·로드·추론은 실행하지 않았다.
- 외부 LLM/provider, API, Runtime, LangGraph Graph 조립은 실행하지 않았다.
- retrieval 품질, latency, threshold, production release readiness는 측정하지 않았다.
- T05 EPS cleaning/index plan과 T06 hybrid retrieval adapter는 시작하지 않았다.
- S2 Sol Gate 및 외부 G1–G7 증거는 이 Task 범위에서 닫지 않았다.

## Rollback

- Safe point: `f13487f540fed74cd336be4aa9df5802aedf7a57`
- 구현 커밋은 packet SHA 위에만 추가되었고, Packet·ledger·기존 T01–T03 파일은 수정하지 않았다.
- 복구가 필요하면 현재 branch와 commit graph를 보존한 채 safe point를 Control Tower의 승인된 Git 절차로 선택한다. 이 작업에서는 reset, clean, stash, rebase, amend, push를 실행하지 않았다.
