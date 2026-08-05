from datetime import datetime
from typing import Any
from uuid import UUID

from app.ocr.models import (
    DatabaseSchemaMismatch,
    DocumentType,
    NormalizedOcrResult,
    OcrPersistenceError,
    OcrRequestSuperseded,
    OcrScope,
)

SCOPE_COLUMNS = (
    "worker_document_id",
    "worker_id",
    "company_id",
    "document_type",
)
OCR_METADATA_COLUMNS = (
    "ocr_status",
    "ocr_request_id",
    "ocr_document_side",
    "ocr_error_code",
    "ocr_processed_at",
)
STRUCTURED_OCR_COLUMNS = (
    "passport_number",
    "surname",
    "given_names",
    "date_of_birth",
    "sex",
    "passport_issue_date",
    "passport_expiry_date",
    "alien_registration_number",
    "visa_type",
    "stay_expiration_date",
    "residence_address_1",
)
REQUIRED_SCHEMA_COLUMNS = frozenset(
    (*SCOPE_COLUMNS, *OCR_METADATA_COLUMNS, *STRUCTURED_OCR_COLUMNS)
)

_SET_TENANT_SQL = "SELECT pg_catalog.set_config('app.company_id', %s, true)"
_SCOPE_PREDICATE = """WHERE worker_document_id = %s
  AND worker_id = %s
  AND company_id = %s"""


class PsycopgWorkerDocumentOcrRepository:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def verify_schema(self) -> None:
        try:
            async with self._pool.connection() as connection:
                async with connection.transaction():
                    async with connection.cursor() as cursor:
                        await cursor.execute(
                            """SELECT column_name
                            FROM information_schema.columns
                            WHERE table_schema = %s
                              AND table_name = %s""",
                            ("public", "worker_document"),
                        )
                        rows = await cursor.fetchall()
        except Exception as exc:
            raise OcrPersistenceError("database operation failed") from exc

        existing_columns = {row[0] for row in rows}
        missing_columns = tuple(sorted(REQUIRED_SCHEMA_COLUMNS - existing_columns))
        if missing_columns:
            raise DatabaseSchemaMismatch(missing_columns)

    async def verify_scope(
        self,
        scope: OcrScope,
        document_type: DocumentType,
    ) -> bool:
        try:
            async with self._pool.connection() as connection:
                async with connection.transaction():
                    async with connection.cursor() as cursor:
                        await self._set_tenant(cursor, scope)
                        await cursor.execute(
                            f"""SELECT 1
                            FROM public.worker_document
                            {_SCOPE_PREDICATE}
                              AND document_type = %s""",
                            (*_scope_params(scope), document_type.value),
                        )
                        return await cursor.fetchone() is not None
        except Exception as exc:
            raise OcrPersistenceError("database operation failed") from exc

    async def mark_processing(self, scope: OcrScope, request_id: UUID) -> None:
        try:
            async with self._pool.connection() as connection:
                async with connection.transaction():
                    async with connection.cursor() as cursor:
                        await self._set_tenant(cursor, scope)
                        await cursor.execute(
                            f"""UPDATE public.worker_document
                            SET ocr_status = %s,
                                ocr_request_id = %s,
                                ocr_error_code = %s,
                                ocr_processed_at = %s
                            {_SCOPE_PREDICATE}""",
                            ("PROCESSING", request_id, None, None, *_scope_params(scope)),
                        )
        except Exception as exc:
            raise OcrPersistenceError("database operation failed") from exc

    async def save_result(
        self,
        scope: OcrScope,
        result: NormalizedOcrResult,
        processed_at: datetime,
        request_id: UUID,
    ) -> None:
        assignments = (
            "ocr_status = %s",
            "ocr_document_side = %s",
            "ocr_error_code = %s",
            "ocr_processed_at = %s",
            *(f"{column} = COALESCE(%s, {column})" for column in STRUCTURED_OCR_COLUMNS),
        )
        values = (
            result.status.value,
            result.document_side.value if result.document_side else None,
            result.error_code,
            processed_at,
            *(result.fields.get(column) for column in STRUCTURED_OCR_COLUMNS),
            *_scope_params(scope),
            request_id,
        )
        try:
            async with self._pool.connection() as connection:
                async with connection.transaction():
                    async with connection.cursor() as cursor:
                        await self._set_tenant(cursor, scope)
                        await cursor.execute(
                            f"""UPDATE public.worker_document
                            SET {", ".join(assignments)}
                            {_SCOPE_PREDICATE}
                              AND ocr_request_id = %s""",
                            values,
                        )
                        if cursor.rowcount != 1:
                            raise OcrRequestSuperseded("OCR request was superseded")
        except OcrRequestSuperseded:
            raise
        except Exception as exc:
            raise OcrPersistenceError("database operation failed") from exc

    async def mark_failed(
        self,
        scope: OcrScope,
        request_id: UUID,
        error_code: str,
        processed_at: datetime,
    ) -> None:
        try:
            async with self._pool.connection() as connection:
                async with connection.transaction():
                    async with connection.cursor() as cursor:
                        await self._set_tenant(cursor, scope)
                        await cursor.execute(
                            f"""UPDATE public.worker_document
                            SET ocr_status = %s,
                                ocr_request_id = %s,
                                ocr_error_code = %s,
                                ocr_processed_at = %s
                            {_SCOPE_PREDICATE}
                              AND ocr_request_id = %s""",
                            (
                                "FAILED",
                                request_id,
                                error_code,
                                processed_at,
                                *_scope_params(scope),
                                request_id,
                            ),
                        )
        except Exception as exc:
            raise OcrPersistenceError("database operation failed") from exc

    @staticmethod
    async def _set_tenant(cursor: Any, scope: OcrScope) -> None:
        await cursor.execute(_SET_TENANT_SQL, (str(scope.company_id),))


def _scope_params(scope: OcrScope) -> tuple[UUID, UUID, UUID]:
    return scope.worker_document_id, scope.worker_id, scope.company_id
