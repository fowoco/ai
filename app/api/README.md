# Internal API

## Swagger 태그 구성

문서 API의 URL은 `/api/v1/documents` 아래에 유지하고 Swagger UI에서는 기능별로
다음 그룹을 분리한다.

| Swagger 태그 | 엔드포인트 |
|---|---|
| Analyses | `POST /internal/v1/analyses` |
| Document Capabilities | `GET /api/v1/documents/capabilities` |
| Document Templates | `GET /api/v1/documents/templates`, `GET /api/v1/documents/templates/{template_id}` |
| Document Inspection | `POST /api/v1/documents/inspect` |
| Document Editing | `POST /api/v1/documents/edit` |
| Document Generation | `POST /api/v1/documents/generate`, `POST /api/v1/documents/generate/from-txt` |
| Document Conversion | `POST /api/v1/documents/convert` |

포맷별 변환 URL은 별도로 만들지 않는다. HWP, HWPX, XML, PDF 사이의 지원되는
모든 변환은 `POST /api/v1/documents/convert` 하나에서 입력 파일을 감지하고
`target_format`에 따라 처리한다.

`app/api`는 FastAPI 라우팅, 요청·응답 검증, 파일 전송, 문서 서비스 조립을 담당한다.
실제 HWP/HWPX 편집이나 외부 변환 프로세스 실행 코드는 `app/documents`에 둔다.
내부 문서 처리 방식은 [문서 처리 아키텍처](../documents/README.md)를 참고한다.

## 진입점

| 항목 | 주소 |
|---|---|
| Swagger UI | `GET /docs` |
| OpenAPI JSON | `GET /openapi.json` |
| 자연어 분석 | `POST /internal/v1/analyses` |
| 문서 기능 조회 | `GET /api/v1/documents/capabilities` |
| 템플릿 목록 | `GET /api/v1/documents/templates` |
| 템플릿 상세 | `GET /api/v1/documents/templates/{template_id}` |
| 문서 식별 | `POST /api/v1/documents/inspect` |
| 문서 편집 | `POST /api/v1/documents/edit` |
| 문서 생성 | `POST /api/v1/documents/generate` |
| TXT 레코드 기반 문서 생성 | `POST /api/v1/documents/generate/from-txt` |
| 범용 문서 변환 | `POST /api/v1/documents/convert` |

## 템플릿과 문서 식별

`GET /documents/templates`는 같은 양식의 HWP/HWPX 변형을 하나의 `template_id` 아래에
묶어서 반환한다. HWP 변형은 등록된 필드의 이름·종류·이미지 크기를 제공한다.
HWPX 변형은 현재 표의 동적 라벨을 사용하므로 `supports_dynamic_labels=true`로
표시한다.

`POST /documents/inspect`는 `file` 하나를 받아 실제 포맷, 편집 지원 여부, SHA-256으로
식별된 템플릿 ID를 반환한다. 등록 원본에서 이미 편집된 HWP/HWPX는 포맷은 감지되지만
템플릿 ID는 `null`일 수 있다.

## 문서 편집

```http
POST /api/v1/documents/edit
Content-Type: multipart/form-data
```

| 필드 | 형식 | 필수 | 설명 |
|---|---|---:|---|
| `file` | binary | 예 | 편집할 HWP 또는 HWPX |
| `payload` | JSON string | 예 | 템플릿, 값, 신청 옵션, asset 매핑 |
| `assets` | binary[] | 아니요 | HWP 사진·서명 파일 |

`payload` 예시:

```json
{
  "template_id": "immigration_integrated_application_v34",
  "values": {
    "family_name": "HONG",
    "given_names": "GILDONG",
    "application_stay_extension": true
  },
  "assets": {
    "photo": "photo.jpg",
    "applicant_signature": "signature.png"
  }
}
```

```powershell
curl.exe -X POST "http://localhost:8000/api/v1/documents/edit" `
  -F "file=@application.hwp" `
  -F 'payload={"template_id":"immigration_integrated_application_v34","values":{"family_name":"HONG"},"assets":{"photo":"photo.jpg"}}' `
  -F "assets=@photo.jpg" `
  --output edited.hwp
```

편집 결과는 입력과 같은 포맷이다. HWP는 텍스트·체크박스·사진·서명을 지원한다.
HWPX는 `values`와 `application_options`의 동적 라벨 편집을 지원하지만 구조화된 이미지
삽입은 아직 지원하지 않으며 asset 요청 시 HTTP 422를 반환한다.

