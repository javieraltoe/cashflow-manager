"""Fixtures compartidas.

- `client`: TestClient de la API (no necesita base de datos).
- `db_connection`: conexión real a PostgreSQL. Si la base no está disponible el test
  se SALTEA, salvo que REQUIRE_DB=1 (lo usa el CI), en cuyo caso FALLA.
"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import engine
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def db_connection():
    try:
        conn = engine.connect()
        conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - depende del entorno
        if os.getenv("REQUIRE_DB") == "1":
            pytest.fail(f"PostgreSQL requerido y no disponible: {exc}")
        pytest.skip("PostgreSQL no disponible (levantalo con: .\\scripts\\dev.ps1 db)")
    try:
        yield conn
    finally:
        conn.close()
