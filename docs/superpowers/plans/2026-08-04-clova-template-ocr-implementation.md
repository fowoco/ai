# CLOVA Template OCR Implementation Plan

> Superseded for persistence schema details by
> `docs/superpowers/plans/2026-08-04-minimal-ocr-schema-implementation.md`.
> This file remains as the historical implementation plan for the original feature.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the AI-side endpoint that accepts original passport or Korean ARC files, recognizes them through the approved CLOVA Template OCR templates, and writes normalized fields directly to the externally provisioned PostgreSQL `worker_document` columns.

**Architecture:** Only `fowoco/ai` changes. A dedicated authenticated FastAPI endpoint calls a provider adapter, normalizes the configured template fields, and persists them with a tenant-scoped Psycopg repository. The Server repository, Server migration, file-reading logic, and Server HTTP client are external prerequisites and remain untouched.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic 2, httpx, Psycopg 3 async pool, pytest, pytest-asyncio, Ruff.

## Global Constraints

- Modify files only inside the `fowoco/ai` repository. Never edit, commit, or create files in `fowoco/server`.
- Treat the Server repository as read-only contract reference.
- Assume an external caller sends the approved multipart request and that the approved `worker_document` OCR columns have already been provisioned.
- Use CLOVA Template OCR `/infer`, not Document OCR.
- Read the invoke URL and `X-OCR-SECRET` only from environment-backed settings.
- Never commit or log the CLOVA secret, document bytes, recognized identity values, raw CLOVA responses, database credentials, passport numbers, alien registration numbers, names, or addresses.
- `FOWOCO_CLOVA_OCR_CONFIDENCE_THRESHOLD` defaults to `0.80`; `FOWOCO_CLOVA_OCR_TIMEOUT_SECONDS` defaults to `30`.
- Set transaction-local PostgreSQL `app.company_id` before every `worker_document` SELECT or UPDATE.
- Update only the externally approved OCR columns. Never update `submission_status`, `expiry_date`, `updated_at`, or `version`.
- One request represents one image or one-page PDF. Multi-page responses become `REVIEW_REQUIRED`.
- Automated tests mock CLOVA and PostgreSQL. A live smoke test runs only with a non-production sample and locally supplied credentials.

## External Preconditions

The implementation assumes:

1. `worker_document` contains every OCR metadata, passport, ARC front, and ARC back column listed in the approved design.
2. The AI database role can SELECT `worker_document_id`, `worker_id`, `company_id`, and `document_type`, and UPDATE only the OCR-owned columns.
3. An authenticated caller sends `file`, `request_id`, `worker_id`, `company_id`, `document_type`, and passport `country_code` to the AI endpoint.
4. The caller uses `PASSPORT_COPY` or `ARC`; country codes are `KOR`, `PHL`, `JPN`, `CHN`, or `VNM`.

If the schema is absent or incomplete, AI startup must fail with a safe column-name-only diagnostic. This plan does not create or migrate Server tables.

## AI File Structure

- `app/ocr/models.py`: provider-neutral commands, enums, results, and exceptions.
- `app/ocr/template_resolver.py`: country/template routing and ARC side mapping.
- `app/ocr/normalizer.py`: CLOVA response validation, field mapping, confidence rules, and date parsing.
- `app/ocr/clova_client.py`: authenticated CLOVA V2 multipart transport.
- `app/ocr/repository.py`: tenant-aware schema verification and OCR-only PostgreSQL updates.
- `app/ocr/service.py`: status orchestration across resolver, CLOVA, normalizer, and repository.
- `app/ocr/runtime.py`: startup/shutdown ownership for `httpx.AsyncClient` and Psycopg pool.
- `app/api/routes/ocr.py`: internal multipart endpoint and safe HTTP error translation.
- `app/api/schemas/ocr.py`: status-only response model.
- `tests/ocr/*`, `tests/api/test_ocr_endpoint.py`: unit and endpoint tests.
- `docs/clova-ocr-integration.md`, `scripts/smoke_clova_ocr.ps1`: external contract and redacted smoke workflow.

