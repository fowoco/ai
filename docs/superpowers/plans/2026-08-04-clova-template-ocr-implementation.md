# CLOVA Template OCR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Accept original passport and Korean ARC files from the Server, recognize them with the approved CLOVA Template OCR templates, and persist normalized fields directly into the existing PostgreSQL `worker_document` row.

**Architecture:** The AI service adds a dedicated authenticated multipart endpoint, a template resolver, CLOVA HTTP adapter, normalizer, and tenant-aware Psycopg repository. The Server adds the Flyway columns, read access to its file storage, a dedicated OCR runtime client, and an explicit retryable OCR trigger after a file is linked. The two repositories keep separate commits and communicate only through the approved multipart contract.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic 2, httpx, Psycopg 3 async pool, pytest; Java 17, Spring Boot 4.1, Java `HttpClient`, Flyway, PostgreSQL/H2, JUnit 5, WireMock, Gradle.

## Global Constraints

- Work in an isolated worktree for each repository at execution time.
- Server paths below are relative to a fresh checkout of `https://github.com/fowoco/server` at or after commit `c2af9d4`; AI paths are relative to `fowoco/ai`.
- Use Template OCR, not Document OCR, and call the supplied `/infer` invoke URL only through environment configuration.
- Never commit or log `X-OCR-SECRET`, document bytes, passport numbers, alien registration numbers, names, addresses, or raw CLOVA responses.
- `FOWOCO_CLOVA_OCR_CONFIDENCE_THRESHOLD` defaults to `0.80`; `FOWOCO_CLOVA_OCR_TIMEOUT_SECONDS` defaults to `30`.
- The AI must set transaction-local PostgreSQL `app.company_id` before every scoped `worker_document` query or update.
- The AI updates only the new OCR-owned columns. It never updates `submission_status`, `expiry_date`, `updated_at`, or `version`.
- The Server JPA `WorkerDocument` entity and create/patch DTOs remain unchanged; extra OCR columns are intentionally unmapped.
- One OCR request represents one image or one-page PDF. Multi-page PDFs produce `REVIEW_REQUIRED`.
- Normal test suites mock CLOVA. A live smoke test is run only with a non-production sample and a locally supplied secret.

## File Structure

### AI repository

- `app/ocr/models.py`: provider-neutral commands, enums, normalized results, and errors.
- `app/ocr/template_resolver.py`: document/country-to-template routing and ARC side mapping.
- `app/ocr/normalizer.py`: CLOVA response validation, field mapping, confidence checks, and date parsing.
- `app/ocr/clova_client.py`: authenticated CLOVA V2 multipart transport.
- `app/ocr/repository.py`: tenant-aware PostgreSQL scope verification and OCR-only updates.
- `app/ocr/service.py`: end-to-end OCR status orchestration.
- `app/ocr/runtime.py`: startup/shutdown ownership for the httpx client and Psycopg pool.
- `app/api/routes/ocr.py`: internal multipart endpoint and HTTP error translation.
- `app/api/schemas/ocr.py`: status-only response schema.
- `tests/ocr/*`, `tests/api/test_ocr_endpoint.py`: unit and endpoint contract tests.

### Server repository

- `src/main/resources/db/migration/V11__add_worker_document_ocr_fields.sql`: OCR columns and check constraints.
- `file/application/port/FileStorage.java`: storage read contract.
- `file/infrastructure/LocalFileStorage.java`: safe local byte reads.
- `file/application/StoredFileContent*.java`: tenant-scoped stored-file metadata and byte loading.
- `ocrintegration/*`: OCR request/response models, port, configuration, HTTP client, and coordinator.
- `worker/api/WorkerDocumentOcrController.java`: explicit OCR trigger that is safe to retry.
- Server tests cover migration, file reads, country mapping, multipart wire contract, and trigger authorization.

---

### Task 1: Add OCR columns to Server `worker_document`

**Repository:** `fowoco/server`

**Files:**
- Create: `src/main/resources/db/migration/V11__add_worker_document_ocr_fields.sql`
- Modify: `src/test/java/com/fowoco/server/PostgreSqlMigrationTests.java`

**Interfaces:**
- Consumes: existing `worker_document(worker_document_id, worker_id, company_id, document_type)`.
- Produces: the exact OCR columns used by AI Task 5 and the status/side check constraints.

- [ ] **Step 1: Add failing migration assertions**

Extend the existing `columnSpecs(connection, "worker_document")` assertion with representative columns from every group:

