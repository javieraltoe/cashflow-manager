"""Pruebas de la interfaz PySide6 en modo invisible (offscreen) contra la API real.

Se ejecutan donde PySide6 está instalado (tu PC con el .venv del proyecto); en el CI se
saltean. Los cuadros de mensaje se reemplazan por un registro y los diálogos modales no
se abren (exec() devuelve "cancelado"), así ningún test queda esperando un clic.
"""

import os
from datetime import timedelta
from decimal import Decimal

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from desktop.app.core.config import AppConfig, load_config  # noqa: E402
from desktop.app.core.formatting import today_local  # noqa: E402
from desktop.app.services.api import ApiClient, new_idempotency_key  # noqa: E402
from desktop.app.views.base import AppContext  # noqa: E402
from desktop.app.views.clients import ClientDialog, ClientsPage  # noqa: E402
from desktop.app.views.credits import (  # noqa: E402
    ApplyCreditDialog,
    CreditOnAccountDialog,
    CreditsPage,
)
from desktop.app.views.imports import ImportPage  # noqa: E402
from desktop.app.views.invoices import (  # noqa: E402
    InvoiceDetailDialog,
    InvoiceDialog,
    InvoicesPage,
)
from desktop.app.views.login import LoginDialog  # noqa: E402
from desktop.app.views.main_window import MainWindow  # noqa: E402
from desktop.app.views.payments import PaymentDialog, VoidDialog  # noqa: E402
from desktop.app.views.settings import SettingsPage, UserDialog  # noqa: E402
from desktop.app.widgets import files, messages  # noqa: E402
from tests.helpers import TEST_PASSWORD  # noqa: E402

pytestmark = pytest.mark.integration
D = Decimal


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


class Messages:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.infos: list[str] = []
        self.questions: list[str] = []
        self.answer = True


@pytest.fixture(autouse=True)
def msgs(monkeypatch, qapp) -> Messages:
    rec = Messages()
    monkeypatch.setattr(messages, "show_error", lambda _p, text, **_k: rec.errors.append(text))
    monkeypatch.setattr(messages, "show_info", lambda _p, text, **_k: rec.infos.append(text))

    def ask(_p, text, **_k):
        rec.questions.append(text)
        return rec.answer

    monkeypatch.setattr(messages, "ask_yes_no", ask)
    # Ningún diálogo modal se abre de verdad durante los tests.
    monkeypatch.setattr(QDialog, "exec", lambda self: 0)
    return rec


@pytest.fixture
def ctx(admin_api) -> AppContext:
    return AppContext(admin_api, AppConfig(api_url=admin_api.base_url))


@pytest.fixture
def factura(ctx) -> dict:
    today = today_local()
    client = ctx.api.create_client({"name": "ACME SA"})
    return ctx.api.create_invoice(
        {
            "client_id": client["id"],
            "invoice_number": "F-0001",
            "issue_date": today - timedelta(days=10),
            "due_date": today + timedelta(days=5),
            "amount": D("1000.00"),
        }
    )


# ---------- Login ----------


def test_login_correcto_guarda_servidor_y_email(api, admin, msgs):
    ctx = AppContext(ApiClient("http://localhost:8000/api/v1", http=api), load_config())
    dlg = LoginDialog(ctx)
    dlg.server.setText("http://testserver")
    dlg.email.setText(admin.email)
    dlg.password.setText(TEST_PASSWORD)
    dlg.on_accept()
    assert dlg.result_data["email"] == admin.email
    assert dlg.password.text() == ""  # la contraseña no queda en memoria del widget
    saved = load_config()
    assert saved.api_url == "http://testserver/api/v1"
    assert saved.last_email == admin.email


def test_login_incorrecto_muestra_error(api, admin):
    ctx = AppContext(ApiClient("http://testserver/api/v1", http=api), AppConfig())
    dlg = LoginDialog(ctx)
    dlg.server.setText("http://testserver")
    dlg.email.setText(admin.email)
    dlg.password.setText("incorrecta")
    dlg.on_accept()
    assert dlg.result_data is None
    assert "incorrectos" in dlg.error_label.text()


def test_login_valida_campos_vacios(api):
    ctx = AppContext(ApiClient("http://testserver/api/v1", http=api), AppConfig())
    dlg = LoginDialog(ctx)
    dlg.email.setText("")
    dlg.on_accept()
    assert dlg.error_label.text() == "Ingresá tu email"


