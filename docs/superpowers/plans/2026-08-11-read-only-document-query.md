# Read-Only Document Query Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert trusted canonical field IDs and server-owned scope identifiers into policy-validated, parameterized PostgreSQL `SELECT` statements against document automation Views and return typed canonical values.

**Architecture:** The query subsystem is independent of MCP and model code. A strict `QueryScopeResolver` detects missing or conflicting IDs, a deterministic planner derives Query IR from the catalog, a deny-by-default policy creates a validated plan, a PostgreSQL compiler emits bounded parameterized SQL, and a read-only executor verifies its DB capabilities before activation.

**Tech Stack:** Python 3.11, Pydantic 2, psycopg 3 with async pool, PostgreSQL Views/RLS, pytest

**Design Reference:** `docs/superpowers/specs/2026-08-11-dynamic-document-automation-design.md`

**Prerequisite:** Complete `2026-08-11-dynamic-field-mapping-foundation.md`; this plan consumes its catalog and mapping contracts.

## Global Constraints

- Execute only parameterized `SELECT` statements generated from catalog metadata.
- Grant the automation role `SELECT` only on approved semantic Views, never on source tables.
- Never accept SQL, View names, column names, JOINs, predicates, or literal scope values from documents or models.
- Require `tenant_id` plus every scope key declared by a canonical field.
- Detect conflicting IDs instead of applying source precedence.
- Enforce read-only transactions, statement timeout, lock timeout, row limit, and response-size limit.
- Log Query IR hashes and SQL fingerprints, never parameter values or returned DB values.
- This plan consumes the catalog contracts from Plan 1 and does not import MCP code.

---

## File Structure

- `app/documents/dynamic_automation/query_models.py`: scope, IR, validated plan, compiled query, and result contracts.
- `app/documents/dynamic_automation/query_scope.py`: multi-source ID resolution and conflict detection.
- `app/documents/dynamic_automation/query_planner.py`: matched canonical IDs to grouped Query IR.
- `app/documents/dynamic_automation/query_policy.py`: allowlist, sensitivity, field-count, and join-graph checks.
- `app/documents/dynamic_automation/query_compiler.py`: PostgreSQL quoting and parameterized SQL compilation.
- `app/documents/dynamic_automation/query_executor.py`: capability check and bounded async execution.
- `app/documents/dynamic_automation/query_results.py`: cardinality and typed canonical results.
- `app/documents/dynamic_automation/audit.py`: metadata-only audit events.
- `docs/contracts/dynamic-document-semantic-views.sql`: Server-owned View and role contract.
- `tests/documents/dynamic_automation/`: unit tests with fake connections.
- `tests/integration/dynamic_automation/`: opt-in PostgreSQL security tests.

### Task 1: Resolve an immutable, conflict-free QueryScope

**Files:**
- Create: `app/documents/dynamic_automation/query_models.py`
- Create: `app/documents/dynamic_automation/query_scope.py`
- Test: `tests/documents/dynamic_automation/test_query_scope.py`

**Interfaces:**
- Consumes: top-level request IDs plus worker, company, task, and previous-state mappings.
- Produces: `QueryScope` and `resolve_query_scope(inputs: QueryScopeInputs) -> QueryScope`.
- Produces errors: `QueryScopeMissingError` and `QueryScopeConflictError`.

- [ ] **Step 1: Write failing fallback and conflict tests**

```python
def test_scope_uses_task_and_worker_relationship_fallbacks() -> None:
    scope = resolve_query_scope(QueryScopeInputs(
        request_id="req-1", tenant_id="tenant-1",
        worker={"worker_id": "w1", "company_id": "c1"},
        company=None,
        task={"task_id": "t1", "worker_id": "w1", "company_id": "c1"},
    ))
    assert scope.worker_id == "w1"
    assert scope.company_id == "c1"
    assert scope.task_id == "t1"


def test_scope_rejects_conflicting_company_ids() -> None:
    with pytest.raises(QueryScopeConflictError, match="company_id"):
        resolve_query_scope(inputs(top_level_company_id="c1", worker_company_id="c2"))
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/documents/dynamic_automation/test_query_scope.py -q`

