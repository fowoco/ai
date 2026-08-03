# T3 Evidence Pack — 보호 사실과 Query

## 식별 정보

- task branch: `task/la-t03-facts-and-queries`
- base SHA: `13d088a7924f837b3c7caf476f62153bee903f2b`
- Packet SHA: `6ac7477701a01b02dcbd0cfe0320dd92bce7f8e7`
- implementation SHA: `c18490c52830627ef8d126e84689f74e01c48a54`
- T3 scope: 보호 사실 추출, 결정적 표준 한국어 포맷, 세 가지 검색 Query, T3 State 키와 경계 테스트
- 통합 상태: `feat/language-assistant`에 아직 병합하지 않음

## 변경 파일

- `app/agents/language/protected_facts.py`
- `app/agents/language/formatting.py`
- `app/agents/language/queries.py`
- `app/agents/language/state.py`
- `tests/agents/language/test_protected_facts.py`
- `tests/agents/language/test_formatting.py`
- `tests/agents/language/test_queries.py`

Packet에서 금지한 `contracts.py`, `codes.py`, `projection.py`, HWPX 영역과 외부 DB/LLM 연동은 변경하지 않았다.

## RED 기준선

구현 전 각 T3 focused test를 실행했고, 모두 `exit 2`와 import 경계 실패를 확인했다.

```text
.venv/bin/python -m pytest tests/agents/language/test_protected_facts.py -q
exit 2 — ModuleNotFoundError: app.agents.language.protected_facts

.venv/bin/python -m pytest tests/agents/language/test_formatting.py -q
exit 2 — ModuleNotFoundError: app.agents.language.formatting

.venv/bin/python -m pytest tests/agents/language/test_queries.py -q
exit 2 — ModuleNotFoundError: app.agents.language.protected_facts
```

## 구현 후 검증

모든 명령은 implementation SHA `c18490c52830627ef8d126e84689f74e01c48a54`에서 실행했다.

### T3 focused test

```text
PYTEST_ADDOPTS='' .venv/bin/python -m pytest tests/agents/language/test_protected_facts.py tests/agents/language/test_formatting.py tests/agents/language/test_queries.py -q
exit 0 — 22 passed
```

검증한 경계:

- 요청 컨텍스트 네 필드 복사와 NFC 정규화
- 날짜·시간·숫자·금액·통화·단위·URL·이메일·전화번호·문서 식별자·버전 보존
- 동일 표면값의 source path 분리
- 표준 포맷의 결정성, 항목 순서, ISO deadline, 제출 방법 중복 방지
- 프롬프트 주입 문장을 데이터로 취급하고 worker/company/DB 사실을 추가하지 않음
- Query 3개, 고정 순서, 고유 kind, 모든 요청 값과 보호 토큰 보존
- T3 State 키(`protected_facts`, `standard_korean_text`, `standard_validation`)

### 전체 test

```text
PYTEST_ADDOPTS='' .venv/bin/python -m pytest -o addopts='' --disable-warnings
exit 0 — 132 passed, 1 warning in 1.04s
```

경고는 sandbox가 worktree 내부 `.pytest_cache`를 생성하지 못해 발생한 `PytestCacheWarning`이며 테스트 실패가 아니다.

### T3 변경 파일 Ruff

```text
RUFF_CACHE_DIR=/private/tmp/la-t03-ruff-cache .venv/bin/ruff check app/agents/language/protected_facts.py app/agents/language/formatting.py app/agents/language/queries.py app/agents/language/state.py tests/agents/language/test_protected_facts.py tests/agents/language/test_formatting.py tests/agents/language/test_queries.py
exit 0 — All checks passed!
```

### 전체 Ruff 기준선

```text
RUFF_CACHE_DIR=/private/tmp/la-t03-ruff-cache .venv/bin/ruff check .
exit 1 — 113 errors
```

전체 Ruff 실패는 T3 범위 밖의 기존 HWP/HWPX 및 crawler 파일 위반을 포함한다. T3 파일의 Ruff는 별도 focused 명령으로 통과했다.

### 계약·작업 트리 확인

```text
git diff --exit-code -- docs/contracts
exit 0 — schema snapshot 변경 없음

git diff --check
exit 0

git status --short --branch
결과 — implementation SHA 기준 clean
```

## 커밋 및 rollback

- Packet: `6ac7477701a01b02dcbd0cfe0320dd92bce7f8e7`
- Implementation: `c18490c52830627ef8d126e84689f74e01c48a54` (`feat: 보호 사실과 결정적 Query 구현`)
- rollback 기준: `13d088a7924f837b3c7caf476f62153bee903f2b`
- 이전 영어 커밋은 수정·재작성하지 않았다.
- 이 Evidence Pack은 별도 docs 커밋으로 기록한다.

## 미검증 항목

- Luna 독립 검증은 Evidence Pack 커밋 후 별도 worktree에서 수행해야 한다.
- T3는 `feat/language-assistant`에 통합하지 않았으므로 통합 후 재검증 결과는 없다.
- 실제 Qdrant, EPS 데이터, 외부 LLM, 운영 API와의 통합 동작은 T3 범위에서 검증하지 않았다.
- 전체 Ruff 저장소 기준선은 기존 113개 위반으로 여전히 실패한다.
- 표준 한국어의 외부 의미 동등성·다국어 생성·S1 review는 T3에서 검증하지 않았다.
