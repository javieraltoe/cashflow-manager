"""Saldo a favor: disponible por cliente, cobros a cuenta, imputación y anulación (ADR-0003)."""

from decimal import Decimal

from PySide6.QtWidgets import QCheckBox, QLabel, QLineEdit, QPushButton, QWidget

from desktop.app.core.formatting import (
    ORIGIN_LABELS,
    format_date,
    format_money,
    method_label,
    to_decimal,
    today_local,
)
from desktop.app.services.api import new_idempotency_key
from desktop.app.views.base import AppContext, BasePage, FormDialog
from desktop.app.views.invoices import is_open
from desktop.app.views.payments import VoidDialog, method_choices
from desktop.app.widgets import messages
from desktop.app.widgets.common import (
    ChoiceCombo,
    DateEdit,
    FieldError,
    MoneyEdit,
    Pager,
    SearchCombo,
)
from desktop.app.widgets.table import Column, DataTable, field

PAGE_SIZE = 50


class CreditOnAccountDialog(FormDialog):
    """Cobro a cuenta: dinero recibido sin factura; queda todo como saldo a favor."""

    ok_text = "Registrar cobro"

    def __init__(self, ctx: AppContext, client: dict, parent: QWidget | None = None):
        super().__init__(ctx, "Cobro a cuenta", parent)
        self.client = client
        self.idempotency_key = new_idempotency_key()
        self.add_row("Cliente", QLabel(client["name"]))
        self.amount = MoneyEdit()
        self.method = ChoiceCombo(method_choices())
        self.date = DateEdit(today_local())
        self.date.setMaximumDate(self.date.date())
        self.reference = QLineEdit()
        self.add_row("Importe recibido *", self.amount, "amount")
        self.add_row("Medio de pago *", self.method, "method")
        self.add_row("Fecha de recepción *", self.date, "payment_date")
        self.add_row("Referencia", self.reference, "reference")

    def submit(self):
        data = {
            "client_id": self.client["id"],
            "amount": self.money(self.amount, "amount"),
            "method": self.method.value(),
            "payment_date": self.date.value(),
            "reference": self.reference.text().strip() or None,
        }
        result = self.ctx.api.create_credit(data, self.idempotency_key)
        if result.replayed:
            messages.show_info(self, "Este cobro ya estaba registrado; no se duplicó.")
        return result.data


