from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator, Literal

from pydantic import BaseModel, ConfigDict

from .hwpx import DocumentError


DocumentStatus = Literal[
    "ANALYZED",
    "READY_FOR_INTERVIEW",
    "WAITING_APPROVAL",
    "APPROVED",
    "PENDING_VISION_REVIEW",
    "VERIFIED_FINAL",
    "NEEDS_HUMAN",
]
AttemptStatus = Literal[
    "RESERVED",
    "PENDING_VISION_REVIEW",
    "FAILED",
    "ABORTED_NO_OUTPUT",
    "VERIFIED_FINAL",
]


class DocumentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    original_sha256: str
    workspace_uri: str
    status: str
    current_plan_id: str | None
    version: int
    created_at: str
    updated_at: str


class PlanRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str
    document_id: str
    plan_sha256: str
    status: str
    created_at: str


class ApprovalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str
    document_id: str
    receipt_sha256: str
    approved_at: str
    revoked_at: str | None


class AttemptRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str
    document_id: str
    sequence: int
    status: str
    modified_sha256: str | None
    report_sha256: str | None
    created_at: str
    completed_at: str | None


class VisionDeliveryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delivery_id: str
    document_id: str
    plan_id: str
    review_id: str
    manifest_sha256: str
    signature: dict[str, Any]
    expires_at: str
    consumed_at: str | None
    created_at: str


class VisionReviewRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_id: str
    document_id: str
    plan_id: str
    delivery_id: str | None
    verdict: str
    review_sha256: str
    created_at: str


class ArtifactRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner_id: str
    kind: str
    uri: str
    sha256: str
    size: int
    created_at: str


