"""HU02: alta, búsqueda, edición y desactivación de clientes."""

import uuid

import pytest
from sqlalchemy import select

from app.models import AuditEvent

pytestmark = pytest.mark.integration

URL = "/api/v1/clients"


def _create(api, headers, **data):
    payload = {"name": "ACME SA"} | data
    return api.post(URL, headers=headers, json=payload)


def test_crear_cliente_y_encontrarlo_por_busqueda(api, operator_h):
    resp = _create(api, operator_h, name="  ACME SA  ", tax_id="30-12345678-9", email="")
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "ACME SA"  # se recortan espacios
    assert body["email"] is None  # cadena vacía -> null
    assert body["is_active"] is True

    for q in ("acme", "ACM", "12345678"):
        found = api.get(URL, headers=operator_h, params={"q": q}).json()
        assert found["total"] == 1, q
        assert found["items"][0]["id"] == body["id"]

    assert api.get(URL, headers=operator_h, params={"q": "zzz"}).json()["total"] == 0


@pytest.mark.parametrize("name", ["", "   "])
def test_nombre_obligatorio(api, operator_h, name):
    resp = _create(api, operator_h, name=name)
    assert resp.status_code == 422
    assert resp.json()["error"]["field"] == "name"


def test_nombre_duplicado_sin_distinguir_mayusculas(api, operator_h):
    _create(api, operator_h, name="Ferretería Sur")
    resp = _create(api, operator_h, name="FERRETERÍA SUR")
    assert resp.status_code == 409
    assert resp.json()["error"] == {
        "code": "client_name_taken",
        "message": "Ya existe un cliente con ese nombre",
        "field": "name",
    }


def test_email_invalido(api, operator_h):
    resp = _create(api, operator_h, email="no-es-email")
    assert resp.status_code == 422
    assert resp.json()["error"]["field"] == "email"


def test_busqueda_escapa_comodines(api, operator_h):
    _create(api, operator_h, name="ACME SA")
    _create(api, operator_h, name="Beta 100% SRL")
    assert api.get(URL, headers=operator_h, params={"q": "%"}).json()["total"] == 1
    assert api.get(URL, headers=operator_h, params={"q": "_"}).json()["total"] == 0


def test_editar_y_desactivar_con_auditoria(api, operator_h, db):
    cid = _create(api, operator_h).json()["id"]
    resp = api.patch(f"{URL}/{cid}", headers=operator_h, json={"phone": "11-5555-0000"})
    assert resp.status_code == 200
    assert resp.json()["phone"] == "11-5555-0000"

    resp = api.patch(f"{URL}/{cid}", headers=operator_h, json={"is_active": False})
    assert resp.json()["is_active"] is False

    activos = api.get(URL, headers=operator_h, params={"is_active": True}).json()
    inactivos = api.get(URL, headers=operator_h, params={"is_active": False}).json()
    assert activos["total"] == 0
    assert inactivos["total"] == 1

    actions = db.scalars(
        select(AuditEvent.action)
        .where(AuditEvent.entity_id == uuid.UUID(cid))
        .order_by(AuditEvent.created_at)
    ).all()
    assert sorted(actions) == ["create", "deactivate", "update"]


def test_renombrar_a_un_nombre_existente_409(api, operator_h):
    _create(api, operator_h, name="Uno")
    cid = _create(api, operator_h, name="Dos").json()["id"]
    resp = api.patch(f"{URL}/{cid}", headers=operator_h, json={"name": "uno"})
    assert resp.status_code == 409


def test_paginacion_y_orden(api, operator_h):
    for n in ("Charlie", "alfa", "Bravo"):
        _create(api, operator_h, name=n)
    page1 = api.get(URL, headers=operator_h, params={"page_size": 2}).json()
    page2 = api.get(URL, headers=operator_h, params={"page_size": 2, "page": 2}).json()
    assert page1["total"] == 3
    assert [c["name"] for c in page1["items"]] == ["alfa", "Bravo"]
    assert [c["name"] for c in page2["items"]] == ["Charlie"]
    assert api.get(URL, headers=operator_h, params={"page_size": 500}).status_code == 422


def test_cliente_inexistente_404(api, operator_h):
    resp = api.get(f"{URL}/{uuid.uuid4()}", headers=operator_h)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "client_not_found"


def test_requiere_autenticacion(api):
    assert api.get(URL).status_code == 401
