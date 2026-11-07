from functools import lru_cache
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
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "qwen3:4b"
    llm_api_key: SecretStr = SecretStr("")
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
