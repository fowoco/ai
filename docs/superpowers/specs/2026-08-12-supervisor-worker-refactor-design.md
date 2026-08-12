# Supervisor–Worker 리팩터링 설계

- 작성일: 2026-08-12
- 상태: 승인됨
- 범위: 현재 동작하는 Analyses, Renewal, OCR, Language Assistant, 등록 문서 생성의 내부 책임 재배치
- 핵심 제약: 외부 계약과 실행 결과를 바꾸지 않는 리팩터링

## 1. 목표

현재 LangGraph, Supervisor, Shared State, Subgraph 구조를 다음 책임으로 정리한다.

```text
Supervisor Agent
├─ 업무 인식 Agent
├─ 문서 지능 Agent
├─ 언어 지원 Agent
├─ 문서 자동화 Agent
└─ Validation / Review Agent

Tools
├─ OCR
├─ MCP
├─ Server Context Resolver
├─ HWP/HWPX 편집
└─ 문서 변환
```

Agent는 판단, 라우팅, 검증만 수행한다. Tool은 외부 호출, 데이터 조회, 파일 처리처럼 제한된 실행을 담당한다.

## 2. 동작 보존 기준

다음 외부 동작은 정확히 유지한다.

- 기존 API 경로, 요청 및 응답 스키마, HTTP 상태
- `outcome`, `status`, `scenario`, `caseSignals`, `progressEvents`
- `requestId`, `attemptId`, `taskId` 전달 규칙
- `PLAN -> CONTEXT_REQUIRED -> ANALYZE` Server Context 조회 계약
- Renewal의 `ask_hr`, `ask_worker`, `ocr`, `generate`, `out_of_scope` 분기
- OCR 후 필드가 부족해도 현재처럼 등록 문서 초안 생성으로 진행하는 동작
- 등록 템플릿 4종과 필드 매핑 우선순위
- 문서 생성 결과의 `REVIEW_REQUIRED`; 자동 완료를 추가하지 않음
- Language Assistant의 표준 한국어, 쉬운 한국어, 번역, EPS 검색, 실패 격리
- MCP의 승인 receipt, typed edit, Vision PASS 최종화 계약
- Server의 인증, tenant 권한, DB Context 조회, 재시도, Case/Task 저장 책임

리팩터링 전후 동일한 요청으로 생성한 공개 응답을 비교하는 characterization test를 변경의 최상위 게이트로 둔다.

## 3. 비목표

- 새 API 또는 응답 필드 추가
- 미등록 문서 자동화 구현
- MCP 호출, Qwen3 embedding/reranking, Canonical Mapping 구현
- Agent 내부 자동 재시도
- 새로운 병렬 실행
- 자동 완료 또는 Human Review 생략
- DB 직접 연결, SQL 생성 또는 SQL 실행
- 현재 등록 템플릿 mapper 교체
- 새 프레임워크나 외부 의존성 추가

미등록 문서, MCP, Qwen3 Canonical Mapping은 이 리팩터링 완료 후 별도 feature-flag 계획으로 구현한다.

## 4. 현재 구조와 목표 책임

### 4.1 Supervisor Agent

현재 `workflow_graph/supervisor.py`의 허용 라우트와 rules-first 결정을 유지한다. Supervisor는 Worker 결과와 Shared State를 읽어 다음 실행 대상을 고른다.

- 기본 판단은 기존 deterministic rules
- 선택적 LLM 제안은 기존 허용 라우트 안에서만 채택
- 재시도는 수행하지 않음
- 권한을 직접 판정하지 않음
- 현재 route token과 phase/step 신호 유지

### 4.2 업무 인식 Agent

현재 Intent, Ambiguity, Workflow 선택 책임을 명확히 묶는다.

- HR instruction에서 Intent와 slot 추출
- 필요한 canonical key 결정
- Workflow Catalog ID 결정
- 부족한 정보에 대한 질문 후보 생성
- Server가 제공한 Context만 소비

기존 `LanguageNode` port와 분석 pipeline을 재사용한다. Intent 분석을 사용자 안내 언어 생성과 혼동하지 않도록 내부 이름만 정리한다.

### 4.3 언어 지원 Agent

현재 독립 Language Assistant graph와 `LanguageGuideBridge`를 유지한다.

- 표준 한국어
- 쉬운 한국어
- 번역
- EPS Hybrid RAG
- protected facts와 semantic validation
- 실패 시 기존 placeholder/fallback

Renewal Shared State 전체를 직접 소유하지 않고 기존 projection을 통해 필요한 입력만 받는다.

### 4.4 문서 지능 Agent

현재 등록 문서 경로에서 `document_field_map.py`가 수행하는 판단을 별도 단계로 드러낸다.

- 등록 template ID 선택
- DB snapshot, slot, OCR 결과 병합
- template field 값 계획 생성
- 생성 전에 문서별 mapping 결과 확정

실제 HWP/HWPX 파일 작업은 수행하지 않는다. 기존 mapper 함수와 template registry를 그대로 재사용한다.

### 4.5 문서 자동화 Agent

문서 지능 Agent가 만든 계획을 기존 `DocumentEditingService`로 실행한다.

- HWP/HWPX 입력
- 등록 template 생성 및 필드 입력
- 기존 변환 서비스 호출
- 문서별 실행 결과 반환

파일 편집과 변환 자체는 Tool이다. Agent는 사용할 Tool과 입력 계획을 고르고 결과를 Shared State patch로 반환한다.

### 4.6 Validation / Review Agent

