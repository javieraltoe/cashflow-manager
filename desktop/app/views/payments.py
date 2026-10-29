"""Pagos: registro con confirmación de excedente, anulación con motivo y listado (HU04/HU09)."""

from collections.abc import Callable

from PySide6.QtWidgets import QCheckBox, QLabel, QLineEdit, QPushButton, QWidget

from desktop.app.core.formatting import (
    METHOD_LABELS,
    PAYMENT_METHODS,
    format_date,
    format_money,
    method_label,
    status_label,
    to_decimal,
    today_local,
)
from desktop.app.services.api import ApiError, new_idempotency_key
from desktop.app.views.base import AppContext, BasePage, FormDialog
from desktop.app.widgets import messages
from desktop.app.widgets.common import (
    ChoiceCombo,
    DateEdit,
    FieldError,
    MoneyEdit,
    OptionalDateEdit,
    Pager,
    SearchCombo,
)
from desktop.app.widgets.table import Column, DataTable, field

PAGE_SIZE = 50
MIN_REASON = 3


def method_choices() -> list[tuple[str, str]]:
    return [(METHOD_LABELS[m], m) for m in PAYMENT_METHODS]


class PaymentDialog(FormDialog):
    """Registrar un cobro sobre una factura.

    La Idempotency-Key se genera al abrir el formulario y se reutiliza en cada intento:
    un doble clic o un reintento tras un corte de red no duplica el cobro.
    """

    ok_text = "Registrar pago"

    def __init__(self, ctx: AppContext, invoice: dict, parent: QWidget | None = None):
        super().__init__(ctx, "Registrar pago", parent)
        self.invoice = invoice
        self.idempotency_key = new_idempotency_key()
        self.replayed = False
        today = today_local()

        self.add_row("Factura", QLabel(f"{invoice['invoice_number']} · {invoice['client_name']}"))
        self.add_row("Saldo pendiente", QLabel(format_money(invoice["balance"])))
        self.amount = MoneyEdit()
        self.amount.set_value(invoice["balance"])
        self.method = ChoiceCombo(method_choices())
        self.date = DateEdit(today)
        self.date.setMaximumDate(self.date.date())  # no se registran cobros a futuro
        self.reference = QLineEdit()
        self.reference.setPlaceholderText("Nº de transferencia, cheque…")
        self.add_row("Importe recibido *", self.amount, "amount")
        self.add_row("Medio de pago *", self.method, "method")
        self.add_row("Fecha de recepción *", self.date, "payment_date")
        self.add_row("Referencia", self.reference, "reference")

    def submit(self):
        data = {
            "invoice_id": self.invoice["id"],
            "amount": self.money(self.amount, "amount"),
            "method": self.method.value(),
            "payment_date": self.date.value(),
            "reference": self.reference.text().strip() or None,
        }
        try:
            result = self.ctx.api.create_payment(data, self.idempotency_key)
        except ApiError as exc:
            if exc.code != "amount_exceeds_balance":
                raise
            excess = data["amount"] - to_decimal(self.invoice["balance"])
            saldo = format_money(self.invoice["balance"])
            question = (
                f"El importe supera el saldo de la factura ({saldo}).\n\n"
                f"¿Registrar el excedente de {format_money(excess)} como saldo a favor "
                f"de {self.invoice['client_name']}?"
            )
            if not messages.ask_yes_no(self, question):
                raise FieldError(
                    "amount", "Corregí el importe o confirmá el saldo a favor."
                ) from exc
            result = self.ctx.api.create_payment(
                data | {"allow_credit": True}, self.idempotency_key
            )
        self.replayed = result.replayed
        if result.replayed:
            messages.show_info(self, "Este pago ya estaba registrado; no se duplicó.")
        return result.data