Expected: FAIL because QueryScope contracts do not exist.

- [ ] **Step 3: Implement source-preserving scope resolution**

```python
class QueryScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request_id: str
    tenant_id: str
    task_id: str | None = None
    worker_id: str | None = None
    company_id: str | None = None
    evidence: dict[str, tuple[str, ...]]


class QueryScopeInputs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request_id: str
    tenant_id: str
    top_level_worker_id: str | None = None
    top_level_company_id: str | None = None
    top_level_task_id: str | None = None
    worker: Mapping[str, Any] | None = None
    company: Mapping[str, Any] | None = None
    task: Mapping[str, Any] | None = None
    previous_state: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class ScopeCandidate:
    source: str
    value: str | None


def _resolve_one(name: str, candidates: Sequence[ScopeCandidate]) -> str | None:
    values = {item.value for item in candidates if item.value}
    if len(values) > 1:
        raise QueryScopeConflictError(name, candidates)
    return next(iter(values), None)
```

Collect `task.worker_id`, `task.company_id`, and `worker.company_id`; do not treat generated `task-<random>` IDs as trusted DB scope. Require non-empty `request_id` and `tenant_id` for every scope.

- [ ] **Step 4: Run tests and commit**

Run: `python -m pytest tests/documents/dynamic_automation/test_query_scope.py -q`

Expected: PASS.

```bash
git add app/documents/dynamic_automation/query_models.py app/documents/dynamic_automation/query_scope.py tests/documents/dynamic_automation/test_query_scope.py
git commit -m "feat(doc-automation): resolve trusted query scope"
```

### Task 2: Plan strict Query IR from matched canonical fields

**Files:**
- Create: `app/documents/dynamic_automation/query_planner.py`
- Test: `tests/documents/dynamic_automation/test_query_planner.py`

**Interfaces:**
- Consumes: `CanonicalMappingPlan`, `CanonicalCatalog`, and `QueryScope`.
- Produces: `QueryIR(fields, scope_refs)` and `plan_queries(mapping_plan, catalog, scope) -> tuple[QueryIR, ...]`.

- [ ] **Step 1: Write failing grouping and rejection tests**

```python
def test_planner_groups_fields_with_same_view_and_scope() -> None:
    plans = plan_queries(mapping_plan("worker.legal_name", "worker.nationality"), catalog, scope)
    assert len(plans) == 1
    assert plans[0].fields == ("worker.legal_name", "worker.nationality")
    assert plans[0].scope_refs == {
        "tenant_id": "context.tenant_id", "worker_id": "context.worker_id"
    }


def test_planner_ignores_ambiguous_and_rejects_missing_scope() -> None:
    with pytest.raises(QueryScopeMissingError, match="company_id"):
        plan_queries(mixed_plan_with_matched_company_field(), catalog, scope_without_company)
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/documents/dynamic_automation/test_query_planner.py -q`

Expected: FAIL because `plan_queries` is missing.

- [ ] **Step 3: Implement deterministic grouping**

Only consume `MATCHED` mappings. Resolve each canonical field through the catalog, require its declared scope keys, sort field IDs, and group by `(source.view, scope_keys)`. Set `QueryIR.model_config.extra="forbid"`; the model must contain no generic SQL or expression field.

```python
class QueryIR(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    fields: tuple[str, ...] = Field(min_length=1, max_length=50)
    scope_refs: dict[ScopeKey, ContextRef]
```

- [ ] **Step 4: Run tests and commit**

Run: `python -m pytest tests/documents/dynamic_automation/test_query_planner.py -q`

Expected: PASS.

```bash
git add app/documents/dynamic_automation/query_planner.py app/documents/dynamic_automation/query_models.py tests/documents/dynamic_automation/test_query_planner.py
git commit -m "feat(doc-automation): plan restricted query IR"
```

