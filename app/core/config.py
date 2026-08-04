import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# 환경변수·.env에서 앱 설정을 읽어 오는 모델
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="FOWOCO_",
        extra="ignore",
    )

    app_name: str = "fowoco-ai"
    app_env: str = "development"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000
    hwp_to_hwpx_enabled: bool = False
    java_path: str = "java"
    hwpx_to_hwp_enabled: bool = False
    rhwp_path: str = "rhwp"
    hwpx_pdf_enabled: bool = False
    soffice_path: str = "soffice"
    document_conversion_timeout_seconds: int = 120
    document_upload_max_bytes: int = Field(default=50 * 1024 * 1024, gt=0)
    document_snapshot_dir: Path = Field(
        default_factory=lambda: Path(tempfile.gettempdir())
        / "fowoco-document-snapshots"
    )

    # LLM — 미설정 시 템플릿 기반 stub 동작
    llm_provider: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None

    # Knowledge — true일 때만 fowoco-knowledge 규칙을 Analyses에 연결
    knowledge_enabled: bool = False
    knowledge_root: str | None = None

    # Supervisor — rules(기본) | llm(FOWOCO_LLM_* 필요, 실패 시 rules 폴백)
    supervisor_mode: str = "rules"

    # Server ↔ AI Internal 호출용 Bearer (#8). 비우면 로컬에서 인증 생략
    internal_api_token: str | None = None

    clova_ocr_enabled: bool = False
    clova_ocr_invoke_url: str | None = None
    clova_ocr_secret: str | None = None
    clova_ocr_timeout_seconds: float = Field(default=30.0, gt=0)
    clova_ocr_confidence_threshold: float = Field(default=0.80, ge=0, le=1)
    database_url: str | None = None

    @model_validator(mode="after")
    def validate_enabled_ocr_settings(self) -> Self:
        if not self.clova_ocr_enabled:
            return self
        required = {
            "clova_ocr_invoke_url": self.clova_ocr_invoke_url,
            "clova_ocr_secret": self.clova_ocr_secret,
            "database_url": self.database_url,
            "internal_api_token": self.internal_api_token,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(f"enabled OCR requires settings: {', '.join(missing)}")
        return self


# Settings 싱글톤을 반환
@lru_cache
def get_settings() -> Settings:
    return Settings()
