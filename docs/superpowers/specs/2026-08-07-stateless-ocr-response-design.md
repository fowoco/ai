# Stateless OCR 응답 설계

**작성일:** 2026-08-07

**이슈:** AI #20

**상태:** 구현 승인

## 목표

근로자 문서 OCR API를 DB 저장형 흐름에서 Stateless 추론 계약으로 변경한다. Server는
문서 소유권과 사업장 범위를 검증하고 AI 응답을 검증·암호화·저장한다. AI Runtime은
파일을 검증하고 CLOVA Template OCR를 호출한 뒤 허용 필드만 정규화해 반환하며 Server
PostgreSQL을 조회하거나 수정하지 않는다.

## 역할 경계

### Server

- AI 호출 전에 문서 소유권과 사업장 권한을 확인한다.
- 원본 파일과 Server가 발급한 요청 식별자를 전달한다.
- AI 응답을 검증하고 민감정보를 암호화해 저장한다.
- HR 검토가 끝난 값을 Worker와 Document에 반영한다.

### AI

- 업로드 파일을 검증한다.
- 배포된 allowlist에서 CLOVA Template을 선택한다.
- CLOVA Template OCR를 호출한다.
- 허용 필드와 신뢰도만 정규화해 반환한다.
- Server PostgreSQL을 조회하거나 수정하지 않는다.

## HTTP 계약

### 요청

```http
POST /internal/v1/ocr/worker-documents/{worker_document_id}
Authorization: Bearer <internal-token>
X-Request-Id: <request-id>
Content-Type: multipart/form-data
```

| Multipart 필드 | 계약 |
|---|---|
| `file` | JPEG·PNG·한 페이지 PDF, 최대 20 MiB |
| `request_id` | Server가 발급한 UUID |
| `document_type` | `PASSPORT_COPY` 또는 `ARC` |
| `country_code` | 여권 Template 선택 코드, ARC는 생략 가능 |

근로자·사업장 식별자는 제거한다. `X-Request-Id`와 multipart `request_id`는 모두
필수이며 같은 UUID여야 한다. 불일치는 CLOVA 호출 전에 거부한다.

여권 `country_code`는 ISO 3166-1 alpha-3 대문자를 사용하며 기존 배포 Template
allowlist를 유지한다.

| 국가 코드 | Template ID |
|---|---:|
| `KOR` | 43019 |
| `PHL` | 43021 |
| `JPN` | 43022 |
| `CHN` | 43023 |
| `VNM` | 43038 |

ARC는 43024와 43025를 사용하며 전달된 `country_code`를 무시한다.

### 응답

```json
{
  "request_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  "worker_document_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  "ocr_status": "SUCCEEDED",
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

`fields`에는 기존 정규화 allowlist를 통과한 값만 포함한다. `field_confidences`에는
해당 필드의 정규화된 신뢰도를 포함한다. Python `date` 값은 응답 모델이
`YYYY-MM-DD` 문자열로 직렬화한다.

## 애플리케이션 설계

HTTP route는 인증, transport 형식, 두 요청 ID의 일치를 검증한다. 이후
`request_id`, `worker_document_id`, `document_type`, `country_code`, `file`만 포함한
`OcrCommand`를 만든다.

`OcrService.process`의 처리 순서는 다음과 같다.

1. 파일 내용, MIME, 크기, 파일명을 검증한다.
2. 기존 Template allowlist로 호출 대상을 선택한다.
3. AI 자체 재시도 없이 CLOVA를 한 번 호출한다.
4. 기존 allowlist·날짜·문서 면·신뢰도·검토 사유 규칙으로 응답을 정규화한다.
5. 상태, Template 메타데이터, 필드, 신뢰도, 검토 사유가 포함된 결과를 반환한다.

서비스에는 Repository와 clock 의존성이 없다. DB tenant 범위만 운반하던 `OcrScope`를
제거하고 `worker_document_id`는 응답 상관관계 용도로만 사용한다.

OCR lifespan은 `httpx.AsyncClient`와 CLOVA client만 생성·정리한다. PostgreSQL pool을
만들거나 schema를 검사하지 않는다.

## 제거 범위

- `PsycopgWorkerDocumentOcrRepository`와 전용 테스트
- OCR의 DB URL 설정
- 프로젝트의 `psycopg[binary,pool]` 의존성과 관련 잠금 항목
- `DatabaseSchemaMismatch`, `WorkerDocumentNotFound`, `OcrPersistenceError`,
  `OcrRequestSuperseded`
- DB 전용 HTTP 404·409·500 변환

## 오류 계약

| 조건 | HTTP 상태 |
|---|---:|
| 필수 UUID·enum·header·multipart 누락 또는 형식 오류 | 422 |
| header와 multipart 요청 ID 불일치 | 400 |
| 빈 파일, 미지원 MIME, 위험한 파일명, 여권 국가 누락·미지원 | 400 |
| 20 MiB 초과 | 413 |
| CLOVA 전송·상태·응답 크기·JSON·인식 오류 | 502 |
| CLOVA timeout | 504 |
| OCR 비활성 또는 런타임 미준비 | 503 |

Provider 오류는 CLOVA 응답 본문, 제출 필드 값, 파일명·bytes, secret, 요청 식별자를
클라이언트 오류에 노출하지 않는 안전한 wrapper로 유지한다.

## 개인정보와 로그

- 원본 파일과 CLOVA 원문 응답은 요청 처리 동안 메모리에서만 사용하고 반환하지 않는다.
- 두 원문과 정규화된 민감 필드를 일반 로그에 기록하지 않는다.
- 정규화 값은 인증된 내부 응답에만 포함한다.
- 오류 메시지는 고정된 비민감 설명을 사용한다.
- 알 수 없는 CLOVA 필드는 응답 생성 전에 버린다.

## Renewal OCR Bridge

기존 Renewal Bridge는 최상위 `fields` mapping을 받을 수 있다. 실제 Stateless 응답
envelope를 사용하는 회귀 테스트로 `fields`만 `ocr_result`와 갱신 slot에 반영되고,
신뢰도와 응답 메타데이터는 근로자 필드로 해석되지 않음을 검증한다.

## 테스트와 문서

구현은 테스트 우선으로 진행한다.

1. 서비스 테스트를 Repository 없는 처리와 필드 반환 계약으로 변경한다.
2. API 테스트에서 범위 식별자를 제거하고 요청 ID 일치, 전체 응답, 상태 코드를 검증한다.
3. 런타임·설정 테스트로 DB 계정 없이 OCR가 활성 기동됨을 증명한다.
4. Renewal Bridge에 Stateless 응답 회귀 테스트를 추가한다.
5. 기존 Template resolver, CLOVA client, normalizer 회귀 테스트를 유지한다.
6. 운영 문서와 smoke script를 새 계약에 맞춘다.

## 완료 조건

- AI Runtime이 Server DB 계정 없이 OCR 활성 상태로 기동된다.
- OCR 응답이 정규화 값과 필드별 신뢰도를 포함한다.
- AI OCR 코드가 Server PostgreSQL을 조회하거나 수정하지 않는다.
- 원본 파일, CLOVA 원문, 정규화된 민감 필드가 일반 로그에 남지 않는다.
- 기존 CLOVA Template OCR와 Renewal Bridge 회귀 테스트가 통과한다.
- Server 저장·암호화·HR 승인·Migration·Client API는 이 변경에 포함하지 않는다.
