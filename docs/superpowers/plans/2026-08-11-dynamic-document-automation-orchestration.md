# Dynamic Document Automation Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compose the mapping and read-only query subsystems into an isolated MCP document workflow with new internal APIs, shadow rollout controls, approval, visual verification, and downloadable artifacts while preserving every existing route.

**Architecture:** A selectively ported automation workflow from commit `fcefe98` lives under the new `dynamic_automation` package. A router identifies registered templates for handoff to the unchanged legacy endpoint and sends unknown documents to conversion plus MCP analysis; the dynamic path maps fields, optionally executes read-only lookup, creates a signed MCP Edit Plan, and records feedback. New routes and dependencies are additive and disabled by default.

**Tech Stack:** Python 3.11, FastAPI, Pydantic 2, httpx, existing document conversion/editing services, existing HWP Editor MCP Control Plane, pytest

**Design Reference:** `docs/superpowers/specs/2026-08-11-dynamic-document-automation-design.md`

**Prerequisites:** Complete `2026-08-11-dynamic-field-mapping-foundation.md` and `2026-08-11-read-only-document-query.md` before this plan.

## Global Constraints

- Do not change the response or behavior of existing `/api/v1/documents/*`, `/internal/v1/workflows/*`, OCR, analyses, or language routes.
- Keep `app/agents/workflow_graph/document_field_map.py` and all registered-template mappers unchanged.
- Add new internal routes only under `/internal/v1/document-automation`.
- Disable the feature by default and support `shadow`, `lookup`, and `fill` modes.
- The `shadow` mode must not connect to DB or create/apply an Edit Plan.
- The `lookup` mode may run read-only queries but must not create/apply an Edit Plan.
- The `fill` mode may create a plan only from `MATCHED` plus `FOUND` values and still requires the existing MCP approval and visual-review lifecycle.
- Preserve source document hashes, plan hashes, attempt idempotency, artifact boundaries, and safe error messages.
- Reuse MCP, conversion, and editing services through adapters; do not copy their implementations.

---

## File Structure

- `app/documents/dynamic_automation/mcp.py`: HTTP MCP adapter and protocol.
- `app/documents/dynamic_automation/routing.py`: known, conversion, and dynamic route decisions.
- `app/documents/dynamic_automation/workflow_models.py`: statuses and persisted workflow contracts.
- `app/documents/dynamic_automation/repository.py`: expiring workflow artifact repository.
- `app/documents/dynamic_automation/service.py`: end-to-end orchestration and mode gates.
- `app/documents/dynamic_automation/edit_plan.py`: canonical results to MCP edits/dispositions.
- `app/api/schemas/dynamic_document_automation.py`: strict camelCase internal contracts.
- `app/api/routes/dynamic_document_automation.py`: new protected endpoints.
- `app/api/dependencies.py`: additive service composition functions.
- `app/main.py`: include the new internal router.
- `app/core/config.py`: disabled-by-default feature and MCP settings.
- `tests/documents/dynamic_automation/`: service and workflow unit tests.
- `tests/api/test_dynamic_document_automation_endpoint.py`: API and regression tests.
- `tests/integration/dynamic_automation/test_end_to_end.py`: opt-in MCP/PostgreSQL flow.
- `docs/dynamic-document-automation-operations.md`: deployment, shadow, rollback, and metrics runbook.

### Task 1: Port the MCP adapter and expiring workflow repository into the new namespace

**Files:**
- Create: `app/documents/dynamic_automation/mcp.py`
- Create: `app/documents/dynamic_automation/workflow_models.py`
- Create: `app/documents/dynamic_automation/repository.py`
- Modify: `hwp-editor/src/hwp_mcp/server.py:632-712`
- Modify: `hwp-editor/src/hwp_mcp/api.py:21-111`
- Modify: `hwp-editor/src/hwp_mcp/plans.py:84-121`
- Test: `tests/documents/dynamic_automation/test_mcp_adapter.py`
- Test: `tests/documents/dynamic_automation/test_workflow_repository.py`
- Test: `hwp-editor/tests/test_api.py`

