# CLOVA Template OCR Integration Design

- Status: Approved
- Date: 2026-08-04
- Scope: `fowoco/ai` OCR runtime and `fowoco/server` database/file-transfer integration

## Objective

The Server sends an original passport or Korean alien registration card file to the AI service. The AI service selects a deployed CLOVA Template OCR template, extracts and normalizes configured fields, and writes the structured result directly into the existing PostgreSQL `worker_document` row.

This is a synchronous MVP. It does not introduce an OCR job queue, a separate OCR result table, or raw CLOVA response storage.

## Existing Context

The Server already stores `worker_document.document_type`, `worker_document.file_id`, and `worker.nationality_code`. Its current AI analysis contract does not send original files or OCR routing metadata.

The AI repository already contains an `OcrNode` protocol, `ExternalOcrEngine`, `OcrNodeAdapter`, output normalization, and a `StubOcrNode`. The new upload endpoint is a focused OCR application flow because the current renewal workflow request carries document metadata rather than file bytes. The existing graph abstractions remain available for later reuse; replacing the graph stub is not required for this MVP endpoint.

## Chosen Approach

The approved approach adds OCR columns directly to `worker_document`.

Alternatives considered:

1. A dedicated `worker_document_ocr_result` table would isolate OCR data cleanly but adds a table and join.
2. Adding columns to `worker_document` is the selected MVP because each row already represents one uploaded worker document and has a single `file_id`.
3. JSONB-only storage was rejected because the result must be queryable as structured data.

## Internal OCR API

The AI service exposes:

```text
POST /internal/v1/ocr/worker-documents/{worker_document_id}
Content-Type: multipart/form-data
Authorization: Bearer <internal token>
```

Required multipart fields:

| Field | Type | Rule |
| --- | --- | --- |
| `file` | binary | Original document file |
| `request_id` | UUID | Request tracing and idempotent retry identity |
| `worker_id` | UUID | Required DB scope |
| `company_id` | UUID | Required tenant scope |
| `document_type` | enum | `PASSPORT_COPY` or `ARC` |
| `country_code` | string | Required for passports; optional and ignored for ARC |

The endpoint reuses the existing internal bearer-token verification. One request represents one `worker_document` file. JPEG, PNG, and single-page PDF inputs are supported in the MVP. A multi-page PDF is returned as `REVIEW_REQUIRED` rather than merging multiple template matches into one row.

The response does not repeat extracted personally identifiable information. It returns:

```json
{
  "request_id": "uuid",
  "worker_document_id": "uuid",
  "ocr_status": "SUCCEEDED",
  "matched_template_id": 43019,
  "document_side": null,
  "review_reasons": []
}
```

## Template Routing

Passport templates are selected from the supplied country code:

| Document | Country | Template ID | Template name |
| --- | --- | ---: | --- |
| Passport | KOR | 43019 | `KOR_PASSPORT` |
| Passport | PHL | 43021 | `PHL_PASSPORT` |
| Passport | JPN | 43022 | `JPN_PASSPORT` |
| Passport | CHN | 43023 | `CHN_PASSPORT` |
| Passport | VNM | 43038 | `VNM_PASSPORT` |
| ARC front | KOR | 43024 | `KOR_ARC_FRONT` |
| ARC back | KOR | 43025 | `KOR_ARC_BACK` |

For a passport request, the AI sends exactly one template ID to CLOVA. An unsupported or missing country code is rejected before calling CLOVA.

For an ARC request, the AI sends template IDs `[43024, 43025]`. It maps `matchedTemplate.id` 43024 to `FRONT` and 43025 to `BACK`; the Server does not need to supply a side.

## AI Components

The implementation is split into focused components:

- **OCR API route** validates multipart input, applies internal authentication, and translates application outcomes to HTTP responses.
- **OCR application service** owns the processing sequence and status transitions.
- **Template resolver** maps `document_type` and `country_code` to allowed template IDs and maps ARC template IDs to sides.
- **CLOVA Template OCR client** creates a V2 multipart request using `httpx`, sends `X-OCR-SECRET`, and returns a provider-neutral result.
- **Field normalizer** maps `fields[].name` to configured structured fields, trims text, parses dates, and records `inferConfidence` by field name.
- **Worker document OCR repository** uses a Psycopg 3 async connection pool to verify the scoped row and update only OCR-owned columns.

The CLOVA invoke URL, secret, timeout, confidence threshold, and database URL are environment settings. Secrets and recognized text are never logged.

