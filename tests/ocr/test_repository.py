import json
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import pytest

from app.ocr.models import (
    DatabaseSchemaMismatch,
    DocumentType,
    NormalizedOcrResult,
    OcrPersistenceError,
    OcrRequestSuperseded,
    OcrScope,
    OcrStatus,
)
from app.ocr.repository import (
    REQUIRED_SCHEMA_COLUMNS,
    PsycopgWorkerDocumentOcrRepository,
)

DOCUMENT_ID = UUID("11111111-1111-4111-8111-111111111111")
WORKER_ID = UUID("22222222-2222-4222-8222-222222222222")
COMPANY_ID = UUID("33333333-3333-4333-8333-333333333333")
REQUEST_ID = UUID("44444444-4444-4444-8444-444444444444")
PROCESSED_AT = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)


class FakeCursor:
    def __init__(self, pool: "FakePool") -> None:
        self.pool = pool
        self.current_sql = ""
        self.rowcount = -1

    async def __aenter__(self) -> "FakeCursor":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        self.current_sql = " ".join(sql.split())
        self.pool.executions.append((self.current_sql, params))
        if self.current_sql.startswith("UPDATE"):
            self.rowcount = self.pool.update_rowcount
        if self.pool.fail_on_execution == len(self.pool.executions):
            raise RuntimeError("synthetic database failure")

    async def fetchall(self) -> list[tuple[str]]:
        return [(column,) for column in sorted(self.pool.existing_columns)]

    async def fetchone(self) -> tuple[int] | None:
        return (1,) if self.pool.scope_exists else None


class FakeTransaction:
    async def __aenter__(self) -> "FakeTransaction":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


class FakeConnection:
    def __init__(self, pool: "FakePool") -> None:
        self.pool = pool

    def transaction(self) -> FakeTransaction:
        return FakeTransaction()

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.pool)


class FakeConnectionContext:
    def __init__(self, pool: "FakePool") -> None:
        self.connection = FakeConnection(pool)

    async def __aenter__(self) -> FakeConnection:
        return self.connection

    async def __aexit__(self, *args: object) -> None:
        return None


class FakePool:
    def __init__(
        self,
        *,
        existing_columns: set[str] | None = None,
        scope_exists: bool = True,
        fail_on_execution: int | None = None,
        update_rowcount: int = 1,
    ) -> None:
        self.existing_columns = existing_columns or set(REQUIRED_SCHEMA_COLUMNS)
        self.scope_exists = scope_exists
        self.fail_on_execution = fail_on_execution
        self.update_rowcount = update_rowcount
        self.executions: list[tuple[str, tuple[Any, ...]]] = []

    def connection(self) -> FakeConnectionContext:
        return FakeConnectionContext(self)


def scope() -> OcrScope:
    return OcrScope(DOCUMENT_ID, WORKER_ID, COMPANY_ID)


def normalized_result() -> NormalizedOcrResult:
    return NormalizedOcrResult(
        status=OcrStatus.SUCCEEDED,
        matched_template_id=43019,
        document_side=None,
        fields={
            "passport_number": "M00000000",
            "date_of_birth": date(2000, 1, 2),
        },
        field_confidences={"passport_number": 0.99, "date_of_birth": 0.98},
        error_code=None,
        review_reasons=(),
    )


@pytest.mark.asyncio
async def test_verify_schema_reports_only_missing_column_names() -> None:
    existing = set(REQUIRED_SCHEMA_COLUMNS) - {"ocr_status", "stay_expiration_date"}
    repository = PsycopgWorkerDocumentOcrRepository(FakePool(existing_columns=existing))

    with pytest.raises(DatabaseSchemaMismatch) as exc:
        await repository.verify_schema()

    assert exc.value.missing_columns == ("ocr_status", "stay_expiration_date")
    assert str(exc.value) == "missing OCR database columns: ocr_status, stay_expiration_date"


