# T10 Task Packet — Native-Translation Subgraph

```yaml
packet_version: 1
wave: W3
task: T10
title: Native-Translation Subgraph and EPS Fallback Policy
status: sealed
```

## Claims

- Native-Translation subgraph uses target-language EPS references when available as untrusted evidence, and falls back to general LLM translation on retrieval failure/no-match.
- Validates candidate translations against `request_context`, retries bounded corrections only for translation/validation, and retains last candidate or returns null text on hard failure.
- Subgraph uses narrow input/output contracts (`TranslationBranchInput`, `TranslationBranchOutput`) without modifying shared Parent Graph or state files.

## Git contract

```yaml
integration_branch: feat/language-assistant
base_sha: 7e491ffeae2679c53c0765c71a3e6aa3276f7f25
packet_sha: recorded in ledger after sealing
task_branch: task/la-native-translation-subgraph
worktree: /Users/parktaejung/Desktop/workspace/ai-language-assistant-t10-native-translation-subgraph
```

## Scope

### Allowed files

- `app/agents/language/translation.py`
- `app/agents/language/retrieval/service.py`
- `tests/agents/language/test_translation.py`

### Forbidden files and behavior

- Do not modify shared files: `app/agents/language/state.py`, `app/agents/language/nodes.py`, Parent Graph files, or T11/T12 files.
- Do not call live external LLM APIs or Qdrant in unit tests.
- Do not modify existing T01–T09 contracts or tests.

## Stop conditions

- Ambiguity in Translation subgraph routing or retrieval fallback policy.
- Files outside allowed list need modification.
