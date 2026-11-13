from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "development"
    app_base_url: str = "http://localhost:3000"
    timezone: str = "Asia/Kolkata"
    database_url: str = "postgresql+psycopg://discmon:discmon@127.0.0.1:55432/discmon"
    owner_auth_mode: str = "disabled"
    owner_api_token: str = "dev-owner-token"
    runtime_sync_token: str | None = None
    session_secret: str = "dev-session-secret-change-me"
    allowed_origins: str = "http://localhost:3000"
    log_level: str = "INFO"
    allow_private_fetch_hosts: bool = False

    collector_global_concurrency: int = 4
    default_source_interval_hours: int = 24
    fetch_timeout_seconds: int = 20
    fetch_max_retries: int = 4
    raw_retention_days: int = 30
    max_response_bytes: int = 20_000_000

    github_token: str | None = None
    changedetection_base_url: str | None = None
    changedetection_api_key: str | None = None
    changedetection_webhook_secret: str | None = None

    telegram_bot_token: str | None = None
    telegram_allowed_chat_id: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_to: str | None = None

    google_sheets_spreadsheet_id: str | None = None
    google_sheets_tab: str = "Opportunities"
    google_service_account_json_path: str | None = None
    sheets_sync_enabled: bool = False

    llm_provider: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    ai_enabled: bool = False
    ai_daily_call_budget: int = 0
    ai_monthly_spend_budget_usd: float = 0

    internal_api_url: str = "http://localhost:8000"
    internal_api_token: str = "dev-owner-token"

    backup_dir: Path = Field(default=Path("backups"))

    @field_validator("app_env")
    @classmethod
    def validate_env(cls, value: str) -> str:
        normalized = value.lower().strip()
        if normalized not in {"development", "test", "production", "staging"}:
            raise ValueError("APP_ENV must be development, test, staging or production")
        return normalized

    @field_validator("runtime_sync_token")
    @classmethod
    def validate_runtime_sync_token(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if len(value) < 32:
            raise ValueError("RUNTIME_SYNC_TOKEN must contain at least 32 characters")
        return value

    @model_validator(mode="after")
    def keep_runtime_token_separate(self) -> Settings:
        if self.runtime_sync_token and self.runtime_sync_token == self.owner_api_token:
            raise ValueError("RUNTIME_SYNC_TOKEN must differ from OWNER_API_TOKEN")
        return self

    @property
    def is_local(self) -> bool:
        return self.app_env in {"development", "test"}

    @property
    def auth_disabled_allowed(self) -> bool:
        return self.app_env in {"development", "test"} and self.owner_auth_mode == "disabled"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def changedetection_enabled(self) -> bool:
        return bool(self.changedetection_base_url and self.changedetection_api_key)

    @property
    def telegram_enabled(self) -> bool:
        chat = self.telegram_allowed_chat_id or ""
        return bool(
            self.telegram_bot_token
            and re.fullmatch(r"-?[1-9][0-9]{0,18}", chat)
            and -(2**63) < int(chat) < 2**63
        )

    @property
    def smtp_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_from and self.smtp_to)

    @property
    def sheets_configured(self) -> bool:
        return bool(
            self.google_sheets_spreadsheet_id and self.google_service_account_json_path
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
