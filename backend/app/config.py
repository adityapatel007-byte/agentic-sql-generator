"""Application settings loaded from environment / .env."""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM providers
    openai_api_key: str = Field(default="")
    openrouter_api_key: str = Field(default="")
    nvidia_api_key: str = Field(default="")
    nvidia_base_url: str = Field(default="https://integrate.api.nvidia.com/v1")

    # Agent config — v1 baseline is Nemotron 3 Nano (OSS MoE, ~3B active params,
    # explicitly built for tool calling). Same family as v4 LoRA fine-tune target.
    # Override via DEFAULT_MODEL env var if the exact id on build.nvidia.com differs.
    default_model: str = Field(default="nvidia/nemotron-3-nano-30b-a3b")
    max_agent_iterations: int = Field(default=5, ge=1, le=10)

    # Execution safety
    query_timeout_seconds: int = Field(default=15, ge=1, le=120)
    max_result_rows: int = Field(default=200, ge=1, le=10_000)

    # RAG
    embedding_model: str = Field(default="BAAI/bge-small-en-v1.5")
    chroma_persist_dir: str = Field(default="./data/chroma")

    # Server
    log_level: str = Field(default="INFO")
    allowed_origins: str = Field(default="http://localhost:5173")

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


settings = Settings()