```java
.containsEntry("ocr_status", new ColumnSpec("varchar", false))
.containsEntry("ocr_request_id", new ColumnSpec("uuid", true))
.containsEntry("ocr_template_id", new ColumnSpec("int8", true))
.containsEntry("ocr_field_confidences", new ColumnSpec("jsonb", false))
.containsEntry("passport_number", new ColumnSpec("varchar", true))
.containsEntry("alien_registration_number", new ColumnSpec("varchar", true))
.containsEntry("stay_expiration_date", new ColumnSpec("date", true))
.containsEntry("residence_address_2", new ColumnSpec("varchar", true));
```

Add a check-constraint assertion that rejects `ocr_status='UNKNOWN'` and `ocr_document_side='MIDDLE'`.

- [ ] **Step 2: Run the migration test and confirm failure**

Run:

```powershell
.\gradlew.bat test --tests com.fowoco.server.PostgreSqlMigrationTests
```

Expected: FAIL because `ocr_status` and the other V11 columns do not exist.

- [ ] **Step 3: Add the V11 migration**

Create the migration with these exact definitions:

```sql
ALTER TABLE worker_document
    ADD COLUMN ocr_status VARCHAR(20) NOT NULL DEFAULT 'NOT_REQUESTED',
    ADD COLUMN ocr_request_id UUID,
    ADD COLUMN ocr_template_id BIGINT,
    ADD COLUMN ocr_document_side VARCHAR(10),
    ADD COLUMN ocr_field_confidences JSONB NOT NULL DEFAULT CAST('{}' AS JSONB),
    ADD COLUMN ocr_error_code VARCHAR(60),
    ADD COLUMN ocr_processed_at TIMESTAMP(6) WITH TIME ZONE,
    ADD COLUMN passport_number VARCHAR(32),
    ADD COLUMN surname VARCHAR(120),
    ADD COLUMN given_names VARCHAR(160),
    ADD COLUMN nationality VARCHAR(80),
    ADD COLUMN date_of_birth DATE,
    ADD COLUMN sex VARCHAR(20),
    ADD COLUMN passport_issue_date DATE,
    ADD COLUMN passport_expiry_date DATE,
    ADD COLUMN alien_registration_number VARCHAR(32),
    ADD COLUMN full_name VARCHAR(200),
    ADD COLUMN visa_type VARCHAR(40),
    ADD COLUMN alien_registration_issue_date DATE,
    ADD COLUMN stay_permit_date DATE,
    ADD COLUMN stay_expiration_date DATE,
    ADD COLUMN residence_report_date_1 DATE,
    ADD COLUMN residence_confirmation_1 VARCHAR(160),
    ADD COLUMN residence_address_1 VARCHAR(300),
    ADD COLUMN residence_report_date_2 DATE,
    ADD COLUMN residence_confirmation_2 VARCHAR(160),
    ADD COLUMN residence_address_2 VARCHAR(300),
    ADD CONSTRAINT ck_worker_document_ocr_status CHECK (
        ocr_status IN ('NOT_REQUESTED', 'PROCESSING', 'SUCCEEDED', 'REVIEW_REQUIRED', 'FAILED')
    ),
    ADD CONSTRAINT ck_worker_document_ocr_side CHECK (
        ocr_document_side IS NULL OR ocr_document_side IN ('FRONT', 'BACK')
    );
```

Do not add identity-field indexes or modify V3/V8/V9/V10.

- [ ] **Step 4: Run migration and Server regression tests**

Run:

```powershell
.\gradlew.bat test --tests com.fowoco.server.PostgreSqlMigrationTests
.\gradlew.bat test
```

Expected: both commands PASS; Hibernate validation still accepts the intentionally unmapped columns.

- [ ] **Step 5: Commit the Server migration**

```powershell
git add src/main/resources/db/migration/V11__add_worker_document_ocr_fields.sql src/test/java/com/fowoco/server/PostgreSqlMigrationTests.java
git commit -m "feat: add worker document OCR fields"
```

---

### Task 2: Define AI OCR models and template routing

**Repository:** `fowoco/ai`

**Files:**
- Create: `app/ocr/__init__.py`
- Create: `app/ocr/models.py`
- Create: `app/ocr/template_resolver.py`
- Create: `tests/ocr/__init__.py`
- Create: `tests/ocr/test_template_resolver.py`

**Interfaces:**
- Produces: `DocumentType`, `OcrStatus`, `DocumentSide`, `OcrScope`, `OcrFile`, `TemplateSelection`, `NormalizedOcrResult`, `OcrProcessResult`, `TemplateResolutionError`, and `TemplateResolver`.
- Later tasks import these types; do not redefine them elsewhere.

- [ ] **Step 1: Write failing routing tests**

Create parameterized tests for all passport mappings and ARC candidates:

```python
import pytest

from app.ocr.models import DocumentSide, DocumentType
from app.ocr.template_resolver import TemplateResolver


@pytest.mark.parametrize(
    ("country", "template_id"),
    [("KOR", 43019), ("PHL", 43021), ("JPN", 43022), ("CHN", 43023), ("VNM", 43038)],
)
def test_resolves_passport_template(country: str, template_id: int) -> None:
    selection = TemplateResolver().resolve(DocumentType.PASSPORT_COPY, country)
    assert selection.template_ids == (template_id,)


def test_resolves_arc_candidates_and_side() -> None:
    resolver = TemplateResolver()
    selection = resolver.resolve(DocumentType.ARC, None)
    assert selection.template_ids == (43024, 43025)
    assert resolver.side_for_template(43024) is DocumentSide.FRONT
    assert resolver.side_for_template(43025) is DocumentSide.BACK
```

Add tests that missing/unsupported passport countries and unexpected matched template IDs raise `TemplateResolutionError`.

- [ ] **Step 2: Run the resolver tests and confirm failure**

Run:

```powershell
python -m pytest tests/ocr/test_template_resolver.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.ocr'`.

- [ ] **Step 3: Add provider-neutral models and resolver**

Use string enums and immutable dataclasses. The central signatures are:

```python
FieldValue = str | date


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


class TemplateResolver:
    def resolve(self, document_type: DocumentType, country_code: str | None) -> TemplateSelection:
        normalized = country_code.strip().upper() if country_code else None
        if document_type is DocumentType.ARC:
            return TemplateSelection((43024, 43025), document_type)
        if normalized not in PASSPORT_TEMPLATE_IDS:
            raise TemplateResolutionError("unsupported passport country")
        return TemplateSelection((PASSPORT_TEMPLATE_IDS[normalized],), document_type)

    def side_for_template(self, template_id: int) -> DocumentSide | None:
        if template_id in PASSPORT_TEMPLATE_IDS.values():
            return None
        try:
            return {43024: DocumentSide.FRONT, 43025: DocumentSide.BACK}[template_id]
        except KeyError as exc:
            raise TemplateResolutionError("unexpected matched template") from exc
```

Normalize country codes with `strip().upper()` but accept only the approved three-letter codes at the AI boundary.

- [ ] **Step 4: Run resolver tests and lint**

Run:

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

### Task 3: Normalize CLOVA fields and classify recognition quality

**Repository:** `fowoco/ai`

**Files:**
- Create: `app/ocr/normalizer.py`
- Create: `tests/ocr/test_normalizer.py`
- Modify: `app/ocr/models.py`

**Interfaces:**
- Consumes: `TemplateSelection` from Task 2 and CLOVA response mappings.
- Produces: `normalize_clova_response(raw, selection, threshold) -> NormalizedOcrResult`.
- `NormalizedOcrResult` contains `status`, `matched_template_id`, `document_side`, `fields`, `field_confidences`, `error_code`, and `review_reasons`.

- [ ] **Step 1: Write failing passport, ARC, and date tests**

Use small synthetic CLOVA responses with no real identity data:

```python
def field(name: str, text: str, confidence: float = 0.99) -> dict[str, object]:
    return {"name": name, "inferText": text, "inferConfidence": confidence}


def test_normalizes_passport_fields_and_dates() -> None:
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
    result = normalize_clova_response(raw, TemplateResolver().resolve(DocumentType.PASSPORT_COPY, "KOR"), 0.8)
    assert result.status is OcrStatus.SUCCEEDED
    assert result.fields["date_of_birth"] == date(2000, 1, 2)
```

Add tests for ARC front, ARC back with only `stay_expiration_date`, optional empty residence row 2, low confidence, missing required field, invalid date, no match, unexpected template, and multiple images.

- [ ] **Step 2: Run normalizer tests and confirm failure**

Run:

```powershell
python -m pytest tests/ocr/test_normalizer.py -v
```

Expected: FAIL because `app.ocr.normalizer` does not exist.

- [ ] **Step 3: Implement strict normalization**

Use these exact field groups:

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

Parse only `%Y-%m-%d`, `%Y.%m.%d`, and `%Y/%m/%d`. Set `REVIEW_REQUIRED` for low-confidence required fields, missing required fields, invalid recognized dates, no match, unexpected template, or multiple images. Never retain unknown field names or the raw response.

- [ ] **Step 4: Run normalizer and resolver tests**

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

### Task 4: Implement the CLOVA Template OCR HTTP client

**Repository:** `fowoco/ai`

**Files:**
- Create: `app/ocr/clova_client.py`
- Create: `tests/ocr/test_clova_client.py`

**Interfaces:**
- Consumes: `OcrFile` and a tuple of template IDs.
- Produces: `await ClovaTemplateOcrClient.infer(file, template_ids, request_id) -> dict[str, Any]`.
- Raises: `ClovaTimeoutError` for timeouts and `ClovaProviderError` for network, non-2xx, oversized, or invalid-JSON responses.