def test_aviso_de_conexion_sin_cifrar(api):
    ctx = AppContext(ApiClient("http://testserver/api/v1", http=api), AppConfig())
    dlg = LoginDialog(ctx)
    dlg.server.setText("http://192.168.0.20:8000")
    assert not dlg.warning.isHidden()
    dlg.server.setText("https://cobranzas.miempresa.com")
    assert dlg.warning.isHidden()


# ---------- Ventana principal ----------


def test_todas_las_paginas_cargan_sin_errores(ctx, factura, msgs):
    win = MainWindow(ctx)
    for row in range(len(win.pages)):
        win.nav.setCurrentRow(row)
    assert msgs.errors == []
    assert win.home.due_soon.value.text() == "$ 1.000,00"
    assert win.home.due_soon.detail.text() == "1 factura"
    assert win.home.receivable.value.text() == "$ 1.000,00"
    assert win.invoices.table.table_model.rowCount() == 1
    assert win.invoices.void_btn.isVisibleTo(win.invoices)  # admin ve "Anular"


def test_operador_no_ve_acciones_de_admin(operator_api):
    ctx = AppContext(operator_api, AppConfig())
    win = MainWindow(ctx)
    assert not win.invoices.void_btn.isVisibleTo(win.invoices)
    assert not win.payments.void_btn.isVisibleTo(win.payments)
    win.nav.setCurrentRow(win.pages.index(win.settings))
    assert not win.settings.users_box.isVisibleTo(win.settings)


def test_sesion_vencida_sin_reingreso_emite_session_lost(ctx, msgs):
    perdidas = []
    ctx.session_lost.connect(lambda: perdidas.append(True))
    ctx.api._access = "token-invalido"
    ctx.api._refresh = None
    assert ctx.call(None, ctx.api.me) is None
    assert perdidas == [True]


# ---------- Clientes ----------


def test_alta_de_cliente_y_duplicado(ctx):
    dlg = ClientDialog(ctx)
    dlg.name.setText("Ferretería Sur")
    dlg.tax_id.setText("30-11111111-1")
    dlg.on_accept()
    assert dlg.result_data["name"] == "Ferretería Sur"

    dup = ClientDialog(ctx)
    dup.name.setText("FERRETERÍA SUR")
    dup.on_accept()
    assert dup.result_data is None
    assert "Ya existe" in dup.error_label.text()
    assert dup.name.styleSheet()  # el campo con error queda resaltado


def test_cliente_nombre_obligatorio(ctx):
    dlg = ClientDialog(ctx)
    dlg.on_accept()
    assert dlg.error_label.text() == "El nombre es obligatorio"


def test_pagina_clientes_busca_y_desactiva(ctx, factura, msgs):
    page = ClientsPage(ctx)
    page.search.setText("acme")
    page.search_now()
    assert page.table.table_model.rowCount() == 1
    page.table.select_first()
    page.toggle_selected()  # msgs.answer = True -> confirma
    assert msgs.questions and "desactivar" in msgs.questions[0]
    assert page.table.table_model.rowCount() == 0  # el filtro es "Activos"


# ---------- Facturas ----------


def test_alta_de_factura_con_importe_argentino(ctx, factura):
    dlg = InvoiceDialog(ctx)
    dlg.client.set_value(factura["client_id"])
    dlg.number.setText("F-0002")
    dlg.amount.setText("1.234,56")
    dlg.on_accept()
    assert dlg.result_data["amount"] == "1234.56"
    assert dlg.result_data["status"] == "PENDIENTE"


def test_factura_vencimiento_anterior_a_emision(ctx, factura):
    dlg = InvoiceDialog(ctx)
    dlg.client.set_value(factura["client_id"])
    dlg.number.setText("F-0003")
    dlg.amount.setText("10")
    dlg.due.set_value(dlg.issue.value() - timedelta(days=1))
    dlg.on_accept()
    assert dlg.result_data is None
    assert "vencimiento" in dlg.error_label.text()


def test_factura_importe_mal_escrito(ctx, factura):
    dlg = InvoiceDialog(ctx)
    dlg.client.set_value(factura["client_id"])
    dlg.number.setText("F-0004")
    dlg.amount.setText("12,345")
    dlg.on_accept()
    assert "2 decimales" in dlg.error_label.text()


