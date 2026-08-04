# T07 Task Packet — Generation Domain Contracts and Resources

```yaml
packet_version: 1
wave: W3
task: T07
title: Structured Generation Port, Versioned Prompts, and Easy-Korean Context Pack
status: sealed
```

## Claims

- Generation interface is strictly behind `StructuredGenerator` Protocol using Pydantic drafts.
- System prompts and Easy Korean rules are versioned package resources with SHA-256 integrity checks.
- HTTP generation adapter uses `httpx.MockTransport` in unit tests without calling live external LLM endpoints.

## Git contract

```yaml
integration_branch: feat/language-assistant
base_sha: 305125d213cf856931af63297d2385c7ed74f56e
packet_sha: recorded in ledger after sealing
task_branch: task/la-generation-resources
worktree: /Users/parktaejung/Desktop/workspace/ai-language-assistant-t07-generation-resources
```

## Scope

### Allowed files

- `app/agents/language/generation/__init__.py`
- `app/agents/language/generation/models.py`
- `app/agents/language/generation/openai_compatible.py`
- `app/agents/language/context_pack.py`
- `app/agents/language/resources/__init__.py`
- `app/agents/language/resources/prompts/__init__.py`
- `app/agents/language/resources/easy_korean_rules.v1.json`
- `app/agents/language/resources/easy_korean_rules.v1.sha256`
- `app/agents/language/resources/prompts/easy_korean.v1.md`
- `app/agents/language/resources/prompts/translation.v1.md`
- `app/agents/language/resources/prompts/semantic_validation.v1.md`
- `app/agents/language/resources/prompts/correction.v1.md`
- `tests/agents/language/test_generation_port.py`
- `tests/agents/language/test_context_pack.py`
- `pyproject.toml`

### Forbidden files and behavior

- Do not modify files outside the allowed list (including T08-T12 files, graph, API routes, or control tower files).
- Do not call live external LLM APIs (OpenAI, Anthropic, etc.) in unit tests.
- Do not modify existing T01–T06 contracts or tests.

## Stop conditions

- Ambiguity in generation draft models or versioned prompt contracts.
- Files outside allowed list need modification.