- [ ] **Step 1: Write failing MockTransport tests**

Build an `httpx.MockTransport` handler that asserts:

```python
assert request.method == "POST"
assert request.headers["X-OCR-SECRET"] == "local-test-secret"
assert request.headers["Content-Type"].startswith("multipart/form-data; boundary=")
body = request.read()
assert b'"version":"V2"' in body
assert b'"templateIds":[43024,43025]' in body
assert b"sample.png" in body
```

Return a synthetic `SUCCESS` response, then add timeout, HTTP 500, and invalid JSON tests.

- [ ] **Step 2: Run client tests and confirm failure**

```powershell
python -m pytest tests/ocr/test_clova_client.py -v
```

Expected: FAIL because `ClovaTemplateOcrClient` is not defined.

- [ ] **Step 3: Implement the client**

The constructor and call contract are:

```python
ClovaTemplateOcrClient(
    invoke_url: str,
    secret: str,
    timeout_seconds: float,
    client: httpx.AsyncClient | None,
    max_response_bytes: int = 1_048_576,
)

await client.infer(
    file: OcrFile,
    template_ids: tuple[int, ...],
    request_id: UUID,
) -> dict[str, Any]
```

Create one `message` JSON part with `version="V2"`, millisecond timestamp, image `format`, safe image `name`, and `templateIds`; create one binary `file` part. Disable redirects, never log the body, enforce the response-size limit before JSON decoding, and close only internally owned clients.

- [ ] **Step 4: Run client tests and lint**

```powershell
python -m pytest tests/ocr/test_clova_client.py -v
python -m ruff check app/ocr/clova_client.py tests/ocr/test_clova_client.py
```

Expected: PASS.

- [ ] **Step 5: Commit the CLOVA adapter**

```powershell
git add app/ocr/clova_client.py tests/ocr/test_clova_client.py
git commit -m "feat: add CLOVA Template OCR client"
```

---

### Task 5: Add the tenant-aware AI PostgreSQL repository

**Repository:** `fowoco/ai`

**Files:**
- Modify: `pyproject.toml`
- Create: `app/ocr/repository.py`
- Create: `tests/ocr/test_repository.py`

**Interfaces:**
- Consumes: `OcrScope`, `DocumentType`, `NormalizedOcrResult`, request IDs, safe error codes, and timestamps.
- Produces: `PsycopgWorkerDocumentOcrRepository` with `verify_scope`, `mark_processing`, `save_result`, and `mark_failed` async methods.

- [ ] **Step 1: Add failing repository contract tests**

Use fake async pool/connection/cursor objects that record SQL and parameters. Assert every method executes this statement first in the same transaction:

```sql
SELECT pg_catalog.set_config('app.company_id', %s, true)
```

Assert every select/update includes:

```sql
WHERE worker_document_id = %s
  AND worker_id = %s
  AND company_id = %s
```

Assert `save_result` does not mention `submission_status`, bare `expiry_date`, `updated_at`, or `version` in its `SET` clause.

- [ ] **Step 2: Run repository tests and confirm failure**

```powershell
python -m pytest tests/ocr/test_repository.py -v
```

Expected: FAIL because the repository module does not exist.

- [ ] **Step 3: Add Psycopg and implement scoped updates**

Add this dependency:

```toml
"psycopg[binary,pool]>=3.2,<4",
```

Implement these signatures:

```python
await repository.verify_scope(scope: OcrScope, document_type: DocumentType) -> bool
await repository.mark_processing(scope: OcrScope, request_id: UUID) -> None
await repository.save_result(
    scope: OcrScope,
    result: NormalizedOcrResult,
    processed_at: datetime,
) -> None
await repository.mark_failed(
    scope: OcrScope,
    request_id: UUID,
    error_code: str,
    processed_at: datetime,
) -> None
```

Each method opens one connection transaction, sets `app.company_id`, then performs its scoped operation. Build `save_result` from a fixed allow-list of all approved OCR columns; never interpolate a CLOVA-provided name into SQL.

- [ ] **Step 4: Install dependencies and run repository tests**

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

### Task 6: Orchestrate OCR processing and statuses

**Repository:** `fowoco/ai`

**Files:**
- Create: `app/ocr/service.py`
- Create: `tests/ocr/test_service.py`
- Modify: `app/ocr/models.py`

**Interfaces:**
- Consumes: resolver, CLOVA client, normalizer, repository, `OcrCommand`, and `OcrFile`.
- Produces: `await OcrService.process(command) -> OcrProcessResult`.
- Raises provider-neutral `InvalidOcrRequest`, `WorkerDocumentNotFound`, `OcrUpstreamTimeout`, `OcrUpstreamFailure`, and `OcrPersistenceFailure`.

