# Stateless OCR Response Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the database-owning worker-document OCR flow with a stateless API that returns normalized fields and field confidences to the Server.

**Architecture:** The FastAPI route validates the internal request envelope and builds a database-free command. `OcrService` validates the file, resolves an approved CLOVA template, calls CLOVA once, normalizes the response, and returns the result; the runtime owns only an HTTP client. The repository, PostgreSQL configuration, DB-only errors, and psycopg dependency are deleted.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic 2, httpx, pytest/pytest-asyncio, Ruff, uv

## Global Constraints

- Keep the endpoint at `POST /internal/v1/ocr/worker-documents/{worker_document_id}`.
- Require `Authorization: Bearer <internal-token>` and `X-Request-Id: <request-id>`.
- Require `X-Request-Id` and multipart `request_id` to be equal UUIDs; mismatch returns HTTP 400.
- Accept only JPEG, PNG, or single-page PDF files up to 20 MiB using the existing validation rules.
- Preserve passport template mappings `KOR=43019`, `PHL=43021`, `JPN=43022`, `CHN=43023`, and `VNM=43038`.
- Preserve ARC template IDs 43024 and 43025 and ignore `country_code` for ARC.
- Return only allowlisted normalized fields and their confidences; never return or log the raw file or raw CLOVA response.
- Return invalid transport data as 422, invalid OCR requests as 400, oversize files as 413, Provider failures as 502, timeouts as 504, and disabled/unavailable OCR as 503.
- Do not add Server persistence, encryption, HR review, migrations, or client-facing OCR APIs.
- Preserve the user's untracked `.worktrees/` directory and unrelated changes.

---

## File Structure

- `app/ocr/models.py`: database-free OCR commands, results, and application errors.
- `app/ocr/service.py`: file validation, template selection, CLOVA invocation, and normalization orchestration.
- `tests/ocr/test_service.py`: service contract and failure behavior without a repository.
- `app/api/schemas/ocr.py`: stateless HTTP response schema.
- `app/api/routes/ocr.py`: multipart/header parsing, request-ID validation, error translation, and response projection.
- `tests/api/test_ocr_endpoint.py`: full HTTP request/response and status-code contract.
- `app/ocr/runtime.py`: HTTP-only OCR lifespan construction and cleanup.
- `app/core/config.py`: OCR startup configuration without a database URL.
- `tests/ocr/test_runtime.py`: OCR enabled/disabled lifespan behavior without PostgreSQL.
- `app/ocr/repository.py`: delete; Server persistence is outside the AI runtime.
- `tests/ocr/test_repository.py`: delete with the removed repository.
- `pyproject.toml`, `uv.lock`: remove the project-level psycopg dependency.
- `tests/agents/test_workflow_adapters.py`: Renewal Bridge regression for the new response envelope.
- `docs/clova-ocr-integration.md`, `README.md`, `.env.example`: document the stateless contract and startup variables.
- `scripts/smoke_clova_ocr.ps1`, `tests/ocr/test_smoke_script.py`: exercise the new request shape without exposing normalized values.

---

### Task 1: Make the OCR domain service stateless

**Files:**
- Modify: `tests/ocr/test_service.py`
- Modify: `app/ocr/models.py`
- Modify: `app/ocr/service.py`

**Interfaces:**
- Consumes: `normalize_clova_response(raw, selection, threshold, resolver) -> NormalizedOcrResult` and the existing `TemplateResolver`/CLOVA client contracts.
- Produces: `OcrCommand(request_id, worker_document_id, document_type, country_code, file)`, `OcrProcessResult(..., fields, field_confidences, review_reasons)`, and `OcrFileTooLarge`.

- [ ] **Step 1: Replace repository-oriented service fixtures with a stateless command and service**

In `tests/ocr/test_service.py`, remove `datetime`, `OcrScope`, all DB errors, `FakeRepository`, and `NOW`. Define the command and builder as:

