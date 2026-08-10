# T09 Easy-Korean Subgraph Evidence Pack

```yaml
evidence_version: 1
wave: W3
task: T09
packet_version: 1
base_sha: 9500bed00cecd083b7ffb5e28a5cfca51e39a3f2
packet_sha: a9a3436a38cd10cb57c95a9e7d32393ac55c540b
implementation_sha: c4692f46fa6d2eca22c31b50304492d6aca051ff
branch: task/la-easy-korean-subgraph
worktree: /Users/parktaejung/Desktop/workspace/ai-language-assistant-t09-easy-korean-subgraph
clean_worktree_at_implementation: true
```

## Claims

| ID | Claim | Evidence |
|---|---|---|
| T09-C01 | 쉬운 한국어 순환 하위 그래프(Easy-Korean Subgraph)는 선택된 Context Pack을 사용하고, 필드별 재작성 텍스트를 렌더링하며, 미승인/비가용 Context Pack 시 LLM 호출 없이 바로 표준 한국어(Standard Korean) 텍스트로 fallback한다. | `test_easy_prompt_uses_request_context_standard_text_and_context_pack_only`, `test_unapproved_context_pack_skips_provider_and_falls_back_to_standard` |
| T09-C02 | 하위 그래프는 명시적이고 좁은 입출력 계약(`EasyBranchInput`, `EasyBranchOutput`, `EasyKoreanResult`)을 사용하며, 공유 파일(`state.py`, `nodes.py`, Parent Graph)을 수정하지 않는다. | `test_easy_prompt_excludes_parent_db_context`, `app/agents/language/easy_korean.py` 내부 상태 격리 |
| T09-C03 | 생성 실패 시 표준 한국어 텍스트 자동 fallback 및 `EASY_KOREAN_GENERATION_FAILED`, `STANDARD_KOREAN_FALLBACK` 경고를 발행한다. | `test_easy_hard_failure_falls_back_to_standard_korean`, `test_easy_retry_exhaustion_returns_last_candidate` |

## RED before implementation

구현 전 packet SHA(`a9a3436a38cd10cb57c95a9e7d32393ac55c540b`)에서 다음 focused 명령을 실행했다.

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest tests/agents/language/test_easy_korean.py -q
```

- Exit code: `2`
- 결과: `ModuleNotFoundError: No module named 'app.agents.language.easy_korean'`
- 의미: T09 easy_korean 모듈이 작성되지 않아 예상대로 RED 발생.

## Implementation verification

모든 명령은 implementation SHA `c4692f46fa6d2eca22c31b50304492d6aca051ff`에서 실행했다.

### Focused test

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest tests/agents/language/test_easy_korean.py -q
```

- Exit code: `0`
- 결과: `12 passed`

### Language regression

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest tests/agents/language/ -q
```

- Exit code: `0`
- 결과: `218 passed`

### Repository regression

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest -q
```

- Exit code: `0`
- 결과: `360 passed`

### Ruff

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/ruff check app/agents/language/easy_korean.py tests/agents/language/test_easy_korean.py
```

- Exit code: `0`
- 결과: `All checks passed!`

### Diff and scope

```bash
git diff --check
git diff --name-status a9a3436a38cd10cb57c95a9e7d32393ac55c540b..c4692f46fa6d2eca22c31b50304492d6aca051ff
```

- Exit code: `0`
- 변경 파일은 허용 파일 범위 2개 한정:

```text
A  app/agents/language/easy_korean.py
A  tests/agents/language/test_easy_korean.py
```

## Scope audit

```yaml
implementation_allowed_files_only: true
unexpected_implementation_files: []
vendor_imports_in_easy_korean_domain: []
evidence_artifact: docs/language-assistant/engineering/execution/evidence/T09-EVIDENCE.md
```

## Unrun and unverified

- 단위 테스트 중 외부 실 LLM API 및 Qdrant 데이터베이스 통신은 수행하지 않았다 (fake generator/validator 사용).
- T10 Translation Subgraph 및 T11 Parent Graph 조립은 시작하지 않았다.

## Rollback

- Safe point: `a9a3436a38cd10cb57c95a9e7d32393ac55c540b`