**Interfaces:**
- Produces: `McpDocumentAnalyzer.analyze/create_plan/approve_plan/apply_plan/finalize_plan`.
- Produces: `DynamicAutomationRun`, `DynamicAutomationStatus`, and `AutomationRunRepository`.
- Consumes: existing MCP HTTP endpoints and local artifact root.

Define the workflow boundary before implementing the adapter:

```python
class DynamicAutomationMode(StrEnum):
    SHADOW = "shadow"
    LOOKUP = "lookup"
    FILL = "fill"


class DynamicAutomationStatus(StrEnum):
    LEGACY_ROUTE = "legacy_route"
    INPUT_REQUIRED = "input_required"
    SHADOW_REVIEW = "shadow_review"
    LOOKUP_REVIEW = "lookup_review"
    PLAN_REVIEW = "plan_review"
    VISION_REVIEW_REQUIRED = "vision_review_required"
    COMPLETED = "completed"
    FAILED = "failed"


class DynamicAutomationStartCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_path: Path
    task_id: UUID
    mode: DynamicAutomationMode
    worker_id: UUID | None = None
    company_id: UUID | None = None
    attempt_id: UUID
```

- [ ] **Step 1: Write failing HTTP boundary and repository tests**

```python
def test_mcp_adapter_rejects_source_outside_shared_root(tmp_path: Path) -> None:
    adapter = HttpMcpDocumentAnalyzer("http://mcp", tmp_path / "shared")
    with pytest.raises(McpAutomationError, match="shared root"):
        adapter.analyze(tmp_path / "outside.hwpx")


def test_repository_rejects_path_escape_and_expires_runs(tmp_path: Path) -> None:
    repository = AutomationRunRepository(tmp_path, ttl_seconds=1)
    run_id, _ = repository.allocate()
    with pytest.raises(AutomationRunNotFound):
        repository.artifact(run_id, "../escape")
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/documents/dynamic_automation/test_mcp_adapter.py tests/documents/dynamic_automation/test_workflow_repository.py -q`

Expected: FAIL because the adapter and repository are absent.

- [ ] **Step 3: Selectively port and tighten the old automation boundary**

Port the relevant behavior from `fcefe98:app/documents/automation/mcp.py` and workflow repository code, renaming the package and models. Keep shared-root path checks, HTTP 4xx/5xx distinction, TTL, `chmod(0o600)` best effort, stable JSON writes, and path-escape rejection. Do not port test profiles, the old substring mapper, or direct canonical values from callers.

- [ ] **Step 4: Add the explicit authenticated approval bridge required by the HTTP adapter**

Port `approve_edit_plan_from_frontend(path, plan_id, approver_subject)` from `fcefe98` into the current MCP server as a separate function that revalidates the stored plan and artifact hash, signs the approval receipt, and records `approver_subject`. Extend `ApprovalReceipt.source` and `create_approval_receipt(..., source=...)` to accept exactly `mcp_elicitation` or `frontend_api`. Expose frontend approval only as additive `POST /plans/approve` with a strict `ApprovePlanRequest`; keep the interactive MCP `approve_edit_plan` tool unchanged. Add API tests for empty subject, stale plan, duplicate approval, receipt source, and a valid signed receipt.

- [ ] **Step 5: Sanitize persisted MCP analysis**

When analysis returns `next_action=confirm_visual_candidates` with mapped SVG geometry, call the existing confirmation endpoint with the reviewed candidate list; an empty list is valid only when the MCP response contains no SVG-only candidates. Persist only `analysis_contract`, layout/analysis hash, and registry keys `field_id`, `target_id`, `label`, `type`, `required`, `kind`, `current_text`, and `constraints`. Do not persist rendered document text or PNG bytes in workflow JSON.

- [ ] **Step 6: Run tests and commit**

Run: `python -m pytest tests/documents/dynamic_automation/test_mcp_adapter.py tests/documents/dynamic_automation/test_workflow_repository.py -q`

Expected: PASS.

Run: `uv run --project hwp-editor pytest hwp-editor/tests/test_api.py -q`

Expected: PASS with the interactive approval tool unchanged and the new HTTP approval path covered.

