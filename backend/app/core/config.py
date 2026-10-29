"""Configuración centralizada leída de variables de entorno / archivo .env.

Nunca se escriben secretos en el código: todo valor sensible viene del entorno.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

# Raíz del monorepo (backend/app/core/config.py -> subir 3 niveles).
REPO_ROOT = Path(__file__).resolve().parents[3]

INSECURE_SECRET_PREFIX = "cambiar"  # noqa: S105  (marcador de clave insegura, no un secreto)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Busca .env en la raíz del repo (ejecución local) o en el cwd (Docker).
        env_file=(REPO_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Aplicación ---
    app_name: str = "CashFlow Manager API"
    app_version: str = "0.4.0"
    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    app_timezone: str = "America/Argentina/Buenos_Aires"

    # --- Seguridad ---
    secret_key: str = Field(default="cambiar-esta-clave-en-env", min_length=16)
    # Orígenes permitidos para CORS, separados por coma (sin comodines en prod).
    cors_origins: str = "http://localhost:8501"
    # Tokens: acceso corto (JWT) + refresh rotatorio (opaco, guardado como hash).
    access_token_minutes: int = Field(default=15, ge=1, le=120)
    refresh_token_days: int = Field(default=7, ge=1, le=60)
    # Bloqueo por intentos fallidos de login (por email).
    login_max_attempts: int = Field(default=5, ge=1)
    login_lockout_minutes: int = Field(default=15, ge=1)

    # --- Base de datos ---
    postgres_host: str = "localhost"
    postgres_port: int = 5433
    postgres_db: str = "cashflow"
    postgres_user: str = "cashflow"
    postgres_password: str = "cashflow_dev"  # noqa: S105  (solo default de desarrollo)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        """URL SQLAlchemy con driver psycopg 3 (contraseña escapada)."""
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        ).render_as_string(hide_password=False)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @model_validator(mode="after")
    def _validar_produccion(self) -> "Settings":
        if self.is_production:
            if self.secret_key.startswith(INSECURE_SECRET_PREFIX):
                raise ValueError("SECRET_KEY por defecto no permitida en producción.")
            if "*" in self.cors_origin_list:
                raise ValueError("CORS con '*' no permitido en producción.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
