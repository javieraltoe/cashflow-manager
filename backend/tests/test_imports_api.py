"""HU07: importo CSV con prevalidación y un reporte de filas rechazadas (spec §10)."""

from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models import AuditEvent, Client, ImportBatch, Invoice
from app.services import imports as imports_service

pytestmark = pytest.mark.integration

PREVIEW = "/api/v1/imports/invoices/preview"
COMMIT = "/api/v1/imports/invoices/commit"
HEADER = "client_name,invoice_number,issue_date,due_date,amount,description\n"


def _send(
    api, headers, url, text: str, create=False, name="facturas.csv", raw: bytes | None = None
):
    content = raw if raw is not None else text.encode("utf-8")
    data = {"create_missing_clients": "true"} if create else {}
    return api.post(url, headers=headers, files={"file": (name, content, "text/csv")}, data=data)


@pytest.fixture
def clientes(api, admin_h):
    for name in ("ACME SA", "Beta SRL"):
        api.post("/api/v1/clients", headers=admin_h, json={"name": name})
    inactivo = api.post("/api/v1/clients", headers=admin_h, json={"name": "Viejo SA"}).json()
    api.patch(f"/api/v1/clients/{inactivo['id']}", headers=admin_h, json={"is_active": False})


def test_ejemplo_del_documento(api, operator_h, clientes, db):
    csv_text = HEADER + "ACME SA,F-0001,2026-10-01,2026-10-30,125000.50,Servicio mensual\n"
    prev = _send(api, operator_h, PREVIEW, csv_text)
    assert prev.status_code == 200, prev.text
    body = prev.json()
    assert (body["row_count"], body["valid_count"], body["rejected_count"]) == (1, 1, 0)
    assert body["rows"][0]["status"] == "ok"
    # La previsualización no guarda nada
    assert db.scalar(select(func.count()).select_from(Invoice)) == 0

    res = _send(api, operator_h, COMMIT, csv_text)
    assert res.status_code == 200
    assert res.json()["imported_count"] == 1
    inv = db.scalar(select(Invoice))
    assert inv.amount == Decimal("125000.50")
    assert inv.description == "Servicio mensual"


def test_reporte_de_filas_rechazadas(api, admin_h, clientes):
    csv_text = HEADER + "\n".join(
        [
            "ACME SA,OK-1,2026-10-01,2026-10-30,100,",  # 2 ok
            "ACME SA,OK-1,2026-10-01,2026-10-30,100,",  # 3 repetida en el archivo
            "Nadie SA,X-1,2026-10-01,2026-10-30,100,",  # 4 cliente inexistente
            "Viejo SA,X-2,2026-10-01,2026-10-30,100,",  # 5 cliente inactivo
            "ACME SA,X-3,01/10/2026,2026-10-30,100,",  # 6 fecha inválida
            "ACME SA,X-4,2026-10-30,2026-10-01,100,",  # 7 vence antes de emitir
            "ACME SA,X-5,2026-10-01,2026-10-30,0,",  # 8 importe cero
            "ACME SA,X-6,2026-10-01,2026-10-30,-5,",  # 9 negativo
            "ACME SA,X-7,2026-10-01,2026-10-30,1.234.50,",  # 10 con miles
            "ACME SA,X-8,2026-10-01,2026-10-30,10.555,",  # 11 tres decimales
            ",X-9,2026-10-01,2026-10-30,10,",  # 12 sin cliente
            "ACME SA,,2026-10-01,2026-10-30,10,",  # 13 sin número
            "ACME SA,X-10,2026-02-30,2026-03-30,10,",  # 14 fecha inexistente
        ]
    )
    body = _send(api, admin_h, PREVIEW, csv_text).json()
    assert body["valid_count"] == 1
    errors = {r["line"]: (r["errors"][0]["field"], r["errors"][0]["message"]) for r in body["rows"]
              if r["status"] == "error"}  # fmt: skip
    assert errors[3][0] == "invoice_number" and "línea 2" in errors[3][1]
    assert errors[4] == ("client_name", "Cliente inexistente: 'Nadie SA'")
    assert errors[5] == ("client_name", "Cliente inactivo: 'Viejo SA'")
    assert errors[6][0] == "issue_date"
    assert errors[7][0] == "due_date"
    assert errors[8][0] == errors[9][0] == errors[10][0] == errors[11][0] == "amount"
    assert errors[12][0] == "client_name"
    assert errors[13][0] == "invoice_number"
    assert errors[14][0] == "issue_date"

    res = _send(api, admin_h, COMMIT, csv_text).json()
    assert res["imported_count"] == 1
    assert res["rejected_count"] == 12
    assert {r["line"] for r in res["rejected"]} == set(range(3, 15))