```python
def command(
    *,
    content: bytes = b"synthetic-image-bytes",
    content_type: str = "image/png",
    filename: str = "sample.png",
    document_type: DocumentType = DocumentType.PASSPORT_COPY,
    country_code: str | None = "KOR",
) -> OcrCommand:
    return OcrCommand(
        request_id=REQUEST_ID,
        worker_document_id=DOCUMENT_ID,
        document_type=document_type,
        country_code=country_code,
        file=OcrFile(filename, content_type, content),
    )


def build_service(
    clova: FakeClovaClient | None = None,
) -> tuple[OcrService, FakeClovaClient]:
    actual_clova = clova or FakeClovaClient()
    return (
        OcrService(
            resolver=TemplateResolver(),
            clova_client=actual_clova,
            confidence_threshold=0.80,
        ),
        actual_clova,
    )
```

Replace the success test with assertions that the result itself carries normalized data:

```python
@pytest.mark.asyncio
async def test_success_calls_clova_and_returns_normalized_result() -> None:
    service, clova = build_service()

    result = await service.process(command())

    assert clova.calls == [((43019,), "sample.png")]
    assert result.status is OcrStatus.SUCCEEDED
    assert result.worker_document_id == DOCUMENT_ID
    assert result.fields["passport_number"] == "M00000000"
    assert result.field_confidences["passport_number"] == 0.99
```

Update invalid-file and unsupported-country tests to assert only that `clova.calls == []`.
Replace provider failure tests with direct mappings that do not mention persistence:

```python
@pytest.mark.asyncio
async def test_clova_timeout_raises_safe_timeout() -> None:
    service, _ = build_service(FakeClovaClient(error=ClovaTimeoutError("timed out")))
    with pytest.raises(OcrUpstreamTimeout, match="timed out"):
        await service.process(command())


@pytest.mark.asyncio
async def test_clova_provider_error_raises_safe_failure() -> None:
    service, _ = build_service(FakeClovaClient(error=ClovaProviderError("request failed")))
    with pytest.raises(OcrUpstreamFailure, match="failed"):
        await service.process(command())
```

Change the oversized-file row into its own test expecting `OcrFileTooLarge`, and make the
review-required test assert returned `fields` and `field_confidences` instead of a saved
repository result.

- [ ] **Step 2: Run the focused service tests and confirm the old model/service fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ocr/test_service.py -q
```

Expected: FAIL because `OcrCommand` still requires `scope`, `OcrService` still requires
`repository` and `clock`, and `OcrFileTooLarge` does not exist.

- [ ] **Step 3: Replace database-scoped domain types with response-bearing stateless types**

In `app/ocr/models.py`, delete `OcrScope`, `DatabaseSchemaMismatch`,
`OcrPersistenceError`, `OcrRequestSuperseded`, and `WorkerDocumentNotFound`. Change the
command/result definitions and add a distinct size error:

```python
@dataclass(frozen=True)
class OcrCommand:
    request_id: UUID
    worker_document_id: UUID
    document_type: DocumentType
    country_code: str | None
    file: OcrFile


@dataclass(frozen=True)
class OcrProcessResult:
    request_id: UUID
    worker_document_id: UUID
    status: OcrStatus
    matched_template_id: int | None
    document_side: DocumentSide | None
    fields: Mapping[str, FieldValue]
    field_confidences: Mapping[str, float]
    review_reasons: tuple[str, ...]


class InvalidOcrRequest(ValueError):
    """The OCR command is invalid before any provider call."""


class OcrFileTooLarge(InvalidOcrRequest):
    """The uploaded OCR file exceeds the configured contract limit."""