HWP는 바이너리 레코드 위치를 안전하게 사용하기 위해 등록된 원본 SHA-256과 템플릿
맵이 일치해야 한다. `template_id`를 생략하면 원본 해시로 자동 식별한다.

성공 응답에는 다음 헤더가 포함된다.

- `X-Document-Template-Id`
- `X-Changed-Field-Count`

## 문서 생성

`POST /documents/generate`는 원본 파일 없이 등록된 템플릿으로 HWP/HWPX를 생성한다.

```json
{
  "template_id": "immigration_integrated_application_v34",
  "format": "hwpx",
  "values": {"성": "PARK", "명": "API"},
  "application_options": {"외국인 등록": true}
}
```

사진·서명이 필요한 HWP 생성은 `/edit`과 동일하게 `assets` 파일과
`payload.assets`의 `필드명 → 파일명` 매핑을 사용한다.

### 테스트 TXT 레코드로 HWP 생성

DB 연결 전에는 `POST /api/v1/documents/generate/from-txt`로 네 개 고정 양식의
규칙 기반 자동 기입을 테스트한다.

```powershell
curl.exe -X POST "http://localhost:8000/api/v1/documents/generate/from-txt" `
  -F "template_id=immigration_integrated_application_v34" `
  -F "file=@tests/fixtures/documents/records/immigration_integrated_application_v34.txt;type=text/plain" `
  --output generated.hwp
```

TXT는 UTF-8이며 빈 줄과 `#` 주석을 제외하고 한 줄에 하나의 `key=value`를
작성한다.

```text
company.name=주식회사 한빛정밀
worker.legal_name=NGUYEN VAN AN
worker.nationality=베트남
worker.phone=010-1111-2222
```

`company.company_id`처럼 매핑 규칙에 없는 컬럼은 무시한다. `worker.legal_name`
과 `worker.phone`은 암호화 컬럼을 복호화한 문서용 projection 별칭이다.
서버는 HWPX 내부 XML에 값을 입력한 다음 COM 없이 HWP로 변환해 반환한다.
PDF가 필요하면 반환된 HWP를 `/convert`에 전달한다.

생성 응답의 다운로드 파일명은 `template_id.hwp`가 아니라 다음 공식 양식명을
사용한다.

- `통합신청서(신고서).hwp`
- `[별지 제6호서식] 표준근로계약서(Standard Labor Contract)(외국인근로자의 고용 등에 관한 법률 시행규칙).hwp`
- `[별지 제12호의3서식] 취업기간 만료자 취업활동 기간 연장신청서(외국인근로자의 고용 등에 관한 법률 시행규칙).hwp`
- `신원보증서(한글).hwp`

`GET /api/v1/documents/templates`와 개별 템플릿 조회 응답의 `display_name`도 같은
공식 양식명을 반환한다. 내부 연동에는 기존의 안정적인 `template_id`를 계속
사용한다.

테스트 TXT는 ERD에서 조회 가능한 projection과 ERD에 없는 사용자·Agent 보완값을
함께 담는다. 현재 scalar XML 규칙 전체가 적용되며 양식별 변경 필드 수는
신원보증서 24개, 취업기간 연장신청서 21개, 통합신청서 40개,
표준근로계약서 70개다. 신원보증서는 한자 이름, 성별 체크, 작성일과 하단 보증인
이름까지 기입한다. 사진·서명 파일과 그 밖의 선택형 체크박스는 별도 asset·option
기능이므로 이 개수에 포함되지 않는다.

신원보증서의 추가 입력 키는 다음과 같다.

```text
foreign_name_hanja=阮文安
foreign_male=true
guarantor_name_hanja=金民洙
guarantor_male=true
guarantee_date=2026년 7월 24일
```

여성을 선택하려면 `foreign_female=true` 또는 `guarantor_female=true`를 사용한다.
하단 보증인 이름은 기존 `guarantor_name` 값을 자동으로 한 번 더 사용한다.

## 범용 문서 변환

```http
POST /api/v1/documents/convert
Content-Type: multipart/form-data
```

요청 필드는 두 개뿐이다.

| 필드 | 형식 | 필수 | 설명 |
|---|---|---:|---|
| `file` | binary | 예 | HWP, HWPX, XML 또는 PDF 입력 |
| `target_format` | string | 예 | `hwp`, `hwpx`, `xml`, `pdf` 중 출력 포맷 |

`source_format`, `options`, `template_id`는 받지 않는다. 서버가 다음 구조를 검사해 입력
포맷을 자동 판별한다.

