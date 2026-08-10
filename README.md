# FOWOCO AI Agent Server

FastAPI 기반 자연어 업무 처리 및 문서 생성·변환 서버다. 문서 처리는 한컴오피스,
COM, `win32com`, `pywin32` 없이 Linux Docker 환경에서 동작한다.

## 빠른 실행

Docker와 Docker Compose가 설치된 환경에서 다음 명령 하나로 빌드하고 실행한다.

```powershell
docker compose up -d --build
```

실행 후 확인할 주소:

- Swagger UI: <http://localhost:8000/docs>
- OpenAPI JSON: <http://localhost:8000/openapi.json>
- 문서 기능 조회: <http://localhost:8000/api/v1/documents/capabilities>

상태와 로그는 Compose로 확인한다.

```powershell
docker compose ps
docker compose logs -f ai
```

종료할 때는 다음 명령을 사용한다.

```powershell
docker compose down
```

`docker compose down`은 문서 스냅샷 볼륨을 보존한다. `docker compose down -v`는
볼륨과 저장된 스냅샷까지 삭제하므로 데이터 초기화가 필요한 경우에만 사용한다.

## 구조와 책임

```text
app/
├─ agents/
│  ├─ intent/            Analyses Intent·슬롯
│  ├─ ambiguity/         모호성·누락 판단
│  ├─ workflow/          Knowledge Catalog 조회
│  ├─ workflow_graph/    재갱신 LangGraph 오케스트레이션
│  ├─ language/          Language 노드 (외국인근로자 다국어·쉬운 한국어 지원 구현 완료)
│  ├─ pipeline.py        Analyses 파이프라인
│  └─ slot_catalog.py    슬롯 카탈로그
├─ api/
│  ├─ routes/            analyses · workflows · documents
│  ├─ schemas/           요청·응답 모델
│  ├─ dependencies.py    서비스·변환기 조립
│  └─ router.py          `/api/v1` 라우터
├─ db/                   worker/company 조회·신분 슬롯 저장
├─ documents/
│  ├─ common/            포맷 enum·감지
│  ├─ editing/           HWP/HWPX 편집·생성 facade
│  ├─ hwp5/ · hwpx/      포맷별 편집·템플릿
│  ├─ conversion/        변환기·외부 엔진
│  ├─ records/           TXT/DB 레코드 → XML 기입
│  ├─ snapshots/         XML 왕복 스냅샷
│  └─ xml/               XML 전용 확장 위치
└─ core/                 환경설정 등 공통 기반
```

의존 방향은 다음 원칙을 따른다.

```text
Server → API → agents (workflow_graph)
             ├→ db
             └→ documents
```

- `agents`는 HWP/HWPX 파일 구조를 알지 않는다.
- `documents`는 자연어를 해석하지 않고 구조화된 값과 파일만 처리한다.
- `api`는 HTTP 계약을 담당하고 두 도메인의 서비스를 조립한다.

상세 문서:

- [Internal API 안내](app/api/README.md)
- [문서 처리 아키텍처](app/documents/README.md)
- [재갱신 워크플로 노드 통합](app/agents/workflow_graph/README.md)
- [Language Assistant 운영 런북](docs/language-assistant-operations.md)
- [Language Assistant 평가 baseline](docs/evaluations/language-assistant-baseline.md)

## Analyses / Workflows / Language Assistant

```text
POST /internal/v1/analyses
POST /internal/v1/workflows/renewal/run
POST /internal/v1/language-assistant
```

- Analyses: 재갱신 고정 Intent + Catalog 필수슬롯·Knowledge 모호표현 ([docs/analyses-contract.md](docs/analyses-contract.md))
- Workflows: 재갱신 LangGraph — 슈퍼바이저 → 안내문(태정) / OCR(주현) / 초안 4종 — [docs/workflows-contract.md](docs/workflows-contract.md)
- Language Assistant: 외국인근로자 15개 언어 번역, 쉬운 한국어 변환 및 표준 한국어 생성 — [docs/contracts/language-assistant-http-request.schema.json](docs/contracts/language-assistant-http-request.schema.json)
- 최종 흐름도: [app/agents/workflow_graph/README.md](app/agents/workflow_graph/README.md)

