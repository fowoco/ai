# T13 Evidence Pack — Runtime Settings, Model Preload, Qdrant Compose, Recovery Runbook

```yaml
wave: W4
task: T13
title: Runtime Settings, Model Preload, Qdrant Compose, and Recovery Runbook
implementation_sha: 3bbeada19158c81b3c7965c011fb16e19ea111af
base_sha: 6d9621072138be779c40ded6b6d0f69ee1021c45
branch: task/la-runtime-qdrant
builder: Language Assistant W4 T13 Builder
date: 2026-08-04
```

---

## 클레임 검증

| # | 클레임 | 검증 방법 | 결과 |
|---|--------|----------|------|
| C1 | Qdrant 서비스 내부전용, 호스트 포트 노출 없음 | `test_qdrant_service_no_external_ports` | ✅ |
| C2 | 프로덕션/테스트 Qdrant 볼륨 완전 격리 | `test_compose_test_qdrant_uses_separate_volume` | ✅ |
| C3 | Qdrant 1.18.3 이미지 고정 | `test_qdrant_service_uses_pinned_image` | ✅ |
| C4 | 모델 리비전 고정 (BGE-M3, Reranker) | `test_manifest_constants_defined` | ✅ |
| C5 | HTTP 요청 중 모델 동적 다운로드 금지 | runtime.py: 환경변수 체크만, 네트워크 접근 없음 | ✅ |
| C6 | Qdrant URL 미설정 시 degraded (크래시 없음) | `test_check_runtime_dependencies_not_ready_when_qdrant_url_missing` | ✅ |
| C7 | uv.lock 기반 재현 가능 Docker 빌드 | Dockerfile: `uv sync --frozen --no-dev` | ✅ |
| C8 | LLM timeout 양수 검증 (0·음수 거부) | `test_llm_timeout_rejects_zero`, `test_llm_timeout_rejects_negative` | ✅ |

---

## 테스트 결과

```
전체: 424 passed, 1 skipped (기존 T01~T12 포함)
T13 신규: 30 tests (test_runtime_config.py: 14, test_model_cache.py: 7, test_compose_config.py: 9)
Ruff: 0 errors
git diff --check: ok
```

---

## 변경 파일 목록 (19개 허용 중 11개 수정/신규)

### 신규 파일 (7개)
- `app/agents/language/runtime.py` — RuntimeStatus, check_runtime_dependencies()
- `scripts/download_language_models.py` — BGE-M3/Reranker 사전 다운로드, verify_model_cache()
- `compose.test.yml` — 테스트 전용 Qdrant 격리 환경
- `docs/language-assistant-operations.md` — 복구 런북
- `tests/agents/language/test_runtime_config.py` — 런타임 설정 14개 테스트
- `tests/agents/language/test_model_cache.py` — 모델 캐시 7개 테스트
- `tests/integration/language/test_compose_config.py` — compose 파일 9개 테스트

### 수정 파일 (4개)
- `app/core/config.py` — FOWOCO_QDRANT_URL/API_KEY, FOWOCO_LLM_TIMEOUT_SECONDS, FOWOCO_MODEL_CACHE_DIR 추가
- `compose.yml` — Qdrant 1.18.3 내부전용 서비스, 볼륨 분리, ai 서비스 환경변수 주입
- `Dockerfile` — pip→uv 전환, uv.lock --frozen --no-dev, 모델 캐시 볼륨 환경변수
- `.dockerignore` — .uv 캐시 디렉터리 무시 추가

---

## 핵심 설계 결정

### Qdrant 내부전용
`compose.yml`에서 `ports` 대신 `expose`만 사용. Docker 네트워크 내부 서비스만 접근 가능.
ai 서비스는 `FOWOCO_QDRANT_URL=http://qdrant:6333`으로 연결.

### RuntimeStatus (ponytail: 최소)
`dataclass(frozen=True)` — Pydantic 불필요. `ready: bool + missing: list[str]`.
환경변수 체크만, 네트워크/파일시스템 접근 없음 → 단위 테스트 완전 격리.

### 모델 캐시 무결성 (ponytail: 최소)
`verify_model_cache(cache_dir)` — `config.json` sentinel 파일 존재 여부만 확인.
실제 체크섬 검증은 사전 다운로드 시 huggingface_hub이 담당.

### uv.lock 재현 가능 빌드
`uv sync --frozen --no-dev` → lock 파일 기반, 개발 의존성 제외. pip 대비 빠른 설치.

---

## 금지 사항 준수

- ✅ 허용 목록 외 파일 미수정
- ✅ 단위 테스트에서 모델 가중치 다운로드 없음
- ✅ 단위 테스트에서 외부 Qdrant 서버 연결 없음
- ✅ T01~T12 테스트 약화 없음 (424 passed 유지)
- ✅ 중앙 feature 브랜치 병합/push 없음
