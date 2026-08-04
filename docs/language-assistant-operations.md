# Language Assistant 운영 런북

> **대상**: W4 Runtime (T13) 이후 배포 환경  
> **최종 업데이트**: T13 구현 완료 시점

---

## 아키텍처 요약

```
[외부] → [fowoco-ai:8000] → [fowoco-qdrant:6333] (내부전용)
                    ↓
          /data/model-cache   (BGE-M3, BGE-Reranker 가중치)
          /data/document-snapshots
```

- Qdrant는 호스트 포트 없음 — Docker 네트워크 내부만 접근 가능
- 모델 가중치는 배포 전 `scripts/download_language_models.py`로 사전 적재
- HTTP 요청 중 모델 다운로드 금지 (계약: T13)

---

## 환경변수 참조

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `FOWOCO_QDRANT_URL` | `None` | Qdrant 엔드포인트. 미설정 시 language assistant degraded |
| `FOWOCO_QDRANT_API_KEY` | `None` | Qdrant API Key (선택) |
| `FOWOCO_LLM_TIMEOUT_SECONDS` | `60` | LLM 요청 타임아웃 (초, 양수 필수) |
| `FOWOCO_MODEL_CACHE_DIR` | `/tmp/fowoco-model-cache` | 모델 가중치 캐시 디렉터리 |

---

## 모델 사전 다운로드

### 초기 배포 전

```bash
# 프로덕션 볼륨 경로에 적재
docker run --rm \
  -v fowoco-document-data:/data \
  python:3.12-slim \
  bash -c "pip install huggingface_hub && \
           python scripts/download_language_models.py --cache-dir /data/model-cache"
```

### 캐시 상태 확인

```bash
python scripts/download_language_models.py --verify-only --cache-dir /data/model-cache
```

### 고정 리비전

| 모델 | 리비전 |
|------|--------|
| `BAAI/bge-m3` | `5617a9f61b028005a4858fdac845db406aefb181` |
| `BAAI/bge-reranker-v2-m3` | `953dc6f6f85ac1e88eb36f5f9ce67a74a6edbc22` |

---

## 장애 대응

### Qdrant 연결 실패

**증상**: `/internal/v1/language-assistant` → 503 `LANGUAGE_ASSISTANT_NOT_CONFIGURED`

**점검**:
```bash
# Qdrant 헬스체크
docker exec fowoco-qdrant wget -qO- http://localhost:6333/readyz

# ai 컨테이너에서 연결 확인
docker exec fowoco-ai wget -qO- http://qdrant:6333/readyz
```

**복구**:
```bash
# Qdrant 재시작
docker compose restart qdrant

# 재시작 후 ai 서비스 연결 확인
docker compose logs --tail=50 ai
```

### Qdrant 데이터 손상

> **경고**: 아래 절차는 Qdrant 인덱스 데이터를 삭제합니다. 색인 재구축 필요.

```bash
# 1. 서비스 중단
docker compose down

# 2. Qdrant 볼륨 삭제
docker volume rm fowoco-qdrant-data

# 3. 서비스 재시작 (빈 Qdrant로 기동)
docker compose up -d

# 4. 데이터 재색인 (별도 색인 스크립트 필요)
python scripts/index_eps_language.py
```

### 모델 캐시 누락

**증상**: `RuntimeStatus.ready=False`, `missing=['model_cache']` 로그

**복구**:
```bash
# 모델 재다운로드
docker exec fowoco-ai \
  python scripts/download_language_models.py \
  --cache-dir /data/model-cache

# 또는 강제 재다운로드
docker exec fowoco-ai \
  python scripts/download_language_models.py \
  --cache-dir /data/model-cache --force
```

### LLM 타임아웃 조정

```bash
# .env 또는 compose.yml environment 섹션에 추가
FOWOCO_LLM_TIMEOUT_SECONDS=120
docker compose up -d ai
```

---

## 볼륨 관리

| 볼륨 | 내용 | 백업 우선순위 |
|------|------|--------------|
| `fowoco-document-data` | 문서 스냅샷, 모델 캐시 | 중 (모델은 재다운로드 가능) |
| `fowoco-qdrant-data` | Qdrant 벡터 인덱스 | 높음 (재색인 비용 큼) |

### 볼륨 백업 (Qdrant)

```bash
docker run --rm \
  -v fowoco-qdrant-data:/source:ro \
  -v $(pwd)/backup:/backup \
  alpine \
  tar czf /backup/qdrant-$(date +%Y%m%d).tar.gz -C /source .
```

---

## 통합 테스트 환경

```bash
# 테스트 전용 Qdrant 기동 (프로덕션 볼륨과 완전 격리)
docker compose -f compose.test.yml up -d

# 테스트 실행
python -m pytest tests/integration/language/

# 정리
docker compose -f compose.test.yml down -v
```

---

## 런타임 상태 확인 (코드)

```python
from app.agents.language.runtime import check_runtime_dependencies

status = check_runtime_dependencies()
if not status.ready:
    print(f"미준비 항목: {status.missing}")
```
