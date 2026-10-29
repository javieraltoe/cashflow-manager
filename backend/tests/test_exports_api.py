"""HU08: filtro facturas por cliente y vencimiento y exporto CSV."""

import csv
import io
from datetime import date

import pytest

from app.seed import seed_demo
from tests.helpers import set_today

pytestmark = pytest.mark.integration

URL = "/api/v1/exports/invoices.csv"
HOY = date(2026, 10, 28)


@pytest.fixture
def demo(db, admin):
    set_today(HOY)
    seed_demo(db, HOY, admin)


def _rows(resp) -> list[dict]:
    assert resp.status_code == 200, resp.text
    text = resp.content.decode("utf-8")
    assert text.startswith("﻿")
    return list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))


def test_exporta_con_los_mismos_filtros_que_el_listado(api, admin_h, demo):
    clientes = api.get("/api/v1/clients", headers=admin_h, params={"q": "Andina"}).json()
    params = {"client_id": clientes["items"][0]["id"], "due_to": "2026-09-30"}
    rows = _rows(api.get(URL, headers=admin_h, params=params))
    listado = api.get("/api/v1/invoices", headers=admin_h, params=params).json()
    assert [r["invoice_number"] for r in rows] == [i["invoice_number"] for i in listado["items"]]
    assert [r["invoice_number"] for r in rows] == ["F-2002", "F-2001"]  # orden por vencimiento
    assert rows[1]["balance"] == "250000.00"
    assert rows[1]["status"] == "VENCIDA"
    assert rows[1]["days_overdue"] == "45"


def test_cabecera_y_metadatos(api, admin_h, demo):
    resp = api.get(URL, headers=admin_h, params={"status": "PAGADA"})
    assert resp.headers["content-type"].startswith("text/csv")
    assert 'filename="facturas_20261028.csv"' in resp.headers["content-disposition"]
    assert resp.headers["cache-control"] == "no-store"
    rows = _rows(resp)
    assert list(rows[0]) == [
        "client_name", "invoice_number", "issue_date", "due_date", "amount", "description",
        "paid_amount", "balance", "status", "days_overdue",
    ]  # fmt: skip
    assert {r["status"] for r in rows} == {"PAGADA"}
    # Anuladas excluidas por defecto
    assert "F-4002" not in {r["invoice_number"] for r in _rows(api.get(URL, headers=admin_h))}


def test_proteccion_contra_formulas(api, admin_h):
    set_today(HOY)
    c = api.post("/api/v1/clients", headers=admin_h, json={"name": "=HYPERLINK(1)"}).json()
    api.post(
        "/api/v1/invoices",
        headers=admin_h,
        json={
            "client_id": c["id"],
            "invoice_number": "+F1",
            "issue_date": "2026-10-01",
            "due_date": "2026-10-30",
            "amount": "10",
            "description": "@SUM(A1)",
        },
    )
    row = _rows(api.get(URL, headers=admin_h))[0]
    assert row["client_name"] == "'=HYPERLINK(1)"
    assert row["invoice_number"] == "'+F1"
    assert row["description"] == "'@SUM(A1)"


def test_ida_y_vuelta_exportar_e_importar(api, admin_h, demo):
    """El CSV exportado es un CSV de importación válido: reimportarlo no duplica nada."""
    content = api.get(URL, headers=admin_h).content
    prev = api.post(
        "/api/v1/imports/invoices/preview",
        headers=admin_h,
        files={"file": ("export.csv", content, "text/csv")},
    )
    assert prev.status_code == 422  # columnas extra (paid_amount, balance, ...)
    # Recortado a las columnas de importación, todas las filas ya existen:
    text = content.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    trimmed = "\n".join(",".join(r[:6]) for r in rows)
    prev = api.post(
        "/api/v1/imports/invoices/preview",
        headers=admin_h,
        files={"file": ("export.csv", trimmed.encode(), "text/csv")},
    ).json()
    assert prev["valid_count"] == 0
    ya_existe = "Ya existe una factura con ese número para el cliente"
    assert all(ya_existe in [e["message"] for e in r["errors"]] for r in prev["rows"])


def test_operador_puede_exportar_y_anonimo_no(api, operator_h):
    assert api.get(URL, headers=operator_h).status_code == 200
    assert api.get(URL).status_code == 401