```bash
git add app/documents/dynamic_automation/mcp.py app/documents/dynamic_automation/workflow_models.py app/documents/dynamic_automation/repository.py tests/documents/dynamic_automation hwp-editor/src/hwp_mcp/server.py hwp-editor/src/hwp_mcp/api.py hwp-editor/src/hwp_mcp/plans.py hwp-editor/tests/test_api.py
git commit -m "feat(doc-automation): add isolated MCP workflow boundary"
```

### Task 2: Route registered templates unchanged and unknown files through conversion/MCP

**Files:**
- Create: `app/documents/dynamic_automation/routing.py`
- Test: `tests/documents/dynamic_automation/test_dynamic_routing.py`

**Interfaces:**
- Consumes: `DocumentEditingService.inspect`, `DocumentConversionService.convert`, and `McpDocumentAnalyzer`.
- Produces: `DynamicRouteDecision(route, source_format, working_path, template_id, layout_fingerprint)`.
- Routes: `LEGACY`, `DYNAMIC`, or `CONVERSION_REQUIRED`.

- [ ] **Step 1: Write failing route isolation tests**

```python
def test_registered_template_returns_legacy_without_calling_mcp(registered_hwpx) -> None:
    decision = router_with_recorders().route(registered_hwpx)
    assert decision.route is DynamicRoute.LEGACY
    assert decision.template_id == "identity_guaranty_v129"
    assert mcp.calls == []


def test_unknown_hwp_converts_to_hwpx_before_mcp(unknown_hwp, tmp_path) -> None:
    decision = router.route(unknown_hwp, workspace=tmp_path)
    assert decision.route is DynamicRoute.DYNAMIC
    assert decision.working_path.suffix == ".hwpx"
    assert conversion.calls[0].target_format is DocumentFormat.HWPX
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/documents/dynamic_automation/test_dynamic_routing.py -q`

Expected: FAIL because the additive router is missing.

- [ ] **Step 3: Implement composition-only routing**

Call `DocumentEditingService.inspect` first. Return `LEGACY` immediately when `template_id` exists. Detect HWP/HWPX using existing format detection. For unknown HWP call `DocumentConversionService.convert(..., source_format=HWP, target_format=HWPX)` inside the workflow workspace; if conversion is unavailable return `CONVERSION_REQUIRED`. Unknown HWPX is `DYNAMIC`. Do not modify any existing registry or route.

- [ ] **Step 4: Run routing plus existing template tests**

Run: `python -m pytest tests/documents/dynamic_automation/test_dynamic_routing.py tests/documents/test_editing_service.py -q`

Expected: PASS and all existing template assertions remain unchanged.

- [ ] **Step 5: Commit Task 2**

```bash
git add app/documents/dynamic_automation/routing.py tests/documents/dynamic_automation/test_dynamic_routing.py
git commit -m "feat(doc-automation): route unknown documents additively"
```

### Task 3: Assemble safe MCP edits and complete field dispositions

**Files:**
- Create: `app/documents/dynamic_automation/edit_plan.py`
- Test: `tests/documents/dynamic_automation/test_edit_plan_assembly.py`

**Interfaces:**
- Consumes: sanitized MCP registry, `CanonicalMappingPlan`, and `CanonicalValueResult` collection.
- Produces: `assemble_edit_plan(...) -> EditPlanRequest(edits, dispositions)`.

- [ ] **Step 1: Write failing completeness and stale-field tests**

```python
def test_plan_includes_disposition_for_every_registry_field() -> None:
    request = assemble_edit_plan(REGISTRY, MAPPINGS, VALUES)
    assert set(request.dispositions) == {item["field_id"] for item in REGISTRY}
    assert request.dispositions["official"] == "intentionally_blank"
    assert request.dispositions["signature"] == "manual_after_export"


def test_only_matched_found_values_become_edits() -> None:
    request = assemble_edit_plan(REGISTRY, MIXED_MAPPINGS, MIXED_VALUES)
    assert [edit.field_id for edit in request.edits] == ["matched-found"]
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/documents/dynamic_automation/test_edit_plan_assembly.py -q`

Expected: FAIL because plan assembly is absent.

- [ ] **Step 3: Implement explicit disposition rules**