## 문서 API

문서 API는 책임별로 분리한다.

```text
GET  /api/v1/documents/templates
GET  /api/v1/documents/templates/{template_id}
POST /api/v1/documents/inspect
POST /api/v1/documents/edit
POST /api/v1/documents/generate
POST /api/v1/documents/generate/from-txt
POST /api/v1/documents/convert
```

- `edit`: 업로드 HWP/HWPX를 같은 포맷으로 편집
- `generate`: 등록 템플릿으로 새 HWP/HWPX 생성
- `generate/from-txt`: DB 대신 테스트 TXT를 읽어 XML 자동기입 후 HWP 생성
- `convert`: 내용 변경 없이 포맷 변환

## 지원 변환

입력 포맷은 확장자가 아니라 실제 파일 시그니처와 구조로 자동 판별한다.

| 입력 | 지원 출력 |
|---|---|
| HWP 5.x | HWPX, XML, PDF |
| HWPX | HWP 5.x, XML, PDF |
| XML | HWP 5.x, HWPX, PDF |
| PDF | 현재 출력 변환 없음 |

HWPX→PDF 직접 렌더링이 실패하면 `HWPX → HWP → PDF` 경로를 자동으로 재시도한다.
현재 포함된 네 가지 HWP/HWPX 양식에 대해 HWP·HWPX 직접 변환과 양쪽에서 만든 XML
역변환을 조합한 Docker HTTP 검사 48건이 모두 통과한다.

## 로컬 개발

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
.\scripts\run.ps1
```

Docker 없이 외부 변환 기능까지 사용하려면 Java/hwp2hwpx, rhwp, LibreOffice와
H2Orestart import filter가 로컬 환경에 별도로 준비돼야 한다. 일반 개발과 실제 변환
검증은 의존성이 고정된 Docker 사용을 권장한다.

환경변수는 `FOWOCO_` 접두사를 사용한다.

```text
FOWOCO_DEBUG=false
FOWOCO_DOCUMENT_UPLOAD_MAX_BYTES=52428800
FOWOCO_DOCUMENT_CONVERSION_TIMEOUT_SECONDS=120
FOWOCO_DOCUMENT_SNAPSHOT_DIR=/data/document-snapshots
```

## CLOVA Template OCR

AI는 인증된 multipart 요청으로 원본 여권/외국인등록증 파일을 받아 CLOVA Template
OCR를 실행한 뒤 허용된 정규화 필드와 필드별 신뢰도를 Server에 반환한다. 문서·사업장
권한 검증, 결과 검증·암호화·저장은 Server가 담당하며 AI는 Server PostgreSQL을
조회하거나 수정하지 않는다. 기능은 기본적으로 비활성화된다.

요청·응답 계약, Template ID, 환경변수와 안전한 smoke 실행 방법은
[`docs/clova-ocr-integration.md`](docs/clova-ocr-integration.md)를 참고한다.

호스트 포트를 변경하려면 Compose 실행 전에 설정한다.

```powershell
$env:FOWOCO_PORT=8080
docker compose up -d --build
```

## 검증

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check app tests
docker compose config --quiet
```

문서 변환의 구조 검증과 별도로 신규 양식, 특수 글꼴, 수식, 그리기 개체를 추가할
때는 PDF 시각 회귀 검증도 수행해야 한다.

## 운영 참고

- 업로드와 변환 중간 파일은 요청별 임시 디렉터리에 저장하고 응답 후 제거한다.
- 스냅샷은 Docker의 `fowoco-document-data` 볼륨에 영속 저장한다.
- 현재 파일 스냅샷 저장소는 단일 테넌트 기준이다.
- 대용량 파일이나 높은 동시성이 필요하면 변환 작업을 별도 작업 큐로 분리한다.
