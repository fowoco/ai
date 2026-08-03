# T02 언어 정규화 Task Record

## Packet

~~~yaml
packet_version: 1
wave: W1
task: T02
title: 15개 언어 정규화와 namespace 충돌 방지
status: sealed
base_sha: bbba26e67fa392b0691f397df162ce07292c7932
task_branch: task/la-t02-language-normalization
worktree: /Users/parktaejung/Desktop/workspace/ai-language-assistant-t02-language-normalization
dependencies:
  - T01: 63e2262d81eea8cd414f2ca57c392d9e5eee0832
claims:
  - 15개 canonical language code가 정확히 하나의 EPS code로 매핑된다.
  - preferred language가 유효하면 nationality보다 우선한다.
  - preferred language가 없을 때만 nationality를 fallback으로 사용한다.
  - 둘 다 없으면 en으로 default하고 warning을 반환한다.
  - 명시적 invalid preferred language는 stable error code를 가진 domain error로 실패한다.
  - legacy alias는 명시적으로 정규화되고 warning을 반환한다.
  - fil/tet와 language/country tl namespace가 조용히 충돌하지 않는다.
allowed_files:
  - app/agents/language/codes.py
  - tests/agents/language/test_codes.py
  - docs/engineering/execution/language-assistant/tasks/T02-language-normalization.md
forbidden_files:
  - all HWPX files and hwp-editor/**
  - app/core/**
  - app/api/**
  - app/agents/language/contracts.py
  - all other app/agents/language files
  - docs/contracts/**
  - all other tests, scripts, and docs
required_failing_tests:
  - .venv/bin/python -m pytest tests/agents/language/test_codes.py -q
required_passing_commands:
  - .venv/bin/python scripts/export_language_schemas.py
  - .venv/bin/python -m pytest tests/agents/language/test_codes.py tests/agents/language/test_contracts.py -q
  - git diff --exit-code -- docs/contracts/language-assistant-input.schema.json docs/contracts/language-assistant-output.schema.json
  - .venv/bin/python -m ruff check app/agents/language/codes.py tests/agents/language/test_codes.py
stop_conditions:
  - Approved language or EPS mapping is ambiguous.
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
rollback_base_sha: bbba26e67fa392b0691f397df162ce07292c7932
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