def test_confirmar_dos_veces_no_duplica(api, admin_h, clientes, db):
    csv_text = (
        HEADER + "ACME SA,F-1,2026-10-01,2026-10-30,10,\nBeta SRL,F-1,2026-10-01,2026-10-30,20,\n"
    )
    first = _send(api, admin_h, COMMIT, csv_text).json()
    second = _send(api, admin_h, COMMIT, csv_text).json()
    assert first["imported_count"] == 2
    assert second["imported_count"] == 0
    assert second["rejected"][0]["errors"][0]["message"].startswith("Ya existe")
    assert db.scalar(select(func.count()).select_from(Invoice)) == 2
    lotes = db.scalars(select(ImportBatch).order_by(ImportBatch.created_at)).all()
    assert [b.status for b in lotes] == ["completed", "rejected"]


def test_crear_clientes_faltantes_es_opcion_explicita(api, admin_h, db):
    csv_text = HEADER + (
        "Nuevo SA,N-1,2026-10-01,2026-10-30,10,\n"
        "nuevo sa,N-2,2026-10-01,2026-10-30,20,\n"  # mismo cliente, otra capitalización
        "Malo SA,N-3,2026-10-01,2026-10-30,0,\n"  # fila inválida: no se crea "Malo SA"
    )
    sin = _send(api, admin_h, PREVIEW, csv_text).json()
    assert sin["valid_count"] == 0
    con = _send(api, admin_h, PREVIEW, csv_text, create=True).json()
    assert con["valid_count"] == 2
    assert con["new_clients"] == ["Nuevo SA"]
    res = _send(api, admin_h, COMMIT, csv_text, create=True).json()
    assert res["created_clients"] == ["Nuevo SA"]
    assert db.scalar(select(func.count()).select_from(Client)) == 1
    ev = db.scalar(select(AuditEvent).where(AuditEvent.entity_type == "import_batch"))
    assert ev.details["imported"] == 2 and ev.details["created_clients"] == 1


def test_formato_excel_punto_y_coma_bom_y_coma_decimal(api, admin_h, clientes):
    csv_text = (
        "\ufeffclient_name;invoice_number;issue_date;due_date;amount\r\n"
        "ACME SA;E-1;2026-10-01;2026-10-30;1500,75\r\n"
    )
    body = _send(api, admin_h, PREVIEW, csv_text).json()
    assert body["valid_count"] == 1  # description es opcional
    res = _send(api, admin_h, COMMIT, csv_text).json()
    assert res["imported_count"] == 1


@pytest.mark.parametrize(
    ("contenido", "codigo"),
    [
        ("", "empty_file"),
        (HEADER, "empty_file"),
        ("cliente,numero\nA,1\n", "invalid_columns"),
        (
            HEADER.replace("\n", ",extra\n") + "ACME SA,1,2026-01-01,2026-01-02,1,,x\n",
            "invalid_columns",
        ),
    ],
)
def test_errores_de_archivo(api, admin_h, contenido, codigo):
    resp = _send(api, admin_h, PREVIEW, contenido)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == codigo
    assert resp.json()["error"]["field"] == "file"


def test_archivo_no_utf8(api, admin_h):
    raw = (HEADER + "Compañía,1,2026-10-01,2026-10-30,1,\n").encode("latin-1")
    resp = _send(api, admin_h, PREVIEW, "", raw=raw)
    assert resp.json()["error"]["code"] == "invalid_encoding"


def test_limites_de_tamano_y_filas(api, admin_h, monkeypatch):
    monkeypatch.setattr(imports_service, "MAX_ROWS", 3)
    filas = "".join(f"A,{n},2026-10-01,2026-10-30,1,\n" for n in range(4))
    resp = _send(api, admin_h, PREVIEW, HEADER + filas)
    assert resp.json()["error"]["code"] == "too_many_rows"

    monkeypatch.setattr(imports_service, "MAX_BYTES", 100)
    resp = _send(api, admin_h, PREVIEW, HEADER + "x" * 200)
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "file_too_large"


def test_nombre_de_archivo_saneado(api, admin_h, clientes, db):
    csv_text = HEADER + "ACME SA,S-1,2026-10-01,2026-10-30,10,\n"
    _send(api, admin_h, COMMIT, csv_text, name="..\\..\\C:\\secreto\\facturas.csv")
    assert db.scalar(select(ImportBatch.filename)) == "facturas.csv"


def test_requiere_autenticacion(api):
    resp = api.post(PREVIEW, files={"file": ("a.csv", b"x", "text/csv")})
    assert resp.status_code == 401