- [ ] **Step 1: Write failing orchestration tests with fakes**

Cover this exact call order on success:

```python
assert fake_repository.calls == [
    "verify_scope",
    "mark_processing",
    "save_result",
]
assert fake_clova.calls == [((43019,), "sample.png")]
assert result.status is OcrStatus.SUCCEEDED
```

Add tests for bad MIME type, file over 20 MiB, missing row, unsupported passport country, CLOVA timeout leading to `mark_failed(command.scope, command.request_id, "CLOVA_TIMEOUT", processed_at)`, provider error leading to `CLOVA_ERROR`, and `REVIEW_REQUIRED` being saved rather than raised.

- [ ] **Step 2: Run service tests and confirm failure**

```powershell
python -m pytest tests/ocr/test_service.py -v
```

Expected: FAIL because `OcrService` does not exist.

- [ ] **Step 3: Implement the application service**

Use this constructor and method boundary:

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

Accept only `image/jpeg`, `image/png`, and `application/pdf`. Validate non-empty bytes and the 20 MiB limit before changing DB state. Store recognized valid fields for `REVIEW_REQUIRED`; on provider failure leave prior structured values intact and update only OCR metadata/status.

- [ ] **Step 4: Run service and OCR unit tests**

```powershell
python -m pytest tests/ocr -v
python -m ruff check app/ocr tests/ocr
```

Expected: PASS.

- [ ] **Step 5: Commit orchestration**

```powershell
git add app/ocr/service.py app/ocr/models.py tests/ocr/test_service.py
git commit -m "feat: orchestrate OCR processing"
```

---

### Task 7: Expose and configure the AI internal OCR endpoint

**Repository:** `fowoco/ai`

**Files:**
- Create: `app/api/schemas/ocr.py`
- Create: `app/api/routes/ocr.py`
- Create: `app/ocr/runtime.py`
- Create: `tests/api/test_ocr_endpoint.py`
- Modify: `app/api/dependencies.py`
- Modify: `app/core/config.py`
- Modify: `app/main.py`
- Modify: `tests/conftest.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `OcrService.process` from Task 6.
- Produces: authenticated `POST /internal/v1/ocr/worker-documents/{worker_document_id}` and `OcrResponse` without recognized PII.

- [ ] **Step 1: Write failing endpoint contract tests**

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
    files={"file": ("sample.png", b"not-real-identity-data", "image/png")},
)
assert response.status_code == 200
assert set(response.json()) == {
    "request_id", "worker_document_id", "ocr_status",
    "matched_template_id", "document_side", "review_reasons",
}
```

Add 401, invalid enum/UUID, missing passport country, 404, 502, 504, and response-without-extracted-fields tests.

- [ ] **Step 2: Run endpoint tests and confirm failure**

```powershell
python -m pytest tests/api/test_ocr_endpoint.py -v
```

Expected: FAIL with route 404.

- [ ] **Step 3: Add settings, dependencies, route, and startup validation**

Add settings with the existing `FOWOCO_` prefix:

```python
clova_ocr_enabled: bool = False
clova_ocr_invoke_url: str | None = None
clova_ocr_secret: str | None = None
clova_ocr_timeout_seconds: float = Field(default=30.0, gt=0)
clova_ocr_confidence_threshold: float = Field(default=0.80, ge=0, le=1)
database_url: str | None = None
```

When enabled, `create_app()` must reject missing invoke URL, secret, or database URL. An async lifespan opens one Psycopg `AsyncConnectionPool` and one `httpx.AsyncClient`, builds the resolver/client/repository/service, stores the service on `app.state`, and closes both resources during shutdown. `get_ocr_service(request: Request)` returns `request.app.state.ocr_service` or raises 503 when OCR is disabled. Register the route directly like the existing analyses/workflows internal routers, and use `verify_internal_bearer`.

Translate errors as follows: invalid input 400/422, scoped row missing 404, provider failure 502, timeout 504, persistence failure 500. Return `REVIEW_REQUIRED` with HTTP 200.

- [ ] **Step 4: Run endpoint, unit, and full AI checks**

```powershell
python -m pytest tests/api/test_ocr_endpoint.py tests/ocr -v
python -m pytest
python -m ruff check app tests
```

Expected: all tests PASS. If unrelated pre-existing lint failures remain, record their exact paths and confirm all changed OCR files pass a targeted Ruff run.

- [ ] **Step 5: Commit the AI endpoint**

