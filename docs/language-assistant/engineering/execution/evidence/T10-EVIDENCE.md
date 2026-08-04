# T10 Native-Translation Subgraph Evidence Pack

```yaml
evidence_version: 1
wave: W3
task: T10
packet_version: 1
base_sha: 7e491ffeae2679c53c0765c71a3e6aa3276f7f25
packet_sha: b6620bbff270a6dc6df48e8f57b9366f8939e4f3
implementation_sha: 5a518c220d07ed1c57343affd63083a3e31a1d1a
branch: task/la-native-translation-subgraph
worktree: /Users/parktaejung/Desktop/workspace/ai-language-assistant-t10-native-translation-subgraph
clean_worktree_at_implementation: true
```

## Claims

| ID | Claim | Evidence |
|---|---|---|
| T10-C01 | Native-Translation 하위 그래프는 가용 시 대상 언어 EPS 참조를 비신뢰 근거(untrusted reference)로 사용하고, 검색 실패/미매칭/장애 시 일반 LLM 번역으로 자동 fallback한다. | `test_translation_prompt_contains_only_top_five_eps_contexts`, `test_no_match_uses_general_llm_and_sets_fallback`, `test_qdrant_failure_uses_general_llm_and_sets_unavailable_warning` |
| T10-C02 | `request_context`에 의존하여 후보 번역을 검증하며, 생성/검증에 대한 제한적 수정 재시도를 수행하고, 하드 장애 발생 시 `text=None`, `status="failed"`, `validation=ComponentValidation(status="not_run", retry_count=0)`를 반환한다. | `test_translation_retry_exhaustion_returns_last_candidate`, `test_translation_no_candidate_returns_null_and_failed` |
| T10-C03 | 명시적이고 좁은 입출력 계약(`TranslationBranchInput`, `TranslationBranchOutput`, `TranslationResult`)을 사용하여 공유 파일(`state.py`, `nodes.py`, Parent Graph)을 수정하지 않고 동작한다. | `test_translation_prompt_excludes_parent_context`, `app/agents/language/translation.py` 내부 상태 격리 |

## RED before implementation

구현 전 packet SHA(`b6620bbff270a6dc6df48e8f57b9366f8939e4f3`)에서 다음 focused 명령을 실행했다.

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest tests/agents/language/test_translation.py -q
```

- Exit code: `2`
- 결과: `ModuleNotFoundError: No module named 'app.agents.language.translation'`
- 의미: T10 translation 모듈이 작성되지 않아 예상대로 RED 발생.

## Implementation verification

모든 명령은 implementation SHA `5a518c220d07ed1c57343affd63083a3e31a1d1a`에서 실행했다.

### Focused test

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest tests/agents/language/test_translation.py -q
```

- Exit code: `0`
- 결과: `14 passed`

### Language regression

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest tests/agents/language/ -q
```

- Exit code: `0`
- 결과: `234 passed`

### Repository regression

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest -q
```

- Exit code: `0`
- 결과: `374 passed`

### Ruff

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/ruff check app/agents/language/translation.py app/agents/language/retrieval/service.py tests/agents/language/test_translation.py
```

- Exit code: `0`
- 결과: `All checks passed!`

### Diff and scope

```bash
git diff --check
git diff --name-status b6620bbff270a6dc6df48e8f57b9366f8939e4f3..5a518c220d07ed1c57343affd63083a3e31a1d1a
```

- Exit code: `0`
- 변경 파일은 허용 파일 범위 3개 한정:

```text
M  app/agents/language/retrieval/service.py
A  app/agents/language/translation.py
A  tests/agents/language/test_translation.py
```

## Scope audit

```yaml
implementation_allowed_files_only: true
unexpected_implementation_files: []
vendor_imports_in_translation_domain: []
evidence_artifact: docs/language-assistant/engineering/execution/evidence/T10-EVIDENCE.md
```

## Unrun and unverified

- 단위 테스트 중 외부 실 LLM API 및 Qdrant 데이터베이스 통신은 수행하지 않았다 (fake retriever/generator/validator 사용).
- T11 Parent Graph 통합 조립은 시작하지 않았다.

## Rollback

- Safe point: `b6620bbff270a6dc6df48e8f57b9366f8939e4f3`
