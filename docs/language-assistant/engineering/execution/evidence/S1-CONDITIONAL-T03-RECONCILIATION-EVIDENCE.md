# S1 Conditional Reconciliation Evidence — T03·fallback provenance

## 1. 식별 정보

- reconciliation id: S1-CONDITIONAL-T03-RECONCILIATION
- branch: repair/la-s1-conditional-t03
- worktree: /Users/parktaejung/Desktop/workspace/ai-language-assistant-repair-s1-conditional-t03
- base/current integrated HEAD before this repair: 0364d957ae508ecaecdb35de70fc268d0022e6e3
- prior S1 repair merge SHA: e6eb0f463458970b6c991415ffe93595461f6477
- prior S1 repair integrated SHA recorded by CT: f4480467d67ec4bd1c9ea51cfdef02decc744eac
- current central ledger HEAD: 0364d957ae508ecaecdb35de70fc268d0022e6e3
- prior effective implementation SHA: f00b9e5b6a9418488c39bf6d055860ccdab3cca4
- prior effective S1 Evidence SHA: a7940d01895585e627e6fdd73fc7404bfa1f179f
- new implementation SHA: 8e90db88d0093423477840242b0e835917126fba
- new reconciliation Evidence SHA: 이 문서의 docs commit 생성 후 보고
- merge status: 이 conditional branch는 중앙 branch에 병합하지 않음

이 문서는 기존 T01 Evidence, T03 Evidence, S1-REPAIR-T01-T03 Evidence를 보강하거나 재작성하지 않는다. 현재 통합 SHA·merge SHA·post-merge 검증 기록과 이번 conditional 변경을 별도 reconciliation 기록으로 연결한다.

## 2. 기존 통합 기록 reconciliation

| 항목 | SHA 또는 결과 | 의미 |
|---|---|---|
| S1 repair merge | e6eb0f463458970b6c991415ffe93595461f6477 | repair/la-t01-t03-s1를 feat/language-assistant에 --no-ff로 통합한 merge commit |
| integrated SHA | f4480467d67ec4bd1c9ea51cfdef02decc744eac | CT가 기록한 S1 repair 통합 결과 |
| final central ledger HEAD | 0364d957ae508ecaecdb35de70fc268d0022e6e3 | 통합 SHA를 확정한 후속 CT ledger commit |
| effective implementation | f00b9e5b6a9418488c39bf6d055860ccdab3cca4 | 이전 T01·T03 보수 implementation, 변경하지 않음 |
| effective Evidence | a7940d01895585e627e6fdd73fc7404bfa1f179f | 이전 S1 보수 Evidence, 변경하지 않음 |

병합 후 CT ledger에 기록된 검증:

~~~text
T01 focused:
.venv/bin/python -m pytest tests/agents/language/test_contracts.py tests/agents/language/test_projection.py -q
exit 0 — 36 passed

T03 focused:
.venv/bin/python -m pytest tests/agents/language/test_protected_facts.py tests/agents/language/test_queries.py -q
exit 0 — 17 passed

full:
PYTEST_ADDOPTS='' .venv/bin/python -m pytest -o addopts='' --disable-warnings
exit 0 — 183 passed, one non-failing cache warning

changed-area Ruff:
RUFF_CACHE_DIR=/private/tmp/la-s1-repair-ruff-cache .venv/bin/ruff check app/agents/language/contracts.py app/agents/language/protected_facts.py app/agents/language/queries.py tests/agents/language/test_contracts.py tests/agents/language/test_protected_facts.py tests/agents/language/test_queries.py
exit 0 — All checks passed!

whole-repository Ruff:
exit 1 — existing baseline 113 errors

schema diff:
git diff --exit-code -- docs/contracts
exit 0 — unchanged

whitespace:
git diff --check
exit 0
~~~

이 reconciliation은 위 역사적 통합 기록을 현재 conditional branch의 새 테스트·최소 Query 수정과 혼동하지 않는다. control-tower.md는 이 branch에서 수정하지 않았다.

## 3. 이번 conditional 변경 파일

implementation commit 8e90db88d0093423477840242b0e835917126fba의 변경 파일:

- app/agents/language/queries.py
- tests/agents/language/test_protected_facts.py
- tests/agents/language/test_queries.py

