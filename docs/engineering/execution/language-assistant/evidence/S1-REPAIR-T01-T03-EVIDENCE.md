# S1 Repair Evidence — T01·T03 계약·보호 사실 보수

## 1. Evidence identity

- repair id: S1-REPAIR-T01-T03
- Packet SHA: 9e34b592f236231bf7a574b01f84f919655cd3c1
- Packet base SHA: 2ce75957e1ba9bcb0af74a259eb5d959d4b57a6f
- implementation SHA: f00b9e5b6a9418488c39bf6d055860ccdab3cca4
- evidence SHA: 기록용 Evidence commit 생성 후 CT ledger에 기록
- branch: repair/la-t01-t03-s1
- worktree: /Users/parktaejung/Desktop/workspace/ai-language-assistant-repair-t01-t03
- integration status: 현재 보수 branch는 feat/language-assistant에 병합하지 않음

이 Evidence Pack은 봉인된 Packet의 허용 범위와 implementation SHA의 결과만 기록한다. Control Tower ledger는 CT만 수정하며, 이 파일은 ledger를 수정하지 않는다.

## 2. 기존 기록 보존

기존 implementation, Evidence Pack, verifier 기록은 변경하거나 다시 작성하지 않았다.

| 기록 | 기존 SHA 또는 ID | 현재 의미 |
|---|---|---|
| T01 implementation | 42f429cd67fbecaf5cff41eef22e2389f8d8ad60 | 기존 구현 기록, 보존 |
| T01 Evidence | cb3fd9812aff1bd299d6e498e23ebc44315aa453 | 기존 Evidence 기록, 보존 |
| T01 verifier | Hume 019fc0ed-3801-7061-9d76-34cfc22f5e5f | 기존 독립 검증 기록, 보존 |
| T03 implementation | c18490c52830627ef8d126e84689f74e01c48a54 | 기존 구현 기록, 보존 |
| T03 Evidence | ae836ab2cd0c9ba4b4aabe1816c63fe5a6826d5f | 기존 Evidence 기록, 보존 |
| T03 verifier | Mill 019fc180-ff45-76c0-ba48-813dee29f5d9 | 기존 독립 검증 기록, 보존 |
| T03 original integration merge | 2ddb84cc3600fe2b7cd03577e5fa364174f19133 | 기존 병합 기록, 보존 |

기존 Evidence의 “아직 병합하지 않음” 문구는 당시 기록의 역사적 상태다. 현재 문맥에서는 기존 W1 산출물은 이미 중앙 branch에 통합되었고, 이 S1 보수 branch와 새 implementation은 아직 통합하지 않은 상태다. 기존 SHA와 본문은 이 구분을 위해 그대로 둔다.

## 3. RED 증거

새 회귀 테스트를 먼저 추가한 뒤 implementation 변경 전에 실행했다. 새 테스트가 의도한 경계를 검출하면서 실패했으므로 RED 순서를 확인했다.

### T01

명령:

~~~bash
PYTEST_ADDOPTS='' .venv/bin/python -m pytest tests/agents/language/test_contracts.py tests/agents/language/test_projection.py -q
~~~

결과:

- exit code: 1
- 32 passed, 4 failed
- 실패한 새 경계: 공백 deadline 거부, fallback 텍스트 변경 미거부, fallback warning 누락 미거부, Standard와 같은 텍스트를 가진 warning 상태의 fallback 오판

### T03

명령:

~~~bash
PYTEST_ADDOPTS='' .venv/bin/python -m pytest tests/agents/language/test_protected_facts.py tests/agents/language/test_queries.py -q
~~~

결과:

- exit code: 1
- 14 passed, 3 failed
- 실패한 새 경계: signed amount 부호 손실, 한국어 날짜 canonicalization 부재, complete unit/source path token surface 부재

첫 환경 준비에서 새 worktree에 .venv가 없어 발생한 exit 127은 테스트 실패가 아니라 실행 환경 준비 오류다. 중앙 worktree의 동일 .venv를 임시 ignored symlink로 연결한 뒤 RED를 재실행했고, Evidence의 RED 수치는 그 재실행 결과다. symlink는 검증 후 제거했다.

## 4. T01 보수 결과

- 문자열 deadline은 주변 공백을 제거한 뒤 YYYY-MM-DD 형식을 검사한다.
- datetime 객체와 datetime 문자열, 잘못된 구분자, 존재하지 않는 달력 날짜는 계속 거부한다.
- Easy 후보가 없는 경우를 Standard Korean fallback으로 명시했다.
- fallback은 easy_korean_text == standard_korean_text, Easy component status warning, Easy validation status not_run, STANDARD_KOREAN_FALLBACK warning을 함께 요구한다.
- fallback의 generation_status와 requires_human_review 조합은 기존 contract와 일관되어야 하며, fallback warning이 있는 경우에도 같은 불변식을 요구한다.
- fallback이라고 주장하면서 Easy 텍스트를 임의로 바꾼 출력은 거부한다.
- 마지막 Easy 후보가 남은 warning은 후보 metadata를 유지하는 별도 상태이며, 후보가 없는 fallback과 혼동하지 않는다.

## 5. T03 보수 결과

### 지원 token 및 canonicalization