Map official regions to `intentionally_blank`, signable regions to `manual_after_export`, `MATCHED` plus `FOUND` to `provided`, unresolved required fields to `needs_input` in the application state without calling MCP create-plan, and unresolved optional fields to `not_applicable`. Copy `expected_text` and anchors from the same analyzed registry; reject missing/duplicate field IDs.

- [ ] **Step 4: Run tests and commit**

Run: `python -m pytest tests/documents/dynamic_automation/test_edit_plan_assembly.py -q`

Expected: PASS.

```bash
git add app/documents/dynamic_automation/edit_plan.py tests/documents/dynamic_automation/test_edit_plan_assembly.py
git commit -m "feat(doc-automation): assemble complete MCP edit plans"
```

### Task 4: Compose the mode-gated end-to-end service

**Files:**
- Create: `app/documents/dynamic_automation/service.py`
- Modify: `app/documents/dynamic_automation/workflow_models.py`
- Test: `tests/documents/dynamic_automation/test_dynamic_service.py`

**Interfaces:**
- Consumes: router, MCP adapter, context builder, mapper, QueryScope resolver, query pipeline, edit-plan assembler, repository, and feedback store.
- Produces: async `DynamicDocumentAutomationService.start(command)`, `submit_answers`, `execute`, `finalize`, and `result_path`.

- [ ] **Step 1: Write failing mode and state-transition tests**

```python
@pytest.mark.asyncio
async def test_shadow_mode_stops_after_mapping() -> None:
    run = await shadow_service.start(COMMAND)
    assert run.status is DynamicAutomationStatus.SHADOW_REVIEW
    assert query_executor.calls == []
    assert mcp.create_plan_calls == []


@pytest.mark.asyncio
async def test_lookup_mode_queries_but_never_creates_plan() -> None:
    run = await lookup_service.start(COMMAND)
    assert run.status is DynamicAutomationStatus.LOOKUP_REVIEW
    assert query_executor.calls
    assert mcp.create_plan_calls == []


@pytest.mark.asyncio
async def test_fill_mode_requires_all_required_values_before_plan() -> None:
    run = await fill_service.start(COMMAND_WITH_MISSING_REQUIRED)
    assert run.status is DynamicAutomationStatus.INPUT_REQUIRED
    assert mcp.create_plan_calls == []
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/documents/dynamic_automation/test_dynamic_service.py -q`

Expected: FAIL because the orchestration service is absent.

- [ ] **Step 3: Implement start flow and fail-closed modes**

Implement route→analyze→context→map for all dynamic modes. In `lookup`, additionally resolve scope and run validated queries. In `fill`, normalize values and assemble/create the MCP plan only when required fields are resolved. Persist every transition and source SHA-256. A `LEGACY` decision returns `LEGACY_ROUTE` metadata so the integration caller continues through the existing endpoint; this new workflow never invokes or changes the legacy service itself.

- [ ] **Step 4: Implement answers, approval execution, and finalization**

Questions use opaque SHA-256 IDs derived from field and canonical IDs. Answer submission updates only named questions and regenerates the plan hash. Execution requires the caller's approved plan hash, calls the existing MCP approval/apply lifecycle, and moves to `VISION_REVIEW_REQUIRED`. Finalization succeeds only after MCP records Vision PASS. Preserve attempt-id idempotency and reject reuse with a different request hash.

- [ ] **Step 5: Run service tests and commit**

Run: `python -m pytest tests/documents/dynamic_automation/test_dynamic_service.py -q`

Expected: PASS for shadow, lookup, fill, ambiguous, missing scope, policy reject, MCP outage, retry, and stale plan cases.

```bash
git add app/documents/dynamic_automation/service.py app/documents/dynamic_automation/workflow_models.py tests/documents/dynamic_automation/test_dynamic_service.py
git commit -m "feat(doc-automation): compose dynamic automation workflow"
```

### Task 5: Add disabled-by-default configuration and service composition

**Files:**
- Modify: `app/core/config.py:19-97`
- Modify: `.env.example`
- Modify: `app/api/dependencies.py:118-242`
- Modify: `tests/conftest.py:11-26`
- Test: `tests/documents/dynamic_automation/test_composition.py`

**Interfaces:**
- Produces: `get_dynamic_document_automation_service()` and `get_dynamic_automation_repository()`.
- Consumes: existing document editing/conversion dependencies and all new subsystem factories.

