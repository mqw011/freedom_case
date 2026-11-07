from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    app_env: str = "development"
    database_url: str = "sqlite:///./data/cqa.db"
    cors_origins: str = "http://localhost:5173"
    dataset_api_url: str = Field(default="", repr=False)
    dataset_api_timeout: float = Field(default=30, gt=0, le=300)
    import_max_bytes: int = Field(default=20 * 1024 * 1024, gt=0)
    llm_provider: Literal["ollama", "openai_compatible"] = "ollama"
    llm_base_url: str = Field(default="http://localhost:11434/v1", repr=False)
    llm_model: str = "qwen3:4b"
    llm_api_key: SecretStr = SecretStr("")
    llm_temperature: float = Field(default=0, ge=0, le=2)
    llm_timeout: float = Field(default=180, gt=0, le=3600)
    llm_max_retries: int = Field(default=2, ge=0, le=5)
    llm_retry_delay: float = Field(default=1, ge=0, le=60)
    llm_max_concurrency: int = Field(default=1, ge=1, le=16)
    llm_context_length: int = Field(default=16384, ge=2048, le=262144)
    llm_max_output_tokens: int = Field(default=3072, ge=256, le=32768)
    llm_response_mode: Literal["auto", "json_schema", "json_object"] = "auto"
    llm_think: bool = False
    llm_seed: int = 42
    llm_keep_alive: str = "10m"
    llm_allow_remote: bool = False
    ai_job_enabled: bool = True
    ai_auto_start_worker: bool = False
    ai_max_repairs: int = Field(default=2, ge=0, le=5)
    ai_job_max_attempts: int = Field(default=2, ge=1, le=10)
    ai_lease_seconds: int = Field(default=90, ge=15, le=3600)
    ai_poll_seconds: float = Field(default=1, gt=0, le=60)
    ai_retry_delay: int = Field(default=10, ge=0, le=3600)
    ai_chunk_overlap: int = Field(default=2, ge=0, le=20)
    ai_max_chunks: int = Field(default=64, ge=1, le=1000)
    ai_explanation_language: Literal["conversation", "RU", "KZ", "EN"] = "conversation"
    ai_semantic_review: bool = True
    log_level: str = "INFO"

    @field_validator("dataset_api_url")
    @classmethod
    def configured_http_url(cls, value: str) -> str:
        if not value:
            return value
        parsed = urlsplit(value.replace("{group_id}", "DEV"))
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("DATASET_API_URL must be an HTTP(S) URL")
        if parsed.username or parsed.password or parsed.fragment:
            raise ValueError("DATASET_API_URL must not contain credentials or fragments")
        if "{" in value.replace("{group_id}", "") or "}" in value.replace("{group_id}", ""):
            raise ValueError("Only {group_id} URL placeholders are supported")
        # The placeholder may occur only in a path/query, never in the target host.
        if "{group_id}" in urlsplit(value).netloc:
            raise ValueError("The dataset host must be fixed")
        return value

    @property
    def origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