| kind | 지원 surface 예시 | canonicalization 규칙 |
|---|---|---|
| date | 2026-08-10, 2026년 8월 10일 | 유효한 날짜는 ISO YYYY-MM-DD; 잘못된 날짜 텍스트는 임의 변환하지 않음 |
| time | 09:30, 9시 30분 | normalized surface |
| number | 42, -3.5 | 부호와 숫자 surface 보존 |
| amount | -1,234.50, ₩-10,000의 숫자 부분 | grouping comma 제거, 부호와 decimal scale 보존 |
| currency | USD, KRW, ₩, 100만원의 통화 표현 | surface 보존 또는 normalized surface; 환율·단위 규모 추론 없음 |
| unit | 42개, 10kg, 3.5% | 수량과 단위를 하나의 complete token으로 보존 |
| url, email, phone | URL, email, phone | 주변 punctuation을 제외한 normalized surface |
| document_identifier, version | ABC-123, v2.1 | normalized surface |

- 통화 기호·코드와 한국어 통화 표현(USD, KRW, ₩, 100만원)을 보호한다.
- 수량 단위(42개, 10kg, 3.5%)를 보호한다.
- complete token을 먼저 매칭해 부분 일치로 부호·통화·단위가 빠지지 않게 했다.
- token의 kind, source_path, surface, canonical_value를 보존하는 multiset 테스트를 추가했다.
- 세 Query가 새 machine token surface와 canonical request field를 그대로 보존하는 테스트를 추가했다.
- queries.py의 production 변경 없이 기존 Query builder의 보존 경계를 회귀 테스트로 고정했다.

## 6. GREEN 및 회귀 검증

모든 명령은 implementation SHA f00b9e5b6a9418488c39bf6d055860ccdab3cca4에서 실행했다.

### T01 focused

명령:

~~~bash
.venv/bin/python -m pytest tests/agents/language/test_contracts.py tests/agents/language/test_projection.py -q
~~~

결과: exit code 0, 36 passed (비실패 PytestCacheWarning 1건).

### T03 focused 및 token 경계

명령:

~~~bash
.venv/bin/python -m pytest tests/agents/language/test_protected_facts.py tests/agents/language/test_queries.py -q
~~~

결과: exit code 0, 17 passed (비실패 PytestCacheWarning 1건). 위 focused suite에는 signed amount, currency, quantity unit, Korean date, source path multiset, 세 Query 보존 경계 테스트가 포함된다.

### 전체 test

명령:

~~~bash
PYTEST_ADDOPTS='' .venv/bin/python -m pytest -o addopts='' --disable-warnings
~~~

결과: exit code 0, 183 passed, 1 warning in 0.99s.

### 변경 영역 Ruff

명령:

~~~bash
RUFF_CACHE_DIR=/private/tmp/la-s1-repair-ruff-cache .venv/bin/ruff check app/agents/language/contracts.py app/agents/language/protected_facts.py app/agents/language/queries.py tests/agents/language/test_contracts.py tests/agents/language/test_protected_facts.py tests/agents/language/test_queries.py
~~~

결과: exit code 0, All checks passed!.

### 범위·스키마·clean 검증

명령:

~~~bash
git diff --exit-code -- docs/contracts
git diff --check
git diff --name-status 9e34b592f236231bf7a574b01f84f919655cd3c1 f00b9e5b6a9418488c39bf6d055860ccdab3cca4
git status --short
~~~

결과:

- git diff --exit-code -- docs/contracts: exit code 0
- git diff --check: exit code 0
- Packet 이후 implementation commit의 변경 파일은 허용된 5개 implementation/test 파일뿐이다. Packet 문서 자체와 Control Tower ledger, 기존 Evidence Pack은 implementation commit에서 변경하지 않았다.
- 검증 후 임시 .venv symlink는 제거되었고 repair worktree는 clean이었다.

기존 W1 기준선의 whole-repo Ruff는 exit code 1, 기존 오류 113건으로 남아 있다. 이번 Packet은 변경 영역 Ruff를 요구했으며, 보수 범위 밖의 기존 전역 lint 문제는 수정하지 않았다.

## 7. 미검증 범위

다음 항목은 이 Evidence Pack에서 검증하지 않았으며 계속 unverified다.

- HTTP/API 실제 호출 및 배포 환경
- LangGraph runtime 실행·checkpoint·graph wiring
- Qdrant 연결·collection·검색 실행
- EPS 원문 ingest 및 실제 retrieval
- 외부 LLM/provider 호출과 품질
- production configuration 및 운영 환경
- 외부 G1–G7 gate와 S1 재검토
- Control Tower의 사용자 Gate 승인
- repair branch의 중앙 branch 병합 및 merge 결과
- W2 구현

## 8. 변경 제한 확인

- 기존 implementation/evidence/verifier SHA는 변경·재작성하지 않았다.
- Control Tower ledger는 이 branch에서 변경하지 않았다.
- Packet 허용 범위 밖의 graph/API/runtime/Qdrant/EPS/LLM/HWPX 파일은 변경하지 않았다.
- 독립 Luna verifier와 CT의 최종 ledger 기록은 Evidence commit 이후 별도 절차로 수행한다.
