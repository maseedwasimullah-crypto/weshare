from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://localhost/weshare"
    secret_key: str = ""
    access_token_minutes: int = 30
    frontend_origin: str = "http://localhost:5173"
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
