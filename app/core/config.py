from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


# 환경변수·.env에서 앱 설정을 읽어 오는 모델
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "fowoco-ai"
    app_env: str = "development"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000

    # LLM — 미설정 시 템플릿 기반 stub 동작
    llm_provider: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None


# Settings 싱글톤을 반환한다
@lru_cache
def get_settings() -> Settings:
    return Settings()