Evidence commit에서 추가하는 파일:

- docs/engineering/execution/language-assistant/evidence/S1-CONDITIONAL-T03-RECONCILIATION-EVIDENCE.md

변경하지 않은 파일:

- docs/engineering/execution/language-assistant/control-tower.md
- 기존 T01-EVIDENCE.md
- 기존 T03-EVIDENCE.md
- 기존 S1-REPAIR-T01-T03-EVIDENCE.md
- app/agents/language/contracts.py
- app/agents/language/formatting.py
- app/agents/language/state.py
- graph, node, API, runtime, Qdrant, EPS, LLM, HWPX 영역

## 4. T03 exact multiset 보강

기존 set/inclusion 검사를 다음 exact Counter 검사로 보강했다.

- kind
- source_path
- surface
- canonical_value
- 같은 source path 안에서 같은 token이 반복되는 경우의 중복 개수

테스트는 request_reason에 같은 금액·통화를 두 번, requested_items에 같은 수량 단위를 두 번 넣고 전체 Counter를 기대값과 비교한다. 따라서 token이 하나 빠지거나 source path·surface·canonical value·중복 개수가 달라지면 실패한다.

expected tuple 예:

~~~text
(amount, request_reason, -1,234.50, -1234.50) × 2
(currency, request_reason, USD, USD) × 2
(number, requested_items[0], 42, 42) × 2
(unit, requested_items[0], 42개, 42개) × 2
(unit, requested_items[1], -3.5%, -3.5%) × 1
(date, deadline, 2026-08-10, 2026-08-10) × 1
(currency, submission_method, ₩, ₩) × 1
(amount, submission_method, -10,000, -10000) × 1
(number, submission_method, 10, 10) × 1
(unit, submission_method, 10kg, 10kg) × 1
~~~

## 5. 세 Query 보존 보강

세 Query 각각에 대해 다음 pair Counter를 비교한다.

~~~text
(surface, canonical_value)
~~~

각 Query는 모든 pair의 expected count를 충족해야 한다. RED에서 기존 Query text에 original surface는 있었지만 canonical amount 값 -1234.50과 -10000이 없어 실패했다.

실패를 확인한 뒤 최소 수정으로 각 Query 뒤에 request facts에서 surface와 다른 canonical value만 안정적 순서로 추가했다.

~~~text
; 정규 보호값 <canonical values>
~~~

이 수정은 기존 request_context 필드·Query 3개 순서·kind를 바꾸지 않으며, 새로운 사실이나 formatter 의존성을 만들지 않는다. canonical 값이 surface와 같으면 중복 suffix를 만들지 않는다.

## 6. RED 증거

새 Counter 및 Query canonical 보존 테스트를 먼저 추가한 뒤 implementation 변경 전에 실행했다.

명령:

~~~bash
PYTEST_ADDOPTS='' /Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest tests/agents/language/test_protected_facts.py tests/agents/language/test_queries.py -q
~~~

결과:

- exit code: 1
- 18 passed, 1 failed
- 실패: test_each_query_preserves_machine_token_surface_and_canonical_counts
- 누락 canonical values: -1234.50, -10000
- Counter exact ProtectedFacts 테스트는 RED 단계에도 통과했다. 기존 token extraction 자체는 요구한 multiset과 일치했고, 기존 Query builder의 canonical text 보존만 실패했다.

새 worktree에는 local .venv가 없어 중앙 worktree의 실행 파일 절대경로를 사용했다. worktree 안에 symlink를 만들지 않았고, 이 환경 차이는 테스트 결과의 의미를 바꾸지 않는다.

## 7. GREEN 및 최종 local 검증

모든 결과는 implementation SHA 8e90db88d0093423477840242b0e835917126fba 이후에 실행했다.

### T03 focused

~~~bash
PYTEST_ADDOPTS='' /Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest tests/agents/language/test_protected_facts.py tests/agents/language/test_queries.py -q
~~~

exit code 0 — 19 passed.

### 전체 pytest

~~~bash
PYTEST_ADDOPTS='' /Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest -o addopts='' --disable-warnings
~~~

exit code 0 — 185 passed, 1 warning in 0.92s.

