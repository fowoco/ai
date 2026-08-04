# T11 Parallel LangGraph Assembly Evidence Pack

```yaml
evidence_version: 1
wave: W3
task: T11
packet_version: 1
base_sha: 771ed97d42cf3891caaaee712c9b4ae15fc81ef3
packet_sha: 19af64409ce6a0cde74490de0d625355b9f9866c
implementation_sha: 1399e8e156cf0271b5c7d471fccdd2b5d6ab1c75
branch: task/la-graph-assembly
worktree: /Users/parktaejung/Desktop/workspace/ai-language-assistant-t11-graph-assembly
clean_worktree_at_implementation: true
```

## Claims

| ID | Claim | Evidence |
|---|---|---|
| T11-C01 | 상위 LangGraph는 Easy Korean 및 Native Translation 하위 그래프를 브랜치 간 엣지 연결 없이 병렬로 조립 및 실행한다. | `test_parallel_execution_without_inter_branch_dependency`, `app/agents/language/graph.py` |
| T11-C02 | 상위 State (`LanguageAssistantState`)는 하위 그래프의 독립 상태 키(`easy_result`, `translation_result`)를 불변 사실 변경 없이 병합한다. | `test_easy_failure_preserves_translation`, `test_both_fail_preserve_standard_korean` |
| T11-C03 | 파사드 객체 `LanguageAssistantGraph.invoke()` 및 `LanguageAssistantService`는 입력 Pydantic 모델 검증 및 출력 Pydantic 모델 검증을 보장한다. | `test_language_assistant_graph_happy_path`, `test_language_assistant_service_node_integration` |

## RED before implementation

구현 전 packet SHA(`19af64409ce6a0cde74490de0d625355b9f9866c`)에서 다음 focused 명령을 실행했다.

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest tests/agents/language/test_graph.py -q
```

- Exit code: `2`
- 결과: `ModuleNotFoundError: No module named 'app.agents.language.graph'`
- 의미: T11 graph 모듈이 작성되지 않아 예상대로 RED 발생.

## Implementation verification

모든 명령은 implementation SHA `1399e8e156cf0271b5c7d471fccdd2b5d6ab1c75`에서 실행했다.

### Focused test

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest tests/agents/language/test_graph.py -q
```

- Exit code: `0`
- 결과: `8 passed`

### Language regression

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest tests/agents/language/ -q
```

- Exit code: `0`
- 결과: `242 passed`

### Repository regression

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest -q
```

- Exit code: `0`
- 결과: `382 passed`

### Ruff

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/ruff check app/agents/language/graph.py app/agents/language/service.py app/agents/language/nodes.py app/agents/language/__init__.py app/agents/language/state.py app/agents/language/projection.py tests/agents/language/test_graph.py
```

- Exit code: `0`
- 결과: `All checks passed!`

### Diff and scope

```bash
git diff --check
git diff --name-status 19af64409ce6a0cde74490de0d625355b9f9866c..1399e8e156cf0271b5c7d471fccdd2b5d6ab1c75
```

- Exit code: `0`
- 변경 파일은 허용 파일 범위 7개 한정:

```text
M  app/agents/language/__init__.py
A  app/agents/language/graph.py
A  app/agents/language/nodes.py
M  app/agents/language/projection.py
A  app/agents/language/service.py
M  app/agents/language/state.py
A  tests/agents/language/test_graph.py
```

## Scope audit

```yaml
implementation_allowed_files_only: true
unexpected_implementation_files: []
vendor_imports_in_graph_assembly_domain: []
evidence_artifact: docs/language-assistant/engineering/execution/evidence/T11-EVIDENCE.md
```

## Unrun and unverified

- 단위 테스트 중 외부 실 LLM API 및 Qdrant 데이터베이스 통신은 수행하지 않았다 (fake retriever/generator/validator 사용).
- T12 HTTP API Endpoint 연결은 시작하지 않았다.

## Rollback

- Safe point: `19af64409ce6a0cde74490de0d625355b9f9866c`
