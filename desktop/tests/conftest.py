"""Fixtures del escritorio.

Reutiliza las del backend (base de test transaccional, usuarios, TestClient) para probar
el ApiClient contra la API REAL, sin levantar un servidor: el TestClient de FastAPI es un
httpx.Client, así que se le inyecta al ApiClient.
"""

import pytest

from desktop.app.services.api import ApiClient
from tests.conftest import (  # noqa: F401  (fixtures del backend)
    _reset_state,
    admin,
    admin_h,
    api,
    database,
    db,
    operator,
    operator_h,
)
from tests.helpers import TEST_PASSWORD

BASE = "http://testserver/api/v1"


@pytest.fixture(autouse=True)
def _config_aislada(tmp_path, monkeypatch):
    """Ningún test toca la configuración real del usuario."""
    monkeypatch.setenv("CASHFLOW_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("CASHFLOW_API_URL", raising=False)


@pytest.fixture
def client_api(api) -> ApiClient:
    """ApiClient sin sesión, conectado a la API real (base de test)."""
    return ApiClient(BASE, http=api)


@pytest.fixture
def admin_api(client_api, admin) -> ApiClient:
    client_api.login(admin.email, TEST_PASSWORD)
    return client_api


@pytest.fixture
def operator_api(api, operator) -> ApiClient:
    c = ApiClient(BASE, http=api)
    c.login(operator.email, TEST_PASSWORD)
    return c
