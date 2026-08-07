# Stateless OCR Response Design

**Date:** 2026-08-07

**Issue:** AI #20

**Status:** Approved for implementation planning

## Objective

Change the internal worker-document OCR endpoint from a database-owning workflow to a
stateless inference contract. The Server validates document ownership and workplace scope,
calls the AI runtime, validates and encrypts the returned OCR data, and persists it. The AI
runtime validates the file, invokes an approved CLOVA Template OCR template, normalizes only
approved fields, and returns the structured result without reading or writing Server
PostgreSQL.

## Ownership Boundary

### Server

- Validate document ownership and workplace authorization before invoking AI.
- Supply the source file and Server-issued request identifier.
- Validate, encrypt, and persist the AI response.
- Apply reviewed values to Worker and Document records.

### AI

- Validate the uploaded file.
- Select an approved CLOVA template.
- Invoke CLOVA Template OCR.
- Normalize only allowlisted fields and confidences.
- Return the normalized result.
- Never query or mutate Server PostgreSQL.

## HTTP Contract

### Request

```http
POST /internal/v1/ocr/worker-documents/{worker_document_id}
Authorization: Bearer <internal-token>
X-Request-Id: <request-id>
Content-Type: multipart/form-data
```

Multipart fields:

| Field | Contract |
|---|---|
| `file` | JPEG, PNG, or single-page PDF; maximum 20 MiB |
| `request_id` | Server-issued UUID used for tracing |
| `document_type` | `PASSPORT_COPY` or `ARC` |
| `country_code` | Passport template selector; omit for ARC |

`worker_id` and `company_id` are removed. `X-Request-Id` and multipart `request_id` are both
required and must contain the same UUID. A mismatch is rejected before CLOVA is called.

Passport `country_code` uses uppercase ISO 3166-1 alpha-3 values. The existing deployed
template allowlist remains authoritative:

| Country code | Template ID |
|---|---:|
| `KOR` | 43019 |
| `PHL` | 43021 |
| `JPN` | 43022 |
| `CHN` | 43023 |
| `VNM` | 43038 |

ARC continues to use template IDs 43024 and 43025 and ignores `country_code` when supplied.

### Response

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

`fields` contains only the values approved by the existing normalizer allowlist.
`field_confidences` contains the corresponding normalized confidence values. Python `date`
values are serialized as ISO `YYYY-MM-DD` strings by the response model.

## Application Design

The HTTP route validates authentication, transport fields, and the equality of the two
request identifiers. It constructs an `OcrCommand` containing only `request_id`,
`worker_document_id`, `document_type`, `country_code`, and `file`.

`OcrService.process` has one linear responsibility:

1. Validate file content, MIME type, size, and filename.
2. Resolve the existing approved template allowlist.
3. Invoke CLOVA exactly once without an AI-side retry.
4. Normalize the CLOVA response with the existing allowlist, date parsing, document-side,
   confidence, and review-reason rules.
5. Return an `OcrProcessResult` containing status, template metadata, normalized fields,
   field confidences, and review reasons.

The service has no repository or clock dependency. `OcrScope` is removed because it exists
only to carry database tenant scope; `worker_document_id` becomes a direct command field used
only for response correlation.

The OCR application lifespan creates and closes only `httpx.AsyncClient` and the CLOVA client.
It does not create a PostgreSQL pool or perform schema verification.

## Removed Database Surface

The following are removed rather than retained as dead compatibility code:

- `PsycopgWorkerDocumentOcrRepository` and its module.
- Repository-specific tests.
- `FOWOCO_DATABASE_URL` / `database_url` OCR configuration.
- `psycopg[binary,pool]` project dependency and lockfile entries no longer needed by any
  project code.
- `DatabaseSchemaMismatch`, `WorkerDocumentNotFound`, `OcrPersistenceError`, and
  `OcrRequestSuperseded`.
- HTTP translations for database-only 404, 409, and 500 failures.

## Error Contract

| Condition | HTTP status |
|---|---:|
| Missing or malformed UUID, enum, required header, or multipart field | 422 |
| `X-Request-Id` differs from multipart `request_id` | 400 |
| Empty file, unsupported MIME, unsafe filename, missing/unsupported passport country | 400 |
| File larger than 20 MiB | 413 |
| CLOVA transport, status, response-size, JSON, or provider recognition failure | 502 |
| CLOVA timeout | 504 |
| OCR disabled or runtime service unavailable | 503 |

Provider failures remain safe wrappers. They do not expose CLOVA response bodies, submitted
field values, filenames, file bytes, secrets, or request identifiers in client error details.

## Privacy and Logging

- The original file and raw CLOVA response remain in memory only for the duration of the
  request and are never returned.
- Neither value is written to normal application logs.
- Normalized sensitive fields are returned only in the authenticated internal response and
  are not logged by the OCR path.
- Error messages use fixed, non-sensitive descriptions.
- Unknown CLOVA fields continue to be dropped before the response is built.

## Renewal OCR Bridge

The existing Renewal bridge already accepts a top-level `fields` mapping. A regression test
will pass a representative stateless HTTP response envelope containing `ocr_status`,
`fields`, `field_confidences`, and metadata. It will verify that only `fields` populate
`ocr_result` and renewal slots, while confidences and response metadata are not interpreted as
worker field values.

## Tests and Documentation

Implementation follows test-driven development:

1. Update service tests to specify repository-free orchestration and result fields.
2. Update endpoint tests to omit `worker_id` and `company_id`, require matching request IDs,
   validate the complete response, and cover 400/413/422/502/503/504 behavior.
3. Update runtime and settings tests to prove enabled OCR starts without a database URL and
   only creates the HTTP resource.
4. Add the Renewal Bridge stateless response regression test.
5. Retain and run Template resolver, CLOVA client, and normalizer regression tests.
6. Remove repository tests and assert source/dependencies no longer reference the deleted
   database surface.

Update the public developer surface in `docs/clova-ocr-integration.md`, `README.md`,
`.env.example`, and `scripts/smoke_clova_ocr.ps1`. The smoke script sends `X-Request-Id`, omits
the removed scope fields, and displays only status/metadata plus field names or counts; it does
not print sensitive normalized values.

## Acceptance Criteria

- The AI runtime starts with OCR enabled and no Server database credentials.
- The OCR response includes normalized values and field-level confidences.
- No AI OCR code reads or writes Server PostgreSQL.
- Raw files, raw CLOVA responses, and normalized sensitive fields do not enter normal logs.
- Existing CLOVA Template OCR behavior and the Renewal Bridge pass their regression suites.
- Server-side storage, encryption, HR review, migrations, and client-facing OCR APIs remain
  outside this change.