## Processing Flow

1. The Server resolves `file_id`, reads the original bytes, and sends the multipart request with identifiers and routing metadata.
2. The AI verifies the file, identifiers, `document_type`, and passport `country_code`.
3. The AI verifies that `worker_document_id`, `worker_id`, `company_id`, and `document_type` identify one existing row.
4. The AI sets `ocr_status=PROCESSING` and records `ocr_request_id` without changing existing Server-owned columns.
5. The template resolver chooses the CLOVA template candidate list.
6. The CLOVA client performs Template OCR.
7. The normalizer validates the matched template, parses known fields, and classifies the result.
8. The repository atomically writes structured values, field confidences, match metadata, error code, processed time, and the final OCR status.
9. The AI returns a status-only response to the Server.

Repeated calls are safe updates to the same row. A failed retry does not erase previously stored structured fields, but consumers must trust them only when `ocr_status` is `SUCCEEDED` or after an explicit human review of `REVIEW_REQUIRED`.

## Database Migration

The Server owns the PostgreSQL schema. A new Flyway migration named `V8__add_worker_document_ocr_fields.sql` is added; the existing V3 migration is not edited.

### OCR metadata columns

| Column | PostgreSQL type | Definition |
| --- | --- | --- |
| `ocr_status` | `VARCHAR(20)` | Not null, default `NOT_REQUESTED` |
| `ocr_request_id` | `UUID` | Nullable |
| `ocr_template_id` | `BIGINT` | Nullable |
| `ocr_document_side` | `VARCHAR(10)` | Nullable; `FRONT` or `BACK` |
| `ocr_field_confidences` | `JSONB` | Not null, default empty object |
| `ocr_error_code` | `VARCHAR(60)` | Nullable, safe machine-readable code |
| `ocr_processed_at` | `TIMESTAMP(6) WITH TIME ZONE` | Nullable |

`ocr_status` is constrained to `NOT_REQUESTED`, `PROCESSING`, `SUCCEEDED`, `REVIEW_REQUIRED`, or `FAILED`. Template IDs are not constrained in SQL because CLOVA deployments can be replaced.

### Passport columns

| Column | PostgreSQL type |
| --- | --- |
| `passport_number` | `VARCHAR(32)` |
| `surname` | `VARCHAR(120)` |
| `given_names` | `VARCHAR(160)` |
| `nationality` | `VARCHAR(80)` |
| `date_of_birth` | `DATE` |
| `sex` | `VARCHAR(20)` |
| `passport_issue_date` | `DATE` |
| `passport_expiry_date` | `DATE` |

### ARC front columns

| Column | PostgreSQL type |
| --- | --- |
| `alien_registration_number` | `VARCHAR(32)` |
| `full_name` | `VARCHAR(200)` |
| `visa_type` | `VARCHAR(40)` |
| `alien_registration_issue_date` | `DATE` |

ARC front shares `nationality` and `sex` with passport rows.

### ARC back columns

| Column | PostgreSQL type |
| --- | --- |
| `stay_permit_date` | `DATE` |
| `stay_expiration_date` | `DATE` |
| `residence_report_date_1` | `DATE` |
| `residence_confirmation_1` | `VARCHAR(160)` |
| `residence_address_1` | `VARCHAR(300)` |
| `residence_report_date_2` | `DATE` |
| `residence_confirmation_2` | `VARCHAR(160)` |
| `residence_address_2` | `VARCHAR(300)` |

All structured OCR fields are nullable. No uniqueness constraint or lookup index is added to sensitive identity fields in the MVP.

The AI updates rows only with this tenant-scoped predicate:

```text
worker_document_id = ? AND worker_id = ? AND company_id = ?
```

It does not modify `submission_status`, `expiry_date`, `updated_at`, or `version`. In particular, `passport_expiry_date` remains separate from the existing Server-owned `expiry_date`.

The Server JPA entity, domain object, create/patch requests, and public response DTO remain unchanged for the MVP because JPA ignores unmapped extra columns. If Server clients later need OCR fields, a dedicated read projection or response is added rather than expanding create/patch input models.

The AI database role receives row access and update permission only for the OCR-owned columns. It does not receive broad write access to Server-owned document fields.

## Field Normalization

Configured CLOVA template field names match the database column names exactly. The normalizer:

- trims leading and trailing whitespace and collapses repeated whitespace in text;
- removes incidental spaces from passport and alien registration numbers without inventing missing characters;
- parses `YYYY-MM-DD`, `YYYY.MM.DD`, and `YYYY/MM/DD` into dates;
- leaves empty optional fields as null;
- stores confidence values in `ocr_field_confidences` keyed by field name;
- never derives a birth date from an alien registration number;
- never stores the full raw CLOVA response.

## Validation and Outcomes

The default confidence threshold is `0.80` and is configurable through `FOWOCO_CLOVA_OCR_CONFIDENCE_THRESHOLD`.

Required fields by matched document are:

- Passport: `passport_number`, `surname`, `given_names`, `nationality`, `date_of_birth`, `passport_expiry_date`.
- ARC front: `alien_registration_number`, `full_name`.
- ARC back: at least one configured `stay_*` or `residence_*` field.

The second residence row is optional. Empty optional template regions do not lower the result status.

Outcome rules:

| Situation | DB status | HTTP behavior |
| --- | --- | --- |
| All required fields parse and meet threshold | `SUCCEEDED` | 200 |
| Matched template but missing/low-confidence required field | `REVIEW_REQUIRED` | 200 |
| Recognized date cannot be parsed | `REVIEW_REQUIRED` | 200 |
| No matching template or unexpected deployed template | `REVIEW_REQUIRED` | 200 |
| Invalid request, unsupported country, type, or file | No CLOVA call | 4xx |
| Scoped `worker_document` row not found | No CLOVA call | 404 |
| CLOVA timeout or provider error | `FAILED` | 502 or 504 |
| Final DB write fails | The request fails | 500 |

`ocr_error_code` stores one stable primary reason such as `LOW_CONFIDENCE`, `MISSING_REQUIRED_FIELD`, `INVALID_DATE`, `TEMPLATE_NOT_MATCHED`, `CLOVA_TIMEOUT`, or `CLOVA_ERROR`. Detailed review reasons are returned in the internal response without recognized text.

## Configuration

The AI service adds these environment-backed settings:

```text
FOWOCO_CLOVA_OCR_ENABLED
FOWOCO_CLOVA_OCR_INVOKE_URL
FOWOCO_CLOVA_OCR_SECRET
FOWOCO_CLOVA_OCR_TIMEOUT_SECONDS
FOWOCO_CLOVA_OCR_CONFIDENCE_THRESHOLD
FOWOCO_DATABASE_URL
```

OCR is disabled by default. Its timeout defaults to 30 seconds and its confidence threshold defaults to 0.80. The existing `FOWOCO_INTERNAL_API_TOKEN` protects the endpoint. Production startup fails fast if OCR is enabled but the CLOVA URL, secret, or database URL is absent.

## Server Changes Outside the Table

The Server adds only the integration needed to initiate OCR:

- a read operation on the existing file storage abstraction;
- an internal OCR client that sends the original bytes and metadata;
- orchestration after an eligible `PASSPORT_COPY` or `ARC` file is linked to a `worker_document`;
- mapping from `worker.nationality_code` to the three-letter passport template country code when necessary.

The existing masked AI analysis request is not reused because its privacy contract intentionally excludes raw identity-document content.

## Testing

Automated tests cover:

- country-to-passport-template routing for all five countries;
- ARC candidate selection and front/back mapping;
- multipart API validation and internal authentication;
- CLOVA success, no-match, malformed response, timeout, and provider error cases;
- field-name mapping, whitespace normalization, and supported date formats;
- required-field, low-confidence, and optional residence-row behavior;
- tenant-scoped row verification and update predicates;
- successful, review-required, and failed DB status transitions;
- Server Flyway migration column and constraint checks;
- Server file-read and multipart client contract.

Normal automated tests mock CLOVA. One manual smoke test uses a non-production sample document and the real deployed templates. Logs and test fixtures must not contain real passport or alien registration data.

## Acceptance Criteria

The feature is complete when:

1. The Server can send one original passport or ARC file with the approved metadata contract.
2. The AI chooses only the approved template candidates and calls the provided CLOVA `/infer` endpoint.
3. ARC side is derived from `matchedTemplate.id` without Server input.
4. Configured fields are normalized into the approved `worker_document` columns.
5. The database update is scoped by document, worker, and company identifiers and does not modify existing Server-owned columns.
6. Low-quality recognition is persisted as `REVIEW_REQUIRED`, while provider failures become `FAILED`.
7. Automated tests pass without requiring real CLOVA credentials. When a CLOVA secret and a non-production sample are available, a redacted manual smoke test succeeds against CLOVA.