class ApplyCreditDialog(FormDialog):
    """Imputar saldo a favor del cliente a una de sus facturas con saldo."""

    ok_text = "Imputar"

    def __init__(
        self,
        ctx: AppContext,
        client: dict,
        invoice: dict | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(ctx, "Imputar saldo a favor", parent)
        self.client = client
        self.idempotency_key = new_idempotency_key()
        self.ready = False
        self.invoices: dict[str, dict] = {}

        balance = ctx.call(parent, ctx.api.client_credit, client["id"])
        if balance is None:
            return
        self.available = to_decimal(balance["available"])
        if self.available <= 0:
            messages.show_info(parent, f"{client['name']} no tiene saldo a favor disponible.")
            return

        if invoice is not None:
            candidates = [invoice]
        else:
            page = ctx.call(
                parent,
                ctx.api.list_invoices,
                client_id=client["id"],
                page_size=100,
                sort="due_date",
            )
            candidates = [i for i in (page or {}).get("items", []) if is_open(i)]
        if not candidates:
            messages.show_info(parent, f"{client['name']} no tiene facturas con saldo pendiente.")
            return
        self.invoices = {i["id"]: i for i in candidates}

        self.add_row("Cliente", QLabel(client["name"]))
        self.add_row("Saldo a favor disponible", QLabel(format_money(self.available)))
        self.invoice = SearchCombo()
        self.invoice.set_items(
            [
                (
                    f"{i['invoice_number']} · vence {format_date(i['due_date'])} · "
                    f"saldo {format_money(i['balance'])}",
                    i["id"],
                )
                for i in candidates
            ],  # fmt: skip
            keep=False,
        )
        self.invoice.setEnabled(invoice is None)
        self.invoice.currentIndexChanged.connect(self._suggest_amount)
        self.amount = MoneyEdit()
        self.add_row("Factura *", self.invoice, "invoice_id")
        self.add_row("Importe a imputar *", self.amount, "amount")
        self._suggest_amount()
        self.ready = True

    def _suggest_amount(self) -> None:
        inv = self.invoices.get(self.invoice.value() or "")
        if inv:
            self.amount.set_value(min(self.available, to_decimal(inv["balance"])))

    def submit(self):
        invoice_id = self.invoice.value()
        if not invoice_id:
            raise FieldError("invoice_id", "Elegí una factura")
        amount: Decimal = self.money(self.amount, "amount")
        result = self.ctx.api.apply_credit(invoice_id, amount, self.idempotency_key)
        return result.data


class CreditsPage(BasePage):
    title = "Saldo a favor"

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)
        bar = self.toolbar()
        self.client = SearchCombo(empty_label="Todos los clientes")
        self.client.currentIndexChanged.connect(lambda _i: self.search_now())
        self.include_void = QCheckBox("Incluir anulados")
        self.include_void.toggled.connect(lambda _c: self.search_now())
        bar.addWidget(QLabel("Cliente"))
        bar.addWidget(self.client)
        bar.addWidget(self.include_void)
        bar.addStretch(1)

        self.summary = QLabel()
        self.summary.setStyleSheet("font-size: 14px; margin: 6px 0;")
        self.layout_.addWidget(self.summary)

        self.table = DataTable(
            [
                Column("Fecha", field("credit_date", format_date)),
                Column("Cliente", field("client_name")),
                Column("Origen", field("origin", lambda o: ORIGIN_LABELS.get(o, o))),
                Column("Importe", field("amount", format_money), align_right=True),
                Column("Medio", field("method", method_label)),
                Column("Referencia", field("reference")),
                Column(
                    "Estado",
                    lambda c: f"Anulado: {c['void_reason']}" if c["is_void"] else "Vigente",
                    color=lambda c: "#6e7781" if c["is_void"] else None,
                ),
            ]
        )
        self.layout_.addWidget(self.table, 1)
        self.pager = Pager(PAGE_SIZE)
        self.pager.changed.connect(lambda _p: self.refresh())
        self.layout_.addWidget(self.pager)

        actions = self.toolbar()
        self.on_account_btn = QPushButton("Cobro a cuenta")
        self.apply_btn = QPushButton("Imputar a factura")
        self.void_btn = QPushButton("Anular cobro a cuenta")
        self.void_btn.setVisible(ctx.api.is_admin)
        self.on_account_btn.clicked.connect(self.on_account)
        self.apply_btn.clicked.connect(self.apply)
        self.void_btn.clicked.connect(self.void_selected)
        for b in (self.on_account_btn, self.apply_btn, self.void_btn):
            actions.addWidget(b)
        actions.addStretch(1)
        self._clients_loaded = False

    def _selected_client(self, require: bool = True) -> dict | None:
        client_id = self.client.value()
        if client_id is None:
            if require:
                messages.show_info(self, "Elegí un cliente arriba.")
            return None
        clients = self.ctx.call(self, self.ctx.clients) or []
        return next((c for c in clients if c["id"] == client_id), None)

    def search_now(self) -> None:
        self.pager.reset()
        self.refresh()

    def refresh(self) -> None:
        if not self._clients_loaded or self.ctx._clients is None:
            items = self.ctx.call(self, self.ctx.client_items)
            if items is not None:
                self.client.blockSignals(True)
                self.client.set_items(items)
                self.client.blockSignals(False)
                self._clients_loaded = True
        client = self._selected_client(require=False)
        if client is not None:
            bal = self.ctx.call(self, self.ctx.api.client_credit, client["id"])
            if bal is not None:
                self.summary.setText(
                    f"<b>{client['name']}</b> · Acreditado {format_money(bal['credited'])} · "
                    f"Imputado {format_money(bal['applied'])} · "
                    f"<b>Disponible {format_money(bal['available'])}</b>"
                )
        else:
            self.summary.setText("Elegí un cliente para ver su saldo disponible.")
        page = self.ctx.call(
            self,
            self.ctx.api.list_credits,
            client_id=self.client.value(),
            include_void=self.include_void.isChecked(),
            page=self.pager.page,
            page_size=PAGE_SIZE,
        )
        if page is None:
            return
        self.table.set_rows(page["items"])
        self.pager.update_total(page["total"])

    def on_account(self) -> None:
        client = self._selected_client()
        if client is None:
            return
        if not client["is_active"]:
            messages.show_info(self, "No se registran cobros a cuenta de un cliente inactivo.")
            return
        if CreditOnAccountDialog(self.ctx, client, parent=self).exec():
            self.refresh()

    def apply(self) -> None:
        client = self._selected_client()
        if client is None:
            return
        dlg = ApplyCreditDialog(self.ctx, client, parent=self)
        if dlg.ready and dlg.exec():
            self.refresh()

    def void_selected(self) -> None:
        credit = self.table.selected()
        if credit is None:
            messages.show_info(self, "Seleccioná el cobro a cuenta a anular.")
            return
        if credit["origin"] != "a_cuenta":
            messages.show_info(
                self, "Es el excedente de un pago: para anularlo, anulá el pago que lo originó."
            )
            return
        if credit["is_void"]:
            messages.show_info(self, "Ese cobro ya está anulado.")
            return
        dlg = VoidDialog(
            self.ctx,
            f"Anular cobro a cuenta de {format_money(credit['amount'])}",
            lambda reason: self.ctx.api.void_credit(credit["id"], reason),
            parent=self,
        )
        if dlg.exec():
            self.refresh()