문서 생성 결과와 기존 검증 증거를 종합해 공개 상태를 결정한다.

- 생성 결과 존재 및 문서별 상태 확인
- 기존 document validation, mapping 및 Tool 결과 소비
- 현재 동작대로 `READY_FOR_REVIEW` / `REVIEW_REQUIRED` 결정
- 불확실하거나 실패한 결과를 자동 완료하지 않음

tenant와 DB 권한은 검증하지 않는다. Server가 검증한 Context만 신뢰하고, 권한 검증 증거가 없으면 실행 가능하다고 추론하지 않는다.

## 5. Tool 경계

### OCR Tool

현재 CLOVA OCR service 계약을 유지한다. Renewal graph는 Server가 전달한 OCR 결과를 정규화한다. OCR Agent를 새로 만들지 않는다.

### Context Resolver Tool

AI는 canonical key를 요청한다. Server가 tenant 및 관계를 검증하고 조회한 Context를 제공한다. 로컬 `InMemoryDb`는 개발과 테스트용 adapter일 뿐 운영 권한 경계가 아니다.

### HWP/HWPX Tool

기존 `DocumentEditingService`, HWP5/HWPX registry와 service를 재사용한다. mapper, editor, converter를 복제하지 않는다.

### MCP Tool

이번 리팩터링에서는 연결하지 않는다. 후속 미등록 문서 단계에서도 MCP는 field registry, Edit Plan, artifact integrity, Vision gate만 담당하며 DB와 Canonical Catalog를 소유하지 않는다.

## 6. Shared State

`RenewalState`의 기존 필드를 유지한다. 내부 단계 분리를 위해 필요한 최소 중간 필드만 추가할 수 있다.

```python
document_field_values: NotRequired[dict[str, dict[str, object]]]
```

이 필드는 문서 지능 Agent가 만들고 문서 자동화 Agent가 소비한다. 공개 API에 노출하거나 TaskStore에 영속 저장하지 않는다.

기존 merge 우선순위를 유지한다.

1. Server/DB snapshot과 기존 slots
2. 요청에서 명시한 slots
3. OCR identity 값은 기존 규칙에 따라 우선
4. 등록 template mapper가 최종 template field 이름으로 투영

## 7. 실행 흐름

```text
Server Request
  -> load_context
  -> 업무 인식 Agent
  -> Supervisor Agent
       ask_hr       -> Server Response
       ask_worker   -> 언어 지원 Agent -> Server Response
       out_of_scope -> Server Response
       ocr          -> OCR Tool Adapter
                    -> 문서 지능 Agent
                    -> 문서 자동화 Agent
                    -> Validation / Review Agent
                    -> Server Response
       generate     -> 문서 지능 Agent
                    -> 문서 자동화 Agent
                    -> Validation / Review Agent
                    -> Server Response
```

현재 Language Assistant 내부의 쉬운 한국어와 번역 병렬 실행만 유지한다. Shared State를 함께 수정하는 상위 Worker 병렬화는 하지 않는다.

## 8. 오류 처리

- Tool 오류는 현재 exception 및 HTTP 매핑을 유지한다.
- Supervisor LLM 실패는 기존 rules fallback을 유지한다.
- Language Assistant 실패는 기존 placeholder fallback을 유지한다.
- 등록 문서 한 건의 편집 실패는 기존 문서별 `stub` 결과를 유지한다.
- Review Agent는 실패 결과를 성공 또는 자동 완료로 승격하지 않는다.
- Agent 내부 retry를 추가하지 않는다. 호출 재시도와 멱등성은 Server 책임이다.

## 9. 테스트 전략

### Characterization

- `ask_hr`, `ask_worker`, `ocr`, `generate`, `out_of_scope` 공개 결과
- OCR 값과 기존 slot 병합 우선순위
- 등록 문서 4종 ID와 mapped fields
- Language Assistant 성공 및 fallback
- progress, evidence, supervisor source/route 신호

### Unit

- 업무 인식 Agent가 기존 `LanguageNode` 결과를 동일하게 투영
- 문서 지능 Agent가 기존 mapper와 동일한 field map 생성
- 문서 자동화 Agent가 미리 계산된 field map만 실행
- Validation / Review Agent가 현재 review 상태를 재현

### Regression

- 기존 agents, workflows, OCR, language, documents test suite
- 공개 Pydantic schema 변경 없음
- 신규 의존성 없음

## 10. 단계 구분

### 1단계: 동작 보존 리팩터링

이번 작업 범위다. characterization test를 먼저 고정하고 기존 기능을 Agent/Tool 책임으로 재배치한다.

### 2단계: 신규 미등록 문서 기능

별도 설계와 계획으로 진행한다.

```text
미등록 문서
  -> 문서 지능 Agent
  -> MCP Analyze Tool
  -> Rule + Qwen3 Canonical Mapping
  -> Server Context Resolver
  -> MCP Edit Plan / Vision
```

`shadow -> lookup -> fill` feature flag 승격과 별도 검증 없이는 1단계에 섞지 않는다.

## 11. 완료 조건

- 기존 공개 계약과 주요 응답이 characterization test에서 동일
- 기존 등록 템플릿 4종 결과 동일
- 상위 Agent 병렬화 및 Agent retry 없음
- OCR, DB Context, HWP/HWPX, MCP가 Tool 경계로 유지됨
- 문서 생성은 여전히 Human Review 대상
- 신규 미등록 문서 기능이 포함되지 않음
- 전체 관련 test와 lint 통과
