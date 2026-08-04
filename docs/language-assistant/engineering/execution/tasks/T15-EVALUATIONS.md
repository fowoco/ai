# T15 Task Packet — Retrieval and Generation Evaluation Harnesses and Release Calibration

```yaml
packet_version: 1
wave: W5
task: T15
title: Build Retrieval and Generation Evaluation Harnesses and Calibrate Release Gates
status: sealed
```

## Claims

- Evaluation harness schemas, metric formulas, and deterministic CLI report generation run cleanly in `HARNESS_ONLY` mode without live external LLMs or Qdrant connections.
- Offline synthetic test fixtures cover 15 target languages and validate deterministic date, number, cardinality, and warning code invariants.
- Evaluators output structured Markdown baseline reports (`docs/evaluations/language-assistant-baseline.md`) with explicit gate status (`status: NOT_RUN` for unclosed external gates).

## Git contract

```yaml
integration_branch: feat/language-assistant
base_sha: 79fe01a2f6460f7e4f20ec6afdd9c231737be26b
packet_sha: recorded in ledger after sealing
task_branch: task/la-evaluations
worktree: /Users/parktaejung/Desktop/workspace/ai-language-assistant-t15-evaluations
```

## Scope

### Allowed files

- `scripts/evaluate_language_retrieval.py`
- `scripts/evaluate_language_generation.py`
- `tests/agents/language/test_evaluation_harness.py`
- `tests/fixtures/language/request_context_cases.json`
- `tests/fixtures/language/retrieval_cases.jsonl`
- `tests/fixtures/language/generation_cases.jsonl`
- `docs/evaluations/language-assistant-baseline.md`
- `tests/integration/language/test_model_offline_smoke.py`
- `pyproject.toml`

### Forbidden files and behavior

- Do not modify files outside the allowed list (including T16 ledger files, control tower).
- Do not make external live LLM/Qdrant calls during `--validate-only` or unit test runs.
- Do not modify existing T01–T14 contracts or tests.

## Stop conditions

- Ambiguity in evaluation metrics or dataset schemas.
- Files outside allowed list need modification.