class VoidDialog(FormDialog):
    """Pide el motivo y ejecuta la anulación recibida (pago o cobro a cuenta)."""

    ok_text = "Anular"

    def __init__(
        self,
        ctx: AppContext,
        title: str,
        action: Callable[[str], dict],
        parent: QWidget | None = None,
    ):
        super().__init__(ctx, title, parent)
        self.action = action
        note = QLabel("La anulación no se puede revertir y queda registrada en la auditoría.")
        note.setWordWrap(True)
        self.form.addRow(note)
        self.reason = QLineEdit()
        self.reason.setPlaceholderText("Ej.: cheque rechazado")
        self.add_row("Motivo *", self.reason, "reason")

    def submit(self):
        reason = self.reason.text().strip()
        if len(reason) < MIN_REASON:
            raise FieldError("reason", f"Indicá el motivo (mínimo {MIN_REASON} caracteres)")
        return self.action(reason)


class PaymentsPage(BasePage):
    title = "Pagos"

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)
        bar = self.toolbar()
        self.client = SearchCombo(empty_label="Todos los clientes")
        self.method = ChoiceCombo(
            [("Todos los medios", None)] + [(v, k) for k, v in METHOD_LABELS.items()]
        )
        self.date_from = OptionalDateEdit("Desde")
        self.date_from.set_value(today_local().replace(day=1))  # mes en curso
        self.date_to = OptionalDateEdit("hasta")
        self.include_void = QCheckBox("Incluir anulados")
        search_btn = QPushButton("Buscar")
        search_btn.clicked.connect(self.search_now)
        for w in (self.client, self.method, self.date_from, self.date_to, self.include_void):
            bar.addWidget(w)
        bar.addWidget(search_btn)

        self.table = DataTable(
            [
                Column("Fecha", field("payment_date", format_date)),
                Column("Factura", field("invoice_number")),
                Column("Cliente", field("client_name")),
                Column("Imputado", field("amount", format_money), align_right=True),
                Column("Excedente", field("credit_amount", format_money), align_right=True),
                Column("Medio", field("method", method_label)),
                Column("Referencia", field("reference")),
                Column("Factura (estado)", field("invoice_status", status_label)),
                Column(
                    "Estado",
                    lambda p: f"Anulado: {p['void_reason']}" if p["is_void"] else "Vigente",
                    color=lambda p: "#6e7781" if p["is_void"] else None,
                ),
            ]
        )
        self.layout_.addWidget(self.table, 1)
        self.pager = Pager(PAGE_SIZE)
        self.pager.changed.connect(lambda _p: self.refresh())
        self.layout_.addWidget(self.pager)

        actions = self.toolbar()
        self.void_btn = QPushButton("Anular pago")
        self.void_btn.setVisible(ctx.api.is_admin)
        self.void_btn.clicked.connect(self.void_selected)
        actions.addWidget(self.void_btn)
        actions.addStretch(1)
        self._clients_loaded = False

    def search_now(self) -> None:
        self.pager.reset()
        self.refresh()

    def refresh(self) -> None:
        if not self._clients_loaded or self.ctx._clients is None:
            items = self.ctx.call(self, self.ctx.client_items)
            if items is not None:
                self.client.set_items(items)
                self._clients_loaded = True
        page = self.ctx.call(
            self,
            self.ctx.api.list_payments,
            client_id=self.client.value(),
            method=self.method.value(),
            date_from=self.date_from.value(),
            date_to=self.date_to.value(),
            include_void=self.include_void.isChecked(),
            page=self.pager.page,
            page_size=PAGE_SIZE,
        )
        if page is None:
            return
        self.table.set_rows(page["items"])
        self.pager.update_total(page["total"])

    def void_selected(self) -> None:
        payment = self.table.selected()
        if payment is None:
            messages.show_info(self, "Seleccioná el pago a anular.")
            return
        if payment["is_void"]:
            messages.show_info(self, "Ese pago ya está anulado.")
            return
        amount = format_money(payment["amount"])
        title = f"Anular pago de {amount} · factura {payment['invoice_number']}"
        dlg = VoidDialog(
            self.ctx,
            title,
            lambda reason: self.ctx.api.void_payment(payment["id"], reason),
            parent=self,
        )
        if dlg.exec():
            self.refresh()
