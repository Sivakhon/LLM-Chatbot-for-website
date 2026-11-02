"""Application settings, loaded from environment variables / `.env`."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProvider = Literal["gemini", "anthropic", "fake"]
ChromaMode = Literal["persistent", "http", "memory"]

DEFAULT_MODELS: dict[str, str] = {
    "gemini": "gemini-2.5-flash",
    "anthropic": "claude-haiku-5-5",
    "fake": "fake-extractive",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---------------------------------------------------------------
    app_name: str = "ShopBot API"
    environment: Literal["local", "test", "production"] = "local"
    log_level: str = "INFO"
    log_json: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:8501"])
    api_key: SecretStr | None = Field(
        default=None, description="If set, every /api request must send it in the X-API-Key header."
    )

    # --- Vector store ------------------------------------------------------
    chroma_mode: ChromaMode = "persistent"
    chroma_path: Path = Path(".chroma")
    chroma_host: str = "localhost"
    chroma_port: int = 8000
    collection_name: str = "products"

    # --- LLM ---------------------------------------------------------------
    llm_provider: LLMProvider = "gemini"
    llm_model: str | None = None
    llm_temperature: float = Field(default=0.3, ge=0, le=1)
    llm_max_tokens: int = Field(default=1024, gt=0)
    llm_timeout_seconds: float = 30.0
    gemini_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None

    # --- RAG ---------------------------------------------------------------
    retrieval_top_k: int = Field(default=6, ge=1, le=20)
    max_history_messages: int = Field(default=10, ge=1)

    @property
    def resolved_llm_model(self) -> str:
        return self.llm_model or DEFAULT_MODELS[self.llm_provider]


@lru_cache
def get_settings() -> Settings:
    return Settings()
