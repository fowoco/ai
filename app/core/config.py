import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DYNAMIC_AUTOMATION_EMBEDDING_PATH = (
    Path("qwen3-embedding-0.6b")
    / "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
)
_DYNAMIC_AUTOMATION_RERANKER_PATH = (
    Path("qwen3-reranker-0.6b")
    / "e61197ed45024b0ed8a2d74b80b4d909f1255473"
)


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

    # LLM — 미설정 시 Language Assistant composition unavailable
    llm_provider: str | None = None
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None

    # Knowledge — true일 때만 fowoco-knowledge 규칙을 Analyses에 연결
    knowledge_enabled: bool = False
    knowledge_root: str | None = None

    # Intent HF — true면 BERT(+선택 A.X) 분류, false면 EXPIRY_RENEWAL 고정
    intent_model_enabled: bool = False
    intent_bert_model_dir: str = "fowoco/klue-roberta-base-intent-classifier"
    intent_ax_base_model: str = "skt/A.X-4.0-Light"
    intent_ax_adapter_path: str = "fowoco/ax-intent-qlora"
    intent_enable_ax: bool = False
    intent_device: str = "cpu"
    intent_margin_threshold: float = 0.76
    intent_max_trained_labels: int = 3
    intent_label_prob_threshold: float = 0.55
    intent_ax_max_new_tokens: int = 96
    # private HF 모델용. 미설정 시 환경변수 HF_TOKEN도 허용(코드에서 조회)
    hf_token: str | None = None

    # Supervisor — rules(기본) | llm(FOWOCO_LLM_* 필요, 실패 시 rules 폴백)
    supervisor_mode: str = "rules"

    # Server ↔ AI Internal 호출용 Bearer (#8). 비우면 로컬에서 인증 생략
    internal_api_token: str | None = None

    # Qdrant — 미설정 시 language assistant degraded 동작
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None

    # LLM 요청 타임아웃 (초). 양수 필수.
    llm_timeout_seconds: int = Field(default=60, gt=0)

    # 모델 가중치 캐시 디렉터리 (사전 다운로드 스크립트와 공유)
    model_cache_dir: Path = Field(
        default_factory=lambda: Path(tempfile.gettempdir()) / "fowoco-model-cache"
    )

    # Dynamic document field mapping — model-backed matching is explicit opt-in.
    dynamic_automation_mapping_enabled: bool = False
    dynamic_automation_embedding_model_path: Path | None = None
    dynamic_automation_reranker_model_path: Path | None = None
    dynamic_automation_min_reranker_score: float = Field(default=0.90, ge=0, le=1)
    dynamic_automation_min_margin: float = Field(default=0.10, ge=0, le=1)

    clova_ocr_enabled: bool = False
    clova_ocr_invoke_url: str | None = None
    clova_ocr_secret: str | None = None
    clova_ocr_timeout_seconds: float = Field(default=30.0, gt=0)
    clova_ocr_confidence_threshold: float = Field(default=0.80, ge=0, le=1)

    @model_validator(mode="after")
    def derive_dynamic_automation_model_paths(self) -> Self:
        embedding_path = self.dynamic_automation_embedding_model_path or (
            self.model_cache_dir / _DYNAMIC_AUTOMATION_EMBEDDING_PATH
        )
        reranker_path = self.dynamic_automation_reranker_model_path or (
            self.model_cache_dir / _DYNAMIC_AUTOMATION_RERANKER_PATH
        )
        self.dynamic_automation_embedding_model_path = _managed_model_path(
            embedding_path,
            model_cache_dir=self.model_cache_dir,
            pinned_suffix=_DYNAMIC_AUTOMATION_EMBEDDING_PATH,
            setting_name="dynamic_automation_embedding_model_path",
        )
        self.dynamic_automation_reranker_model_path = _managed_model_path(
            reranker_path,
            model_cache_dir=self.model_cache_dir,
            pinned_suffix=_DYNAMIC_AUTOMATION_RERANKER_PATH,
            setting_name="dynamic_automation_reranker_model_path",
        )
        return self

    @model_validator(mode="after")
    def validate_enabled_ocr_settings(self) -> Self:
        if not self.clova_ocr_enabled:
            return self
        required = {
            "clova_ocr_invoke_url": self.clova_ocr_invoke_url,
            "clova_ocr_secret": self.clova_ocr_secret,
            "internal_api_token": self.internal_api_token,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(f"enabled OCR requires settings: {', '.join(missing)}")
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


# Settings 싱글톤을 반환
@lru_cache
def get_settings() -> Settings:
    return Settings()
