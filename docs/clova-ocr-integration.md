# CLOVA Template OCR 연동 계약

이 문서는 `fowoco/ai`가 원본 여권 또는 외국인등록증 파일을 받아 CLOVA Template
OCR로 인식하고, 외부에서 준비된 PostgreSQL `worker_document` 행에 결과를 직접
저장하는 내부 연동 계약이다. `fowoco/server`의 호출 코드와 DB 마이그레이션은 이
구현 범위 밖이며 이 브랜치에서 수정하지 않는다.

## 처리 흐름

1. 인증된 호출자가 원본 파일과 문서·근로자·회사 식별자를 AI에 전송한다.
2. AI가 문서 종류와 국가에 맞는 배포 템플릿 후보만 CLOVA `/infer`에 전달한다.
3. AI가 템플릿 필드명과 같은 이름의 허용 컬럼만 정규화한다.
4. 같은 DB 트랜잭션에서 `app.company_id`를 먼저 설정한 뒤 범위가 일치하는
   `worker_document` 한 행만 갱신한다.
5. HTTP 응답에는 인식된 신원정보를 포함하지 않고 처리 상태만 반환한다.

Document OCR가 아닌 CLOVA Template OCR V2를 사용한다. 한 요청에는 JPEG, PNG
또는 한 페이지 PDF 하나만 허용하며 파일 크기 상한은 20 MiB이다. CLOVA가 여러
`images` 결과를 반환하면 첫 결과만 구조화하고 상태를 `REVIEW_REQUIRED`로 저장한다.

## 내부 HTTP API

```text
POST /internal/v1/ocr/worker-documents/{worker_document_id}
Authorization: Bearer <FOWOCO_INTERNAL_API_TOKEN>
Content-Type: multipart/form-data
```

multipart 필드:

| 이름 | 형식 | 규칙 |
| --- | --- | --- |
| `file` | binary | 원본 JPEG, PNG 또는 PDF |
| `request_id` | UUID | 추적 및 동일 재시도 식별자 |
| `worker_id` | UUID | DB 행 범위 |
| `company_id` | UUID | 테넌트 및 RLS 범위 |
| `document_type` | enum | `PASSPORT_COPY` 또는 `ARC` |
| `country_code` | string | 여권은 `KOR`, `PHL`, `JPN`, `CHN`, `VNM` 중 하나, ARC는 생략 가능 |

성공 또는 검토 필요 응답은 HTTP 200이며 구조는 다음과 같다.

```json
{
  "request_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  "worker_document_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  "ocr_status": "SUCCEEDED",
  "matched_template_id": 43019,
  "document_side": null,
  "review_reasons": []
}
```

응답과 애플리케이션 로그에는 여권번호, 외국인등록번호, 이름, 주소, 원본 파일 또는
CLOVA 원문 응답을 기록하지 않는다.

## 배포 템플릿

| 문서 | 국가/면 | 템플릿 ID | 템플릿명 |
| --- | --- | ---: | --- |
| 여권 | KOR | 43019 | `KOR_PASSPORT` |
| 여권 | PHL | 43021 | `PHL_PASSPORT` |
| 여권 | JPN | 43022 | `JPN_PASSPORT` |
| 여권 | CHN | 43023 | `CHN_PASSPORT` |
| 여권 | VNM | 43038 | `VNM_PASSPORT` |
| 외국인등록증 | 앞면 | 43024 | `KOR_ARC_FRONT` |
| 외국인등록증 | 뒷면 | 43025 | `KOR_ARC_BACK` |

ARC 요청에는 43024와 43025를 함께 전달하고 `matchedTemplate.id`로 `FRONT` 또는
`BACK`을 결정한다.

## 환경 설정

```text
FOWOCO_CLOVA_OCR_ENABLED=true
FOWOCO_CLOVA_OCR_INVOKE_URL=<API Gateway /infer URL>
FOWOCO_CLOVA_OCR_SECRET=<X-OCR-SECRET value>
FOWOCO_CLOVA_OCR_TIMEOUT_SECONDS=30
FOWOCO_CLOVA_OCR_CONFIDENCE_THRESHOLD=0.80
FOWOCO_DATABASE_URL=postgresql://<restricted-role>@<host>/<database>
FOWOCO_INTERNAL_API_TOKEN=<internal bearer token>
```

OCR은 기본적으로 비활성화된다. 활성화했는데 invoke URL, secret, DB URL 또는 내부
Bearer 토큰이 없으면 애플리케이션이 기동 전에 실패한다. secret과 DB 자격 증명은
환경변수로만 주입하며 커밋하거나 로그로 출력하지 않는다.

## 외부 DB 선행 조건

AI는 테이블을 생성하거나 변경하지 않는다. 외부에서 아래 컬럼을 먼저 준비해야 한다.

| 그룹 | 컬럼과 PostgreSQL 형식 |
| --- | --- |
| 범위 | `worker_document_id UUID`, `worker_id UUID`, `company_id UUID`, `document_type VARCHAR` |
| OCR 메타데이터 | `ocr_status VARCHAR(20)`, `ocr_request_id UUID`, `ocr_template_id BIGINT`, `ocr_document_side VARCHAR(10)`, `ocr_field_confidences JSONB`, `ocr_error_code VARCHAR(60)`, `ocr_processed_at TIMESTAMPTZ` |
| 여권 | `passport_number VARCHAR(32)`, `surname VARCHAR(120)`, `given_names VARCHAR(160)`, `nationality VARCHAR(80)`, `date_of_birth DATE`, `sex VARCHAR(20)`, `passport_issue_date DATE`, `passport_expiry_date DATE` |
| ARC 앞면 | `alien_registration_number VARCHAR(32)`, `full_name VARCHAR(200)`, `visa_type VARCHAR(40)`, `alien_registration_issue_date DATE` |
| ARC 뒷면 | `stay_permit_date DATE`, `stay_expiration_date DATE`, `residence_report_date_1 DATE`, `residence_confirmation_1 VARCHAR(160)`, `residence_address_1 VARCHAR(300)`, `residence_report_date_2 DATE`, `residence_confirmation_2 VARCHAR(160)`, `residence_address_2 VARCHAR(300)` |