- [ ] **Step 1: Write failing disabled/configuration tests**

```python
def test_dynamic_automation_is_disabled_by_default() -> None:
    assert Settings(_env_file=None).dynamic_automation_enabled is False


def test_fill_mode_requires_models_mcp_and_read_only_db() -> None:
    with pytest.raises(ValueError, match="fill mode requires"):
        Settings(_env_file=None, dynamic_automation_enabled=True,
                 dynamic_automation_mode="fill")
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/documents/dynamic_automation/test_composition.py -q`

Expected: FAIL because settings and factories are absent.

- [ ] **Step 3: Add exact feature settings and validators**

Add mode `shadow|lookup|fill`, MCP base URL/shared root/timeout, workflow root/TTL, catalog path, feedback path, model thresholds, and DB settings. `shadow` requires MCP and catalog; `lookup` additionally requires DB; `fill` additionally requires local models and signing-capable MCP. Keep `dynamic_automation_enabled=false` in defaults and `.env.example`.

- [ ] **Step 4: Compose cached services without changing existing factories**

Add new factory functions at the end of `dependencies.py`; do not alter return values of existing dependency functions. Extend the autouse fixture to clear only new caches. Make startup capability checks lazy until the new service is requested, so a disabled feature cannot prevent the existing app from starting.

- [ ] **Step 5: Run composition and application startup tests**

Run: `python -m pytest tests/documents/dynamic_automation/test_composition.py tests/test_health.py -q`

Expected: PASS with the default environment and no model/DB/MCP present.

- [ ] **Step 6: Commit Task 5**

```bash
git add app/core/config.py .env.example app/api/dependencies.py tests/conftest.py tests/documents/dynamic_automation/test_composition.py
git commit -m "feat(doc-automation): configure isolated automation services"
```

### Task 6: Expose new protected internal APIs without changing existing routes

**Files:**
- Create: `app/api/schemas/dynamic_document_automation.py`
- Create: `app/api/routes/dynamic_document_automation.py`
- Modify: `app/main.py:43-48`
- Modify: `app/api/openapi.py`
- Test: `tests/api/test_dynamic_document_automation_endpoint.py`

**Interfaces:**
- Produces endpoints under `/internal/v1/document-automation`.
- Consumes: `verify_internal_bearer` and `DynamicDocumentAutomationService`.

- [ ] **Step 1: Write failing API contract and disabled-route tests**

```python
@pytest.mark.asyncio
async def test_disabled_dynamic_automation_returns_404(client) -> None:
    response = await client.post("/internal/v1/document-automation/runs", data={}, files={})
    assert response.status_code == 404


def test_request_contract_forbids_extra_scope_fields() -> None:
    with pytest.raises(ValidationError):
        DynamicAutomationStartRequest.model_validate({
            "requestId": "r1", "attemptId": "a1", "tenantId": "t1",
            "workerId": "w1", "sql": "SELECT * FROM worker",
        })
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/api/test_dynamic_document_automation_endpoint.py -q`

Expected: FAIL because schemas and routes do not exist.

- [ ] **Step 3: Implement strict camelCase contracts**

Define `StartRequest` with request/attempt/tenant/task/worker/company IDs, deadline, contract/catalog version, and no caller field values. Define answer, execute approval, finalize, question, mapping summary, query summary, plan summary, and run response models using `alias_generator=to_camel`, `populate_by_name=True`, and `extra="forbid"`.

- [ ] **Step 4: Add the new endpoint set**

Implement:

```text
POST /internal/v1/document-automation/runs
GET  /internal/v1/document-automation/runs/{run_id}
POST /internal/v1/document-automation/runs/{run_id}/answers
POST /internal/v1/document-automation/runs/{run_id}/execute
POST /internal/v1/document-automation/runs/{run_id}/finalize
GET  /internal/v1/document-automation/runs/{run_id}/result
```

The start endpoint accepts multipart `request` JSON plus HWP/HWPX. Use existing upload size, type detection, filename validation, and internal Bearer verification. Map scope/policy conflicts to 409/422, disabled to 404, MCP/DB unavailable to 503, and never return DB values in errors.

- [ ] **Step 5: Run new API and existing API regression tests**

