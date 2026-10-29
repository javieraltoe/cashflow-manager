"""Matriz de permisos: recorre TODAS las rutas de la API (spec §3, §8 y checklist §18).

Si se agrega un endpoint y no se lo clasifica acá, el test falla: obliga a decidir
explícitamente quién puede usarlo.
"""

import uuid

import pytest
from fastapi.routing import APIRoute

from app.main import app

pytestmark = pytest.mark.integration

PUBLIC = {
    ("GET", "/api/v1/health"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/auth/logout"),
}
ADMIN_ONLY = {
    ("GET", "/api/v1/users"),
    ("POST", "/api/v1/users"),
    ("PATCH", "/api/v1/users/{user_id}"),
    ("POST", "/api/v1/payments/{payment_id}/void"),
    ("POST", "/api/v1/credits/{credit_id}/void"),
}


def _routes() -> list[tuple[str, str]]:
    out = []
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith("/api/v1"):
            out.extend((m, route.path) for m in sorted(route.methods))
    return out


def _url(path: str) -> str:
    # Cualquier id con formato válido sirve: la autorización se evalúa antes que el recurso.
    import re

    return re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)


def test_toda_ruta_privada_exige_autenticacion(api):
    for method, path in _routes():
        if (method, path) in PUBLIC:
            continue
        resp = api.request(method, _url(path))
        assert resp.status_code == 401, f"{method} {path} respondió {resp.status_code} sin token"
        assert resp.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize(("method", "path"), sorted(ADMIN_ONLY))
def test_operador_recibe_403_en_rutas_de_administrador(api, operator_h, method, path):
    body = {"reason": "motivo de prueba"} if path.endswith("/void") else {}
    resp = api.request(method, _url(path), headers=operator_h, json=body)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


def test_las_rutas_de_admin_existen():
    rutas = set(_routes())
    assert rutas >= ADMIN_ONLY, ADMIN_ONLY - rutas
    assert rutas >= PUBLIC, PUBLIC - rutas
