# T01 Domain Contracts Task Record

## Packet

~~~yaml
packet_version: 1
wave: W1
task: T01
title: Domain contracts, child state, projection, and JSON schemas
status: sealed
base_sha: cd3fabbfbf6e996f3ef1d068804e04cc9f85e07a
task_branch: task/la-t01-domain-contracts
worktree: /Users/parktaejung/Desktop/workspace/ai-language-assistant-t01-domain-contracts
dependencies:
  - T0: cd3fabbfbf6e996f3ef1d068804e04cc9f85e07a
claims:
  - Strict graph input accepts exactly the four approved top-level fields.
  - Request context fields are mandatory, normalized, bounded, and extra-forbidden.
  - Parent projection ignores unrelated context and does not mutate its input.
  - Output contracts represent success, warning, failed translation, validation details, and retrieval degradation.
allowed_files:
  - app/agents/language/__init__.py
  - app/agents/language/contracts.py
  - app/agents/language/state.py
  - app/agents/language/projection.py
  - scripts/export_language_schemas.py
  - docs/contracts/language-assistant-input.schema.json
  - docs/contracts/language-assistant-output.schema.json
  - tests/agents/language/__init__.py
  - tests/agents/language/test_contracts.py
  - tests/agents/language/test_projection.py
  - docs/engineering/execution/language-assistant/tasks/T01-domain-contracts.md
forbidden_files:
  - all HWPX files and hwp-editor/**
  - app/core/**
  - app/api/**
  - pyproject.toml
  - all other app/agents/language files
  - all other tests, scripts, and docs
required_failing_tests:
  - .venv/bin/python -m pytest tests/agents/language/test_contracts.py -q
  - .venv/bin/python -m pytest tests/agents/language/test_projection.py -q
required_passing_commands:
  - .venv/bin/python scripts/export_language_schemas.py
  - .venv/bin/python -m pytest tests/agents/language/test_contracts.py tests/agents/language/test_projection.py -q
  - .venv/bin/python -m ruff check app/agents/language scripts/export_language_schemas.py tests/agents/language
stop_conditions:
  - Approved input or output contract is ambiguous.
  - A required change falls outside allowed_files.
  - Unrelated user changes appear in this Task worktree.
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
rollback_base_sha: cd3fabbfbf6e996f3ef1d068804e04cc9f85e07a
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
