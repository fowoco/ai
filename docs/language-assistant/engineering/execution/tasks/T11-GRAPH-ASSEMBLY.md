# T11 Task Packet — LangGraph Graph Assembly, Standalone Service, and Parent Adapter

```yaml
packet_version: 1
wave: W3
task: T11
title: Parallel LangGraph Assembly, Standalone Service, and Parent Adapter
status: sealed
```

## Claims

- LangGraph Parent Graph connects Easy Korean and Native Translation subgraphs in parallel without inter-branch edges.
- Shared Parent State (`LanguageAssistantState`) imports branch results without mutating state or adding reducers to immutable facts.
- Public facade `LanguageAssistantGraph.invoke()` accepts input models and returns validated `LanguageAssistantOutput`.

## Git contract

```yaml
integration_branch: feat/language-assistant
base_sha: 771ed97d42cf3891caaaee712c9b4ae15fc81ef3
packet_sha: recorded in ledger after sealing
task_branch: task/la-graph-assembly
worktree: /Users/parktaejung/Desktop/workspace/ai-language-assistant-t11-graph-assembly
```

## Scope

### Allowed files

- `app/agents/language/graph.py`
- `app/agents/language/service.py`
- `app/agents/language/nodes.py`
- `app/agents/language/__init__.py`
- `app/agents/language/state.py`
- `app/agents/language/projection.py`
- `tests/agents/language/test_graph.py`

### Forbidden files and behavior

- Do not modify files outside the allowed list (including T12 API files, router, control tower).
- Do not call live external LLM APIs or Qdrant in unit tests.
- Do not modify existing T01–T10 contracts or tests.

## Stop conditions

- Ambiguity in Parent Graph shape or state aggregation.
- Files outside allowed list need modification.