### Task 3: Validate query policy and compile bounded PostgreSQL SQL

**Files:**
- Create: `app/documents/dynamic_automation/query_policy.py`
- Create: `app/documents/dynamic_automation/query_compiler.py`
- Test: `tests/documents/dynamic_automation/test_query_policy.py`
- Test: `tests/documents/dynamic_automation/test_query_compiler.py`

**Interfaces:**
- Consumes: `QueryIR`, catalog, scope, and `QueryPolicy`.
- Produces: `validate_query(ir, catalog, scope, policy) -> ValidatedQueryPlan`.
- Produces: `PostgresQueryCompiler.compile(plan, scope) -> CompiledQuery(sql, params, fingerprint)`.

- [ ] **Step 1: Write failing deny-by-default and SQL snapshot tests**

```python
def test_policy_rejects_unknown_view_even_when_ir_is_structurally_valid() -> None:
    tampered = catalog_with_source("worker.legal_name", view="pg_catalog.pg_user")
    with pytest.raises(QueryPolicyRejected, match="view"):
        validate_query(ir("worker.legal_name"), tampered, scope, DEFAULT_POLICY)


def test_compiler_emits_only_parameterized_select() -> None:
    compiled = PostgresQueryCompiler().compile(validated_worker_plan, scope)
    assert compiled.sql.startswith('SELECT "w"."legal_name"')
    assert "%(worker_id)s" in compiled.sql
    assert "w1" not in compiled.sql
    assert compiled.sql.endswith("LIMIT 2")
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/documents/dynamic_automation/test_query_policy.py tests/documents/dynamic_automation/test_query_compiler.py -q`

Expected: FAIL because policy and compiler modules are missing.

- [ ] **Step 3: Implement immutable policy and validated plan**

Allow exactly `document_worker_view`, `document_company_view`, `document_task_view`, and `document_identity_view`. Allow only the catalog columns seeded in Plan 1. The first version rejects all joins and queries each semantic View independently; each View must expose `tenant_id` and its declared scope keys. Cap one IR at 50 fields and one run at four queries.

```python
@dataclass(frozen=True)
class ValidatedQueryPlan:
    view: str
    fields: tuple[CanonicalFieldDefinition, ...]
    scope_keys: tuple[ScopeKey, ...]
    catalog_version: str


@dataclass(frozen=True)
class CompiledQuery:
    sql: str
    params: Mapping[str, str]
    fingerprint: str
    canonical_field_ids: tuple[str, ...]
```

- [ ] **Step 4: Implement safe identifier quoting and parameter compilation**

Validate every identifier against `^[a-z][a-z0-9_]*$`, quote it with double quotes, and derive aliases from canonical IDs by replacing `.` with `__`. Parameters must come only from `QueryScope`. Compile a single-View `SELECT`, equality scope predicates, and `LIMIT 2`; reject joins, subqueries, and semicolons as defense-in-depth assertions.

- [ ] **Step 5: Run tests and commit**

Run: `python -m pytest tests/documents/dynamic_automation/test_query_policy.py tests/documents/dynamic_automation/test_query_compiler.py -q`

Expected: PASS, including system catalog, unsafe identifier, excessive field, and literal injection tests.

```bash
git add app/documents/dynamic_automation/query_policy.py app/documents/dynamic_automation/query_compiler.py app/documents/dynamic_automation/query_models.py tests/documents/dynamic_automation
git commit -m "feat(doc-automation): validate and compile read-only queries"
```

### Task 4: Execute queries with a verified read-only PostgreSQL capability

**Files:**
- Create: `app/documents/dynamic_automation/query_executor.py`
- Modify: `app/core/config.py:79-97`
- Modify: `.env.example`
- Modify: `pyproject.toml:47-51`
- Test: `tests/documents/dynamic_automation/test_query_executor.py`
- Test: `tests/documents/dynamic_automation/test_query_executor_config.py`