```powershell
git add app/api/schemas/ocr.py app/api/routes/ocr.py app/api/dependencies.py app/core/config.py app/main.py app/ocr/runtime.py tests/conftest.py tests/api/test_ocr_endpoint.py README.md
git commit -m "feat: expose internal CLOVA OCR endpoint"
```

---

### Task 8: Add safe Server file reads for OCR forwarding

**Repository:** `fowoco/server`

**Files:**
- Modify: `src/main/java/com/fowoco/server/file/application/port/FileStorage.java`
- Modify: `src/main/java/com/fowoco/server/file/infrastructure/LocalFileStorage.java`
- Modify: `src/test/java/com/fowoco/server/file/support/FakeFileStorage.java`
- Create: `src/main/java/com/fowoco/server/file/application/StoredFileContent.java`
- Create: `src/main/java/com/fowoco/server/file/application/StoredFileContentReader.java`
- Create: `src/test/java/com/fowoco/server/file/application/StoredFileContentReaderTest.java`

**Interfaces:**
- Produces: `byte[] FileStorage.read(String storageKey)` and `StoredFileContentReader.read(UUID fileId, UUID companyId) -> StoredFileContent`.
- `StoredFileContent` contains `fileId`, `name`, `mimeType`, `size`, and defensive-copy `bytes`.

- [ ] **Step 1: Write failing storage and tenant-scope tests**

Assert that `LocalFileStorage.read("safe-key")` returns stored bytes and rejects `../escape`. Assert `StoredFileContentReader` looks up `StoredFileRepository.findByIdAndCompanyId(fileId, companyId)`, sets tenant context in an active read-only transaction, and throws `FILE_NOT_FOUND` for another tenant.

- [ ] **Step 2: Run focused Server tests and confirm failure**

```powershell
.\gradlew.bat test --tests "*StoredFileContentReaderTest" --tests "*FileSecurityIntegrationTest"
```

Expected: FAIL because the read contract does not exist.

- [ ] **Step 3: Implement bounded, normalized reads**

Extend the port:

```java
public interface FileStorage {
    void store(String storageKey, InputStream content, long size, String mimeType);
    byte[] read(String storageKey);
}
```

In `LocalFileStorage`, resolve and normalize the key exactly as `store` does, require the target to remain under the storage root, and call `Files.readAllBytes`. The 20 MiB upload limit bounds memory use. In `StoredFileContentReader`, load metadata by file ID and company ID, then read by the server-generated storage key; never accept a client-supplied path.

- [ ] **Step 4: Run file tests**

```powershell
.\gradlew.bat test --tests "*StoredFileContentReaderTest" --tests "*FileSecurityIntegrationTest" --tests "*DocumentSecurityIntegrationTest"
```

Expected: PASS.

- [ ] **Step 5: Commit file read support**

```powershell
git add src/main/java/com/fowoco/server/file src/test/java/com/fowoco/server/file
git commit -m "feat: read stored files for OCR"
```

---

### Task 9: Implement the Server-to-AI multipart OCR client

**Repository:** `fowoco/server`

**Files:**
- Create: `src/main/java/com/fowoco/server/ocrintegration/application/model/OcrRuntimeRequest.java`
- Create: `src/main/java/com/fowoco/server/ocrintegration/application/model/OcrRuntimeResponse.java`
- Create: `src/main/java/com/fowoco/server/ocrintegration/application/port/OcrRuntimeClient.java`
- Create: `src/main/java/com/fowoco/server/ocrintegration/application/error/OcrRuntimeCallException.java`
- Create: `src/main/java/com/fowoco/server/ocrintegration/infrastructure/http/OcrRuntimeProperties.java`
- Create: `src/main/java/com/fowoco/server/ocrintegration/infrastructure/http/OcrRuntimeHttpConfiguration.java`
- Create: `src/main/java/com/fowoco/server/ocrintegration/infrastructure/http/RemoteOcrRuntimeClient.java`
- Create: `src/main/java/com/fowoco/server/ocrintegration/infrastructure/http/DisabledOcrRuntimeClient.java`
- Create: `src/test/java/com/fowoco/server/ocrintegration/infrastructure/http/RemoteOcrRuntimeClientWireMockTest.java`
- Modify: `src/main/resources/application.yaml`
- Modify: `.env.example`

**Interfaces:**
- Consumes: `StoredFileContent` from Task 8 and document/tenant identifiers.
- Produces: `OcrRuntimeClient.recognize(OcrRuntimeRequest) -> OcrRuntimeResponse`.

- [ ] **Step 1: Write failing WireMock multipart tests**

Verify POST path, Bearer header, multipart part names, UUID/string values, MIME type, filename, and exact bytes. Return this safe JSON:

```json
{
  "request_id": "00000000-0000-0000-0000-000000000001",
  "worker_document_id": "00000000-0000-0000-0000-000000000002",
  "ocr_status": "SUCCEEDED",
  "matched_template_id": 43019,
  "document_side": null,
  "review_reasons": []
}
```

Add tests for disabled client, invalid endpoint/credential, timeout, non-2xx, oversized response, malformed JSON, and unknown response fields.

- [ ] **Step 2: Run the wire test and confirm failure**

```powershell
.\gradlew.bat test --tests "*RemoteOcrRuntimeClientWireMockTest"
```

Expected: FAIL because the OCR runtime package does not exist.

- [ ] **Step 3: Implement isolated OCR HTTP configuration**

Use a dedicated property namespace, not `app.ai-runtime`:

```yaml
app:
  ocr-runtime:
    enabled: ${OCR_RUNTIME_ENABLED:false}
    endpoint: ${OCR_RUNTIME_ENDPOINT:http://127.0.0.1:8000/internal/v1/ocr/worker-documents}
    service-credential: ${OCR_RUNTIME_SERVICE_CREDENTIAL:}
    connect-timeout: ${OCR_RUNTIME_CONNECT_TIMEOUT:2s}
    overall-timeout: ${OCR_RUNTIME_OVERALL_TIMEOUT:45s}
    max-response-bytes: ${OCR_RUNTIME_MAX_RESPONSE_BYTES:65536}
```

Define the outbound model with these exact fields:

```java
public record OcrRuntimeRequest(
        UUID requestId,
        UUID workerDocumentId,
        UUID workerId,
        UUID companyId,
        String documentType,
        String countryCode,
        String fileName,
        String mimeType,
        byte[] content
) {
    public OcrRuntimeRequest {
        content = content.clone();
    }

    @Override
    public byte[] content() {
        return content.clone();
    }
}
```

Build the target URI by appending `/{worker_document_id}` to the configured base path. Use a random boundary and Java `HttpClient.BodyPublishers.concat` to send `file`, `request_id`, `worker_id`, `company_id`, `document_type`, and optional `country_code` parts. Follow no redirects, send the existing internal bearer credential, cap response bytes, and deserialize with unknown-field rejection.

- [ ] **Step 4: Run client tests and Server regression tests**

```powershell
.\gradlew.bat test --tests "*RemoteOcrRuntimeClientWireMockTest"
.\gradlew.bat test
```

Expected: PASS.

- [ ] **Step 5: Commit the Server OCR client**

```powershell
git add src/main/java/com/fowoco/server/ocrintegration src/test/java/com/fowoco/server/ocrintegration src/main/resources/application.yaml .env.example
git commit -m "feat: add AI OCR runtime client"
```

---

### Task 10: Add an explicit, retryable Server OCR trigger and run end-to-end verification

**Repositories:** `fowoco/server`, then `fowoco/ai`

**Files (Server):**
- Create: `src/main/java/com/fowoco/server/ocrintegration/application/PassportCountryCodeMapper.java`
- Create: `src/main/java/com/fowoco/server/ocrintegration/application/WorkerDocumentOcrContext.java`
- Create: `src/main/java/com/fowoco/server/ocrintegration/application/WorkerDocumentOcrContextReader.java`
- Create: `src/main/java/com/fowoco/server/ocrintegration/application/WorkerDocumentOcrService.java`
- Create: `src/main/java/com/fowoco/server/worker/api/WorkerDocumentOcrController.java`
- Create: `src/main/java/com/fowoco/server/worker/api/WorkerDocumentOcrResponse.java`
- Create: `src/test/java/com/fowoco/server/ocrintegration/application/PassportCountryCodeMapperTest.java`
- Create: `src/test/java/com/fowoco/server/worker/WorkerDocumentOcrSecurityIntegrationTest.java`
- Modify: `docs/ai-runtime-contract.md`
- Create: `docs/ocr-database-role.md`

**Files (AI):**
- Modify: `README.md`
- Create: `scripts/smoke_clova_ocr.ps1`

**Interfaces:**
- Produces Server endpoint: `POST /api/v1/workers/{workerId}/documents/{documentId}/ocr`.
- The endpoint is called after `file_id` is linked and may be called repeatedly with the same document.

- [ ] **Step 1: Write failing country-mapping and trigger tests**

Test the exact mapping:

```java
@ParameterizedTest
@CsvSource({"KR,KOR", "KOR,KOR", "PH,PHL", "PHL,PHL", "JP,JPN", "CN,CHN", "VN,VNM"})
void mapsSupportedNationalityCodes(String input, String expected) {
    assertThat(mapper.toTemplateCountry(input)).isEqualTo(expected);
}
```

The controller integration test must prove:

- ADMIN/HR can trigger; VIEWER and cross-tenant callers cannot.
- missing document/file returns 404 or 409 without calling AI;
- `CONTRACT`/`PERMIT` returns 422 without calling AI;
- passport sends mapped country and ARC sends null country;
- stored bytes and MIME type reach the fake `OcrRuntimeClient` unchanged;
- response contains status/template/side/reasons but no recognized field values;
- a second POST calls the fake again, proving retryability.

- [ ] **Step 2: Run trigger tests and confirm failure**

```powershell
.\gradlew.bat test --tests "*PassportCountryCodeMapperTest" --tests "*WorkerDocumentOcrSecurityIntegrationTest"
```

Expected: FAIL because the mapper, service, and endpoint do not exist.

- [ ] **Step 3: Implement the coordinator and endpoint**

`WorkerDocumentOcrContextReader.read(documentId, workerId, companyId)` is a read-only transaction that binds `app.company_id`, loads the document, worker nationality, and `StoredFileContent`, and returns an immutable `WorkerDocumentOcrContext`. `WorkerDocumentOcrService.recognize(documentId, workerId, actor)` itself is not transactional and must:

1. call the context reader with the actor company;
2. require `file_id` and an eligible document type from the returned context;
3. map worker nationality only for passports and send null country for ARC;
4. generate a fresh UUID request ID;
5. call `OcrRuntimeClient` after the context reader transaction has completed;
6. return the AI status-only result.

Keep the network call outside a Server DB transaction. The explicit endpoint avoids holding the file-link transaction open and gives operators a safe retry path.

- [ ] **Step 4: Run both repositories' automated verification**

Server:

```powershell
.\gradlew.bat test --tests "*PassportCountryCodeMapperTest" --tests "*WorkerDocumentOcrSecurityIntegrationTest"
.\gradlew.bat test
```

AI:

```powershell
python -m pytest
python -m ruff check app tests
```

Expected: all tests PASS, or only previously recorded unrelated lint findings remain while every changed file passes targeted Ruff.

- [ ] **Step 5: Add a redacted local smoke script and documentation**

The PowerShell script must read these environment variables and refuse to run if any are absent:

```text
FOWOCO_INTERNAL_API_TOKEN
OCR_SAMPLE_FILE
OCR_WORKER_DOCUMENT_ID
OCR_WORKER_ID
OCR_COMPANY_ID
OCR_DOCUMENT_TYPE
OCR_COUNTRY_CODE
```

It posts the sample to the local AI endpoint and prints only HTTP status, `ocr_status`, template ID, side, and review reasons. It must never print file bytes or recognized fields. Document the Server trigger, AI endpoint, template map, configuration, and retry behavior.

Document this least-privilege production role contract without a password:

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

State that deployment supplies the password through secret management and that every AI transaction sets `app.company_id` before SELECT/UPDATE so the existing/future RLS policy applies.

- [ ] **Step 6: Commit integration changes separately**

Server:

```powershell
git add src/main/java/com/fowoco/server/ocrintegration src/main/java/com/fowoco/server/worker/api/WorkerDocumentOcrController.java src/main/java/com/fowoco/server/worker/api/WorkerDocumentOcrResponse.java src/test/java/com/fowoco/server/ocrintegration src/test/java/com/fowoco/server/worker/WorkerDocumentOcrSecurityIntegrationTest.java docs/ai-runtime-contract.md docs/ocr-database-role.md
git commit -m "feat: trigger OCR for worker documents"
```

AI:

```powershell
git add README.md scripts/smoke_clova_ocr.ps1
git commit -m "docs: add CLOVA OCR smoke workflow"
```

- [ ] **Step 7: Run the optional live smoke test**

With the CLOVA invoke URL, secret, database URL, restricted AI DB account, and non-production sample configured locally:

```powershell
.\scripts\smoke_clova_ocr.ps1
```

Expected: HTTP 200 with `SUCCEEDED` or `REVIEW_REQUIRED`; the scoped `worker_document` row contains normalized OCR fields and confidences, and logs contain identifiers/status only.

## Final Review Checklist

- [ ] Confirm `git diff --check` passes in both repositories.
- [ ] Confirm no secret or real identity data appears in tracked files: `rg -n "X-OCR-SECRET|passport_number.*[A-Z0-9]{6}|alien_registration_number.*[0-9]{6}" .` returns no credential/real-data match.
- [ ] Confirm the AI SQL allow-list contains every approved front/back field and no Server-owned field.
- [ ] Confirm all AI DB operations set `app.company_id` transaction-locally before touching `worker_document`.
- [ ] Confirm Server and AI contract names match exactly, including snake_case multipart and response fields.
- [ ] Confirm both full test suites pass and the manual smoke output is redacted.