---

### Task 1: Define OCR models and template routing

**Files:**
- Create: `app/ocr/__init__.py`
- Create: `app/ocr/models.py`
- Create: `app/ocr/template_resolver.py`
- Create: `tests/ocr/__init__.py`
- Create: `tests/ocr/test_template_resolver.py`

**Interfaces:**
- Produces: `DocumentType`, `OcrStatus`, `DocumentSide`, `OcrScope`, `OcrFile`, `OcrCommand`, `TemplateSelection`, `NormalizedOcrResult`, `OcrProcessResult`, and `TemplateResolutionError`.
- Produces: `TemplateResolver.resolve(document_type, country_code)` and `TemplateResolver.side_for_template(template_id)`.

- [ ] **Step 1: Write failing routing tests**

Create parameterized tests for every approved passport template and both ARC templates:

```python
import pytest

from app.ocr.models import DocumentSide, DocumentType, TemplateResolutionError
from app.ocr.template_resolver import TemplateResolver


@pytest.mark.parametrize(
    ("country", "template_id"),
    [("KOR", 43019), ("PHL", 43021), ("JPN", 43022), ("CHN", 43023), ("VNM", 43038)],
)
def test_resolves_passport_template(country: str, template_id: int) -> None:
    selection = TemplateResolver().resolve(DocumentType.PASSPORT_COPY, country)
    assert selection.template_ids == (template_id,)


def test_resolves_arc_candidates_and_matched_side() -> None:
    resolver = TemplateResolver()
    assert resolver.resolve(DocumentType.ARC, None).template_ids == (43024, 43025)
    assert resolver.side_for_template(43024) is DocumentSide.FRONT
    assert resolver.side_for_template(43025) is DocumentSide.BACK


def test_rejects_missing_passport_country() -> None:
    with pytest.raises(TemplateResolutionError, match="passport country"):
        TemplateResolver().resolve(DocumentType.PASSPORT_COPY, None)
```

Also test lower/outer whitespace normalization, unsupported country, and unexpected matched template ID.

- [ ] **Step 2: Run the resolver test and verify red**

```powershell
python -m pytest tests/ocr/test_template_resolver.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.ocr'`.

- [ ] **Step 3: Implement immutable models and exact mappings**

Use these central definitions:

```python
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Mapping, TypeAlias
from uuid import UUID

FieldValue: TypeAlias = str | date


class DocumentType(StrEnum):
    PASSPORT_COPY = "PASSPORT_COPY"
    ARC = "ARC"


class OcrStatus(StrEnum):
    NOT_REQUESTED = "NOT_REQUESTED"
    PROCESSING = "PROCESSING"
    SUCCEEDED = "SUCCEEDED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    FAILED = "FAILED"


class DocumentSide(StrEnum):
    FRONT = "FRONT"
    BACK = "BACK"


@dataclass(frozen=True)
class OcrScope:
    worker_document_id: UUID
    worker_id: UUID
    company_id: UUID


@dataclass(frozen=True)
class OcrFile:
    filename: str
    content_type: str
    content: bytes


@dataclass(frozen=True)
class OcrCommand:
    request_id: UUID
    scope: OcrScope
    document_type: DocumentType
    country_code: str | None
    file: OcrFile


@dataclass(frozen=True)
class TemplateSelection:
    template_ids: tuple[int, ...]
    expected_document_type: DocumentType


@dataclass(frozen=True)
class NormalizedOcrResult:
    status: OcrStatus
    matched_template_id: int | None
    document_side: DocumentSide | None
    fields: Mapping[str, FieldValue]
    field_confidences: Mapping[str, float]
    error_code: str | None
    review_reasons: tuple[str, ...]


@dataclass(frozen=True)
class OcrProcessResult:
    request_id: UUID
    worker_document_id: UUID
    status: OcrStatus
    matched_template_id: int | None
    document_side: DocumentSide | None
    review_reasons: tuple[str, ...]
```

