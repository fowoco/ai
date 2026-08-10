"""T13 — 런타임 설정 RED 테스트.

config.py: FOWOCO_QDRANT_URL, FOWOCO_LLM_TIMEOUT_SECONDS 등 환경변수 및 검증 규칙.
runtime.py: RuntimeStatus 타입과 check_runtime_dependencies() 함수.
"""

import pytest


class TestQdrantUrlConfig:
    """FOWOCO_QDRANT_URL 환경변수 설정 검증."""

    def test_qdrant_url_defaults_to_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FOWOCO_QDRANT_URL", raising=False)
        from app.core.config import get_settings

        get_settings.cache_clear()
        try:
            s = get_settings()
            assert s.qdrant_url is None
        finally:
            get_settings.cache_clear()

    def test_qdrant_url_reads_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FOWOCO_QDRANT_URL", "http://qdrant:6333")
        from app.core.config import get_settings

        get_settings.cache_clear()
        try:
            s = get_settings()
            assert s.qdrant_url == "http://qdrant:6333"
        finally:
            get_settings.cache_clear()

    def test_qdrant_api_key_defaults_to_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FOWOCO_QDRANT_API_KEY", raising=False)
        from app.core.config import get_settings

        get_settings.cache_clear()
        try:
            s = get_settings()
            assert s.qdrant_api_key is None
        finally:
            get_settings.cache_clear()


class TestLlmTimeoutConfig:
    """FOWOCO_LLM_TIMEOUT_SECONDS 환경변수 설정 검증."""

    def test_llm_timeout_has_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FOWOCO_LLM_TIMEOUT_SECONDS", raising=False)
        from app.core.config import get_settings

        get_settings.cache_clear()
        try:
            s = get_settings()
            assert s.llm_timeout_seconds > 0
        finally:
            get_settings.cache_clear()

    def test_llm_timeout_reads_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FOWOCO_LLM_TIMEOUT_SECONDS", "120")
        from app.core.config import get_settings

        get_settings.cache_clear()
        try:
            s = get_settings()
            assert s.llm_timeout_seconds == 120
        finally:
            get_settings.cache_clear()

    def test_llm_timeout_rejects_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FOWOCO_LLM_TIMEOUT_SECONDS", "0")
        from pydantic import ValidationError

        from app.core.config import Settings

        with pytest.raises(ValidationError):
            Settings()

    def test_llm_timeout_rejects_negative(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FOWOCO_LLM_TIMEOUT_SECONDS", "-5")
        from pydantic import ValidationError

        from app.core.config import Settings

        with pytest.raises(ValidationError):
            Settings()


class TestLlmBaseUrlConfig:
    """FOWOCO_LLM_BASE_URL 환경변수 설정 검증."""

    def test_llm_base_url_reads_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FOWOCO_LLM_BASE_URL", "http://ollama:11434/v1")
        from app.core.config import get_settings

        get_settings.cache_clear()
        try:
            s = get_settings()
            assert s.llm_base_url == "http://ollama:11434/v1"
        finally:
            get_settings.cache_clear()


class TestModelCacheConfig:
    """FOWOCO_MODEL_CACHE_DIR 환경변수 설정 검증."""

    def test_model_cache_dir_defaults_to_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("FOWOCO_MODEL_CACHE_DIR", raising=False)
        from app.core.config import get_settings

        get_settings.cache_clear()
        try:
            s = get_settings()
            assert s.model_cache_dir is not None
        finally:
            get_settings.cache_clear()

    def test_model_cache_dir_reads_from_env(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        monkeypatch.setenv("FOWOCO_MODEL_CACHE_DIR", str(tmp_path / "models"))
        from app.core.config import get_settings

        get_settings.cache_clear()
        try:
            s = get_settings()
            assert str(s.model_cache_dir).endswith("models")
        finally:
            get_settings.cache_clear()


class TestRuntimeStatus:
    """runtime.py RuntimeStatus 타입 계약."""

    def test_runtime_status_ok_has_ready_true(self) -> None:
        from app.agents.language.runtime import RuntimeStatus

        status = RuntimeStatus(ready=True, missing=[])
        assert status.ready is True
        assert status.missing == []

    def test_runtime_status_degraded_has_ready_false(self) -> None:
        from app.agents.language.runtime import RuntimeStatus

        status = RuntimeStatus(ready=False, missing=["qdrant_url", "model_cache"])
        assert status.ready is False
        assert "qdrant_url" in status.missing

    def test_check_runtime_dependencies_returns_status(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("FOWOCO_QDRANT_URL", raising=False)
        from app.core.config import get_settings

        get_settings.cache_clear()
        try:
            from app.agents.language.runtime import RuntimeStatus, check_runtime_dependencies

            status = check_runtime_dependencies()
            assert isinstance(status, RuntimeStatus)
        finally:
            get_settings.cache_clear()

    def test_check_runtime_dependencies_ready_when_qdrant_url_set(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        monkeypatch.setenv("FOWOCO_QDRANT_URL", "http://qdrant:6333")
        monkeypatch.setenv("FOWOCO_MODEL_CACHE_DIR", str(tmp_path / "models"))
        from app.core.config import get_settings

        get_settings.cache_clear()
        try:
            from app.agents.language.runtime import check_runtime_dependencies

            status = check_runtime_dependencies()
            # qdrant_url 설정 시 ready=True (모델 파일은 선택적)
            assert status.ready is True
        finally:
            get_settings.cache_clear()

    def test_check_runtime_dependencies_not_ready_when_qdrant_url_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("FOWOCO_QDRANT_URL", raising=False)
        from app.core.config import get_settings

        get_settings.cache_clear()
        try:
            from app.agents.language.runtime import check_runtime_dependencies

            status = check_runtime_dependencies()
            assert status.ready is False
            assert "qdrant_url" in status.missing
        finally:
            get_settings.cache_clear()
