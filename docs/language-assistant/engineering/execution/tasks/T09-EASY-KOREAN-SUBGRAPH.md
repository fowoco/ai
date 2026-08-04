# T09 Task Packet — Easy-Korean Subgraph

```yaml
packet_version: 1
wave: W3
task: T09
title: Easy-Korean Subgraph
status: sealed
```

## Claims

- Easy Korean subgraph uses selected Context Pack, returns field-wise rewrite, preserves request facts, retries only itself up to bounded limit, and falls back to Standard Korean on hard failure.
- Subgraph uses narrow input/output contracts (`EasyBranchInput`, `EasyBranchOutput`) without modifying shared Parent Graph or state files.

## Git contract

```yaml
integration_branch: feat/language-assistant
base_sha: 9500bed00cecd083b7ffb5e28a5cfca51e39a3f2
packet_sha: recorded in ledger after sealing
task_branch: task/la-easy-korean-subgraph
worktree: /Users/parktaejung/Desktop/workspace/ai-language-assistant-t09-easy-korean-subgraph
```

## Scope

### Allowed files

- `app/agents/language/easy_korean.py`
- `tests/agents/language/test_easy_korean.py`

### Forbidden files and behavior

- Do not modify shared files: `app/agents/language/state.py`, `app/agents/language/nodes.py`, Parent Graph files, or T10/T11/T12 files.
- Do not call live external LLM APIs or Qdrant in unit tests.
- Do not modify existing T01–T08 contracts or tests.

## Stop conditions

- Ambiguity in Easy Korean subgraph routing or fallback policy.
- Files outside allowed list need modification.
