# Language Assistant Reranker·Docker Runtime Design

## 상태

- 날짜: 2026-08-10
- 브랜치: `feat/language-assistant-runtime-composition`
- 기준: `dd8d2cd556bd1932722ee851c20f4478a29610be`
- 결정: BGE-M3 encoder와 BGE reranker의 고정 revision 가중치를 production Docker image에 포함한다.

## 목적

1. 기존 `FlagEmbeddingReranker`를 production `HybridEpsRetriever`에 연결한다.
2. 잘못 고정된 reranker revision을 Hugging Face에서 실제 존재하는 revision으로 통일한다.
3. Docker image 하나만으로 encoder·reranker 모델을 사용할 수 있게 한다.
4. 이전 Docker one-shot 정지가 코드 결함인지 런타임 일시 장애인지 실제 기동으로 판정한다.

OpenAI API 실호출과 provider 변경은 이 작업에서 제외한다.

## 결정과 이유

모델용 named volume과 별도 초기화 서비스를 두지 않는다. 대신 Docker build 중 두 모델을 고정 revision으로 내려받아 image에 포함한다. 이미지가 수 GB 커지고 build가 Hugging Face 네트워크에 의존하지만, 배포 시 추가 초기화 절차가 없어 운영 설명과 재현 절차가 단순해진다.

요청 처리 중 모델 다운로드는 금지한다. build가 모델 다운로드에 실패하면 image build도 실패해야 한다.

## 구성

### Revision 단일화

`app/agents/language/retrieval/manifest.py`가 다음 값을 단일 소스로 제공한다.

- encoder: `BAAI/bge-m3@5617a9f61b028005a4858fdac845db406aefb181`
- reranker: `BAAI/bge-reranker-v2-m3@953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`

다운로드 스크립트, production composition, reranker adapter와 테스트가 같은 상수를 사용한다. 현재 다운로드 스크립트의 존재하지 않는 `953dc6f6f85ac1e88eb36f5f9ce67a74a6edbc22`는 제거한다.

### Production composition

`_build_retriever()`는 기존 encoder와 Qdrant store에 다음 reranker를 추가한다.

```text
<model_cache_dir>/bge-reranker-v2-m3/<fixed revision>
  → FlagEmbeddingReranker
  → HybridEpsRetriever(reranker=...)
```

모델은 service 생성이나 app import 시 로드하지 않는다. 첫 retrieval에서 lazy load한다. 모델 경로 누락이나 추론 실패는 기존 계약대로 cross-query RRF 상위 5개를 사용하고 `degraded_components=["reranker"]`를 반환한다.

CPU 기반 Docker 실행을 기본으로 하므로 reranker는 FP16을 강제하지 않는다. 별도 GPU 최적화와 score threshold는 추가하지 않는다.

### Docker image

Dockerfile은 application과 다운로드 스크립트를 복사한 뒤 `/app/.venv/bin/python`으로 고정-revision 다운로드를 실행한다.

```text
/opt/fowoco/language-models/
  bge-m3/<encoder revision>/
  bge-reranker-v2-m3/<reranker revision>/
```

image의 `FOWOCO_MODEL_CACHE_DIR` 기본값은 `/opt/fowoco/language-models`다. Compose의 기존 `/data/model-cache` override도 같은 baked model 경로로 바꾼다. Compose에는 모델 초기화 서비스나 모델 volume을 추가하지 않는다.

`.dockerignore`는 전체 `scripts` 제외를 `scripts/*`로 좁히고 `scripts/download_language_models.py`만 다시 포함한다. host의 모델 캐시와 나머지 스크립트는 build context에 넣지 않는다.

### Docker 정지 판정

현재 최신 image에서 다음 경로는 모두 정상 종료했다.

- `/bin/true`
- `/app/.venv/bin/python --version`
- `uv run python --version`
- `uv run python -c 'from app.main import create_app; ...'`

따라서 선제 코드 수정은 하지 않는다. 모델 포함 image를 새로 build한 뒤 one-shot import와 `docker compose up -d ai` healthcheck가 통과하면 이전 정지는 OrbStack 런타임의 일시 상태로 기록한다. 같은 경계에서 다시 정지할 때만 재현 테스트를 만든 후 진입점을 수정한다.

## 테스트와 검증

자동 테스트는 외부 네트워크를 사용하지 않는다.

1. reranker repo/revision 단일 상수와 다운로드 spec 일치
2. 유효한 Qdrant 설정에서 production composition이 `FlagEmbeddingReranker`를 주입
3. reranker 모델 누락·실패 시 기존 RRF fallback/degradation 유지
4. Dockerfile이 두 모델을 image build 중 다운로드하고 image 내부 경로를 설정
5. 기존 Language Assistant 및 전체 회귀 테스트 통과

실검증은 다음을 별도 Evidence로 남긴다.

1. 고정 revision 두 모델의 Docker build-time 다운로드 성공
2. 실제 BGE-M3 + production Qdrant + reranker 검색에서 context 5개, `selected_by="reranker"`, reranker degradation 없음
3. production Docker image one-shot import 성공
4. `docker compose up -d ai` 후 AI container healthcheck 성공
5. image 크기와 build 시간 기록

## 변경 예상 파일

- `app/agents/language/retrieval/manifest.py`
- `app/agents/language/retrieval/reranker.py`
- `app/agents/language/composition.py`
- `scripts/download_language_models.py`
- `Dockerfile`
- `.dockerignore`
- `compose.yml`
- 관련 Language Assistant·Docker 테스트
- `T13-RUNTIME-COMPOSITION-EVIDENCE.md`

## 비범위

- 실제 OpenAI API 검증 또는 provider 변경
- reranker 품질 평가, score threshold, PR curve
- GPU/CUDA 최적화와 다중 worker 모델 공유
- 모델 volume·초기화 서비스·request-time 다운로드
- GitHub 이슈·댓글 수정

## 보안

`.env`, API key, token, secret을 만들거나 커밋하지 않는다. 모델은 공개 Hugging Face repository의 고정 revision만 사용한다.