`TemplateResolver` uses exactly `{KOR: 43019, PHL: 43021, JPN: 43022, CHN: 43023, VNM: 43038}` and ARC candidates `(43024, 43025)`.

- [ ] **Step 4: Run resolver tests and targeted lint**

```powershell
python -m pytest tests/ocr/test_template_resolver.py -v
python -m ruff check app/ocr/models.py app/ocr/template_resolver.py tests/ocr/test_template_resolver.py
```

Expected: PASS.

- [ ] **Step 5: Commit models and routing**

```powershell
git add app/ocr tests/ocr
git commit -m "feat: add OCR template routing"
```

---

### Task 2: Normalize CLOVA fields and recognition quality

**Files:**
- Create: `app/ocr/normalizer.py`
- Create: `tests/ocr/test_normalizer.py`
- Modify: `app/ocr/models.py`

**Interfaces:**
- Consumes: CLOVA response mappings and `TemplateSelection`.
- Produces: `normalize_clova_response(raw, selection, threshold, resolver) -> NormalizedOcrResult`.

- [ ] **Step 1: Write failing normalization tests**

Use synthetic values only:

```python
from datetime import date

from app.ocr.models import DocumentType, OcrStatus
from app.ocr.normalizer import normalize_clova_response
from app.ocr.template_resolver import TemplateResolver


def field(name: str, text: str, confidence: float = 0.99) -> dict[str, object]:
    return {"name": name, "inferText": text, "inferConfidence": confidence}


def test_normalizes_passport_dates() -> None:
    resolver = TemplateResolver()
    raw = {
        "images": [{
            "inferResult": "SUCCESS",
            "matchedTemplate": {"id": 43019, "name": "KOR_PASSPORT"},
            "fields": [
                field("passport_number", " M00000000 "),
                field("surname", "TEST"),
                field("given_names", "USER"),
                field("nationality", "KOR"),
                field("date_of_birth", "2000.01.02"),
                field("passport_expiry_date", "2030/01/02"),
            ],
        }]
    }
    result = normalize_clova_response(
        raw,
        resolver.resolve(DocumentType.PASSPORT_COPY, "KOR"),
        0.80,
        resolver,
    )
    assert result.status is OcrStatus.SUCCEEDED
    assert result.fields["date_of_birth"] == date(2000, 1, 2)
```

Add tests for ARC front, ARC back with only `stay_expiration_date`, blank second residence row, low-confidence required field, missing required field, invalid date, no match, unexpected template, unknown field, and multiple images.

- [ ] **Step 2: Run the normalizer test and verify red**

```powershell
python -m pytest tests/ocr/test_normalizer.py -v
```

Expected: FAIL because `app.ocr.normalizer` does not exist.

- [ ] **Step 3: Implement strict allow-list normalization**

Use these exact groups:

```python
DATE_FIELDS = frozenset({
    "date_of_birth", "passport_issue_date", "passport_expiry_date",
    "alien_registration_issue_date", "stay_permit_date", "stay_expiration_date",
    "residence_report_date_1", "residence_report_date_2",
})
PASSPORT_REQUIRED = frozenset({
    "passport_number", "surname", "given_names", "nationality",
    "date_of_birth", "passport_expiry_date",
})
ARC_FRONT_REQUIRED = frozenset({"alien_registration_number", "full_name"})
ARC_BACK_PREFIXES = ("stay_", "residence_")
```

The allow-list also includes `sex`, `visa_type`, all three residence fields for rows 1 and 2, and every approved passport/ARC column. Parse only `%Y-%m-%d`, `%Y.%m.%d`, and `%Y/%m/%d`. Ignore empty optional boxes and unknown fields. Set `REVIEW_REQUIRED` for missing/low-confidence required fields, recognized invalid dates, no match, unexpected match, or multiple images. Never return or store the raw response.

- [ ] **Step 4: Run normalization tests and lint**

```powershell
python -m pytest tests/ocr/test_normalizer.py tests/ocr/test_template_resolver.py -v
python -m ruff check app/ocr tests/ocr
```

