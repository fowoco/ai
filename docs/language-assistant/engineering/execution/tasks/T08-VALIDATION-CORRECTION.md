# T08 Task Packet — Deterministic and Semantic Validation With Bounded Correction

```yaml
packet_version: 1
wave: W3
task: T08
title: Deterministic and Semantic Validation With Bounded Correction
status: sealed
```

## Claims

- Deterministic validator checks machine-checkable facts (dates, amounts, machine tokens, cardinality) against `request_context`.
- Semantic validator checks equivalence, modality, and entity preservation; unavailable status yields `inconclusive`.
- Bounded correction caps retries at max 2 per branch and respects `LanguageExecutionPolicy` time budget.

## Git contract

```yaml
integration_branch: feat/language-assistant
base_sha: e732df0c7c34d3efb0790ce0e556488d575c3efc
packet_sha: recorded in ledger after sealing
task_branch: task/la-generation-adapter
worktree: /Users/parktaejung/Desktop/workspace/ai-language-assistant-t08-generation-adapter
```

## Scope

### Allowed files

- `app/agents/language/validation.py`
- `app/agents/language/contracts.py`
- `app/agents/language/generation/models.py`
- `tests/agents/language/test_validation.py`

### Forbidden files and behavior

- Do not modify files outside the allowed list (including T09-T12 files, nodes, graph, API, control tower).
- Do not call live external LLM APIs or Qdrant in unit tests.
- Do not modify existing T01–T07 contracts or tests.

## Stop conditions

- Ambiguity in validation check IDs or correction budget policy.
- Files outside allowed list need modification.