def test_editar_factura_envia_solo_cambios(ctx, factura, monkeypatch):
    enviados = []
    original = ctx.api.update_invoice

    def spy(invoice_id, data):
        enviados.append(data)
        return original(invoice_id, data)

    monkeypatch.setattr(ctx.api, "update_invoice", spy)
    dlg = InvoiceDialog(ctx, factura)
    assert not dlg.client.isEnabled()
    dlg.on_accept()  # sin cambios: no llama a la API, devuelve la misma
    assert dlg.result_data["id"] == factura["id"]
    assert enviados == []
    dlg = InvoiceDialog(ctx, factura)
    dlg.amount.setText("1500")
    dlg.on_accept()
    assert dlg.result_data["amount"] == "1500.00"
    assert list(enviados[0]) == ["amount"]


def test_pagina_facturas_filtra_por_estado(ctx, factura):
    page = InvoicesPage(ctx)
    page.status.set_value("VENCIDA")
    page.search_now()
    assert page.table.table_model.rowCount() == 0
    page.status.set_value("PENDIENTE")
    page.search_now()
    assert page.table.table_model.rowCount() == 1


def test_detalle_de_factura(ctx, factura):
    dlg = InvoiceDetailDialog(ctx, factura["id"])
    assert dlg.labels["balance"].text() == "$ 1.000,00"
    assert dlg.pay_btn.isEnabled()


# ---------- Pagos ----------


def test_pago_parcial(ctx, factura):
    dlg = PaymentDialog(ctx, factura)
    assert dlg.amount.text() == "1000,00"  # se propone el saldo
    dlg.amount.setText("400")
    dlg.on_accept()
    assert dlg.result_data["invoice_balance"] == "600.00"
    assert dlg.result_data["invoice_status"] == "PARCIAL"


def test_doble_clic_no_duplica_el_pago(ctx, factura, msgs):
    dlg = PaymentDialog(ctx, factura)
    dlg.amount.setText("400")
    dlg.on_accept()
    dlg.on_accept()  # segundo envío con la misma Idempotency-Key
    assert dlg.replayed
    assert ctx.api.list_payments(invoice_id=factura["id"])["total"] == 1


def test_sobrepago_confirmado_genera_saldo_a_favor(ctx, factura, msgs):
    dlg = PaymentDialog(ctx, factura)
    dlg.amount.setText("1.100")
    dlg.on_accept()
    assert "saldo a favor" in msgs.questions[0]
    assert dlg.result_data["credit_amount"] == "100.00"
    assert ctx.api.client_credit(factura["client_id"])["available"] == "100.00"


def test_sobrepago_rechazado_queda_abierto(ctx, factura, msgs):
    msgs.answer = False
    dlg = PaymentDialog(ctx, factura)
    dlg.amount.setText("1100")
    dlg.on_accept()
    assert dlg.result_data is None
    assert "Corregí el importe" in dlg.error_label.text()


def test_anular_pago_exige_motivo(ctx, factura):
    pago = ctx.api.create_payment(
        {"invoice_id": factura["id"], "amount": D("400"), "method": "cheque"},
        new_idempotency_key(),
    ).data
    dlg = VoidDialog(ctx, "Anular", lambda r: ctx.api.void_payment(pago["id"], r))
    dlg.on_accept()
    assert "motivo" in dlg.error_label.text()
    dlg.reason.setText("cheque rechazado")
    dlg.on_accept()
    assert dlg.result_data["is_void"] is True
    assert dlg.result_data["invoice_balance"] == "1000.00"


# ---------- Saldo a favor ----------


def test_cobro_a_cuenta_e_imputacion(ctx, factura, msgs):
    client = ctx.api.get_client(factura["client_id"])
    dlg = CreditOnAccountDialog(ctx, client)
    dlg.amount.setText("300")
    dlg.on_accept()
    assert dlg.result_data["client_available"] == "300.00"

    apply = ApplyCreditDialog(ctx, client)
    assert apply.ready
    assert apply.amount.text() == "300,00"  # min(disponible, saldo de la factura)
    apply.on_accept()
    assert apply.result_data["method"] == "saldo_a_favor"
    assert apply.result_data["invoice_balance"] == "700.00"

    page = CreditsPage(ctx)
    page.refresh()
    page.client.set_value(client["id"])
    page.refresh()
    assert "Disponible $ 0,00" in page.summary.text()


def test_imputar_sin_saldo_avisa(ctx, factura, msgs):
    client = ctx.api.get_client(factura["client_id"])
    dlg = ApplyCreditDialog(ctx, client)
    assert not dlg.ready
    assert "no tiene saldo a favor" in msgs.infos[0]


