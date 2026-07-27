from __future__ import annotations

import hashlib
from pathlib import Path
from typing import BinaryIO

from pydantic import BaseModel, ConfigDict

from .hwpx import DocumentError
from .state import SqliteWorkflowRepository


class ArtifactRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner_id: str
    kind: str
    uri: str
    sha256: str
    size: int
    created_at: str


class LocalArtifactStore:
    """기존 local workspace 파일을 SQLite 지문과 결합합니다."""

    def __init__(
        self,
        root: str | Path,
        repository: SqliteWorkflowRepository,
    ) -> None:
        self.root = Path(root).resolve()
        self.repository = repository

    def put(
        self,
        owner_id: str,
        kind: str,
        source: str | Path,
    ) -> ArtifactRecord:
        path = self._resolve_inside_root(source)
        if not path.is_file():
            raise DocumentError(f"artifact 파일을 찾지 못했습니다: {path}")
        row = self.repository.record_artifact(
            owner_id,
            kind,
            str(path),
            _sha256(path),
            path.stat().st_size,
        )
        return ArtifactRecord.model_validate(row.model_dump())

    def get(self, owner_id: str, kind: str) -> ArtifactRecord:
        row = self.repository.get_artifact(owner_id, kind)
        return ArtifactRecord.model_validate(row.model_dump())

    def verify(self, owner_id: str, kind: str) -> ArtifactRecord:
        artifact = self.get(owner_id, kind)
        path = self._resolve_inside_root(artifact.uri)
        if (
            not path.is_file()
            or path.stat().st_size != artifact.size
            or _sha256(path) != artifact.sha256
        ):
            raise DocumentError(
                f"ARTIFACT_TAMPERED: {owner_id}/{kind} 파일 지문이 DB와 다릅니다."
            )
        return artifact

    def open_verified(self, owner_id: str, kind: str) -> BinaryIO:
        artifact = self.verify(owner_id, kind)
        return Path(artifact.uri).open("rb")

    def _resolve_inside_root(self, source: str | Path) -> Path:
        path = Path(source).expanduser().resolve()
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise DocumentError(f"허용된 작업 폴더 밖의 artifact입니다: {path}") from exc
        return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
