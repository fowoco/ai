# Mac 시연용 AI Agent 서빙과 Kubernetes 이전

## 목적과 경계

Kubernetes AI Agent가 준비되기 전까지 배포 Backend가 Mac에서 실행되는 동일한
FOWOCO AI Agent의 PLAN·ANALYZE API를 호출한다. Server가 BERT나 A.X를 직접 호출하거나
별도 모델 API를 추가하지 않는다.

```text
배포 Backend
→ Cloudflare Tunnel
→ Mac 127.0.0.1:8000
→ FOWOCO AI Agent
   ├─ POST /internal/v1/analyses (PLAN)
   ├─ POST /internal/v1/analyses (ANALYZE)
   ├─ BERT
   └─ A.X + Knowledge prompt
```

Mac Agent는 임시 시연 대상이다. Kubernetes 전환 후에도 소스·계약·Prompt 버전은
같고 Backend의 Base URL과 Token만 교체한다.

## 고정된 런타임 계약

| 항목 | 값 |
|---|---|
| Analyses contract | `1.1.0` |
| Knowledge prompt | `knowledge-25e778ad` |
| BERT | `fowoco/klue-roberta-base-intent-classifier` |
| A.X Base | `skt/A.X-4.0-Light` |
| A.X Adapter | `fowoco/ax-intent-qlora` |
| Mac device | `mps` |
| API worker | `1` |
| 동시 Intent 추론 | `1` |

`.env.mac.example`은 검증된 Hugging Face commit SHA를 포함한다. 실제 Token은 포함하지
않으며 `.env.mac`은 Git에 추가하지 않는다.

## Mac 최초 설치

Python 3.11 이상을 사용한다. Docker Desktop Linux 컨테이너는 macOS MPS를 전달하지
않으므로 Mac 시연은 네이티브 가상환경으로 실행한다.

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[intent-ax]"
cp .env.mac.example .env.mac
```

`.env.mac`에 다음 Secret을 입력한다.

- `FOWOCO_INTERNAL_API_TOKEN`: 배포 Backend와 Agent 사이의 긴 임의 Bearer Token
- `FOWOCO_HF_TOKEN`: private Adapter를 읽을 수 있는 신규 read-only Hugging Face Token

`FOWOCO_INTERNAL_API_AUTH_REQUIRED=true`이므로 Internal Token이 비어 있으면 Agent는
시작하지 않는다. Tunnel은 이 검사를 해제하는 이유가 될 수 없다.

모델을 한 번 내려받은 뒤 네트워크 없는 상태까지 확인하려면 Hugging Face cache를
보존하고 `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`로 별도 재검증한다.

## 실행

저장소 루트에서 다음 명령을 실행한다.

```bash
chmod +x scripts/run_mac_agent.sh
scripts/run_mac_agent.sh
```

스크립트는 다음을 강제한다.

- `127.0.0.1` 바인딩: 공유기 포트포워딩과 직접 공개 금지
- uvicorn worker 1개: 프로세스별 모델 중복 로딩 방지
- BERT/A.X 추론 1개씩 직렬화: 24GB 통합 메모리의 동시 generate 방지
- `caffeinate`: 프로세스 실행 중 macOS 절전 방지
- startup warmup 실패 시 시작 실패

기본 포트는 8000이다. 충돌할 때만 실행 전에 `FOWOCO_MAC_PORT`를 지정한다.

```bash
FOWOCO_MAC_PORT=8010 scripts/run_mac_agent.sh
```

## Health와 인증

| Endpoint | 인증 | 의미 |
|---|---|---|
| `GET /health/live` | 애플리케이션 없음 | FastAPI 프로세스 생존 여부 |
| `GET /internal/v1/health/ready` | Bearer | 모델 warmup과 A.X 가용성 |
| `GET /internal/v1/intent/readiness` | Bearer | 기존 Intent readiness 호환 경로 |

Cloudflare Access가 Tunnel hostname 전체를 보호하고 Agent의 Bearer 인증을 추가로
적용한다. liveness에는 Secret이나 모델 상세가 포함되지 않는다.

준비 완료 응답은 다음 조건을 만족해야 한다.

```json
{
  "intentModelEnabled": true,
  "axEnabled": true,
  "initialized": true,
  "bertAvailable": true,
  "axAvailable": true,
  "ready": true,
  "warmupCompleted": true,
  "degraded": false,
  "promptVersion": "knowledge-25e778ad"
}
```

## 로컬 스모크 테스트

Agent가 준비된 다음 별도 터미널에서 실행한다.

```bash
.venv/bin/python scripts/smoke_mac_agent.py --env-file .env.mac
```

이 스크립트는 Token을 출력하지 않고 다음을 검증한다.

1. liveness 200
2. readiness의 BERT/A.X 및 Prompt 버전
3. A.X를 사용하는 PLAN 성공
4. PLAN의 Intent·Workflow로 ANALYZE 성공
5. ANALYZE `providerAttemptCount=0`
6. Candidate `workflowId`와 PLAN `workflowId` 동일

Tunnel 연결 후에는 배포 주소를 지정해 같은 검증을 반복한다.

```bash
.venv/bin/python scripts/smoke_mac_agent.py \
  --env-file .env.mac \
  --base-url https://ai-mac.example.com