ARC 앞면은 여권 그룹의 `nationality`, `sex`도 공유한다. 모든 구조화 필드는 nullable,
`ocr_status`는 기본값 `NOT_REQUESTED`, `ocr_field_confidences`는 기본 빈 JSON 객체여야
한다. AI 시작 시 컬럼 집합을 검사하고 누락 시 컬럼명만 포함한 오류로 기동을 중단한다.

예시 최소 권한 역할은 다음과 같다. 실제 역할 생성과 권한 부여는 DB 소유자가 수행한다.

```sql
CREATE ROLE fowoco_ai_ocr LOGIN;
GRANT USAGE ON SCHEMA public TO fowoco_ai_ocr;
GRANT SELECT (worker_document_id, worker_id, company_id, document_type)
    ON public.worker_document TO fowoco_ai_ocr;
GRANT UPDATE (
    ocr_status, ocr_request_id, ocr_template_id, ocr_document_side,
    ocr_field_confidences, ocr_error_code, ocr_processed_at,
    passport_number, surname, given_names, nationality, date_of_birth, sex,
    passport_issue_date, passport_expiry_date,
    alien_registration_number, full_name, visa_type, alien_registration_issue_date,
    stay_permit_date, stay_expiration_date,
    residence_report_date_1, residence_confirmation_1, residence_address_1,
    residence_report_date_2, residence_confirmation_2, residence_address_2
) ON public.worker_document TO fowoco_ai_ocr;
```

모든 `worker_document` 조회와 갱신은 같은 트랜잭션에서 먼저 다음 구문을 실행한다.

```sql
SELECT pg_catalog.set_config('app.company_id', '<company UUID>', true);
```

행 조건은 항상 `worker_document_id`, `worker_id`, `company_id`를 모두 포함한다. AI는
`submission_status`, 기존 `expiry_date`, `updated_at`, `version`을 갱신하지 않는다.

## 필드 정규화와 상태

- 템플릿 `fields[].name`이 승인된 DB 컬럼명과 정확히 같은 경우만 저장한다.
- 문자열 양끝과 반복 공백을 정리하고, 식별번호에서는 공백만 제거한다.
- 날짜는 `YYYY-MM-DD`, `YYYY.MM.DD`, `YYYY/MM/DD`만 `DATE`로 변환한다.
- 여권 필수 필드는 `passport_number`, `surname`, `given_names`, `nationality`,
  `date_of_birth`, `passport_expiry_date`이다.
- ARC 앞면 필수 필드는 `alien_registration_number`, `full_name`이다.
- ARC 뒷면은 `stay_*` 또는 `residence_*` 중 하나 이상이 인식돼야 한다. 두 번째
  거소 행의 빈 템플릿 상자는 무시한다.
- 필수값 누락, 기준 미만 신뢰도, 잘못된 날짜, 불일치 템플릿은
  `REVIEW_REQUIRED`로 저장한다.

| 상황 | HTTP | DB `ocr_status` |
| --- | ---: | --- |
| 정상 인식 | 200 | `SUCCEEDED` |
| 검토 필요 | 200 | `REVIEW_REQUIRED` |
| 잘못된 요청 | 400/422 | 변경 없음 |
| 범위 행 없음 | 404 | 변경 없음 |
| CLOVA 오류 | 502 | `FAILED`, `CLOVA_ERROR` |
| CLOVA 타임아웃 | 504 | `FAILED`, `CLOVA_TIMEOUT` |
| DB 오류 | 500 | 트랜잭션 결과에 따름 |
| OCR 비활성/미기동 | 503 | 변경 없음 |

AI는 자동 재시도를 수행하지 않는다. 호출자는 같은 `request_id`로 재호출할 수 있고
같은 범위 행을 안전하게 갱신한다. 공급자 실패 재시도는 이전 구조화 값을 지우지 않지만,
소비자는 `SUCCEEDED` 또는 사람이 확인한 `REVIEW_REQUIRED` 상태의 값만 신뢰해야 한다.

## 직접 AI 스모크 테스트

실제 외부 스키마, 제한 DB 계정, CLOVA 설정과 비운영 샘플이 준비된 경우에만 실행한다.

```powershell
$env:FOWOCO_INTERNAL_API_TOKEN="..."
$env:OCR_SAMPLE_FILE="C:\samples\synthetic-passport.png"
$env:OCR_WORKER_DOCUMENT_ID="..."
$env:OCR_WORKER_ID="..."
$env:OCR_COMPANY_ID="..."
$env:OCR_DOCUMENT_TYPE="PASSPORT_COPY"
$env:OCR_COUNTRY_CODE="KOR"
$env:FOWOCO_AI_BASE_URL="http://localhost:8000" # 선택
.\scripts\smoke_clova_ocr.ps1
```

`OCR_COUNTRY_CODE`는 `OCR_DOCUMENT_TYPE=ARC`일 때만 생략할 수 있다. 스크립트는 HTTP
상태, `ocr_status`, 템플릿 ID, 면, 검토 사유만 출력하며 파일 내용이나 인식 필드는
출력하지 않는다.