# ---------- Configuración ----------


def test_admin_crea_y_edita_usuario(ctx):
    dlg = UserDialog(ctx)
    dlg.email.setText("nueva@demo.com.ar")
    dlg.full_name.setText("Nueva Operadora")
    dlg.password.setText("corta")
    dlg.on_accept()
    assert "10 caracteres" in dlg.error_label.text()
    dlg.password.setText("una-clave-larga-1")
    dlg.on_accept()
    user = dlg.result_data
    assert user["role"] == "operator"

    edit = UserDialog(ctx, user)
    edit.active.setChecked(False)
    edit.on_accept()
    assert edit.result_data["is_active"] is False


def test_cambio_de_password_pide_reingresar(ctx, msgs):
    page = SettingsPage(ctx)
    page.refresh()
    emitted = []
    page.password_changed.connect(lambda: emitted.append(True))
    page.current_pwd.setText(TEST_PASSWORD)
    page.new_pwd.setText("nueva-clave-segura-1")
    page.repeat_pwd.setText("otra-cosa")
    page.change_password()
    assert "no coinciden" in msgs.errors[-1]
    page.current_pwd.setText(TEST_PASSWORD)
    page.new_pwd.setText("nueva-clave-segura-1")
    page.repeat_pwd.setText("nueva-clave-segura-1")
    page.change_password()
    assert emitted == [True]


# ---------- Importación y exportación CSV (HU07 / HU08) ----------


def test_importar_csv_previsualiza_y_confirma(ctx, factura, tmp_path, monkeypatch, msgs):
    hoy = today_local()
    csv_path = tmp_path / "facturas.csv"
    csv_path.write_text(
        "client_name,invoice_number,issue_date,due_date,amount,description\n"
        f"ACME SA,I-1,{hoy},{hoy + timedelta(days=30)},1500.50,Importada\n"
        f"ACME SA,F-0001,{hoy},{hoy},10,ya existe\n"
        f"Nadie SA,I-2,{hoy},{hoy},10,\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(files, "ask_open_csv", lambda _p: str(csv_path))
    page = ImportPage(ctx)
    page.choose_file()  # elige y previsualiza
    assert "3 filas · 1 válidas · 2 con errores" in page.summary.text()
    assert page.commit_btn.isEnabled()
    assert ctx.api.list_invoices(q="I-1")["total"] == 0  # la previsualización no guarda

    page.create_missing.setChecked(True)  # cambiar la opción obliga a previsualizar de nuevo
    assert not page.commit_btn.isEnabled()
    page.run_preview()
    assert "2 válidas" in page.summary.text() and "1 clientes nuevos" in page.summary.text()

    page.run_commit()
    assert "Nadie SA" in msgs.questions[-1]
    assert "2 facturas cargadas" in msgs.infos[-1]
    assert ctx.api.list_invoices(q="I-")["total"] == 2
    assert page.table.table_model.rowCount() == 1  # queda a la vista la fila rechazada


def test_importar_archivo_invalido_muestra_error(ctx, tmp_path, monkeypatch, msgs):
    bad = tmp_path / "malo.csv"
    bad.write_text("columna,otra\n1,2\n", encoding="utf-8")
    monkeypatch.setattr(files, "ask_open_csv", lambda _p: str(bad))
    page = ImportPage(ctx)
    page.choose_file()
    assert "Columnas inválidas" in msgs.errors[-1]
    assert not page.commit_btn.isEnabled()


def test_descargar_plantilla(ctx, tmp_path, monkeypatch):
    target = tmp_path / "plantilla.csv"
    monkeypatch.setattr(files, "ask_save_csv", lambda _p, _n: str(target))
    ImportPage(ctx).save_template()
    assert target.read_text(encoding="utf-8").startswith("client_name,invoice_number")


def test_exportar_facturas_filtradas(ctx, factura, tmp_path, monkeypatch, msgs):
    target = tmp_path / "export.csv"
    monkeypatch.setattr(files, "ask_save_csv", lambda _p, _n: str(target))
    page = InvoicesPage(ctx)
    page.status.set_value("PENDIENTE")
    page.export_csv()
    text = target.read_text(encoding="utf-8-sig")
    assert text.splitlines()[1].startswith("ACME SA,F-0001,")
    assert "1 facturas" in msgs.infos[-1]
    page.status.set_value("VENCIDA")
    page.export_csv()
    assert len(target.read_text(encoding="utf-8-sig").splitlines()) == 1  # solo cabecera