```

Cloudflare Access Service Token 헤더는 인프라에서 Backend에 주입한다. Access 적용 후
수동 smoke가 필요하면 해당 헤더를 추가하는 방식으로 스크립트를 확장하되 Secret을
CLI 인자로 넘기거나 로그에 출력하지 않는다.

## Backend와 Tunnel 계약

AI팀의 완료 경계는 localhost PLAN·ANALYZE·Health 성공이다. 인프라는 named Tunnel과
DNS, Cloudflare Access를 설정하고 Server팀은 배포 Backend에 다음 Secret을 주입한다.

```text
AI Base URL       = Mac Tunnel HTTPS URL
AI Bearer Token   = FOWOCO_INTERNAL_API_TOKEN과 같은 값
Access Client ID  = Cloudflare Access service token ID
Access Secret     = Cloudflare Access service token secret
```

Server 요청 timeout 권장값은 PLAN 90초, ANALYZE 30초다. startup/readiness는 첫 모델
다운로드가 아닌 cache가 준비된 상태에서도 여유 있게 300초를 허용한다. 트래픽은
readiness 200 이후에만 보낸다.

## Kubernetes 이전

Kubernetes 이미지에는 `intent-ax` extra가 설치되어 있어야 하며 현재 Dockerfile은 이를
포함한다. 배포 환경에서는 다음만 달라진다.

| 항목 | Mac | Kubernetes |
|---|---|---|
| 실행 | 네이티브 Python | Docker image |
| device | `mps` | `cuda` 또는 실제 검증 장치 |
| ingress | Cloudflare Tunnel | ClusterIP Service |
| 모델 cache | Mac HF cache | Persistent Volume |
| Agent URL | Mac Tunnel URL | Kubernetes Service URL |

Kubernetes에서도 worker 1개, startup warmup, required warmup, Internal Bearer 인증을
유지한다. Base/Adapter revision과 Prompt 버전이 Mac smoke 결과와 같아야 한다.

전환 순서는 다음과 같다.

1. 동일 commit으로 Kubernetes Agent 배포
2. readiness에서 A.X와 Prompt 버전 확인
3. Kubernetes Endpoint로 PLAN→ANALYZE smoke 수행
4. Backend AI Base URL과 Token을 Kubernetes 값으로 교체
5. 배포 Backend 통합 smoke 통과 후 Mac Tunnel 중지

Mac과 Kubernetes 사이의 요청 단위 자동 fallback은 이 범위에 포함하지 않는다. 전환
중 PLAN과 ANALYZE가 다른 Agent 버전으로 분리되는 것을 막기 위해 Endpoint는 배포
설정으로 명시적으로 전환한다.

## 시연 직전 체크리스트

- Mac 전원과 안정적인 Wi-Fi 연결
- `.env.mac` Secret과 고정 revision 확인
- Agent startup warmup 완료
- readiness `ready=true`, `axAvailable=true`
- 로컬 smoke 통과
- named Tunnel 연결 및 Access 정책 확인
- 배포 Backend에서 Tunnel PLAN→ANALYZE 통과
- 실제 발화 로그와 Secret 출력 여부 확인
- 시연 종료 후 Mac용 Token과 Tunnel 유지 여부 결정
