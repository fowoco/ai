# T03 보호 사실·일반 한국어·Query Task Record

## Packet

~~~yaml
packet_version: 1
wave: W1
task: T03
title: 보호 사실, 결정적 일반 한국어, 세 개의 faithful Query
status: sealed
base_sha: 13d088a7924f837b3c7caf476f62153bee903f2b
task_branch: task/la-t03-facts-and-queries
worktree: /Users/parktaejung/Desktop/workspace/ai-language-assistant-t03-facts-and-queries
dependencies:
  - T01: 63e2262d81eea8cd414f2ca57c392d9e5eee0832
parallel_candidates:
  - T02: task/la-t02-language-normalization (not a dependency; not merged here)
claims:
  - ProtectedFacts는 request_context 구조 필드에서만 만들어지고 machine token의 source path를 보존한다.
  - 날짜, 시간, 숫자, 금액, 통화, 단위, URL, email, phone, 문서 식별자와 version을 결정적으로 보호한다.
  - 일반 한국어 formatter는 request facts만 deterministic하게 렌더링하고 순서와 ISO deadline을 보존한다.
  - formatter는 worker, company, DB context, 생성 text를 추가하지 않으며 invariant 위반을 programming error로 드러낸다.
  - 세 Query는 stable order와 서로 다른 kind를 가지며 네 request_context 필드와 보호값을 모두 보존한다.
  - LanguageAssistantState는 T3 소유의 protected facts, standard Korean, standard validation만 추가한다.
allowed_files:
  - app/agents/language/protected_facts.py
  - app/agents/language/formatting.py
  - app/agents/language/queries.py
  - app/agents/language/state.py
  - tests/agents/language/test_protected_facts.py
  - tests/agents/language/test_formatting.py
  - tests/agents/language/test_queries.py
  - docs/engineering/execution/language-assistant/tasks/T03-facts-and-queries.md
forbidden_files:
  - all HWPX files and hwp-editor/**
  - app/core/**
  - app/api/**
  - app/agents/language/contracts.py
  - app/agents/language/codes.py
  - app/agents/language/projection.py
  - all other app/agents/language files
  - docs/contracts/**
  - all other tests, scripts, and docs
required_failing_tests:
  - .venv/bin/python -m pytest tests/agents/language/test_protected_facts.py -q
  - .venv/bin/python -m pytest tests/agents/language/test_formatting.py -q
  - .venv/bin/python -m pytest tests/agents/language/test_queries.py -q
required_passing_commands:
  - .venv/bin/python -m pytest tests/agents/language/test_protected_facts.py tests/agents/language/test_formatting.py tests/agents/language/test_queries.py -q
  - .venv/bin/python -m pytest tests/agents/language/test_contracts.py tests/agents/language/test_projection.py tests/agents/language/test_protected_facts.py tests/agents/language/test_formatting.py tests/agents/language/test_queries.py -q
  - .venv/bin/python -m ruff check app/agents/language/protected_facts.py app/agents/language/formatting.py app/agents/language/queries.py app/agents/language/state.py tests/agents/language/test_protected_facts.py tests/agents/language/test_formatting.py tests/agents/language/test_queries.py
stop_conditions:
  - Protected fact source authority or formatter contract is ambiguous.
  - A required change falls outside allowed_files.
  - T2 code or another unrelated user change must be modified.
  - External service, model download, or destructive action becomes necessary.
~~~

## Builder evidence

~~~yaml
packet_sha: recorded in Control Tower ledger after this docs-only commit
implementation_sha: null
evidence_sha: null
changed_files: []
commands: []
deviations: []
unrun: []
unverified: []
rollback_base_sha: 13d088a7924f837b3c7caf476f62153bee903f2b
~~~

## Luna verification

~~~yaml
verdict: null
verified_evidence_sha: null
claim_results: []
reproduced_commands: []
counterexamples: []
unverified: []
~~~

## Integration

~~~yaml
merge_sha: null
integrated_sha: null
merge_method: --no-ff
~~~