**Interfaces:**
- Consumes: `CompiledQuery`.
- Produces: `PostgresReadOnlyExecutor.start()`, `close()`, and `execute_many(queries) -> tuple[RawQueryResult, ...]`.
- Produces settings prefixed `dynamic_automation_db_` for DSN, role expectation, timeouts, row bytes, and pool size.

- [ ] **Step 1: Write failing capability and execution tests using fake async connections**

```python
@pytest.mark.asyncio
async def test_start_fails_when_transaction_is_not_read_only() -> None:
    executor = executor_with_capabilities(transaction_read_only="off")
    with pytest.raises(QueryCapabilityError, match="read-only"):
        await executor.start()


@pytest.mark.asyncio
async def test_execute_sets_local_limits_and_never_logs_params(caplog) -> None:
    executor, connection = recording_executor()
    await executor.execute_many((COMPILED_WORKER_QUERY,))
    assert "SET LOCAL statement_timeout" in connection.commands
    assert "SET LOCAL lock_timeout" in connection.commands
    assert "worker-1" not in caplog.text
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/documents/dynamic_automation/test_query_executor.py tests/documents/dynamic_automation/test_query_executor_config.py -q`

Expected: FAIL because the executor and settings are absent.

- [ ] **Step 3: Add PostgreSQL dependency and disabled-by-default settings**

Add `psycopg[pool]>=3.2,<4` to `document-automation`. Add `FOWOCO_DYNAMIC_AUTOMATION_DB_ENABLED=false`, DSN, expected role, `statement_timeout_ms=2000`, `lock_timeout_ms=500`, `max_result_bytes=262144`, pool size `1..5`, and forbidden relations `worker,company,task,worker_document`. Validation must require all DB settings only when enabled.

- [ ] **Step 4: Implement startup capability checks and bounded execution**

At startup verify `current_user`, `transaction_read_only`, and access to all four Views. For every configured source-table name, require `has_table_privilege(current_user, source_table, 'SELECT')` to return false. For each run, start a read-only transaction, set local timeouts and `app.tenant_id`, execute with parameters, fetch at most two rows, enforce serialized byte size, then roll back/close the transaction even after success.

- [ ] **Step 5: Run tests and commit**

Run: `python -m pytest tests/documents/dynamic_automation/test_query_executor.py tests/documents/dynamic_automation/test_query_executor_config.py -q`

Expected: PASS.

```bash
git add pyproject.toml .env.example app/core/config.py app/documents/dynamic_automation/query_executor.py tests/documents/dynamic_automation
git commit -m "feat(doc-automation): add verified read-only postgres executor"
```

### Task 5: Normalize query results and emit privacy-safe audit events

**Files:**
- Create: `app/documents/dynamic_automation/query_results.py`
- Create: `app/documents/dynamic_automation/audit.py`
- Test: `tests/documents/dynamic_automation/test_query_results.py`
- Test: `tests/documents/dynamic_automation/test_query_audit.py`

**Interfaces:**
- Consumes: raw rows, validated plan, and catalog formatters.
- Produces: `CanonicalValueResult` with statuses `FOUND`, `NOT_FOUND`, `NULL_VALUE`, `MULTIPLE_ROWS`, `SCOPE_MISSING`, `POLICY_REJECTED`, `QUERY_FAILED`.
- Produces: `QueryAuditEvent` with hashes, timing, row count, and policy result only.

- [ ] **Step 1: Write failing cardinality, format, and privacy tests**

```python
def test_two_rows_become_multiple_rows_without_values() -> None:
    result = resolve_query_result(validated_plan, [ROW_ONE, ROW_TWO], catalog)
    assert all(item.status is CanonicalValueStatus.MULTIPLE_ROWS for item in result.values)
    assert all(item.value is None for item in result.values)


def test_audit_event_excludes_sql_params_and_returned_values() -> None:
    event = build_query_audit(COMPILED_QUERY, RAW_RESULT)
    payload = event.model_dump_json()
    assert "worker-1" not in payload
    assert "NGUYEN" not in payload
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/documents/dynamic_automation/test_query_results.py tests/documents/dynamic_automation/test_query_audit.py -q`

