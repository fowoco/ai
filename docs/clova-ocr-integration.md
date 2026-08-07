# CLOVA Template OCR 연동 계약

AI Runtime은 여권 사본과 외국인등록증 파일을 CLOVA Template OCR로 처리하고,
허용된 필드만 정규화해 Server에 반환한다. 문서 소유권·사업장 권한 검증과 결과
검증·암호화·저장은 Server가 담당한다. AI는 Server PostgreSQL을 조회하거나 수정하지
않는다.

## 역할 경계

### Server

1. 문서 소유권과 사업장 접근 권한을 확인한다.
2. Server가 발급한 요청 ID와 파일을 AI에 전달한다.
3. AI 응답의 필드와 신뢰도를 검증한다.
4. 민감정보를 암호화해 저장한다.
5. HR 검토가 끝난 값을 Worker와 Document에 반영한다.

### AI

1. 파일 크기·MIME·파일명을 검증한다.
2. 배포된 Template allowlist에서 호출 대상을 선택한다.
3. CLOVA Template OCR를 한 번 호출한다.
4. 허용된 필드와 필드별 신뢰도만 정규화한다.
5. 저장 없이 구조화 결과를 반환한다.

## 요청 계약

```http
POST /internal/v1/ocr/worker-documents/{worker_document_id}
Authorization: Bearer <internal-token>
X-Request-Id: <request-id>
Content-Type: multipart/form-data
```

| Multipart 필드 | 형식 | 설명 |
|---|---|---|
| `file` | binary | JPEG·PNG·한 페이지 PDF, 최대 20 MiB |
| `request_id` | UUID | Server가 발급한 실행 추적 ID |
| `document_type` | enum | `PASSPORT_COPY` 또는 `ARC` |
| `country_code` | string | 여권 Template 선택용 alpha-3 코드, ARC는 생략 가능 |

`X-Request-Id`와 multipart `request_id`는 모두 필수이며 같은 UUID여야 한다. AI가 DB
범위를 확인하지 않으므로 근로자·사업장 식별자는 요청하지 않는다.

## Template allowlist

| 문서 | 국가/면 | Template ID |
|---|---|---:|
| 여권 | `KOR` | 43019 |
| 여권 | `PHL` | 43021 |
| 여권 | `JPN` | 43022 |
| 여권 | `CHN` | 43023 |
| 여권 | `VNM` | 43038 |
| 외국인등록증 | 앞면 | 43024 |
| 외국인등록증 | 뒷면 | 43025 |

Server의 일반 국적 코드가 ISO 3166-1 alpha-2라면 AI 호출 전에 alpha-3로 변환한다.
현재 대응은 `KR→KOR`, `PH→PHL`, `JP→JPN`, `CN→CHN`, `VN→VNM`이다. 배포된 여권
Template이 없는 국가는 Server가 AI 호출 전에 지원하지 않는 OCR 국가로 처리한다.
ARC 요청은 `country_code`를 보내지 않는다. AI는 ARC에 값이 오더라도 Template 선택에
사용하지 않는다.

## 응답 계약

```json
{
  "request_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  "worker_document_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  "ocr_status": "REVIEW_REQUIRED",
  "matched_template_id": 43019,
  "document_side": null,
  "fields": {
    "passport_number": "M12345678",
    "surname": "NGUYEN",
    "given_names": "VAN AN",
    "date_of_birth": "1995-03-01",
    "passport_expiry_date": "2028-03-01"
  },
  "field_confidences": {
    "passport_number": 0.98,
    "surname": 0.94,
    "given_names": 0.91,
    "date_of_birth": 0.99,
    "passport_expiry_date": 0.97
  },
  "review_reasons": []
}
```

- `ocr_status`는 정상 결과면 `SUCCEEDED`, 누락·형식·신뢰도 검토가 필요하면
  `REVIEW_REQUIRED`이다.
- `fields`에는 기존 정규화 allowlist를 통과한 값만 포함한다.
- 날짜는 `YYYY-MM-DD` 문자열로 반환한다.
- `field_confidences`에는 정규화 대상 필드별 `0.0..1.0` 신뢰도를 포함한다.
- ARC의 `document_side`는 `FRONT` 또는 `BACK`이며, 여권은 `null`이다.

## 허용 필드

| 필드 | 비고 |
|---|---|
| `passport_number` | 공백 제거 |
| `surname` | 내부 공백 정규화 |
| `given_names` | 내부 공백 정규화 |
| `date_of_birth` | 날짜 정규화 |
| `sex` | 문자열 정규화 |
| `passport_issue_date` | 날짜 정규화 |
| `passport_expiry_date` | 날짜 정규화 |
| `alien_registration_number` | 공백 제거 |
| `visa_type` | 문자열 정규화 |
| `stay_expiration_date` | 날짜 정규화 |
| `residence_address_1` | 문자열 정규화 |

allowlist에 없는 CLOVA 필드는 값과 신뢰도 모두 버린다.

## 오류 계약

| 조건 | HTTP 상태 |
|---|---:|
| 필수 header/form 누락, UUID·enum 형식 오류 | 422 |
| header와 multipart 요청 ID 불일치 | 400 |
| 빈 파일, 미지원 MIME, 위험한 파일명, 여권 국가 누락·미지원 | 400 |
| 파일이 20 MiB를 초과함 | 413 |
| CLOVA 전송·상태·응답 크기·JSON·인식 오류 | 502 |
| CLOVA timeout | 504 |
| OCR 비활성 또는 런타임 준비 실패 | 503 |

AI는 자동 재시도하지 않는다. 재시도와 결과 저장의 멱등성은 Server가 같은
`request_id`를 기준으로 관리한다.

## 환경변수

```dotenv
FOWOCO_CLOVA_OCR_ENABLED=false
FOWOCO_CLOVA_OCR_INVOKE_URL=https://example.invalid/clova-template-ocr
FOWOCO_CLOVA_OCR_SECRET=replace-with-secret
FOWOCO_CLOVA_OCR_TIMEOUT_SECONDS=30
FOWOCO_CLOVA_OCR_CONFIDENCE_THRESHOLD=0.80
FOWOCO_INTERNAL_API_TOKEN=replace-with-internal-token
```

OCR가 비활성화되면 CLOVA HTTP client를 만들지 않는다. 활성화할 때는 CLOVA URL,
secret, Internal API token이 필수다. Server DB 계정은 필요하지 않다.

## 개인정보와 로그

- 원본 파일과 CLOVA 원문 응답은 HTTP 응답에 포함하지 않는다.
- 원본 파일 bytes, CLOVA 원문, 정규화된 민감 필드 값을 일반 로그에 기록하지 않는다.
- Provider 오류 응답 본문이나 secret을 예외 메시지에 포함하지 않는다.
- 오류 응답은 고정된 안전한 설명만 사용한다.

## Smoke 실행

```powershell
$env:FOWOCO_INTERNAL_API_TOKEN="replace-with-internal-token"
$env:FOWOCO_AI_BASE_URL="http://localhost:8000"
$env:OCR_SAMPLE_FILE="C:\samples\passport.png"
$env:OCR_WORKER_DOCUMENT_ID="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
$env:OCR_DOCUMENT_TYPE="PASSPORT_COPY"
$env:OCR_COUNTRY_CODE="KOR"
./scripts/smoke_clova_ocr.ps1
```

smoke script는 요청 ID header와 multipart 값을 동일하게 전송한다. 성공 시 상태,
Template ID, 문서 면, 검토 사유, 반환 필드 개수만 출력하며 민감 필드 값과 신뢰도는
출력하지 않는다.
