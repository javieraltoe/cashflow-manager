"""Fixtures compartidas.

Base de datos de TEST: se usa una base separada (por defecto "<POSTGRES_DB>_test", o la
indicada en TEST_POSTGRES_DB) para no tocar los datos de desarrollo. Se crea sola y se
migra con Alembic al inicio de la sesión de tests. Cada test corre dentro de una
transacción que se revierte al final, así los tests no dejan datos.

Si PostgreSQL no está disponible, los tests que usan la base se SALTEAN, salvo que
REQUIRE_DB=1 (lo usa el CI), en cuyo caso FALLAN.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.core import config

# --- Redirigir la app a la base de test ANTES de crear el engine ---
_dev_settings = config.Settings()
TEST_DB = os.getenv("TEST_POSTGRES_DB") or f"{_dev_settings.postgres_db}_test"
os.environ["POSTGRES_DB"] = TEST_DB
os.environ.setdefault("APP_ENV", "test")
config.get_settings.cache_clear()

import psycopg  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.session import engine, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Role, User  # noqa: E402
from app.services.auth import login_limiter  # noqa: E402
from tests.helpers import auth_headers, make_user  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _skip_or_fail(reason: str) -> None:
    if os.getenv("REQUIRE_DB") == "1":
        pytest.fail(f"PostgreSQL requerido y no disponible: {reason}")
    pytest.skip("PostgreSQL no disponible (levantalo con: .\\scripts\\dev.ps1 db)")


def _ensure_test_database() -> None:
    s = config.get_settings()
    conninfo = psycopg.conninfo.make_conninfo(
        host=s.postgres_host,
        port=s.postgres_port,
        user=s.postgres_user,
        password=s.postgres_password,
        dbname="postgres",
        connect_timeout=3,
    )
    with psycopg.connect(conninfo, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)).fetchone()
        if not exists:
            conn.execute(
                psycopg.sql.SQL("CREATE DATABASE {}").format(psycopg.sql.Identifier(TEST_DB))
            )


@pytest.fixture(scope="session")
def database() -> None:
    """Crea la base de test (si falta) y la lleva a la última migración."""
    try:
        _ensure_test_database()
    except psycopg.Error as exc:
        _skip_or_fail(str(exc))
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")


@pytest.fixture
def db(database) -> Iterator[Session]:
    """Sesión dentro de una transacción externa que se revierte al terminar el test."""
    connection = engine.connect()
    outer = connection.begin()
    session = Session(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    )
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


@pytest.fixture
def db_connection(db):
    """Conexión cruda (tests de infraestructura)."""
    return db.connection()


@pytest.fixture(autouse=True)
def _reset_state():
    login_limiter.reset()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client() -> TestClient:
    """Cliente HTTP sin base de datos (health, errores)."""
    return TestClient(app)


@pytest.fixture
def api(db) -> TestClient:
    """Cliente HTTP cuya API usa la sesión transaccional del test."""

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    return TestClient(app)


@pytest.fixture
def admin(db) -> User:
    return make_user(db, "admin@demo.com.ar", Role.ADMIN, "Admin Demo")


@pytest.fixture
def operator(db) -> User:
    return make_user(db, "operador@demo.com.ar", Role.OPERATOR, "Operador Demo")


@pytest.fixture
def admin_h(admin) -> dict[str, str]:
    return auth_headers(admin)


@pytest.fixture
def operator_h(operator) -> dict[str, str]:
    return auth_headers(operator)


@pytest.fixture
def pg_version(db_connection) -> int:
    return int(db_connection.execute(text("SHOW server_version_num")).scalar_one())