class SqliteWorkflowRepository:
    """단일 MCP 서버 workflow의 authoritative SQLite 저장소입니다."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _initialize(self) -> None:
        try:
            with self._connect() as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS documents (
                        document_id TEXT PRIMARY KEY,
                        original_sha256 TEXT NOT NULL,
                        workspace_uri TEXT NOT NULL,
                        status TEXT NOT NULL,
                        current_plan_id TEXT,
                        version INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS plans (
                        plan_id TEXT PRIMARY KEY,
                        document_id TEXT NOT NULL REFERENCES documents(document_id),
                        plan_sha256 TEXT NOT NULL,
                        status TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS approvals (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        plan_id TEXT NOT NULL REFERENCES plans(plan_id),
                        document_id TEXT NOT NULL REFERENCES documents(document_id),
                        receipt_sha256 TEXT NOT NULL,
                        approved_at TEXT NOT NULL,
                        revoked_at TEXT
                    );

                    CREATE TABLE IF NOT EXISTS attempts (
                        plan_id TEXT PRIMARY KEY REFERENCES plans(plan_id),
                        document_id TEXT NOT NULL REFERENCES documents(document_id),
                        sequence INTEGER NOT NULL,
                        status TEXT NOT NULL,
                        modified_sha256 TEXT,
                        report_sha256 TEXT,
                        created_at TEXT NOT NULL,
                        completed_at TEXT,
                        UNIQUE(document_id, sequence)
                    );

                    CREATE TABLE IF NOT EXISTS vision_deliveries (
                        delivery_id TEXT PRIMARY KEY,
                        document_id TEXT NOT NULL REFERENCES documents(document_id),
                        plan_id TEXT NOT NULL REFERENCES plans(plan_id),
                        review_id TEXT NOT NULL,
                        manifest_sha256 TEXT NOT NULL,
                        signature_json TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        consumed_at TEXT,
                        created_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS vision_reviews (
                        review_id TEXT PRIMARY KEY,
                        document_id TEXT NOT NULL REFERENCES documents(document_id),
                        plan_id TEXT NOT NULL REFERENCES plans(plan_id),
                        delivery_id TEXT REFERENCES vision_deliveries(delivery_id),
                        verdict TEXT NOT NULL,
                        review_sha256 TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS artifacts (
                        owner_id TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        uri TEXT NOT NULL,
                        sha256 TEXT NOT NULL,
                        size INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        PRIMARY KEY(owner_id, kind)
                    );
                    """
                )
        except sqlite3.Error as exc:
            raise DocumentError(f"workflow DB를 초기화하지 못했습니다: {exc}") from exc

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def ensure_document(
        self,
        document_id: str,
        original_sha256: str,
        workspace_uri: str,
    ) -> DocumentRecord:
        now = _now()
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM documents WHERE document_id = ?",
                (document_id,),
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO documents (
                        document_id, original_sha256, workspace_uri, status,
                        current_plan_id, version, created_at, updated_at
                    ) VALUES (?, ?, ?, 'ANALYZED', NULL, 1, ?, ?)
                    """,
                    (document_id, original_sha256, workspace_uri, now, now),
                )
            elif (
                row["original_sha256"] != original_sha256
                or row["workspace_uri"] != workspace_uri
            ):
                raise DocumentError("workflow DB의 문서 지문 또는 workspace가 다릅니다.")
        return self.get_document(document_id)

    def get_document(self, document_id: str) -> DocumentRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM documents WHERE document_id = ?",
                (document_id,),
            ).fetchone()
        if row is None:
            raise DocumentError("workflow DB에서 문서를 찾지 못했습니다.")
        return DocumentRecord.model_validate(dict(row))

    def set_analysis_status(
        self,
        document_id: str,
        status: Literal["ANALYZED", "READY_FOR_INTERVIEW"],
    ) -> DocumentRecord:
        with self._transaction() as connection:
            changed = connection.execute(
                """
                UPDATE documents
                SET status = ?, version = version + 1, updated_at = ?
                WHERE document_id = ?
                """,
                (status, _now(), document_id),
            ).rowcount
            if changed != 1:
                raise DocumentError("workflow DB에서 문서를 찾지 못했습니다.")
        return self.get_document(document_id)

    def create_plan(
        self,
        document_id: str,
        plan_id: str,
        plan_sha256: str,
    ) -> PlanRecord:
        now = _now()
        with self._transaction() as connection:
            document = _require_document(connection, document_id)
            if document["status"] != "READY_FOR_INTERVIEW":
                raise DocumentError("현재 DB 상태에서 새 Edit Plan을 만들 수 없습니다.")
            if document["current_plan_id"]:
                connection.execute(
                    "UPDATE plans SET status = 'SUPERSEDED' WHERE plan_id = ?",
                    (document["current_plan_id"],),
                )
            connection.execute(
                """
                UPDATE approvals
                SET revoked_at = ?
                WHERE document_id = ? AND revoked_at IS NULL
                """,
                (now, document_id),
            )
            try:
                connection.execute(
                    """
                    INSERT INTO plans (plan_id, document_id, plan_sha256, status, created_at)
                    VALUES (?, ?, ?, 'WAITING_APPROVAL', ?)
                    """,
                    (plan_id, document_id, plan_sha256, now),
                )
            except sqlite3.IntegrityError as exc:
                raise DocumentError("같은 Edit Plan이 이미 workflow DB에 있습니다.") from exc
            connection.execute(
                """
                UPDATE documents
                SET current_plan_id = ?, status = 'WAITING_APPROVAL',
                    version = version + 1, updated_at = ?
                WHERE document_id = ?
                """,
                (plan_id, now, document_id),
            )
        return self.get_plan(plan_id)

    def get_plan(self, plan_id: str) -> PlanRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM plans WHERE plan_id = ?",
                (plan_id,),
            ).fetchone()
        if row is None:
            raise DocumentError("workflow DB에서 Edit Plan을 찾지 못했습니다.")
        return PlanRecord.model_validate(dict(row))

    def approve_plan(
        self,
        document_id: str,
        plan_id: str,
        *,
        receipt_sha256: str,
        approved_at: str,
    ) -> ApprovalRecord:
        with self._transaction() as connection:
            document = _require_current_plan(connection, document_id, plan_id)
            plan = _require_plan(connection, plan_id)
            if document["status"] != "WAITING_APPROVAL" or plan["status"] != "WAITING_APPROVAL":
                raise DocumentError("현재 승인 대기 중인 Edit Plan이 아닙니다.")
            connection.execute(
                """
                INSERT INTO approvals (
                    plan_id, document_id, receipt_sha256, approved_at, revoked_at
                ) VALUES (?, ?, ?, ?, NULL)
                """,
                (plan_id, document_id, receipt_sha256, approved_at),
            )
            connection.execute(
                "UPDATE plans SET status = 'APPROVED' WHERE plan_id = ?",
                (plan_id,),
            )
            connection.execute(
                """
                UPDATE documents
                SET status = 'APPROVED', version = version + 1, updated_at = ?
                WHERE document_id = ?
                """,
                (_now(), document_id),
            )
        return self.require_active_approval(document_id, plan_id)

    def require_active_approval(
        self,
        document_id: str,
        plan_id: str,
    ) -> ApprovalRecord:
        with self._connect() as connection:
            document = _require_current_plan(connection, document_id, plan_id)
            row = connection.execute(
                """
                SELECT plan_id, document_id, receipt_sha256, approved_at, revoked_at
                FROM approvals
                WHERE document_id = ? AND plan_id = ? AND revoked_at IS NULL
                ORDER BY id DESC
                LIMIT 1
                """,
                (document_id, plan_id),
            ).fetchone()
        if row is None or document["status"] not in {
            "APPROVED",
            "PENDING_VISION_REVIEW",
            "VERIFIED_FINAL",
        }:
            raise DocumentError("workflow DB에 현재 plan의 유효한 승인이 없습니다.")
        return ApprovalRecord.model_validate(dict(row))

    def reserve_attempt(self, document_id: str, plan_id: str) -> int:
        now = _now()
        limit_reached = False
        sequence = 0
        with self._transaction() as connection:
            document = _require_current_plan(connection, document_id, plan_id)
            if document["status"] != "APPROVED":
                raise DocumentError("승인된 현재 plan만 attempt를 예약할 수 있습니다.")
            approval = connection.execute(
                """
                SELECT 1 FROM approvals
                WHERE document_id = ? AND plan_id = ? AND revoked_at IS NULL
                """,
                (document_id, plan_id),
            ).fetchone()
            if approval is None:
                raise DocumentError("workflow DB에 현재 plan의 유효한 승인이 없습니다.")
            if connection.execute(
                "SELECT 1 FROM attempts WHERE plan_id = ?",
                (plan_id,),
            ).fetchone():
                raise DocumentError("이 plan의 attempt가 이미 예약되었습니다.")
            consumed = connection.execute(
                """
                SELECT COUNT(*) FROM attempts
                WHERE document_id = ? AND status != 'ABORTED_NO_OUTPUT'
                """,
                (document_id,),
            ).fetchone()[0]
            if consumed >= 2:
                connection.execute(
                    """
                    UPDATE documents
                    SET status = 'NEEDS_HUMAN', version = version + 1, updated_at = ?
                    WHERE document_id = ?
                    """,
                    (now, document_id),
                )
                limit_reached = True
            else:
                sequence = connection.execute(
                    "SELECT COALESCE(MAX(sequence), 0) + 1 FROM attempts WHERE document_id = ?",
                    (document_id,),
                ).fetchone()[0]
                try:
                    connection.execute(
                        """
                        INSERT INTO attempts (
                            plan_id, document_id, sequence, status,
                            modified_sha256, report_sha256, created_at, completed_at
                        ) VALUES (?, ?, ?, 'RESERVED', NULL, NULL, ?, NULL)
                        """,
                        (plan_id, document_id, sequence, now),
                    )
                except sqlite3.IntegrityError as exc:
                    raise DocumentError("이 plan의 attempt가 이미 예약되었습니다.") from exc
        if limit_reached:
            raise DocumentError("XML/SVG 조정 2회를 소진해 사람 검토가 필요합니다.")
        return int(sequence)

    def complete_attempt(
        self,
        plan_id: str,
        *,
        status: AttemptStatus,
        modified_sha256: str | None = None,
        report_sha256: str | None = None,
    ) -> AttemptRecord:
        if status in {"FAILED", "PENDING_VISION_REVIEW"} and (
            not modified_sha256 or not report_sha256
        ):
            raise DocumentError("출력이 생성된 attempt에는 수정본과 보고서 hash가 필요합니다.")
        now = _now()
        with self._transaction() as connection:
            attempt = connection.execute(
                "SELECT * FROM attempts WHERE plan_id = ?",
                (plan_id,),
            ).fetchone()
            if attempt is None or attempt["status"] != "RESERVED":
                raise DocumentError("예약된 attempt를 찾지 못했습니다.")
            connection.execute(
                """
                UPDATE attempts
                SET status = ?, modified_sha256 = ?, report_sha256 = ?, completed_at = ?
                WHERE plan_id = ?
                """,
                (status, modified_sha256, report_sha256, now, plan_id),
            )
            document_status = {
                "ABORTED_NO_OUTPUT": "APPROVED",
                "FAILED": "NEEDS_HUMAN",
                "PENDING_VISION_REVIEW": "PENDING_VISION_REVIEW",
                "VERIFIED_FINAL": "VERIFIED_FINAL",
                "RESERVED": "APPROVED",
            }[status]
            connection.execute(
                """
                UPDATE documents
                SET status = ?, version = version + 1, updated_at = ?
                WHERE document_id = ?
                """,
                (document_status, now, attempt["document_id"]),
            )
        return self.get_attempt(plan_id)

    def get_attempt(self, plan_id: str) -> AttemptRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM attempts WHERE plan_id = ?",
                (plan_id,),
            ).fetchone()
        if row is None:
            raise DocumentError("workflow DB에서 attempt를 찾지 못했습니다.")
        return AttemptRecord.model_validate(dict(row))

    def list_attempts(self, document_id: str) -> list[AttemptRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM attempts
                WHERE document_id = ?
                ORDER BY sequence
                """,
                (document_id,),
            ).fetchall()
        return [AttemptRecord.model_validate(dict(row)) for row in rows]

    def list_reserved_attempts(self) -> list[AttemptRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM attempts
                WHERE status = 'RESERVED'
                ORDER BY document_id, sequence
                """
            ).fetchall()
        return [AttemptRecord.model_validate(dict(row)) for row in rows]

    def record_artifact(
        self,
        owner_id: str,
        kind: str,
        uri: str,
        sha256: str,
        size: int,
    ) -> ArtifactRow:
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO artifacts (owner_id, kind, uri, sha256, size, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(owner_id, kind) DO UPDATE SET
                    uri = excluded.uri,
                    sha256 = excluded.sha256,
                    size = excluded.size,
                    created_at = excluded.created_at
                """,
                (owner_id, kind, uri, sha256, size, _now()),
            )
        return self.get_artifact(owner_id, kind)

    def get_artifact(self, owner_id: str, kind: str) -> ArtifactRow:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM artifacts WHERE owner_id = ? AND kind = ?",
                (owner_id, kind),
            ).fetchone()
        if row is None:
            raise DocumentError("workflow DB에서 artifact를 찾지 못했습니다.")
        return ArtifactRow.model_validate(dict(row))

    def record_vision_delivery(
        self,
        *,
        delivery_id: str,
        document_id: str,
        plan_id: str,
        review_id: str,
        manifest_sha256: str,
        signature: dict[str, Any],
        expires_at: str,
    ) -> VisionDeliveryRecord:
        now = _now()
        with self._transaction() as connection:
            document = _require_current_plan(connection, document_id, plan_id)
            if document["status"] != "PENDING_VISION_REVIEW":
                raise DocumentError("현재 Vision 검토 대기 plan이 아닙니다.")
            connection.execute(
                """
                UPDATE vision_deliveries
                SET consumed_at = ?
                WHERE document_id = ? AND plan_id = ? AND consumed_at IS NULL
                """,
                (now, document_id, plan_id),
            )
            connection.execute(
                """
                INSERT INTO vision_deliveries (
                    delivery_id, document_id, plan_id, review_id,
                    manifest_sha256, signature_json, expires_at, consumed_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    delivery_id,
                    document_id,
                    plan_id,
                    review_id,
                    manifest_sha256,
                    json.dumps(signature, sort_keys=True, separators=(",", ":")),
                    expires_at,
                    now,
                ),
            )
        return self.require_vision_delivery(delivery_id, document_id, plan_id, review_id)

    def require_vision_delivery(
        self,
        delivery_id: str,
        document_id: str,
        plan_id: str,
        review_id: str,
    ) -> VisionDeliveryRecord:
        with self._connect() as connection:
            _require_current_plan(connection, document_id, plan_id)
            row = connection.execute(
                """
                SELECT * FROM vision_deliveries
                WHERE delivery_id = ? AND document_id = ? AND plan_id = ?
                    AND review_id = ? AND consumed_at IS NULL
                """,
                (delivery_id, document_id, plan_id, review_id),
            ).fetchone()
        if row is None:
            raise DocumentError("현재 Vision delivery를 찾지 못했습니다.")
        value = dict(row)
        value["signature"] = json.loads(value.pop("signature_json"))
        return VisionDeliveryRecord.model_validate(value)

    def record_vision_review(
        self,
        *,
        review_id: str,
        document_id: str,
        plan_id: str,
        delivery_id: str | None,
        verdict: str,
        review_sha256: str,
    ) -> VisionReviewRecord:
        now = _now()
        with self._transaction() as connection:
            document = _require_current_plan(connection, document_id, plan_id)
            if document["status"] != "PENDING_VISION_REVIEW":
                raise DocumentError("현재 Vision 검토 대기 plan이 아닙니다.")
            if delivery_id is not None:
                delivery = connection.execute(
                    """
                    SELECT * FROM vision_deliveries
                    WHERE delivery_id = ? AND document_id = ? AND plan_id = ?
                        AND review_id = ? AND consumed_at IS NULL
                    """,
                    (delivery_id, document_id, plan_id, review_id),
                ).fetchone()
                if delivery is None:
                    raise DocumentError("현재 Vision delivery를 찾지 못했습니다.")
                connection.execute(
                    "UPDATE vision_deliveries SET consumed_at = ? WHERE delivery_id = ?",
                    (now, delivery_id),
                )
            connection.execute(
                """
                INSERT INTO vision_reviews (
                    review_id, document_id, plan_id, delivery_id,
                    verdict, review_sha256, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(review_id) DO UPDATE SET
                    delivery_id = excluded.delivery_id,
                    verdict = excluded.verdict,
                    review_sha256 = excluded.review_sha256,
                    created_at = excluded.created_at
                """,
                (
                    review_id,
                    document_id,
                    plan_id,
                    delivery_id,
                    verdict,
                    review_sha256,
                    now,
                ),
            )
            status = "PENDING_VISION_REVIEW" if verdict == "PASS" else "NEEDS_HUMAN"
            connection.execute(
                """
                UPDATE documents
                SET status = ?, version = version + 1, updated_at = ?
                WHERE document_id = ?
                """,
                (status, now, document_id),
            )
        return self.get_vision_review(review_id)

    def get_vision_review(self, review_id: str) -> VisionReviewRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM vision_reviews WHERE review_id = ?",
                (review_id,),
            ).fetchone()
        if row is None:
            raise DocumentError("workflow DB에서 Vision review를 찾지 못했습니다.")
        return VisionReviewRecord.model_validate(dict(row))

    def get_plan_vision_review(self, plan_id: str) -> VisionReviewRecord:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM vision_reviews
                WHERE plan_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (plan_id,),
            ).fetchone()
        if row is None:
            raise DocumentError("workflow DB에서 현재 plan의 Vision review를 찾지 못했습니다.")
        return VisionReviewRecord.model_validate(dict(row))

    def finalize(self, document_id: str, plan_id: str) -> DocumentRecord:
        now = _now()
        with self._transaction() as connection:
            document = _require_current_plan(connection, document_id, plan_id)
            if document["status"] != "PENDING_VISION_REVIEW":
                raise DocumentError("현재 Vision PASS plan을 최종화할 수 없습니다.")
            review = connection.execute(
                """
                SELECT 1 FROM vision_reviews
                WHERE document_id = ? AND plan_id = ? AND verdict = 'PASS'
                """,
                (document_id, plan_id),
            ).fetchone()
            if review is None:
                raise DocumentError("workflow DB에 현재 plan의 Vision PASS가 없습니다.")
            connection.execute(
                """
                UPDATE documents
                SET status = 'VERIFIED_FINAL', version = version + 1, updated_at = ?
                WHERE document_id = ?
                """,
                (now, document_id),
            )
            connection.execute(
                """
                UPDATE attempts
                SET status = 'VERIFIED_FINAL', completed_at = ?
                WHERE plan_id = ?
                """,
                (now, plan_id),
            )
        return self.get_document(document_id)


def _require_document(
    connection: sqlite3.Connection,
    document_id: str,
) -> sqlite3.Row:
    row = connection.execute(
        "SELECT * FROM documents WHERE document_id = ?",
        (document_id,),
    ).fetchone()
    if row is None:
        raise DocumentError("workflow DB에서 문서를 찾지 못했습니다.")
    return row


def _require_plan(connection: sqlite3.Connection, plan_id: str) -> sqlite3.Row:
    row = connection.execute(
        "SELECT * FROM plans WHERE plan_id = ?",
        (plan_id,),
    ).fetchone()
    if row is None:
        raise DocumentError("workflow DB에서 Edit Plan을 찾지 못했습니다.")
    return row


def _require_current_plan(
    connection: sqlite3.Connection,
    document_id: str,
    plan_id: str,
) -> sqlite3.Row:
    document = _require_document(connection, document_id)
    if document["current_plan_id"] != plan_id:
        raise DocumentError("현재 승인/작업 plan과 workflow DB의 plan이 다릅니다.")
    return document


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