warning은 새 worktree의 .pytest_cache 생성 권한이 없어 발생한 non-failing PytestCacheWarning이며 테스트 실패가 아니다.

### 변경 영역 Ruff

~~~bash
RUFF_CACHE_DIR=/private/tmp/la-s1-conditional-ruff-cache /Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/ruff check app/agents/language/queries.py app/agents/language/protected_facts.py tests/agents/language/test_protected_facts.py tests/agents/language/test_queries.py
~~~

exit code 0 — All checks passed!

### 범위·공백

~~~bash
git diff --check
git diff --name-status 0364d957ae508ecaecdb35de70fc268d0022e6e3 8e90db88d0093423477840242b0e835917126fba
~~~

결과:

- git diff --check: exit code 0
- implementation 변경은 위 3개 파일뿐이다.
- control-tower.md와 기존 Evidence Pack은 implementation commit에서 변경하지 않았다.
- implementation worktree는 implementation SHA 기준 clean이었다.

## 8. fallback provenance 조사 결과

이번 conditional 작업에서 contracts.py에 request_context를 추가하지 않았고, contracts.py에 formatter를 import하지 않았다.

실제 저장소 경계 조사:

~~~bash
rg --files app/agents/language | sort
~~~

결과:

~~~text
app/agents/language/__init__.py
app/agents/language/codes.py
app/agents/language/contracts.py
app/agents/language/formatting.py
app/agents/language/projection.py
app/agents/language/protected_facts.py
app/agents/language/queries.py
app/agents/language/state.py
~~~

~~~bash
rg -n "assemble_output|generate_easy_korean|validate_easy_korean|correct_easy_korean|LanguageAssistantOutput\\(|generation_status|fallback_used|STANDARD_KOREAN_FALLBACK" app/agents tests/agents/language
~~~

결과: LanguageAssistantOutput contract와 fallback validation 테스트는 존재하지만, 실제 output producer, Easy candidate producer, assemble_output, Graph node/edge 조립 파일은 현재 구현되어 있지 않다. state.py는 output 타입을 선언할 뿐 조립하지 않고, formatting.py는 standard Korean renderer만 제공한다.

따라서 이번 범위에서 다음을 하지 않았다.

- contracts.py에 request_context provenance를 억지로 추가
- contracts.py에서 formatting.py를 import
- 존재하지 않는 factory·Graph·producer를 테스트용으로 발명
- fallback source를 가짜 metadata로 채움

### T11 이월 필요성 및 인수조건

현재는 fallback provenance를 기록할 실제 producer/Graph 조립 경계가 없으므로 T11 Graph assembly로 이월해야 한다.

T11 인수조건:

1. 실제 assemble_output 또는 동등한 Graph 조립 경계가 Easy candidate source와 no-candidate 상태를 소유한다.
2. no-candidate fallback은 standard text를 그대로 사용하고 source provenance를 명시한다.
3. 마지막 후보가 남은 warning과 no-candidate fallback을 별도 상태로 조립한다.
4. fallback output은 Easy warning, validation not_run, STANDARD_KOREAN_FALLBACK warning, generation_status, requires_human_review를 하나의 조립 결과로 검증한다.
5. Graph assembly 테스트는 candidate 있음·candidate 없음·fallback text 변경·warning/status 불일치를 실제 producer 경계에서 검증한다.
6. contracts.py는 domain validation만 담당하고, formatter import나 producer 호출을 갖지 않는다.

이 이월은 구현 누락의 은폐가 아니라 현재 repository에 실제 조립 경계가 없어서 임의 factory를 만들지 않은 결과다.

## 9. 미검증 범위와 중단 상태

계속 unverified:

- 실제 LangGraph runtime과 output producer/Graph assembly
- HTTP/API 배포 경계
- Qdrant 연결·collection·검색
- EPS ingest/retrieval
- 외부 LLM/provider와 생성 품질
- production configuration
- T11 구현 및 Graph assembly acceptance
- S1 재검토 최종 판정과 User Gate
- 이번 conditional branch의 중앙 merge 및 merge 후 replay
- W2

이번 branch는 Evidence commit 이후에도 중앙에 병합하지 않는다. control-tower.md 갱신, S1 재검토, W2 개방은 CT와 별도 세션의 책임이다.
