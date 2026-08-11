from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_core_config_import_does_not_require_document_automation_extras() -> None:
    project_root = Path(__file__).parents[3]

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.modules['yaml'] = None; import app.core.config",
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_bge_downloader_import_does_not_require_document_automation_extras() -> None:
    project_root = Path(__file__).parents[3]

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.modules['yaml'] = None; import scripts.download_language_models",
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_dynamic_mapping_is_disabled_and_uses_pinned_cache_paths_by_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("FOWOCO_MODEL_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("FOWOCO_DYNAMIC_AUTOMATION_MAPPING_ENABLED", raising=False)
    monkeypatch.delenv("FOWOCO_DYNAMIC_AUTOMATION_EMBEDDING_MODEL_PATH", raising=False)
    monkeypatch.delenv("FOWOCO_DYNAMIC_AUTOMATION_RERANKER_MODEL_PATH", raising=False)

    settings = Settings(_env_file=None)

    assert settings.dynamic_automation_mapping_enabled is False
    assert settings.dynamic_automation_embedding_model_path == (
        tmp_path
        / "qwen3-embedding-0.6b"
        / "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
    )
    assert settings.dynamic_automation_reranker_model_path == (
        tmp_path
        / "qwen3-reranker-0.6b"
        / "e61197ed45024b0ed8a2d74b80b4d909f1255473"
    )


def test_dynamic_mapping_settings_read_explicit_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    model_cache_dir = tmp_path / "model-cache"
    embedding_path = (
        model_cache_dir
        / "custom"
        / "qwen3-embedding-0.6b"
        / "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
    )
    reranker_path = (
        model_cache_dir
        / "custom"
        / "qwen3-reranker-0.6b"
        / "e61197ed45024b0ed8a2d74b80b4d909f1255473"
    )
    monkeypatch.setenv("FOWOCO_MODEL_CACHE_DIR", str(model_cache_dir))
    monkeypatch.setenv("FOWOCO_DYNAMIC_AUTOMATION_MAPPING_ENABLED", "true")
    monkeypatch.setenv(
        "FOWOCO_DYNAMIC_AUTOMATION_EMBEDDING_MODEL_PATH", str(embedding_path)
    )
    monkeypatch.setenv("FOWOCO_DYNAMIC_AUTOMATION_RERANKER_MODEL_PATH", str(reranker_path))
    monkeypatch.setenv("FOWOCO_DYNAMIC_AUTOMATION_MIN_RERANKER_SCORE", "0.93")
    monkeypatch.setenv("FOWOCO_DYNAMIC_AUTOMATION_MIN_MARGIN", "0.12")

    settings = Settings(_env_file=None)

    assert settings.dynamic_automation_mapping_enabled is True
    assert settings.dynamic_automation_embedding_model_path == embedding_path
    assert settings.dynamic_automation_reranker_model_path == reranker_path
    assert settings.dynamic_automation_min_reranker_score == pytest.approx(0.93)
    assert settings.dynamic_automation_min_margin == pytest.approx(0.12)


def test_dynamic_mapping_rejects_model_path_outside_managed_cache(
    tmp_path: Path,
) -> None:
    model_cache_dir = tmp_path / "managed-cache"
    outside_path = (
        tmp_path
        / "outside-cache"
        / "qwen3-embedding-0.6b"
        / "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
    )

    with pytest.raises(ValidationError, match="must be below model_cache_dir"):
        Settings(
            _env_file=None,
            model_cache_dir=model_cache_dir,
            dynamic_automation_embedding_model_path=outside_path,
        )


def test_dynamic_mapping_rejects_unpinned_revision_inside_managed_cache(
    tmp_path: Path,
) -> None:
    model_cache_dir = tmp_path / "managed-cache"
    unpinned_path = (
        model_cache_dir / "qwen3-reranker-0.6b" / "not-the-pinned-revision"
    )

    with pytest.raises(ValidationError, match="must end in the pinned revision directory"):
        Settings(
            _env_file=None,
            model_cache_dir=model_cache_dir,
            dynamic_automation_reranker_model_path=unpinned_path,
        )


@pytest.mark.parametrize(
    ("setting", "value"),
    [
        ("dynamic_automation_min_reranker_score", 1.01),
        ("dynamic_automation_min_margin", -0.01),
    ],
)
def test_dynamic_mapping_thresholds_must_be_probabilities(
    setting: str, value: float
) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{setting: value})


def test_qwen_download_specs_are_opt_in_and_pinned(tmp_path: Path) -> None:
    from app.documents.dynamic_automation.qwen import (
        QWEN3_EMBEDDING_REPO,
        QWEN3_EMBEDDING_REVISION,
        QWEN3_RERANKER_REPO,
        QWEN3_RERANKER_REVISION,
    )
    from scripts.download_language_models import (
        DOCUMENT_AUTOMATION_MODEL_SPECS,
        verify_model_cache,
    )

    assert DOCUMENT_AUTOMATION_MODEL_SPECS == [
        {
            "name": "qwen3-embedding-0.6b",
            "repo": QWEN3_EMBEDDING_REPO,
            "revision": QWEN3_EMBEDDING_REVISION,
        },
        {
            "name": "qwen3-reranker-0.6b",
            "repo": QWEN3_RERANKER_REPO,
            "revision": QWEN3_RERANKER_REVISION,
        },
    ]

    assert "qwen3-embedding-0.6b" not in verify_model_cache(tmp_path)
    missing = verify_model_cache(tmp_path, include_document_automation=True)

    assert "qwen3-embedding-0.6b" in missing
    assert "qwen3-reranker-0.6b" in missing

    (tmp_path / "qwen3-embedding-0.6b" / QWEN3_EMBEDDING_REVISION).mkdir(
        parents=True
    )
    (
        tmp_path
        / "qwen3-embedding-0.6b"
        / QWEN3_EMBEDDING_REVISION
        / "config.json"
    ).write_text("{}")
    (tmp_path / "qwen3-reranker-0.6b" / QWEN3_RERANKER_REVISION).mkdir(
        parents=True
    )
    (
        tmp_path
        / "qwen3-reranker-0.6b"
        / QWEN3_RERANKER_REVISION
        / "config.json"
    ).write_text("{}")

    assert not {
        "qwen3-embedding-0.6b",
        "qwen3-reranker-0.6b",
    }.intersection(verify_model_cache(tmp_path, include_document_automation=True))


def test_document_automation_extra_pins_local_model_runtime_dependencies() -> None:
    project_root = Path(__file__).parents[3]
    configuration = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))

    dependencies = configuration["project"]["optional-dependencies"][
        "document-automation"
    ]

    assert "sentence-transformers>=5,<6" in dependencies
    assert "transformers>=4.51,<5" in dependencies
    assert "torch>=2.2,<3" in dependencies
