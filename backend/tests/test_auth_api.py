"""HU01: autenticación, sesiones y roles (integración API + PostgreSQL)."""

import pytest

from app.models import Role
from tests.helpers import TEST_PASSWORD, make_user

pytestmark = pytest.mark.integration


def _login(api, email, password=TEST_PASSWORD):
    return api.post("/api/v1/auth/login", json={"email": email, "password": password})


def test_login_correcto_devuelve_tokens(api, admin):
    resp = _login(api, "ADMIN@demo.com.ar ")  # email sin distinguir mayúsculas/espacios
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0
    me = api.get("/api/v1/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == "admin@demo.com.ar"
    assert me.json()["role"] == "admin"
    assert "password_hash" not in me.json()


@pytest.mark.parametrize("email,password", [("admin@demo.com.ar", "mala"), ("nadie@x.com", "x")])
def test_credenciales_invalidas_mismo_error(api, admin, email, password):
    resp = _login(api, email, password)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_credentials"


def test_usuario_inactivo_no_puede_ingresar(api, db):
    user = make_user(db, "baja@demo.com.ar", Role.OPERATOR)
    user.is_active = False
    db.commit()
    assert _login(api, "baja@demo.com.ar").status_code == 401


def test_bloqueo_tras_intentos_fallidos(api, admin):
    for _ in range(5):
        assert _login(api, "admin@demo.com.ar", "incorrecta").status_code == 401
    resp = _login(api, "admin@demo.com.ar")  # incluso con la clave correcta
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "too_many_attempts"


def test_refresh_rota_y_detecta_reutilizacion(api, admin):
    first = _login(api, "admin@demo.com.ar").json()
    r1 = api.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert r1.status_code == 200
    second = r1.json()
    assert second["refresh_token"] != first["refresh_token"]

    # Reusar el token viejo -> 401 y se revocan TODAS las sesiones (también la nueva).
    reuse = api.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert reuse.status_code == 401
    again = api.post("/api/v1/auth/refresh", json={"refresh_token": second["refresh_token"]})
    assert again.status_code == 401


def test_logout_revoca_el_refresh(api, admin):
    tokens = _login(api, "admin@demo.com.ar").json()
    out = api.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert out.status_code == 204
    resp = api.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 401


def test_sin_token_401_con_www_authenticate(api):
    resp = api.get("/api/v1/me")
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == "Bearer"
    assert resp.json()["error"]["code"] == "unauthorized"


def test_token_basura_401(api):
    resp = api.get("/api/v1/me", headers={"Authorization": "Bearer xxx.yyy.zzz"})
    assert resp.status_code == 401


def test_cambio_de_password(api, admin, admin_h):
    resp = api.post(
        "/api/v1/me/password",
        headers=admin_h,
        json={"current_password": TEST_PASSWORD, "new_password": "nueva-clave-segura"},
    )
    assert resp.status_code == 204
    assert _login(api, "admin@demo.com.ar").status_code == 401
    assert _login(api, "admin@demo.com.ar", "nueva-clave-segura").status_code == 200


def test_cambio_de_password_exige_la_actual(api, admin_h):
    resp = api.post(
        "/api/v1/me/password",
        headers=admin_h,
        json={"current_password": "equivocada", "new_password": "nueva-clave-segura"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["field"] == "current_password"
