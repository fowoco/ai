"""공용 테스트 설정."""

from collections.abc import Iterator

import pytest

from app.api import dependencies
from app.core.config import get_settings


@pytest.fixture(autouse=True)
def isolated_document_snapshots(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    monkeypatch.setenv("FOWOCO_DOCUMENT_SNAPSHOT_DIR", str(tmp_path / "snapshots"))
    get_settings.cache_clear()
    dependencies.get_document_snapshot_repository.cache_clear()
    dependencies.get_document_conversion_service.cache_clear()
    yield
    dependencies.get_document_conversion_service.cache_clear()
    dependencies.get_document_snapshot_repository.cache_clear()
    get_settings.cache_clear()