Run: `python -m pytest tests/api/test_dynamic_document_automation_endpoint.py tests/api/test_document_editing_endpoint.py tests/api/test_workflows_endpoint.py -q`

Expected: PASS with existing route response snapshots unchanged.

- [ ] **Step 6: Commit Task 6**

```bash
git add app/api/schemas/dynamic_document_automation.py app/api/routes/dynamic_document_automation.py app/main.py app/api/openapi.py tests/api/test_dynamic_document_automation_endpoint.py
git commit -m "feat(api): expose dynamic document automation runs"
```

### Task 7: Verify end-to-end security, feedback, rollout, and rollback

**Files:**
- Create: `tests/integration/dynamic_automation/test_end_to_end.py`
- Create: `tests/integration/dynamic_automation/test_adversarial.py`
- Create: `docs/dynamic-document-automation-operations.md`
- Modify: `compose.test.yml`
- Modify: `README.md`

**Interfaces:**
- Exercises the public interfaces from Tasks 1-6 and Plans 1-2.
- Produces an operations runbook and rollout gates.

- [ ] **Step 1: Write the failing end-to-end and injection tests**

```python
@pytest.mark.dynamic_automation_integration
async def test_unknown_form_maps_reads_plans_and_preserves_source(runtime) -> None:
    run = await runtime.start(UNKNOWN_HWPX, VERIFIED_SCOPE)
    assert run.plan_hash
    assert sha256(UNKNOWN_HWPX) == ORIGINAL_SHA256
    assert run.audit.query_count <= 4


@pytest.mark.dynamic_automation_integration
async def test_document_sql_prompt_cannot_change_query(runtime) -> None:
    run = await runtime.start(HWPX_WITH_LABEL_DROP_TABLE, VERIFIED_SCOPE)
    assert "DROP TABLE" not in run.audit.sql_fingerprints
    assert run.status in {"INPUT_REQUIRED", "READY_FOR_APPROVAL"}
    assert await source_table_still_exists()
```

- [ ] **Step 2: Run tests and verify integration fixture failure**

Run: `python -m pytest -m dynamic_automation_integration tests/integration/dynamic_automation -q`

Expected: FAIL until MCP, model cache, semantic Views, and read-only role are composed in `compose.test.yml`.

- [ ] **Step 3: Compose the isolated integration runtime**

Add test-only MCP, PostgreSQL, and AI services with a shared document root, pinned model cache, read-only DSN, signing keys, health checks, and no production secrets. Provision a known unknown-layout fixture and tenant-scoped rows.

- [ ] **Step 4: Write the operations and rollback runbook**

Document exact environment variables, startup capability evidence, catalog/model revisions, feedback retention, metrics, and rollout gates. Specify the rollback action as setting `FOWOCO_DYNAMIC_AUTOMATION_ENABLED=false` and restarting only AI workers; existing routes remain available. Define promotion gates: shadow review complete, automatic precision ≥0.99, sensitive precision ≥0.995, no scope-policy bypass, and acceptable p95 latency.

- [ ] **Step 5: Run full verification**

Run: `python -m pytest tests/documents/dynamic_automation tests/api/test_dynamic_document_automation_endpoint.py -q`

Expected: PASS.

Run: `python -m pytest -m dynamic_automation_integration tests/integration/dynamic_automation -q`

Expected: PASS.

Run: `python -m pytest -q`

Expected: PASS for the complete existing and new suite.

Run: `python -m ruff check app tests scripts`

Expected: PASS.

- [ ] **Step 6: Commit Task 7**

```bash
git add compose.test.yml README.md docs/dynamic-document-automation-operations.md tests/integration/dynamic_automation
git commit -m "test(doc-automation): verify secure end-to-end rollout"
```

## Plan 3 Completion Gate

Run:

```bash
python -m pytest -q
python -m ruff check app tests scripts
python -m pytest -m dynamic_automation_integration tests/integration/dynamic_automation -q
git diff --check
```

Required result: all commands exit 0; the feature remains disabled by default; existing endpoints and registered templates are unchanged; unknown documents work through the new path; DB access is read-only and scope-bound; only approved, visually verified MCP artifacts are downloadable.
