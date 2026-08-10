# T13 Task Packet — Runtime Settings, Model Preload, Qdrant Compose, and Recovery Runbook

```yaml
packet_version: 1
wave: W4
task: T13
title: Runtime Settings, Model Preload, Qdrant Compose, and Recovery Runbook
status: sealed
```

## Claims

- Qdrant service is internal-only and persistent; exact model revisions are preloaded into a volume and never downloaded dynamically on HTTP requests.
- Missing dependencies or model files yield typed runtime status without crashing existing document endpoints.
- Docker build uses `uv.lock` with isolated production/integration Qdrant volume configurations.

## Git contract

```yaml
integration_branch: feat/language-assistant
base_sha: 0431c33f81e6490fc6a49dbaf1e4414840d046cd
packet_sha: recorded in ledger after sealing
task_branch: task/la-runtime-qdrant
worktree: /Users/parktaejung/Desktop/workspace/ai-language-assistant-t13-runtime-qdrant
```

## Scope

### Allowed files

- `scripts/download_language_models.py`
- `compose.test.yml`
- `docs/language-assistant-operations.md`
- `app/agents/language/runtime.py`
- `tests/agents/language/test_runtime_config.py`
- `tests/agents/language/test_model_cache.py`
- `tests/integration/language/test_compose_config.py`
- `app/core/config.py`
- `app/api/dependencies.py`
- `app/main.py`
- `compose.yml`
- `Dockerfile`
- `.dockerignore`
- `README.md`
- `app/api/README.md`
- `tests/conftest.py`
- `tests/api/test_language_endpoint.py`
- `pyproject.toml`
- `uv.lock`

### Forbidden files and behavior

- Do not modify files outside the allowed list (including T14 privacy files, core graph logic, control tower).
- Do not download model weights or connect to external live Qdrant servers in unit tests.
- Do not modify existing T01–T12 contracts or tests.

## Stop conditions

- Ambiguity in runtime config or Qdrant volume isolation.
- Files outside allowed list need modification.
