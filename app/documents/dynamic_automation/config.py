"""Package-owned settings for opt-in dynamic document mapping."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .qwen import (
    QWEN3_EMBEDDING_CACHE_NAME,
    QWEN3_EMBEDDING_REVISION,
    QWEN3_RERANKER_CACHE_NAME,
    QWEN3_RERANKER_REVISION,
)

_EMBEDDING_PATH = Path(QWEN3_EMBEDDING_CACHE_NAME) / QWEN3_EMBEDDING_REVISION
_RERANKER_PATH = Path(QWEN3_RERANKER_CACHE_NAME) / QWEN3_RERANKER_REVISION


class DynamicAutomationSettings(BaseSettings):
    """Read dynamic-only settings without extending the FastAPI settings model."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="FOWOCO_",
        extra="ignore",
    )

    model_cache_dir: Path = Field(
        default_factory=lambda: Path(tempfile.gettempdir()) / "fowoco-model-cache"
    )
    dynamic_automation_mapping_enabled: bool = False
    dynamic_automation_embedding_model_path: Path | None = None
    dynamic_automation_reranker_model_path: Path | None = None
    dynamic_automation_min_reranker_score: float = Field(default=0.90, ge=0, le=1)
    dynamic_automation_min_margin: float = Field(default=0.10, ge=0, le=1)

    @model_validator(mode="after")
    def derive_model_paths(self) -> Self:
        """Resolve and validate pinned model paths inside the managed cache."""
        embedding_path = self.dynamic_automation_embedding_model_path or (
            self.model_cache_dir / _EMBEDDING_PATH
        )
        reranker_path = self.dynamic_automation_reranker_model_path or (
            self.model_cache_dir / _RERANKER_PATH
        )
        self.dynamic_automation_embedding_model_path = _managed_model_path(
            embedding_path,
            model_cache_dir=self.model_cache_dir,
            pinned_suffix=_EMBEDDING_PATH,
            setting_name="dynamic_automation_embedding_model_path",
        )
        self.dynamic_automation_reranker_model_path = _managed_model_path(
            reranker_path,
            model_cache_dir=self.model_cache_dir,
            pinned_suffix=_RERANKER_PATH,
            setting_name="dynamic_automation_reranker_model_path",
        )
        return self


def _managed_model_path(
    path: Path,
    *,
    model_cache_dir: Path,
    pinned_suffix: Path,
    setting_name: str,
) -> Path:
    resolved_cache = model_cache_dir.resolve(strict=False)
    resolved_path = path.resolve(strict=False)
    try:
        relative_path = resolved_path.relative_to(resolved_cache)
    except ValueError as err:
        raise ValueError(f"{setting_name} must be below model_cache_dir") from err
    if relative_path.parts[-2:] != pinned_suffix.parts:
        raise ValueError(
            f"{setting_name} must end in the pinned revision directory "
            f"{pinned_suffix.as_posix()}"
        )
    return resolved_path
