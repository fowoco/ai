# T02 언어 정규화 Evidence Pack

~~~yaml
evidence_version: 1
wave: W1
task: T02
packet_version: 1
base_sha: bbba26e67fa392b0691f397df162ce07292c7932
packet_sha: e41f66dbee21d6c9bb63d685882b1645de7a730b
implementation_sha: 5acaecb961ffbcaa56db80f21fa4571061f6c158
evidence_sha: recorded in the Control Tower ledger after this docs-only commit
branch: task/la-t02-language-normalization
worktree: /Users/parktaejung/Desktop/workspace/ai-language-assistant-t02-language-normalization
clean_worktree: true
~~~

## Claims

| ID | Claim | Evidence |
|---|---|---|
| T02-C01 | 15개 canonical language code가 정확히 하나의 EPS code로 매핑된다. | 15개 parameterized mapping tests |
| T02-C02 | 지원 nationality fallback이 별도 table로 동작한다. | 14개 nationality mapping tests |
| T02-C03 | 유효한 preferred language가 nationality보다 우선하고, 없을 때만 nationality를 사용한다. | precedence와 nationality resolution tests |
| T02-C04 | preferred와 nationality가 모두 없으면 en과 typed warning을 반환한다. | default resolution test |
| T02-C05 | 명시적 invalid preferred language는 rejected value를 포함하지 않는 stable domain error로 실패한다. | invalid preference test |
| T02-C06 | legacy alias는 명시적으로 정규화되고 warning을 반환한다. | legacy alias와 `tl → tet` tests |
| T02-C07 | `fil`/`tet`와 country `TL` namespace가 조용히 충돌하지 않는다. | EPS code와 country namespace tests |

## Exact commands and results

### Required failing test before implementation

~~~bash
.venv/bin/python -m pytest tests/agents/language/test_codes.py -q
~~~

Exit code: `2`.

Decisive result:

~~~text
ModuleNotFoundError: No module named 'app.agents.language.codes'
~~~

### T2 focused tests after implementation

~~~bash
.venv/bin/python -m pytest tests/agents/language/test_codes.py -q
~~~

Exit code: `0`; 38 tests passed. Pytest emitted one non-failing cache write warning because the isolated worktree cannot write `.pytest_cache`.

~~~bash
.venv/bin/python -m pytest tests/agents/language/test_codes.py tests/agents/language/test_contracts.py -q
~~~

Exit code: `0`; 62 tests passed. The same non-failing pytest cache warning was emitted.

### Full regression

~~~bash
.venv/bin/python -m pytest -q
~~~

Exit code: `0`.

Diagnostic summary:

~~~bash
.venv/bin/python -m pytest -o addopts='' -ra
~~~

Exit code: `0`; 148 passed, 1 non-failing pytest cache warning.

### Ruff

~~~bash
.venv/bin/python -m ruff check app/agents/language/codes.py tests/agents/language/test_codes.py
~~~

The exact command returned exit code `2` because the sandbox could not create `.ruff_cache` in the isolated worktree.

The same checks with a disposable cache path passed:

~~~bash
RUFF_CACHE_DIR=/private/tmp/la-t02-ruff-cache .venv/bin/python -m ruff check app/agents/language/codes.py tests/agents/language/test_codes.py
RUFF_CACHE_DIR=/private/tmp/la-t02-ruff-cache .venv/bin/python -m ruff check app tests scripts/export_language_schemas.py
~~~

Both returned exit code `0` and `All checks passed!`.

### Schema export reproducibility

The plan-required exporter was run twice at `implementation_sha`:

~~~bash
.venv/bin/python scripts/export_language_schemas.py
before_input=$(/sbin/sha256sum docs/contracts/language-assistant-input.schema.json)
before_output=$(/sbin/sha256sum docs/contracts/language-assistant-output.schema.json)
.venv/bin/python scripts/export_language_schemas.py
after_input=$(/sbin/sha256sum docs/contracts/language-assistant-input.schema.json)
after_output=$(/sbin/sha256sum docs/contracts/language-assistant-output.schema.json)
test "$before_input" = "$after_input"
test "$before_output" = "$after_output"
git diff --exit-code -- docs/contracts/language-assistant-input.schema.json docs/contracts/language-assistant-output.schema.json
~~~

Exit code: `0`.

Stable SHA-256:

~~~text
de356f84e6be665e97aa15578827dba909e4dbc72407f9e638df7ff1a1ce49ac  docs/contracts/language-assistant-input.schema.json
6fc746446196a47bf594157d75cb45f3f60cc8633bf98b662a59ccf0eb9b326d  docs/contracts/language-assistant-output.schema.json
~~~

### Scope and cleanliness

~~~bash
git status --short --branch
git diff --check
git diff --name-only bbba26e67fa392b0691f397df162ce07292c7932..HEAD
~~~

Result: clean Task worktree. Changed implementation paths are limited to the sealed Packet's two code/test files; the Packet record is preserved and schema snapshots are unchanged.

## Changed implementation files

~~~text
app/agents/language/codes.py
tests/agents/language/test_codes.py
~~~

## Unverified

- Independent Luna Verifier replay has not run.
- T02 has not been merged into `feat/language-assistant`.
- S1 Sol review and user Gate decision have not run.
- T03 and all later Tasks have not started.
- HTTP, LangGraph runtime, provider, Qdrant, model, and production behavior remain unverified.
- External G1-G7 evidence remains open.

## Rollback

Safe point: `bbba26e67fa392b0691f397df162ce07292c7932`.

No reset, clean, stash, rebase, amend, cherry-pick, squash, or destructive rollback was run. Return to the safe point only by explicit user-directed Git operation.