@pytest.mark.asyncio
async def test_verify_schema_accepts_complete_worker_document_contract() -> None:
    pool = FakePool()

    await PsycopgWorkerDocumentOcrRepository(pool).verify_schema()

    sql, params = pool.executions[0]
    assert "information_schema.columns" in sql
    assert params == ("public", "worker_document")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation",
    ["verify_scope", "mark_processing", "save_result", "mark_failed"],
)
async def test_every_scoped_operation_sets_tenant_before_worker_document_access(
    operation: str,
) -> None:
    pool = FakePool()
    repository = PsycopgWorkerDocumentOcrRepository(pool)

    if operation == "verify_scope":
        assert await repository.verify_scope(scope(), DocumentType.PASSPORT_COPY)
    elif operation == "mark_processing":
        await repository.mark_processing(scope(), REQUEST_ID)
    elif operation == "save_result":
        await repository.save_result(scope(), normalized_result(), PROCESSED_AT, REQUEST_ID)
    else:
        await repository.mark_failed(scope(), REQUEST_ID, "CLOVA_ERROR", PROCESSED_AT)

    tenant_sql, tenant_params = pool.executions[0]
    document_sql, document_params = pool.executions[1]
    assert tenant_sql == "SELECT pg_catalog.set_config('app.company_id', %s, true)"
    assert tenant_params == (str(COMPANY_ID),)
    assert "worker_document" in document_sql
    assert "WHERE worker_document_id = %s" in document_sql
    assert "AND worker_id = %s" in document_sql
    assert "AND company_id = %s" in document_sql
    assert DOCUMENT_ID in document_params
    assert WORKER_ID in document_params
    assert COMPANY_ID in document_params
    if operation in {"save_result", "mark_failed"}:
        assert "AND ocr_request_id = %s" in document_sql
        assert document_params[-1] == REQUEST_ID


@pytest.mark.asyncio
async def test_verify_scope_includes_document_type_and_reports_missing_row() -> None:
    pool = FakePool(scope_exists=False)
    repository = PsycopgWorkerDocumentOcrRepository(pool)

    found = await repository.verify_scope(scope(), DocumentType.ARC)

    sql, params = pool.executions[1]
    assert found is False
    assert "AND document_type = %s" in sql
    assert params == (DOCUMENT_ID, WORKER_ID, COMPANY_ID, "ARC")


@pytest.mark.asyncio
async def test_save_result_uses_fixed_columns_and_native_values() -> None:
    pool = FakePool()
    repository = PsycopgWorkerDocumentOcrRepository(pool)

    await repository.save_result(scope(), normalized_result(), PROCESSED_AT, REQUEST_ID)

    sql, params = pool.executions[1]
    assignments = sql.split(" SET ", 1)[1].split(" WHERE ", 1)[0]
    assigned_columns = {part.strip().split(" = ", 1)[0] for part in assignments.split(",")}
    assert "passport_number" in assigned_columns
    assert "passport_expiry_date" in assigned_columns
    assert "submission_status" not in assigned_columns
    assert "expiry_date" not in assigned_columns
    assert "updated_at" not in assigned_columns
    assert "version" not in assigned_columns
    assert (
        "ocr_field_confidences = "
        "COALESCE(ocr_field_confidences, '{}'::jsonb) || %s::jsonb"
    ) in assignments
    for column in assigned_columns & {
        "passport_number",
        "surname",
        "given_names",
        "nationality",
        "date_of_birth",
        "sex",
        "passport_issue_date",
        "passport_expiry_date",
        "alien_registration_number",
        "full_name",
        "visa_type",
        "alien_registration_issue_date",
        "stay_permit_date",
        "stay_expiration_date",
        "residence_report_date_1",
        "residence_confirmation_1",
        "residence_address_1",
        "residence_report_date_2",
        "residence_confirmation_2",
        "residence_address_2",
    }:
        assert f"{column} = COALESCE(%s, {column})" in assignments
    assert date(2000, 1, 2) in params
    confidence_json = next(
        item for item in params if isinstance(item, str) and item.startswith("{")
    )
    assert json.loads(confidence_json) == {
        "date_of_birth": 0.98,
        "passport_number": 0.99,
    }


@pytest.mark.asyncio
async def test_save_result_rejects_a_response_superseded_by_a_newer_request() -> None:
    repository = PsycopgWorkerDocumentOcrRepository(FakePool(update_rowcount=0))

    with pytest.raises(OcrRequestSuperseded, match="superseded"):
        await repository.save_result(scope(), normalized_result(), PROCESSED_AT, REQUEST_ID)


@pytest.mark.asyncio
async def test_database_failures_are_translated_to_safe_persistence_error() -> None:
    repository = PsycopgWorkerDocumentOcrRepository(FakePool(fail_on_execution=1))

    with pytest.raises(OcrPersistenceError, match="database operation failed") as exc:
        await repository.mark_processing(scope(), REQUEST_ID)

    assert "synthetic database failure" not in str(exc.value)