```

- [ ] **Step 4: Remove all repository and clock work from `OcrService`**

Change `OcrService.__init__` to accept only `resolver`, `clova_client`, and
`confidence_threshold`. Make `process` validate, resolve, infer, normalize, and return:

```python
async def process(self, command: OcrCommand) -> OcrProcessResult:
    self._validate_file(command)
    try:
        selection = self._resolver.resolve(command.document_type, command.country_code)
    except TemplateResolutionError as exc:
        raise InvalidOcrRequest(str(exc)) from exc

    try:
        raw = await self._clova_client.infer(
            command.file,
            selection.template_ids,
            command.request_id,
        )
    except ClovaTimeoutError as exc:
        raise OcrUpstreamTimeout("CLOVA OCR timed out") from exc
    except ClovaProviderError as exc:
        raise OcrUpstreamFailure("CLOVA OCR failed") from exc

    normalized = normalize_clova_response(
        raw,
        selection,
        self._confidence_threshold,
        self._resolver,
    )
    return OcrProcessResult(
        request_id=command.request_id,
        worker_document_id=command.worker_document_id,
        status=normalized.status,
        matched_template_id=normalized.matched_template_id,
        document_side=normalized.document_side,
        fields=dict(normalized.fields),
        field_confidences=dict(normalized.field_confidences),
        review_reasons=normalized.review_reasons,
    )
```

Raise `OcrFileTooLarge("OCR file is too large")` from the existing size check. Keep the
empty-content, MIME, filename, template, allowlist, and normalization rules unchanged.

- [ ] **Step 5: Run service and normalizer regression tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ocr/test_service.py tests/ocr/test_normalizer.py tests/ocr/test_template_resolver.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit the stateless service**

```powershell
git add app/ocr/models.py app/ocr/service.py tests/ocr/test_service.py
git commit -m "refactor(ocr): return normalized result without persistence"
```

---

### Task 2: Publish the new internal HTTP contract

**Files:**
- Modify: `tests/api/test_ocr_endpoint.py`
- Modify: `app/api/schemas/ocr.py`
- Modify: `app/api/routes/ocr.py`

**Interfaces:**
- Consumes: Task 1 `OcrCommand`, `OcrProcessResult`, `OcrFileTooLarge`,
  `OcrUpstreamFailure`, and `OcrUpstreamTimeout`.
- Produces: `OcrResponse` with `fields` and `field_confidences`; route parameters no longer
  include `worker_id` or `company_id`.

- [ ] **Step 1: Rewrite endpoint fixtures around the stateless request and complete response**

In `tests/api/test_ocr_endpoint.py`, remove DB-only error imports/constants. Build the fake
result with normalized values:

```python
self.result = result or OcrProcessResult(
    request_id=REQUEST_ID,
    worker_document_id=DOCUMENT_ID,
    status=OcrStatus.SUCCEEDED,
    matched_template_id=43019,
    document_side=None,
    fields={
        "passport_number": "M00000000",
        "date_of_birth": date(2000, 1, 2),
    },
    field_confidences={"passport_number": 0.99, "date_of_birth": 0.98},
    review_reasons=(),
)
```

Make `request_data()` contain only `request_id`, `document_type`, and `country_code`. Make
`post_ocr()` include both headers by default while preserving an explicitly supplied empty
header mapping for the authentication test:

```python
(
    headers
    if headers is not None
    else {
        "Authorization": "Bearer internal-test-token",
        "X-Request-Id": str(REQUEST_ID),
    }
)
```

Assert a successful response equals:

```python
{
    "request_id": str(REQUEST_ID),
    "worker_document_id": str(DOCUMENT_ID),
    "ocr_status": "SUCCEEDED",
    "matched_template_id": 43019,
    "document_side": None,
    "fields": {
        "passport_number": "M00000000",
        "date_of_birth": "2000-01-02",
    },
    "field_confidences": {
        "passport_number": 0.99,
        "date_of_birth": 0.98,
    },
    "review_reasons": [],
}
```

Also assert `command.worker_document_id == DOCUMENT_ID` and that `OcrCommand` has neither a
`worker_id` nor `company_id` attribute.

- [ ] **Step 2: Add request-ID, size, and retained error-status tests**

Add these cases:

```python
def test_endpoint_requires_x_request_id(authenticated_client) -> None:
    client, service = authenticated_client
    response = post_ocr(
        client,
        headers={"Authorization": "Bearer internal-test-token"},
    )
    assert response.status_code == 422
    assert service.commands == []