- HWP: OLE/CFB 컨테이너와 `FileHeader`
- HWPX: ZIP 패키지와 `mimetype`
- XML: 안전한 XML 파싱
- PDF: `%PDF-` 헤더

파일 확장자가 알려진 포맷이면서 감지 결과와 다르면 HTTP 400을 반환한다. 성공 응답의
`X-Detected-Source-Format` 헤더에서 감지된 입력 포맷을 확인할 수 있다.

### HWP→XML

```powershell
curl.exe -X POST "http://localhost:8000/api/v1/documents/convert" `
  -F "file=@document.hwp" `
  -F "target_format=xml" `
  --output document.xml
```

이 호출은 XML만 추출하는 것이 아니라 원본 리소스가 포함된 HWPX 스냅샷도 영속
저장한다. 반환 XML에는 원본 패키지를 가리키는 불투명한 `snapshot-ref`가 포함된다.

### 편집한 XML→HWP

```powershell
curl.exe -X POST "http://localhost:8000/api/v1/documents/convert" `
  -F "file=@document.xml" `
  -F "target_format=hwp" `
  --output document.hwp
```

### 편집한 XML→PDF

```powershell
curl.exe -X POST "http://localhost:8000/api/v1/documents/convert" `
  -F "file=@document.xml" `
  -F "target_format=pdf" `
  --output document.pdf
```

XML 내부 `snapshot-ref`가 있으면 파일명을 바꿔도 정확한 원본 스냅샷을 찾는다. 참조가
없으면 확장자를 제외한 XML 파일명으로 최신 스냅샷 별칭을 조회한다.

## 지원 조합

실행 중인 worker에 실제 등록된 변환 조합은
`/api/v1/documents/capabilities` 응답을 기준으로 판단한다. Docker 기본 구성에서는
다음 조합을 제공한다.

```text
HWP  → HWPX, XML, PDF
HWPX → HWP,  XML, PDF
XML  → HWP,  HWPX, PDF
```

직접 변환기가 없으면 가장 짧은 변환 그래프를 조합한다.

```text
HWP → XML: HWP → HWPX → XML
XML → HWP: XML → HWPX → HWP
XML → PDF: XML → HWPX → PDF
```

HWP는 LibreOffice로 바로 PDF 변환한다. HWPX→PDF가 문서 호환성 문제로 실패하면
`HWPX → HWP → PDF` fallback을 자동 실행하며 XML→PDF도 같은 fallback을 사용한다.

## 응답과 오류

성공 시 변환 파일을 attachment로 반환하며 원래 파일명의 stem과 출력 확장자를
사용한다.

| 상태 | 의미 |
|---:|---|
| 200 | 변환 성공 |
| 400 | 알려진 파일 확장자와 실제 감지 포맷이 일치하지 않음 |
| 404 | XML이 참조하는 스냅샷을 찾을 수 없음 |
| 409 | 같은 문서 이름이 서로 다른 양식 구조에 이미 연결됨 |
| 413 | 업로드 크기 제한 초과 |
| 422 | 지원하지 않는 조합, 손상된 문서, 변환 실패 |
| 503 | Java, rhwp, LibreOffice 등 설정된 엔진을 사용할 수 없음 |

기본 업로드 제한은 50 MiB이며
`FOWOCO_DOCUMENT_UPLOAD_MAX_BYTES`로 변경한다. 현재 변환 API는 동기 방식이므로
reverse proxy에도 요청 크기와 timeout을 함께 설정해야 한다.

## 코드 배치

```text
app/api/
├─ dependencies.py                 worker 단위 서비스·변환기 조립
├─ router.py                       `/api/v1` 하위 라우터 구성
├─ routes/documents/
│  ├─ capabilities.py              등록된 기능 조회
│  ├─ templates.py                 템플릿 목록·상세
│  ├─ inspect.py                   포맷·템플릿 식별
│  ├─ edit.py                      업로드 문서 편집
│  ├─ generate.py                  템플릿 문서 생성
│  └─ convert.py                   업로드·변환·다운로드
└─ schemas/documents/
   ├─ capabilities.py              capability 응답 모델
   └─ editing.py                   편집·생성·템플릿 모델
```

새 API를 추가할 때 지킬 경계:

- 라우트는 HTTP 입력을 도메인 타입으로 바꾸고 오류를 HTTP 상태로 매핑한다.
- 파일 포맷 로직과 외부 프로세스 실행은 `app/documents`에 구현한다.
- 구현체 조립은 `dependencies.py`에서 수행한다.
- OpenAPI 요청 필드와 실제 동작을 API 테스트로 함께 고정한다.
