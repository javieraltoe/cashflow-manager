"""HU01: solo el administrador gestiona usuarios."""

import pytest
from sqlalchemy import select

from app.models import AuditEvent

pytestmark = pytest.mark.integration

NUEVO = {
    "email": "Nuevo@Demo.com.ar",
    "full_name": "Nuevo Operador",
    "role": "operator",
    "password": "clave-larga-123",
}


def test_admin_crea_y_lista_usuarios(api, admin_h, db):
    resp = api.post("/api/v1/users", headers=admin_h, json=NUEVO)
    assert resp.status_code == 201
    created = resp.json()
    assert created["email"] == "nuevo@demo.com.ar"
    assert created["role"] == "operator"

    listing = api.get("/api/v1/users", headers=admin_h).json()
    assert listing["total"] == 2
    ev = db.scalar(select(AuditEvent).where(AuditEvent.entity_type == "user"))
    assert ev is not None
    assert "password" not in ev.details


@pytest.mark.parametrize(
    "method,path",
    [("get", "/api/v1/users"), ("post", "/api/v1/users"), ("patch", "/api/v1/users/{id}")],
)
def test_operador_no_administra_usuarios(api, operator, operator_h, method, path):
    kwargs = {"headers": operator_h}
    if method != "get":
        kwargs["json"] = NUEVO if method == "post" else {"role": "admin"}
    resp = getattr(api, method)(path.format(id=operator.id), **kwargs)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


def test_email_duplicado_409(api, admin_h):
    api.post("/api/v1/users", headers=admin_h, json=NUEVO)
    resp = api.post("/api/v1/users", headers=admin_h, json=NUEVO | {"email": "NUEVO@demo.com.ar"})
    assert resp.status_code == 409
    assert resp.json()["error"]["field"] == "email"


def test_password_corta_rechazada(api, admin_h):
    resp = api.post("/api/v1/users", headers=admin_h, json=NUEVO | {"password": "corta"})
    assert resp.status_code == 422
    assert resp.json()["error"]["field"] == "password"


def test_admin_no_puede_desactivarse_a_si_mismo(api, admin, admin_h):
    resp = api.patch(f"/api/v1/users/{admin.id}", headers=admin_h, json={"is_active": False})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "cannot_modify_self"


def test_desactivar_usuario_corta_su_acceso_inmediato(api, admin_h, operator, operator_h):
    assert api.get("/api/v1/me", headers=operator_h).status_code == 200
    resp = api.patch(f"/api/v1/users/{operator.id}", headers=admin_h, json={"is_active": False})
    assert resp.status_code == 200
    assert api.get("/api/v1/me", headers=operator_h).status_code == 401


def test_cambio_de_rol_se_aplica_desde_la_base(api, admin_h, operator, operator_h):
    """El token dice 'operator', pero el rol se verifica contra la base en cada request."""
    api.patch(f"/api/v1/users/{operator.id}", headers=admin_h, json={"role": "admin"})
    assert api.get("/api/v1/users", headers=operator_h).status_code == 200