def test_endpoint_rejects_mismatched_request_ids(authenticated_client) -> None:
    client, service = authenticated_client
    response = post_ocr(
        client,
        headers={
            "Authorization": "Bearer internal-test-token",
            "X-Request-Id": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
        },
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid OCR request"}
    assert service.commands == []


def test_oversized_file_returns_413(authenticated_client) -> None:
    client, service = authenticated_client
    service.error = OcrFileTooLarge("OCR file is too large")
    response = post_ocr(client)
    assert response.status_code == 413
    assert response.json() == {"detail": "OCR file is too large"}
```

Keep Provider failure 502, timeout 504, disabled 503, invalid UUID/enum 422, missing passport
country 400, authentication 401, and review-required 200 tests. Delete DB-only 404, 409, and
500 cases.

- [ ] **Step 3: Run endpoint tests and confirm the old route/schema fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api/test_ocr_endpoint.py -q
```

Expected: FAIL because the route still requires tenant IDs and does not accept/validate the
header or serialize the result fields.

- [ ] **Step 4: Extend the response schema**

In `app/api/schemas/ocr.py`, import `date` and define:

```python
class OcrResponse(BaseModel):
    request_id: UUID
    worker_document_id: UUID
    ocr_status: OcrStatus
    matched_template_id: int | None
    document_side: DocumentSide | None
    fields: dict[str, str | date]
    field_confidences: dict[str, float]
    review_reasons: list[str]
```

- [ ] **Step 5: Change the route parameters, validation, and error mapping**

In `app/api/routes/ocr.py`:

- Import `Header` and `OcrFileTooLarge`.
- Delete imports and handlers for `OcrScope` and all DB-only errors.
- Add `x_request_id: Annotated[UUID, Header(alias="X-Request-Id")]`.
- Remove `worker_id` and `company_id` form parameters.
- Before reading/building the command, return HTTP 400 with fixed detail
  `"Invalid OCR request"` if `x_request_id != request_id`.
- Build `OcrCommand(worker_document_id=worker_document_id, ...)` directly.
- Catch `OcrFileTooLarge` before `InvalidOcrRequest` and map it to HTTP 413 with fixed detail
  `"OCR file is too large"`.
- Return `fields=dict(result.fields)` and
  `field_confidences=dict(result.field_confidences)` in `OcrResponse`.

- [ ] **Step 6: Run endpoint and OpenAPI tests**

Run the endpoint tests and inspect the generated OpenAPI response schema:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api/test_ocr_endpoint.py -q
.\.venv\Scripts\python.exe -c "from app.main import create_app; s=create_app().openapi(); o=s['components']['schemas']['OcrResponse']['properties']; assert 'fields' in o and 'field_confidences' in o"
```

Expected: PASS.

- [ ] **Step 7: Commit the HTTP contract**

```powershell
git add app/api/schemas/ocr.py app/api/routes/ocr.py tests/api/test_ocr_endpoint.py
git commit -m "feat(ocr): expose stateless normalized response"
```

---

### Task 3: Remove the PostgreSQL runtime and dependency surface

**Files:**
- Modify: `tests/ocr/test_runtime.py`
- Modify: `app/ocr/runtime.py`
- Modify: `app/core/config.py`
- Delete: `app/ocr/repository.py`
- Delete: `tests/ocr/test_repository.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `tests/api/test_ocr_endpoint.py`

**Interfaces:**
- Consumes: Task 1 repository-free `OcrService` constructor.
- Produces: `create_ocr_lifespan(settings)` that owns only `httpx.AsyncClient`; enabled OCR
  settings require CLOVA URL, secret, and internal API token but no database URL.

- [ ] **Step 1: Rewrite runtime tests to prohibit database setup**

Delete `FakePool` and `FakeRepository` from `tests/ocr/test_runtime.py`. Remove
`database_url` from `enabled_settings()`. Keep `FakeHttpClient`, then assert:

```python
@pytest.mark.asyncio
async def test_enabled_lifespan_exposes_service_and_closes_http_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeHttpClient.instances.clear()
    monkeypatch.setattr(runtime.httpx, "AsyncClient", FakeHttpClient)
    app = FastAPI()

    async with runtime.create_ocr_lifespan(enabled_settings())(app):
        assert app.state.ocr_service is not None
        assert len(FakeHttpClient.instances) == 1
        assert FakeHttpClient.instances[0].closed is False

    assert FakeHttpClient.instances[0].closed is True
    assert not hasattr(app.state, "ocr_service")
```

The disabled test should monkeypatch only `httpx.AsyncClient` to fail if called.

In `tests/api/test_ocr_endpoint.py`, remove `FOWOCO_DATABASE_URL` from the required-setting
parameterization and add:

```python
def test_enabled_ocr_accepts_missing_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOWOCO_CLOVA_OCR_ENABLED", "true")
    monkeypatch.setenv("FOWOCO_CLOVA_OCR_INVOKE_URL", "https://example.invalid/infer")
    monkeypatch.setenv("FOWOCO_CLOVA_OCR_SECRET", "local-test-secret")
    monkeypatch.setenv("FOWOCO_INTERNAL_API_TOKEN", "internal-test-token")
    monkeypatch.delenv("FOWOCO_DATABASE_URL", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.clova_ocr_enabled is True
```

- [ ] **Step 2: Run runtime/startup tests and confirm they fail against DB requirements**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ocr/test_runtime.py tests/api/test_ocr_endpoint.py -q
```

Expected: FAIL because the current lifespan creates a pool/repository and settings still
require `database_url`.

- [ ] **Step 3: Reduce runtime construction to HTTP resources**

In `app/ocr/runtime.py`, delete `datetime`, `AsyncConnectionPool`, and repository imports.
Construct `ClovaTemplateOcrClient` from one `httpx.AsyncClient`, construct `OcrService` with
`resolver`, `clova_client`, and `confidence_threshold`, yield, then delete the app state and
close the HTTP client in `finally`.

- [ ] **Step 4: Remove database configuration and code**

In `app/core/config.py`, delete `database_url` and remove it from
`validate_enabled_ocr_settings.required`. Delete `app/ocr/repository.py` and
`tests/ocr/test_repository.py` with the patch tool so no repository code remains.

- [ ] **Step 5: Remove psycopg from project metadata and refresh the lockfile**

Delete this line from `pyproject.toml`:

```toml
"psycopg[binary,pool]>=3.2,<4",
```

Then run:

```powershell
uv lock
```

Expected: `uv.lock` is regenerated without direct or transitive psycopg packages required by
this project.

- [ ] **Step 6: Prove the DB surface is absent and run focused tests**

Run:

```powershell
rg -n "PsycopgWorkerDocumentOcrRepository|AsyncConnectionPool|app\.ocr\.repository|database_url|OcrPersistenceError|OcrRequestSuperseded|WorkerDocumentNotFound|DatabaseSchemaMismatch" app tests pyproject.toml
```

Expected: no matches. Then run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ocr tests/api/test_ocr_endpoint.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit database removal**

```powershell
git add app/ocr/runtime.py app/core/config.py app/ocr/repository.py tests/ocr/test_runtime.py tests/ocr/test_repository.py tests/api/test_ocr_endpoint.py pyproject.toml uv.lock
git commit -m "refactor(ocr): remove server database integration"
```

---

### Task 4: Verify the Renewal Bridge consumes stateless fields

**Files:**
- Modify: `tests/agents/test_workflow_adapters.py`

**Interfaces:**
- Consumes: existing `normalize_ocr_output(raw, base_slots, base_missing)`.
- Produces: regression evidence that top-level `fields` is the only stateless response payload
  interpreted as worker slots.

- [ ] **Step 1: Add a representative response-envelope regression test**

Append to `tests/agents/test_workflow_adapters.py`:

```python
def test_normalize_ocr_output_consumes_stateless_response_fields_only() -> None:
    out = normalize_ocr_output(
        {
            "request_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "worker_document_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            "ocr_status": "REVIEW_REQUIRED",
            "matched_template_id": 43019,
            "document_side": None,
            "fields": {
                "passport_number": "M12345678",
                "surname": "NGUYEN",
                "given_names": "VAN AN",
                "date_of_birth": "1995-03-01",
            },
            "field_confidences": {
                "passport_number": 0.98,
                "surname": 0.94,
            },
            "review_reasons": ["low_confidence:given_names"],
        },
        base_slots={},
        base_missing=["passport_number", "full_name"],
    )

    assert out["ocr_result"] == {
        "passport_number": "M12345678",
        "full_name": "NGUYEN VAN AN",
        "date_of_birth": "1995-03-01",
    }
    assert out["slots"] == out["ocr_result"]
    assert out["missing_slots"] == []
    assert "field_confidences" not in out["slots"]
    assert "matched_template_id" not in out["slots"]
```

- [ ] **Step 2: Run the Bridge test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/agents/test_workflow_adapters.py::test_normalize_ocr_output_consumes_stateless_response_fields_only -q
```

Expected: PASS because the bridge already prioritizes top-level `fields`; no production bridge
change is expected.

- [ ] **Step 3: Run all workflow bridge/adapter tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/agents/test_workflow_adapters.py tests/agents/test_workflow_bridges.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit the Bridge regression coverage**

```powershell
git add tests/agents/test_workflow_adapters.py app/agents/workflow_graph/adapters.py
git commit -m "test(renewal): verify stateless OCR field bridge"
```

---

### Task 5: Update contract documentation and smoke tooling

**Files:**
- Modify: `tests/ocr/test_smoke_script.py`
- Modify: `scripts/smoke_clova_ocr.ps1`
- Modify: `docs/clova-ocr-integration.md`
- Modify: `README.md`
- Modify: `.env.example`

**Interfaces:**
- Consumes: Task 2 request/response contract and Task 3 environment contract.
- Produces: operator-facing setup and smoke-test instructions with no database credentials or
  tenant-scope form fields.

- [ ] **Step 1: Specify the smoke script request shape**

In `tests/ocr/test_smoke_script.py`, remove `OCR_WORKER_ID` and `OCR_COMPANY_ID` from the
environment cleanup list and add a static contract test:

```python
def test_smoke_script_uses_stateless_request_contract() -> None:
    script = Path(__file__).parents[2] / "scripts" / "smoke_clova_ocr.ps1"
    source = script.read_text(encoding="utf-8")

    assert '"X-Request-Id"' in source
    assert '"request_id"' in source
    assert "OCR_WORKER_ID" not in source
    assert "OCR_COMPANY_ID" not in source
    assert "field_count:" in source
    assert "ConvertTo-Json" not in source
```

- [ ] **Step 2: Run the smoke-script tests and confirm the old script fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ocr/test_smoke_script.py -q
```

Expected: FAIL because the current script still requires/sends the two tenant identifiers and
does not send `X-Request-Id`.

- [ ] **Step 3: Update the PowerShell smoke request**

In `scripts/smoke_clova_ocr.ps1`:

- Remove `OCR_WORKER_ID` and `OCR_COMPANY_ID` from `$requiredVariables`.
- Add `$client.DefaultRequestHeaders.Add("X-Request-Id", $requestId)` after assigning the
  Bearer header.
- Remove the two corresponding `$form.Add(...)` calls.
- Keep `request_id`, `document_type`, optional `country_code`, and `file`.
- After success, print `ocr_status`, `matched_template_id`, `document_side`, review reasons,
  and a count derived from `$result.fields.PSObject.Properties.Count`; never print field
  values or confidence values.

- [ ] **Step 4: Rewrite the OCR integration contract around Server-owned storage**

In `docs/clova-ocr-integration.md`, replace the DB workflow/column/grant/RLS sections with:

- the exact request headers and four multipart fields;
- the alpha-3/template table;
- the complete stateless response example including `fields` and `field_confidences`;
- the 400/413/422/502/503/504 error table;
- the Server/AI ownership boundary;
- privacy rules prohibiting raw file/raw CLOVA response logging;
- startup variables `FOWOCO_CLOVA_OCR_ENABLED`, `FOWOCO_CLOVA_OCR_INVOKE_URL`,
  `FOWOCO_CLOVA_OCR_SECRET`, `FOWOCO_CLOVA_OCR_TIMEOUT_SECONDS`,
  `FOWOCO_CLOVA_OCR_CONFIDENCE_THRESHOLD`, and `FOWOCO_INTERNAL_API_TOKEN`.

Do not retain SQL, grants, database URLs, worker/company form fields, or claims that AI saves
the result.

- [ ] **Step 5: Update README and example environment**

Change the README OCR section to say AI returns normalized data and Server persists it. Add
the same six OCR startup variables to `.env.example` with OCR disabled by default and clearly
non-production example URL/secret values. Do not add `FOWOCO_DATABASE_URL`.

- [ ] **Step 6: Run documentation and smoke contract checks**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ocr/test_smoke_script.py -q
rg -n "OCR_WORKER_ID|OCR_COMPANY_ID|FOWOCO_DATABASE_URL|worker_document.*UPDATE|GRANT (SELECT|UPDATE)" docs/clova-ocr-integration.md README.md .env.example scripts/smoke_clova_ocr.ps1
```

Expected: smoke tests PASS and the search returns no matches.

- [ ] **Step 7: Commit documentation and smoke tooling**

```powershell
git add tests/ocr/test_smoke_script.py scripts/smoke_clova_ocr.ps1 docs/clova-ocr-integration.md README.md .env.example
git commit -m "docs(ocr): document stateless server-owned storage contract"
```

---

### Task 6: Run final security and regression verification

**Files:**
- Verify: all files changed in Tasks 1-5

**Interfaces:**
- Consumes: the complete implementation.
- Produces: evidence that the issue acceptance criteria and repository quality gates pass.

- [ ] **Step 1: Run the complete OCR and Renewal Bridge suites**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ocr tests/api/test_ocr_endpoint.py tests/agents/test_workflow_adapters.py tests/agents/test_workflow_bridges.py -q
```

Expected: PASS.

- [ ] **Step 2: Run the full project test suite**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: PASS with no failures.

- [ ] **Step 3: Run static analysis and diff validation**

```powershell
.\.venv\Scripts\python.exe -m ruff check app tests
git diff --check origin/develop...HEAD
```

Expected: both commands succeed with no findings.

- [ ] **Step 4: Verify no OCR database or unsafe logging surface remains**

```powershell
rg -n "PsycopgWorkerDocumentOcrRepository|AsyncConnectionPool|app\.ocr\.repository|FOWOCO_DATABASE_URL|database_url|OcrPersistenceError|OcrRequestSuperseded|WorkerDocumentNotFound|DatabaseSchemaMismatch" app tests pyproject.toml README.md docs/clova-ocr-integration.md scripts/smoke_clova_ocr.ps1
rg -n "logger\..*(content|fields|raw)|print\(.*(content|fields|raw)|response\.text" app/ocr app/api/routes/ocr.py
```

Expected: both searches return no matches.

- [ ] **Step 5: Inspect the final diff and commit any verification-only corrections**

```powershell
git status --short
git diff --stat origin/develop...HEAD
git log --oneline origin/develop..HEAD
```

Expected: only the approved OCR implementation, tests, docs, dependency lockfile, the design
document, and this plan are present. If verification required a correction, stage only the
affected approved files and commit it with a message describing that concrete correction.
