# T14 Task Packet — Privacy-Safe Tracing, Prompt-Injection Boundaries, and Fault Isolation

```yaml
packet_version: 1
wave: W4
task: T14
title: Privacy-Safe Tracing, Prompt-Injection Boundaries, and Fault Isolation
status: sealed
```

## Claims

- Traces contain no raw PII, DB objects, Prompt text, Query strings, or response text; only allowlisted telemetry attributes are captured.
- User request inputs and EPS contexts are safely quoted in delimited JSON data blocks without prompt injection risks.
- All system component failures map to stable warning codes (`WarningCode` enum) with fault isolation across parallel branches.

## Git contract

```yaml
integration_branch: feat/language-assistant
base_sha: d77d0b83e404b9aa11fbff3b4aa73b5ebaa2221b
packet_sha: recorded in ledger after sealing
task_branch: task/la-privacy-resilience
worktree: /Users/parktaejung/Desktop/workspace/ai-language-assistant-t14-privacy-resilience
```

## Scope

### Allowed files

- `app/agents/language/observability.py`
- `tests/agents/language/test_observability.py`
- `app/agents/language/nodes.py`
- `app/agents/language/generation/openai_compatible.py`
- `app/agents/language/retrieval/service.py`
- `app/api/dependencies.py`
- `tests/agents/language/test_graph.py`

### Forbidden files and behavior

- Do not modify files outside the allowed list (including W5 evaluation files, control tower).
- Do not log raw PII, request text, or API keys in trace events or logs.
- Do not modify existing T01–T13 contracts or tests.

## Stop conditions

- Ambiguity in trace attribute allowlist or prompt injection sanitization.
- Files outside allowed list need modification.
