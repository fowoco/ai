# Coordinator (프로토타입)

knowledge 상태머신과 복합 요청 분리를 **검증·제안**하는 AI 쪽 모듈이다.

## 소유 경계

| 관심사 | 소유 |
|---|---|
| 상태 모델 9값 (`DRAFT` … `CANCELLED`) | knowledge `workflow_catalog.yaml` |
| 전이 규칙 코드 (`transitions.py`) | ai (server로 이식 예정) |
| WorkItem 영속·승인·권한·알림 | **server** (`/api/work-items`) |
| client HR UI | client → **server만** 호출 |

AI는 최종 업무카드 저장소가 아니다. client가 이 모듈의 HTTP를 직접 치면 안 된다.

## 패키지

```text
app/coordinator/
├─ transitions.py   순수 전이 계약 (server 이식 대상)
├─ models.py        비영속 TaskCard 스냅샷
└─ service.py       propose_split / validate_transition + 임시 인메모리
```

## Internal API

prefix: `/api/v1/internal/coordinator`

| Method | Path | 성격 |
|---|---|---|
| POST | `/propose-split` | **AI 핵심** — 복합 요청 분리 초안, 비영속 |
| POST | `/validate-transition` | **AI 핵심** — 전이 가능 여부, 저장 불필요 |
| * | `/work-items/*` | 로컬 상태머신 검증용 임시 시뮬레이터 |

운영에서는 server가 WorkItem을 만들고, AI는 propose/validate만 호출하는 형태가 된다.