Expected: FAIL because result and audit modules are absent.

- [ ] **Step 3: Implement exact status and formatter behavior**

Return no values for zero or multiple rows. For one row, distinguish SQL NULL from a valid scalar and apply catalog formatters for ISO date, phone, business number, person name, amount, and boolean. A formatter failure becomes `QUERY_FAILED` for that canonical field and must not expose the raw value in the error.

- [ ] **Step 4: Implement metadata-only audit records**

Include request/task identifiers, catalog version, Query IR SHA-256, SQL fingerprint, Views, duration, row count, field IDs, and result statuses. Configure model fields with `extra="forbid"`; do not include SQL text, params, or values.

- [ ] **Step 5: Run tests and commit**

Run: `python -m pytest tests/documents/dynamic_automation/test_query_results.py tests/documents/dynamic_automation/test_query_audit.py -q`

Expected: PASS.

```bash
git add app/documents/dynamic_automation/query_results.py app/documents/dynamic_automation/audit.py tests/documents/dynamic_automation
git commit -m "feat(doc-automation): normalize and audit query results"
```

### Task 6: Publish the semantic View contract and verify real PostgreSQL restrictions

**Files:**
- Create: `docs/contracts/dynamic-document-semantic-views.sql`
- Create: `tests/integration/dynamic_automation/test_postgres_read_only.py`
- Modify: `compose.test.yml`
- Modify: `tests/conftest.py:11-26`

**Interfaces:**
- Consumes: PostgreSQL executor from Task 4.
- Produces: an executable reference contract for Server-owned Views and role grants.

- [ ] **Step 1: Write the opt-in integration test before the SQL contract**

```python
@pytest.mark.postgres_integration
async def test_automation_role_can_read_views_but_not_source_tables(pg_executor) -> None:
    assert await pg_executor.fetch_worker_name("tenant-1", "worker-1") == "Demo Worker"
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        await raw_query("SELECT * FROM worker")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        await raw_query("UPDATE document_worker_view SET legal_name = 'x'")
```

- [ ] **Step 2: Run the integration test and verify fixture failure**

Run: `python -m pytest -m postgres_integration tests/integration/dynamic_automation/test_postgres_read_only.py -q`

Expected: FAIL because the test database and View contract are not provisioned.

- [ ] **Step 3: Add exact PostgreSQL View and role reference SQL**

Define `document_worker_view`, `document_company_view`, `document_task_view`, and `document_identity_view` with `tenant_id` and their scope keys. Revoke `PUBLIC` access, create/grant the expected read-only role, grant `SELECT` on Views only, revoke schema create/temp capabilities, enable RLS-compatible tenant filtering using `current_setting('app.tenant_id', true)`, and include seed data only in the test compose initialization block.

- [ ] **Step 4: Run integration and unit suites**

Run: `docker compose -f compose.test.yml up -d postgres-test`

Run: `python -m pytest -m postgres_integration tests/integration/dynamic_automation/test_postgres_read_only.py -q`

Expected: PASS with View reads allowed and table reads/writes denied.

Run: `python -m pytest tests/documents/dynamic_automation -q`

Expected: PASS.

- [ ] **Step 5: Commit Task 6**

```bash
git add docs/contracts/dynamic-document-semantic-views.sql compose.test.yml tests/conftest.py tests/integration/dynamic_automation/test_postgres_read_only.py
git commit -m "test(doc-automation): verify postgres read-only boundary"
```

## Plan 2 Completion Gate

Run:

```bash
python -m pytest tests/documents/dynamic_automation -q
python -m pytest -m postgres_integration tests/integration/dynamic_automation/test_postgres_read_only.py -q
python -m ruff check app/documents/dynamic_automation tests/documents/dynamic_automation tests/integration/dynamic_automation
git diff --check
```

Required result: all commands exit 0; a trusted `CanonicalMappingPlan` resolves through bounded Query IR to canonical results; the PostgreSQL role cannot read source tables or perform writes.
