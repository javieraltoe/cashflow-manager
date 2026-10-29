"""Fixtures del dashboard: reutiliza las del backend y conecta el cliente del dashboard
a la API real (TestClient) sin levantar servidores."""

import sys
from pathlib import Path

import pytest

DASHBOARD_DIR = Path(__file__).resolve().parents[1]
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.append(str(DASHBOARD_DIR))  # al final: "tests" sigue siendo el del backend

from components import api as dash_api_module  # noqa: E402
from components.api import DashboardApi  # noqa: E402
from tests.conftest import (  # noqa: E402, F401  (fixtures del backend)
    _reset_state,
    admin,
    admin_h,
    api,
    database,
    db,
    operator,
    operator_h,
)
from tests.helpers import TEST_PASSWORD  # noqa: E402

BASE = "http://testserver/api/v1"


@pytest.fixture
def wired(api, monkeypatch):
    """Todo DashboardApi creado durante el test usa la API real de la base de test."""
    monkeypatch.setattr(dash_api_module, "HTTP_FACTORY", lambda: api)
    monkeypatch.setenv("API_BASE_URL", BASE)
    return api


@pytest.fixture
def dash(wired, admin) -> DashboardApi:
    client = DashboardApi(BASE)
    client.login(admin.email, TEST_PASSWORD)
    return client
