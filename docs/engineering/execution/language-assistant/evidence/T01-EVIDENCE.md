# T01 Domain Contracts Evidence Pack

~~~yaml
evidence_version: 1
wave: W1
task: T01
packet_version: 1
base_sha: cd3fabbfbf6e996f3ef1d068804e04cc9f85e07a
packet_sha: 536dc6a36c66bdfe6346482748672b0882cb7c41
implementation_sha: 42f429cd67fbecaf5cff41eef22e2389f8d8ad60
evidence_sha: recorded in the Control Tower ledger after this docs-only commit
branch: task/la-t01-domain-contracts
worktree: /Users/parktaejung/Desktop/workspace/ai-language-assistant-t01-domain-contracts
clean_worktree: true
~~~

## Claims

| ID | Claim | Evidence |
|---|---|---|
| T01-C01 | Strict input accepts only worker_id, preferred_language, nationality_code, and request_context. | contract tests for structured input and rejected removed fields |
| T01-C02 | Request strings are NFC-normalized, trimmed, bounded, and dates require ISO format. | normalization, bound, and invalid-date tests |
| T01-C03 | Output model enforces success/warning/failed candidate and validation invariants. | 24 contract tests |
| T01-C04 | Parent projection copies only approved fields and does not mutate or depend on Parent extras. | 3 projection tests |
| T01-C05 | Input/output JSON schemas export deterministically and contain no removed contract fields. | two export runs, equal SHA-256 values, schema audit |

## Exact commands and results

### Required failing tests before implementation

~~~bash
.venv/bin/python -m pytest tests/agents/language/test_contracts.py -q
~~~

Exit code: 2.

Decisive result:

~~~text
ModuleNotFoundError: No module named 'app.agents.language.contracts'
~~~

~~~bash
.venv/bin/python -m pytest tests/agents/language/test_projection.py -q
~~~

Exit code: 2.

Decisive result:

~~~text
ModuleNotFoundError: No module named 'app.agents.language.projection'
~~~

### Focused tests after implementation

~~~bash
.venv/bin/python -m pytest tests/agents/language/test_contracts.py tests/agents/language/test_projection.py -q
~~~

Exit code: 0; 27 passed.

### Full regression

~~~bash
.venv/bin/python -m pytest -q
~~~

Exit code: 0; 88 passed.

Collection confirmation:

~~~bash
.venv/bin/python -m pytest --collect-only -q
~~~

Exit code: 0; 24 contract tests, 3 projection tests, 61 pre-existing tests.

### Ruff

~~~bash
.venv/bin/python -m ruff check app tests scripts/export_language_schemas.py
~~~

Exit code: 0.

Result:

~~~text
All checks passed!
~~~

### Schema export reproducibility

~~~bash
.venv/bin/python scripts/export_language_schemas.py
before_input=$(/sbin/sha256sum docs/contracts/language-assistant-input.schema.json)
before_output=$(/sbin/sha256sum docs/contracts/language-assistant-output.schema.json)
.venv/bin/python scripts/export_language_schemas.py
after_input=$(/sbin/sha256sum docs/contracts/language-assistant-input.schema.json)
after_output=$(/sbin/sha256sum docs/contracts/language-assistant-output.schema.json)
test "$before_input" = "$after_input"
test "$before_output" = "$after_output"
git diff --exit-code -- docs/contracts
~~~

Exit code: 0.

Stable schema SHA-256:

~~~text
de356f84e6be665e97aa15578827dba909e4dbc72407f9e638df7ff1a1ce49ac  docs/contracts/language-assistant-input.schema.json
6fc746446196a47bf594157d75cb45f3f60cc8633bf98b662a59ccf0eb9b326d  docs/contracts/language-assistant-output.schema.json
~~~

### Scope and cleanliness

~~~bash
git status --short --branch
git diff --check
git diff --name-only cd3fabbfbf6e996f3ef1d068804e04cc9f85e07a..HEAD
~~~

Result: clean worktree; implementation paths are limited to the sealed Packet scope plus the Packet record.

## Changed files

~~~text
app/agents/language/__init__.py
app/agents/language/contracts.py
app/agents/language/projection.py
app/agents/language/state.py
docs/contracts/language-assistant-input.schema.json
docs/contracts/language-assistant-output.schema.json
scripts/export_language_schemas.py
tests/agents/language/__init__.py
tests/agents/language/test_contracts.py
tests/agents/language/test_projection.py
~~~

Packet record is preserved at:

~~~text
docs/engineering/execution/language-assistant/tasks/T01-domain-contracts.md
~~~

## Unverified

- Independent Luna Verifier replay has not run.
- T01 has not been merged into feat/language-assistant.
- S1 Sol review and user Gate decision have not run.
- T02 onward has not started.
- HTTP, LangGraph runtime, provider, Qdrant, model, and production behavior remain unverified.
- External G1-G7 evidence remains open.

## Rollback

Safe point: cd3fabbfbf6e996f3ef1d068804e04cc9f85e07a.

No reset, clean, stash, rebase, or destructive rollback was run. Return Task branch to safe point only by explicit user-directed Git operation.