Expected: PASS.

- [ ] **Step 5: Commit normalization**

```powershell
git add app/ocr/models.py app/ocr/normalizer.py tests/ocr/test_normalizer.py
git commit -m "feat: normalize CLOVA OCR fields"
```

---

### Task 3: Implement the CLOVA Template OCR client

**Files:**
- Create: `app/ocr/clova_client.py`
- Create: `tests/ocr/test_clova_client.py`

**Interfaces:**
- Consumes: `OcrFile`, template ID tuple, and request UUID.
- Produces: `await ClovaTemplateOcrClient.infer(file, template_ids, request_id) -> dict[str, Any]`.
- Raises: `ClovaTimeoutError` and `ClovaProviderError` from `app.ocr.models`.

- [ ] **Step 1: Write failing `httpx.MockTransport` tests**

Assert the outbound wire contract:

```python
async def handler(request: httpx.Request) -> httpx.Response:
    assert request.method == "POST"
    assert request.headers["X-OCR-SECRET"] == "local-test-secret"
    assert request.headers["Content-Type"].startswith("multipart/form-data; boundary=")
    body = await request.aread()
    assert b'"version":"V2"' in body
    assert b'"templateIds":[43024,43025]' in body
    assert b"sample.png" in body
    return httpx.Response(200, json={"images": []})
```

Add tests for timeout, network error, redirect, HTTP 500, oversized body, and invalid JSON.

- [ ] **Step 2: Run the client test and verify red**

```powershell
python -m pytest tests/ocr/test_clova_client.py -v
```

Expected: FAIL because `ClovaTemplateOcrClient` is undefined.

- [ ] **Step 3: Implement the V2 multipart client**

Use this call boundary:

```python
client = ClovaTemplateOcrClient(
    invoke_url="https://example.invalid/infer",
    secret="local-test-secret",
    timeout_seconds=30.0,
    client=httpx_client,
    max_response_bytes=1_048_576,
)
raw: dict[str, Any] = await client.infer(
    file=ocr_file,
    template_ids=(43024, 43025),
    request_id=request_id,
)
```

Send one JSON `message` part containing `version="V2"`, UUID request ID, millisecond timestamp, one image entry with file format/name/template IDs, plus one binary `file` part. Disable redirects. Enforce the byte cap before JSON decoding. Do not include the secret or response body in exceptions.

- [ ] **Step 4: Run client tests and lint**

```powershell
python -m pytest tests/ocr/test_clova_client.py -v
python -m ruff check app/ocr/clova_client.py tests/ocr/test_clova_client.py
```

Expected: PASS.

- [ ] **Step 5: Commit the provider adapter**

```powershell
git add app/ocr/clova_client.py tests/ocr/test_clova_client.py
git commit -m "feat: add CLOVA Template OCR client"
```

---

### Task 4: Add tenant-aware PostgreSQL persistence

**Files:**
- Modify: `pyproject.toml`
- Create: `app/ocr/repository.py`
- Create: `tests/ocr/test_repository.py`

**Interfaces:**
- Produces: `PsycopgWorkerDocumentOcrRepository.verify_schema()`.
- Produces: async `verify_scope`, `mark_processing`, `save_result`, and `mark_failed` methods.
- Raises: `DatabaseSchemaMismatch` and `OcrPersistenceError` from `app.ocr.models`.

- [ ] **Step 1: Write failing repository tests with fake async DB objects**

Assert every scoped operation executes this first in the same transaction:

```sql
SELECT pg_catalog.set_config('app.company_id', %s, true)
```

Assert every document SELECT/UPDATE contains:

```sql
WHERE worker_document_id = %s
  AND worker_id = %s
  AND company_id = %s
```

Assert `verify_schema()` compares `information_schema.columns` against all approved column names and raises `DatabaseSchemaMismatch` listing only missing column names. Assert update SQL does not set `submission_status`, bare `expiry_date`, `updated_at`, or `version`.

- [ ] **Step 2: Run repository tests and verify red**

