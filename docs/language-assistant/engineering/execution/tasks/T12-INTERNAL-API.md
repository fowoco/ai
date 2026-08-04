# T12 Task Packet — Internal HTTP Contract and Router Integration

```yaml
packet_version: 1
wave: W3
task: T12
title: Internal HTTP Contract, Route Integration, and Backend Fixtures
status: sealed
```

## Claims

- Internal HTTP route `POST /internal/v1/language-assistant` projects allowed fields and ignores extra parent fields.
- Dependency overrides allow endpoint testing using fake graph service without live LLMs or Qdrant connections.
- App startup and OpenAPI schema generation run cleanly without downloading model weights.

## Git contract

```yaml
integration_branch: feat/language-assistant
base_sha: 020bfce5288fbaf8c8ce7565576a08416fb9a5d3
packet_sha: recorded in ledger after sealing
task_branch: task/la-internal-api
worktree: /Users/parktaejung/Desktop/workspace/ai-language-assistant-t12-internal-api
```

## Scope

### Allowed files

- `app/api/schemas/language.py`
- `app/api/routes/language.py`
- `docs/contracts/language-assistant-http-request.schema.json`
- `tests/api/test_language_endpoint.py`
- `tests/fixtures/language/backend-language-request.json`
- `tests/fixtures/language/backend-language-response.json`
- `app/api/dependencies.py`
- `app/api/openapi.py`
- `app/main.py`
- `scripts/export_language_schemas.py`

### Forbidden files and behavior

- Do not modify files outside the allowed list (including W4/W5 files, core graph files, control tower).
- Do not call live external LLM APIs or Qdrant in unit/endpoint tests.
- Do not modify existing T01–T11 contracts or tests.

## Stop conditions

- Ambiguity in endpoint router schema or dependency injection.
- Files outside allowed list need modification.
