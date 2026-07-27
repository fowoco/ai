from __future__ import annotations

from pathlib import Path

import pytest

from hwp_mcp.artifacts import LocalArtifactStore
from hwp_mcp.hwpx import DocumentError
from hwp_mcp.state import SqliteWorkflowRepository


def _store(tmp_path: Path) -> LocalArtifactStore:
    repository = SqliteWorkflowRepository(tmp_path / ".hwp-mcp" / "state.sqlite3")
    return LocalArtifactStore(tmp_path, repository)


def test_local_artifact_store_rejects_changed_bytes(tmp_path: Path) -> None:
    source = tmp_path / "attempts" / "edit-plan.json"
    source.parent.mkdir()
    source.write_bytes(b"original")
    store = _store(tmp_path)
    artifact = store.put("p1", "edit_plan", source)

    source.write_bytes(b"tampered")

    assert artifact.uri == str(source.resolve())
    with pytest.raises(DocumentError, match="ARTIFACT_TAMPERED"):
        store.open_verified("p1", "edit_plan")


def test_local_artifact_store_survives_repository_restart(tmp_path: Path) -> None:
    source = tmp_path / "attempts" / "report.json"
    source.parent.mkdir()
    source.write_bytes(b"report")
    _store(tmp_path).put("p1", "verification_report", source)

    with _store(tmp_path).open_verified("p1", "verification_report") as opened:
        assert opened.read() == b"report"


def test_local_artifact_store_rejects_path_outside_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-artifact.txt"
    outside.write_bytes(b"outside")

    with pytest.raises(DocumentError, match="작업 폴더"):
        _store(tmp_path).put("p1", "outside", outside)