```powershell
python -m pytest tests/ocr/test_repository.py -v
```

Expected: FAIL because the repository module does not exist.

- [ ] **Step 3: Add Psycopg and fixed SQL allow-lists**

Add:

```toml
"psycopg[binary,pool]>=3.2,<4",
```

Implement these exact method contracts:

```text
await repository.verify_schema() -> None
await repository.verify_scope(scope: OcrScope, document_type: DocumentType) -> bool
await repository.mark_processing(scope: OcrScope, request_id: UUID) -> None
await repository.save_result(scope: OcrScope, result: NormalizedOcrResult, processed_at: datetime) -> None
await repository.mark_failed(scope: OcrScope, request_id: UUID, error_code: str, processed_at: datetime) -> None
```

Every method uses one connection transaction. Set `app.company_id` before querying `worker_document`. Construct `save_result` from a Python constant containing every approved OCR column; never interpolate CLOVA field names directly into SQL. Serialize confidence values to JSON and dates as native `date` objects.

- [ ] **Step 4: Install dependencies and run persistence checks**

```powershell
python -m pip install -e ".[dev]"
python -m pytest tests/ocr/test_repository.py -v
python -m ruff check app/ocr/repository.py tests/ocr/test_repository.py
```

Expected: PASS.

- [ ] **Step 5: Commit persistence**

```powershell
git add pyproject.toml app/ocr/repository.py tests/ocr/test_repository.py
git commit -m "feat: persist OCR fields to worker documents"
```

---

### Task 5: Orchestrate recognition and DB statuses

**Files:**
- Create: `app/ocr/service.py`
- Create: `tests/ocr/test_service.py`
- Modify: `app/ocr/models.py`

**Interfaces:**
- Consumes: resolver, CLOVA client, normalizer, repository, `OcrCommand`.
- Produces: `await OcrService.process(command) -> OcrProcessResult`.
- Raises safe application errors: `InvalidOcrRequest`, `WorkerDocumentNotFound`, `OcrUpstreamTimeout`, `OcrUpstreamFailure`, and `OcrPersistenceError`.

- [ ] **Step 1: Write failing orchestration tests**

Using fakes, assert success ordering:

```python
result = await service.process(command)
assert repository.calls == ["verify_scope", "mark_processing", "save_result"]
assert clova.calls == [((43019,), "sample.png")]
assert result.status is OcrStatus.SUCCEEDED
```

Add tests for empty file, unsupported MIME type, file over 20 MiB, missing scoped row, unsupported passport country, CLOVA timeout calling `mark_failed(command.scope, command.request_id, "CLOVA_TIMEOUT", processed_at)`, provider error calling `mark_failed(command.scope, command.request_id, "CLOVA_ERROR", processed_at)`, persistence failure, and `REVIEW_REQUIRED` being saved and returned.

- [ ] **Step 2: Run service tests and verify red**

```powershell
python -m pytest tests/ocr/test_service.py -v
```

Expected: FAIL because `OcrService` does not exist.

- [ ] **Step 3: Implement deterministic orchestration**

Construct and call the service through this boundary:

```python
service = OcrService(
    resolver=resolver,
    clova_client=clova_client,
    repository=repository,
    confidence_threshold=0.80,
    clock=lambda: datetime.now(UTC),
)
result: OcrProcessResult = await service.process(command)
```

Validate `image/jpeg`, `image/png`, or `application/pdf`, non-empty bytes, safe filename, and 20 MiB limit before changing DB state. Resolve the template, verify scope/type, mark processing, call CLOVA, normalize, then save final result. On provider timeout/error, keep prior structured values and update only OCR status metadata through `mark_failed`.

- [ ] **Step 4: Run service and all OCR unit tests**

```powershell
python -m pytest tests/ocr -v
python -m ruff check app/ocr tests/ocr
```

Expected: PASS.

- [ ] **Step 5: Commit orchestration**

```powershell
git add app/ocr/models.py app/ocr/service.py tests/ocr/test_service.py
git commit -m "feat: orchestrate OCR processing"
```

