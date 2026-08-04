# Language Assistant Developer Onboarding & Architecture Guide

외국인 근로자 15개 언어 지원 시스템(`app/agents/language`)의 인계인수 및 개발자 온보딩 가이드입니다.

---

## 0) New Engineer Fast Path (30분 인계인수 코스)

1. **시스템 개요**: [1) System at a glance](#1-system-at-a-glance)
2. **핵심 데이터 구조 & 파이프라인 (Qdrant & LLM & PDF)**: [2) Architecture & Models](#2-architecture--models)
3. **입출력 State & 메인 그래프 연동법**: [3) State & Main Graph Integration](#3-state--main-graph-integration)
4. **로컬 실행 및 테스트 명령어**: [4) Local Verification](#4-local-verification)
5. **자주 묻는 질문 (FAQ & Troubleshooting)**: [5) FAQ & Debugging](#5-faq--debugging)

---

## 1) System at a glance

### What / Why
- **목표**: 행정 서류 및 고용허가제(EPS) 안내문을 **격식체 표준 한국어**, **알기 쉬운 한국어**, **15개 외국인 근로자 원어 번역**으로 동시에 생성·검증하는 파이프라인.
- **핵심 원칙**:
  - **SSOT (Single Source of Truth)**: 날짜("2026-08-15"), 금액("150,000원"), 수량 등 고정 사실(`ProtectedFacts`) 손상 차단.
  - **PII 및 상위 DB 격리**: 메인 그래프 DB의 불필요한 메타데이터를 도메인 진입 전 Projection으로 완전 차단.
  - **장애 격리 (Fault Isolation)**: Qdrant나 특정 LLM 실패 시 전체 크래시 없이 경고(`WarningItem`)와 포괄적 Fallback 반환.

### 15개 지원 언어 목록
- `en`(영어), `zh-Hans`(중국어 간체), `vi`(베트남어), `th`(태국어), `fil`(필리핀어), `id`(인도네시아어), `mn`(몽골어), `si`(신할라어), `ru`(러시아어), `uz`(우즈베크어), `ky`(키르기스어), `bn`(벵골어), `ur`(우르두어), `km`(크메르어), `tet`(테툼어)

---

## 2) Architecture & Models

### 임베딩 모델 (Embedding): `BAAI/bge-m3`
- **선정 이유**: 15개 외국인 근로자 국적 언어(테툼어, 신할라어 등)를 광범위하게 지원하는 최상위 다국어 하이브리드 모델.
- **특징**: Dense(1024차원 의미 유사도) + Sparse(BM25 스타일 토큰 키워드 가중치)를 동시에 추출하여 법률/행정 단어의 **키워드 정확도**와 **의미 맥락**을 RRF 정렬 알고리즘(k=60)으로 상위 5개 선출.
- **리랭커 (Reranker)**: `BAAI/bge-reranker-v2-m3` (상위 30개 후보 재정렬)

### VectorDB (Qdrant) 청킹 및 인덱싱 구조
- **원본 데이터**: `data/eps_language_db.json` (총 17,902개 EPS 전용 행정/대화 매칭 쌍)
- **청킹 방식 (Sentence-level Pair)**:
  - 긴 글 자르기가 아닌 행정 문장/표현 1:1 대응 정제.
  - 유니코드 NFC 정규화 및 `UUID5(namespace, korean_text + lang)` 결정적 고유 ID 생성.
- **Qdrant 컬렉션**: `eps_language_phrases_active` (Dense 1024D + Sparse Vector + Payload)

### Context Pack (알기 쉬운 한국어 규칙)
- **원본 자료**: 법제처 『알기 쉬운 법령 정비기준(제10판 수정증보판)』 PDF
- **구조화**: `app/agents/language/resources/easy_korean_rules.v1.json` (SHA-256 무결성 검증 수록)
- **핵심 규칙**: 한자어/행정어 쉬운 우리말 교체("금회"→"이번", "지체 없이"→"곧바로"), 문장 단문화, 경어체(~하세요) 정규화.

### LLM 연동 및 환경변수 (`.env`)
- 프로젝트 공통 OpenAI-compatible 규격을 사용하며 `app/core/config.py`에 정의되어 있습니다.
```bash
FOWOCO_LLM_PROVIDER=openai-compatible
FOWOCO_LLM_BASE_URL=https://api.openai.com/v1
FOWOCO_LLM_API_KEY=sk-...
FOWOCO_LLM_MODEL=gpt-4o
FOWOCO_LLM_TIMEOUT_SECONDS=30
FOWOCO_QDRANT_URL=http://qdrant:6333
```

---

## 3) State & Main Graph Integration

### 입출력 데이터 규격 (`contracts.py`)

#### 입력: `LanguageAssistantInput`
- `worker_id`: 근로자 식별자 (응답 매칭용)
- `preferred_language`: 희망 언어 코드 (`vi`, `zh-Hans` 등)
- `nationality_code`: 국적 코드 (언어 미지정 시 추론용)
- `request_context`: 요청 사유, 제출 서류 목록, 마감일, 제출 방법

#### 출력: `LanguageAssistantOutput`
```python
class LanguageAssistantOutput(FrozenContract):
    worker_id: str
    target_language: SupportedLanguage
    generation_status: GenerationStatus        # "success" | "warning" | "failed"
    requires_human_review: bool               # 사람 검수 필요 여부
    standard_korean_text: str                 # 격식체 표준 한국어
    easy_korean_text: str                     # 알기 쉬운 한국어
    translated_text: str | None               # 원어 번역문 (실패 시 None)
    component_status: ComponentStatus          # 컴포넌트별 진단 상태
    validation: ValidationSummary              # 날짜/수량 보존 검증 결과
    warnings: tuple[WarningItem, ...]         # 발생한 경고 목록
    retrieval_metadata: RetrievalMetadata      # EPS 참고 출처 ID
```

### 메인 그래프 팀원 연동 방법

메인 그래프의 State 및 Node에 아래와 같이 추가하면 바로 동작합니다:

```python
from typing import TypedDict, Any
from app.agents.language.nodes import build_language_assistant_node

# 1. 메인 그래프 State에 필드 추가
class MainState(TypedDict):
    # ... 기존 메인 필드들 ...
    language_assistant: dict[str, Any]  # LanguageAssistantOutput.model_dump() 결과 저장

# 2. 메인 그래프 노드 생성 및 추가
language_node = build_language_assistant_node(service)
workflow.add_node("language_assistant", language_node)

# 3. 결과 텍스트 꺼내 쓰는 방법
# state["language_assistant"]["easy_korean_text"]
# state["language_assistant"]["translated_text"]
```

---

## 4) Local Verification

로컬 환경에서 직접 실행할 수 있는 명령어입니다:

```bash
# 1. 전체 453개 유닛/통합 테스트 전수 실행
.venv/bin/python -m pytest

# 2. 내부 HTTP API 엔드포인트 동작만 실행
.venv/bin/python -m pytest tests/api/test_language_endpoint.py -v

# 3. 상위 LangGraph 병렬 조립 테스트만 실행
.venv/bin/python -m pytest tests/agents/language/test_graph.py -v

# 4. OpenAPI 명세서 추출 스크립트 실행 (diff 0건 검증)
.venv/bin/python scripts/export_language_schemas.py

# 5. 15개 언어 60개 시나리오 오프라인 평가 Harness 검증
.venv/bin/python scripts/evaluate_language_retrieval.py --cases tests/fixtures/language/retrieval_cases.jsonl --validate-only
.venv/bin/python scripts/evaluate_language_generation.py --cases tests/fixtures/language/generation_cases.jsonl --validate-only
```

---

## 5) FAQ & Debugging

| 질문 / 증상 | 설명 및 대처 방안 |
|---|---|
| **안 쓰는 필드 처리** | `requires_human_review`, `component_status`, `warnings` 등 안 쓰는 필드는 삭제하지 않고 메인/프론트에서 참조하지 않고 무시(`ignore`)하면 됩니다. (백엔드 모니터링/로그용) |
| **Qdrant 연결 주소** | 동일 EC2 내 Docker Compose 활용 시 `http://qdrant:6333` 내부 통신을 사용합니다. 외부 포트(6333)를 개방하지 않아도 보안 통신이 가능합니다. |
| **OpenAI 모델 전환** | `.env`에 `FOWOCO_LLM_PROVIDER=openai-compatible` 및 OpenAI API Key를 적어주면 즉시 연동됩니다. |
