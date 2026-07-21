"""Application configuration.

All settings are read from environment variables (loaded from a local `.env`
in development). Secrets never have real defaults — infra/dev-only values do.
"""

from functools import lru_cache

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    # ── App / environment ────────────────────────────────
    app_env: str = "development"
    app_port: int = 5000
    log_level: str = "info"

    # ── Admin (control-panel login) ──────────────────────
    admin_username: str = "admin"
    admin_password: str = "change_me"
    session_secret: str = "dev-insecure-session-secret"
    access_token_expire_minutes: int = 60 * 12

    # ── Security ─────────────────────────────────────────
    # Fernet key (urlsafe base64, 32 bytes) used to encrypt secrets at rest.
    secrets_encryption_key: str = ""

    # ── Database (PostgreSQL) ────────────────────────────
    # Railway sets DATABASE_URL; local dev uses DB_* fields
    database_url_override: str = Field(default="", validation_alias="DATABASE_URL")
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "element_bot"
    db_user: str = "postgres"
    db_password: str = "postgres"

    # ── Redis (Celery broker + cache) — Phase 2 ──────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Element / Matrix (E2EE room) — Phase 1 ───────────
    matrix_homeserver_url: str = ""
    matrix_bot_username: str = ""
    matrix_bot_password: str = ""
    matrix_room_id: str = ""
    # Task-assignment room — bot reads (does not post) developer tasks here.
    matrix_task_room_id: str = ""
    matrix_device_id: str = "PAIRFLOW_BOT"
    matrix_access_token: str = ""
    # Optional: personal Matrix token for reading the pairing room (e.g. team lead
    # who posts Faz + Hamza reports). Decrypts member messages the bot cannot.
    matrix_room_reader_token: str = ""
    matrix_room_reader_device_id: str = ""
    matrix_recovery_key: str = ""
    matrix_e2ee_store_path: str = "./data/matrix_store"
    matrix_pickle_key: str = ""

    # ── LLM (provider-agnostic) — Phase 4 ────────────────
    llm_provider: str = "anthropic"
    llm_api_key: str = ""
    llm_model: str = ""

    # ── Scheduling ───────────────────────────────────────
    timezone: str = "Asia/Karachi"
    daily_send_time: str = "11:00"
    working_days: str = "mon,tue,wed,thu,fri"
    timeliness_cutoff: str = "23:59"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        """SQLAlchemy connection string (sync psycopg2 driver)."""
        raw = (self.database_url_override or "").strip()
        if raw:
            if raw.startswith("postgres://"):
                raw = "postgresql://" + raw[len("postgres://") :]
            if raw.startswith("postgresql://"):
                return "postgresql+psycopg2://" + raw[len("postgresql://") :]
            return raw
        return (
            f"postgresql+psycopg2://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