---

### Task 6: Expose and configure the internal AI OCR endpoint

**Files:**
- Create: `app/api/schemas/ocr.py`
- Create: `app/api/routes/ocr.py`
- Create: `app/ocr/runtime.py`
- Create: `tests/api/test_ocr_endpoint.py`
- Modify: `app/api/dependencies.py`
- Modify: `app/core/config.py`
- Modify: `app/main.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Consumes: `OcrService.process`.
- Produces: `POST /internal/v1/ocr/worker-documents/{worker_document_id}`.
- Produces a status-only response with no extracted PII.

- [ ] **Step 1: Write failing endpoint and configuration tests**

Override `get_ocr_service` with a fake and send:

```python
response = client.post(
    f"/internal/v1/ocr/worker-documents/{document_id}",
    headers={"Authorization": "Bearer internal-test-token"},
    data={
        "request_id": str(request_id),
        "worker_id": str(worker_id),
        "company_id": str(company_id),
        "document_type": "PASSPORT_COPY",
        "country_code": "KOR",
    },
    files={"file": ("sample.png", b"synthetic-image-bytes", "image/png")},
)
assert response.status_code == 200
assert set(response.json()) == {
    "request_id", "worker_document_id", "ocr_status",
    "matched_template_id", "document_side", "review_reasons",
}
```

Add tests for Bearer 401, disabled OCR 503, invalid UUID/enum, missing passport country, 404 scope miss, 502 provider error, 504 timeout, 500 persistence error, `REVIEW_REQUIRED` 200, and absence of recognized fields in the response. Add startup tests for enabled OCR with missing invoke URL/secret/database URL.

- [ ] **Step 2: Run endpoint tests and verify red**

```powershell
python -m pytest tests/api/test_ocr_endpoint.py -v
```

Expected: FAIL with route 404.

- [ ] **Step 3: Add settings, resource lifecycle, dependency, and route**

Add to `Settings` under the existing `FOWOCO_` prefix:

```python
clova_ocr_enabled: bool = False
clova_ocr_invoke_url: str | None = None
clova_ocr_secret: str | None = None
clova_ocr_timeout_seconds: float = Field(default=30.0, gt=0)
clova_ocr_confidence_threshold: float = Field(default=0.80, ge=0, le=1)
database_url: str | None = None
```

When enabled, validate all required settings before serving requests. The FastAPI lifespan opens one Psycopg `AsyncConnectionPool` and one `httpx.AsyncClient`, builds repository/client/service, runs `repository.verify_schema()`, stores the service on `app.state`, and closes both resources at shutdown. `get_ocr_service(request: Request)` returns the state service or raises 503.

Use `verify_internal_bearer`. Translate invalid input to 400/422, scope miss to 404, provider failure to 502, timeout to 504, and persistence failure to 500. Return `SUCCEEDED` or `REVIEW_REQUIRED` with HTTP 200.

- [ ] **Step 4: Run endpoint, unit, and AI regression checks**

```powershell
python -m pytest tests/api/test_ocr_endpoint.py tests/ocr -v
python -m pytest
python -m ruff check app tests
```

Expected: tests PASS. If the repository still has unrelated pre-existing Ruff findings, record their exact paths and require every changed OCR/API file to pass a targeted Ruff run.

- [ ] **Step 5: Commit the internal endpoint**

```powershell
git add app/api/schemas/ocr.py app/api/routes/ocr.py app/api/dependencies.py app/core/config.py app/main.py app/ocr/runtime.py tests/conftest.py tests/api/test_ocr_endpoint.py
git commit -m "feat: expose internal CLOVA OCR endpoint"
```

---

### Task 7: Document the external contract and verify the AI-only integration

**Files:**
- Create: `docs/clova-ocr-integration.md`
- Create: `scripts/smoke_clova_ocr.ps1`
- Modify: `README.md`

**Interfaces:**
- Documents the exact multipart contract, expected external DB columns, restricted DB role permissions, configuration, template map, statuses, and retry behavior.
- Provides a redacted direct-to-AI smoke command; it does not call or modify Server code.

- [ ] **Step 1: Add a failing documentation contract test**

Create `tests/ocr/test_documented_contract.py` that reads the integration document and asserts it contains:

```python
REQUIRED_TERMS = {
    "/internal/v1/ocr/worker-documents/{worker_document_id}",
    "PASSPORT_COPY", "ARC", "43019", "43024", "43025",
    "passport_number", "alien_registration_number",
    "stay_permit_date", "stay_expiration_date", "residence_address_2",
    "FOWOCO_CLOVA_OCR_INVOKE_URL", "FOWOCO_CLOVA_OCR_SECRET",
    "FOWOCO_DATABASE_URL", "app.company_id",
}
```

Assert the document says `fowoco/server` is outside implementation scope.

- [ ] **Step 2: Run the documentation test and verify red**

```powershell
python -m pytest tests/ocr/test_documented_contract.py -v
```

Expected: FAIL because `docs/clova-ocr-integration.md` does not exist.

- [ ] **Step 3: Write AI integration and database precondition documentation**

Document the multipart request, response, template table, all expected DB columns/types, confidence/date rules, error mapping, RLS transaction context, and this example least-privilege role without any password:

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

State clearly that DB migration and caller implementation are owned externally and are not changed by this branch.

- [ ] **Step 4: Add a redacted direct AI smoke script**

The script reads these environment variables and exits before sending if any required value is absent:

```text
FOWOCO_INTERNAL_API_TOKEN
OCR_SAMPLE_FILE
OCR_WORKER_DOCUMENT_ID
OCR_WORKER_ID
OCR_COMPANY_ID
OCR_DOCUMENT_TYPE
OCR_COUNTRY_CODE
```

It posts to the local AI endpoint and prints only HTTP status, `ocr_status`, matched template ID, side, and review reasons. It never prints bytes or recognized fields. `OCR_COUNTRY_CODE` is optional only when `OCR_DOCUMENT_TYPE=ARC`.

- [ ] **Step 5: Run complete AI verification**

```powershell
python -m pytest
python -m ruff check app tests
git diff --check
rg -n "fowoco/server|gradlew|src/main/java/com/fowoco/server|V11__add_worker_document_ocr_fields" app tests scripts README.md docs/clova-ocr-integration.md
```

Expected: tests pass; the final `rg` output may mention `fowoco/server` only in the explicit statement that it is outside scope, and must contain no Server file path, Gradle command, or migration filename.

- [ ] **Step 6: Commit documentation and smoke workflow**

```powershell
git add README.md docs/clova-ocr-integration.md scripts/smoke_clova_ocr.ps1 tests/ocr/test_documented_contract.py
git commit -m "docs: add AI-only CLOVA OCR integration guide"
```

- [ ] **Step 7: Run optional live smoke test**

Only when the external DB schema, restricted DB account, CLOVA secret, invoke URL, and non-production sample are available:

```powershell
.\scripts\smoke_clova_ocr.ps1
```

Expected: HTTP 200 with `SUCCEEDED` or `REVIEW_REQUIRED`; the externally provisioned scoped row contains normalized values/confidences and AI logs contain identifiers/status only.

## Final Review Checklist

- [ ] Confirm `git status --short` contains changes only under the AI repository.
- [ ] Confirm no Server checkout was modified.
- [ ] Confirm `git diff --check` passes.
- [ ] Confirm all changed Python files pass targeted Ruff.
- [ ] Confirm the full AI test suite passes.
- [ ] Confirm template mappings and front/back field allow-lists match the approved design.
- [ ] Confirm every DB operation sets `app.company_id` before touching `worker_document`.
- [ ] Confirm SQL never updates `submission_status`, `expiry_date`, `updated_at`, or `version`.
- [ ] Confirm the HTTP response and logs contain no recognized identity fields.
- [ ] Confirm the smoke script sends directly to AI and does not depend on Server source changes.
