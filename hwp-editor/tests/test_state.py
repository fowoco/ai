from __future__ import annotations

from pathlib import Path

import pytest

from hwp_mcp.artifacts import LocalArtifactStore
from hwp_mcp.hwpx import DocumentError
from hwp_mcp.server import _recover_reserved_attempts
from hwp_mcp.state import SqliteWorkflowRepository


def _repository(tmp_path: Path) -> SqliteWorkflowRepository:
    return SqliteWorkflowRepository(tmp_path / "state.sqlite3")


def _ready_document(
    repository: SqliteWorkflowRepository,
    *,
    document_id: str = "doc",
) -> None:
    repository.ensure_document(
        document_id,
        original_sha256="a" * 64,
        workspace_uri="workspace",
    )
    repository.set_analysis_status(document_id, "READY_FOR_INTERVIEW")


def test_sqlite_state_survives_new_repository_instance(tmp_path: Path) -> None:
    first = _repository(tmp_path)
    _ready_document(first)
    first.create_plan("doc", "p1", "b" * 64)

    restarted = _repository(tmp_path)
    document = restarted.get_document("doc")

    assert document.current_plan_id == "p1"
    assert document.status == "WAITING_APPROVAL"


def test_new_plan_revokes_previous_approval(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _ready_document(repository)
    repository.create_plan("doc", "p1", "b" * 64)
    repository.approve_plan(
        "doc",
        "p1",
        receipt_sha256="c" * 64,
        approved_at="2026-07-27T00:00:00+00:00",
    )
    repository.set_analysis_status("doc", "READY_FOR_INTERVIEW")

    repository.create_plan("doc", "p2", "d" * 64)

    with pytest.raises(DocumentError, match="승인"):
        repository.require_active_approval("doc", "p1")


def test_projection_cannot_reset_two_attempt_limit(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _ready_document(repository)
    for sequence, plan_id in enumerate(("p1", "p2"), start=1):
        repository.create_plan("doc", plan_id, str(sequence) * 64)
        repository.approve_plan(
            "doc",
            plan_id,
            receipt_sha256=str(sequence + 2) * 64,
            approved_at=f"2026-07-27T00:00:0{sequence}+00:00",
        )
        assert repository.reserve_attempt("doc", plan_id) == sequence
        repository.complete_attempt(
            plan_id,
            status="FAILED",
            modified_sha256=str(sequence + 4) * 64,
            report_sha256=str(sequence + 6) * 64,
        )
        if sequence == 1:
            repository.set_analysis_status("doc", "READY_FOR_INTERVIEW")

    repository.set_analysis_status("doc", "READY_FOR_INTERVIEW")
    repository.create_plan("doc", "p3", "9" * 64)
    repository.approve_plan(
        "doc",
        "p3",
        receipt_sha256="0" * 64,
        approved_at="2026-07-27T00:00:03+00:00",
    )

    with pytest.raises(DocumentError, match="2회"):
        repository.reserve_attempt("doc", "p3")
    assert repository.get_document("doc").status == "NEEDS_HUMAN"


def test_failure_before_output_releases_attempt_slot(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _ready_document(repository)
    repository.create_plan("doc", "p1", "1" * 64)
    repository.approve_plan(
        "doc",
        "p1",
        receipt_sha256="2" * 64,
        approved_at="2026-07-27T00:00:00+00:00",
    )
    repository.reserve_attempt("doc", "p1")
    repository.complete_attempt("p1", status="ABORTED_NO_OUTPUT")
    repository.set_analysis_status("doc", "READY_FOR_INTERVIEW")

    repository.create_plan("doc", "p2", "3" * 64)
    repository.approve_plan(
        "doc",
        "p2",
        receipt_sha256="4" * 64,
        approved_at="2026-07-27T00:00:01+00:00",
    )

    assert repository.reserve_attempt("doc", "p2") == 2


def test_duplicate_attempt_reservation_is_rejected(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _ready_document(repository)
    repository.create_plan("doc", "p1", "1" * 64)
    repository.approve_plan(
        "doc",
        "p1",
        receipt_sha256="2" * 64,
        approved_at="2026-07-27T00:00:00+00:00",
    )
    repository.reserve_attempt("doc", "p1")

    with pytest.raises(DocumentError, match="이미"):
        _repository(tmp_path).reserve_attempt("doc", "p1")


def test_vision_delivery_is_one_time_use(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _ready_document(repository)
    repository.create_plan("doc", "p1", "1" * 64)
    repository.approve_plan(
        "doc",
        "p1",
        receipt_sha256="2" * 64,
        approved_at="2026-07-27T00:00:00+00:00",
    )
    repository.reserve_attempt("doc", "p1")
    repository.complete_attempt(
        "p1",
        status="PENDING_VISION_REVIEW",
        modified_sha256="3" * 64,
        report_sha256="4" * 64,
    )
    repository.record_vision_delivery(
        delivery_id="d" * 64,
        document_id="doc",
        plan_id="p1",
        review_id="r" * 64,
        manifest_sha256="5" * 64,
        signature={
            "key_id": "v1",
            "algorithm": "HMAC-SHA256",
            "value": "signature",
        },
        expires_at="2026-07-27T00:10:00+00:00",
    )
    repository.record_vision_review(
        review_id="r" * 64,
        document_id="doc",
        plan_id="p1",
        delivery_id="d" * 64,
        verdict="PASS",
        review_sha256="6" * 64,
    )

    with pytest.raises(DocumentError, match="delivery"):
        repository.require_vision_delivery(
            "d" * 64,
            "doc",
            "p1",
            "r" * 64,
        )


@pytest.mark.parametrize(
    ("has_output", "expected_status"),
    [(False, "ABORTED_NO_OUTPUT"), (True, "FAILED")],
)
def test_restart_recovers_reserved_attempt(
    tmp_path: Path,
    has_output: bool,
    expected_status: str,
) -> None:
    workspace = tmp_path / "document-workspace"
    workspace.mkdir()
    repository = _repository(tmp_path)
    repository.ensure_document(
        "doc",
        original_sha256="a" * 64,
        workspace_uri=str(workspace),
    )
    repository.set_analysis_status("doc", "READY_FOR_INTERVIEW")
    repository.create_plan("doc", "p1", "1" * 64)
    repository.approve_plan(
        "doc",
        "p1",
        receipt_sha256="2" * 64,
        approved_at="2026-07-27T00:00:00+00:00",
    )
    repository.reserve_attempt("doc", "p1")
    attempt_dir = workspace / "attempts" / "p1"
    attempt_dir.mkdir(parents=True)
    if has_output:
        (attempt_dir / "modified.hwpx").write_bytes(b"partial-output")

    _recover_reserved_attempts(
        repository,
        LocalArtifactStore(tmp_path, repository),
    )

    assert repository.get_attempt("p1").status == expected_status
