from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://localhost/weshare"
    secret_key: str = ""
    access_token_minutes: int = 30
    frontend_origin: str = "http://localhost:5173"
    frontend_origin_regex: str = ""
    cookie_secure: bool = False
    email_host: str = ""
    email_port: int = 587
    email_user: str = ""
    email_password: str = ""
    email_from: str = ""
    email_use_tls: bool = True
    moderation_blocked_terms_file: str = str(PROJECT_ROOT / "moderation" / "blocked_terms.txt")
    dev_verification_tokens: bool = True

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("database_url")
    @classmethod
    def default_to_psycopg3(cls, value: str) -> str:
        """Use the psycopg 3 driver unless an explicit driver was requested.

        Managed Postgres providers (Render, Neon, Supabase, Railway) hand out
        a plain ``postgresql://`` URL. SQLAlchemy maps that to psycopg2, which
        is not installed, so the connection would fail with "No module named
        psycopg2". Rewrite the scheme unless the URL already names a driver.
        """
        for prefix in ("postgresql://", "postgres://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix) :]
        return value

    @property
    def frontend_origins(self) -> list[str]:
        """The exact browser origins allowed to call the API.

        ``FRONTEND_ORIGIN`` may list several origins separated by commas, so a
        production deployment can allow a stable domain and a preview
        deployment at the same time. Blank entries are dropped so an empty
        value can never widen the policy to "any origin".
        """
        origins = (origin.strip() for origin in self.frontend_origin.split(","))
        return [origin.rstrip("/") for origin in origins if origin]

    @property
    def blocked_terms_path(self) -> Path:
        path = Path(self.moderation_blocked_terms_file)
        return path if path.is_absolute() else (PROJECT_ROOT / path)

    @property
    def smtp_configured(self) -> bool:
        return bool(self.email_host and self.email_from)

    @property
    def exposes_verification_token(self) -> bool:
        return self.dev_verification_tokens and not self.smtp_configured


settings = Settings()
