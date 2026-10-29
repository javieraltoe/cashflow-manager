"""Facturas: listado con filtros, alta/edición, anulación y detalle con sus pagos (HU03/HU05)."""

from datetime import timedelta

from PySide6.QtWidgets import (
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from desktop.app.core.formatting import (
    STATUS_LABELS,
    format_date,
    format_money,
    method_label,
    parse_api_date,
    status_label,
    to_decimal,
    today_local,
)
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
from desktop.app.widgets.table import Column, DataTable, field, status_color

PAGE_SIZE = 50
DEFAULT_TERM_DAYS = 30

INVOICE_COLUMNS = [
    Column("Número", field("invoice_number")),
    Column("Cliente", field("client_name")),
    Column("Emisión", field("issue_date", format_date)),
    Column("Vencimiento", field("due_date", format_date)),
    Column("Importe", field("amount", format_money), align_right=True),
    Column("Cobrado", field("paid_amount", format_money), align_right=True),
    Column("Saldo", field("balance", format_money), align_right=True),
    Column("Estado", field("status", status_label), color=status_color()),
    Column("Mora (días)", lambda r: r["days_overdue"] or "", align_right=True),
]


def is_open(invoice: dict) -> bool:
    return not invoice["is_void"] and invoice["status"] != "PAGADA"


class InvoiceDialog(FormDialog):
    def __init__(self, ctx: AppContext, invoice: dict | None = None, parent: QWidget | None = None):
        super().__init__(ctx, "Editar factura" if invoice else "Nueva factura", parent)
        self.invoice = invoice
        today = today_local()
        self.client = SearchCombo()
        items = ctx.call(parent, ctx.client_items, not invoice) or []
        self.client.set_items(items, keep=False)
        self.number = QLineEdit()
        self.number.setPlaceholderText("F-0001")
        self.issue = DateEdit(today)
        self.due = DateEdit(today + timedelta(days=DEFAULT_TERM_DAYS))
        self.amount = MoneyEdit()
        self.description = QLineEdit()
        if invoice:
            self.client.set_value(invoice["client_id"])
            self.client.setEnabled(False)  # una factura no cambia de cliente
            self.number.setText(invoice["invoice_number"])
            self.issue.set_value(parse_api_date(invoice["issue_date"]))
            self.due.set_value(parse_api_date(invoice["due_date"]))
            self.amount.set_value(invoice["amount"])
            self.description.setText(invoice.get("description") or "")
        self.add_row("Cliente *", self.client, "client_id")
        self.add_row("Número *", self.number, "invoice_number")
        self.add_row("Emisión *", self.issue, "issue_date")
        self.add_row("Vencimiento *", self.due, "due_date")
        self.add_row("Importe (ARS) *", self.amount, "amount")
        self.add_row("Descripción", self.description, "description")

    def submit(self):
        client_id = self.client.value()
        if not client_id:
            raise FieldError("client_id", "Elegí un cliente de la lista")
        number = self.number.text().strip()
        if not number:
            raise FieldError("invoice_number", "El número es obligatorio")
        issue, due = self.issue.value(), self.due.value()
        if due < issue:
            raise FieldError("due_date", "El vencimiento no puede ser anterior a la emisión")
        data = {
            "invoice_number": number,
            "issue_date": issue,
            "due_date": due,
            "amount": self.money(self.amount, "amount"),
            "description": self.description.text().strip() or None,
        }
        if self.invoice is None:
            return self.ctx.api.create_invoice(data | {"client_id": client_id})
        old = self.invoice
        before = {
            "invoice_number": old["invoice_number"],
            "issue_date": parse_api_date(old["issue_date"]),
            "due_date": parse_api_date(old["due_date"]),
            "amount": to_decimal(old["amount"]),
            "description": old.get("description") or None,
        }
        changes = {k: v for k, v in data.items() if v != before[k]}
        if not changes:
            return old
        return self.ctx.api.update_invoice(old["id"], changes)


class InvoiceDetailDialog(FormDialog):
    """Detalle de una factura con su historial de pagos y las acciones de cobranza."""

    ok_text = "Cerrar"

    def __init__(self, ctx: AppContext, invoice_id: str, parent: QWidget | None = None):
        super().__init__(ctx, "Detalle de factura", parent)
        self.setMinimumWidth(820)
        self.invoice_id = invoice_id
        self.invoice: dict | None = None
        self.changed = False
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).hide()

        self.info = QGridLayout()
        self.labels: dict[str, QLabel] = {}
        for i, (key, title) in enumerate(
            [
                ("invoice_number", "Factura"),
                ("client_name", "Cliente"),
                ("issue_date", "Emisión"),
                ("due_date", "Vencimiento"),
                ("amount", "Importe"),
                ("paid_amount", "Cobrado"),
                ("balance", "Saldo"),
                ("status", "Estado"),
            ]
        ):
            value = QLabel()
            value.setStyleSheet("font-weight: 600;")
            self.labels[key] = value
            self.info.addWidget(QLabel(title), i // 4 * 2, i % 4)
            self.info.addWidget(value, i // 4 * 2 + 1, i % 4)
        self.form.addRow(self.info)

        self.form.addRow(QLabel("Pagos"))
        self.payments = DataTable(
            [
                Column("Fecha", field("payment_date", format_date)),
                Column("Imputado", field("amount", format_money), align_right=True),
                Column("Excedente", field("credit_amount", format_money), align_right=True),
                Column("Medio", field("method", method_label)),
                Column("Referencia", field("reference")),
                Column(
                    "Estado",
                    lambda p: f"Anulado: {p['void_reason']}" if p["is_void"] else "Vigente",
                    color=lambda p: "#6e7781" if p["is_void"] else None,
                ),
            ]
        )
        self.payments.setMinimumHeight(200)
        self.form.addRow(self.payments)

        actions = QHBoxLayout()
        self.pay_btn = QPushButton("Registrar pago")
        self.credit_btn = QPushButton("Imputar saldo a favor")
        self.void_btn = QPushButton("Anular pago")
        self.void_btn.setVisible(ctx.api.is_admin)
        self.pay_btn.clicked.connect(self.register_payment)
        self.credit_btn.clicked.connect(self.apply_credit)
        self.void_btn.clicked.connect(self.void_payment)
        for b in (self.pay_btn, self.credit_btn, self.void_btn):
            actions.addWidget(b)
        actions.addStretch(1)
        self.form.addRow(actions)
        self.reload()

    def reload(self) -> None:
        inv = self.ctx.call(self, self.ctx.api.get_invoice, self.invoice_id)
        if inv is None:
            return
        self.invoice = inv
        fmt = {
            "issue_date": format_date,
            "due_date": format_date,
            "amount": format_money,
            "paid_amount": format_money,
            "balance": format_money,
            "status": status_label,
        }
        for key, label in self.labels.items():
            label.setText(str(fmt.get(key, str)(inv[key])))
        if inv["days_overdue"]:
            self.labels["status"].setText(f"Vencida ({inv['days_overdue']} días)")
        open_ = is_open(inv)
        self.pay_btn.setEnabled(open_)
        self.credit_btn.setEnabled(open_)
        page = self.ctx.call(
            self, self.ctx.api.list_payments, invoice_id=self.invoice_id, include_void=True,
            page_size=100, sort="payment_date",
        )  # fmt: skip
        if page is not None:
            self.payments.set_rows(page["items"])

    def submit(self):
        return True  # "Cerrar"

    def register_payment(self) -> None:
        from desktop.app.views.payments import PaymentDialog

        if self.invoice and PaymentDialog(self.ctx, self.invoice, parent=self).exec():
            self.changed = True
            self.reload()

    def apply_credit(self) -> None:
        from desktop.app.views.credits import ApplyCreditDialog

        if not self.invoice:
            return
        dlg = ApplyCreditDialog(
            self.ctx,
            {"id": self.invoice["client_id"], "name": self.invoice["client_name"]},
            invoice=self.invoice,
            parent=self,
        )
        if dlg.ready and dlg.exec():
            self.changed = True
            self.reload()

    def void_payment(self) -> None:
        from desktop.app.views.payments import VoidDialog

        payment = self.payments.selected()
        if payment is None:
            messages.show_info(self, "Seleccioná el pago a anular.")
            return
        if payment["is_void"]:
            messages.show_info(self, "Ese pago ya está anulado.")
            return
        dlg = VoidDialog(
            self.ctx,
            f"Anular pago de {format_money(payment['amount'])}",
            lambda reason: self.ctx.api.void_payment(payment["id"], reason),
            parent=self,
        )
        if dlg.exec():
            self.changed = True
            self.reload()


class InvoicesPage(BasePage):
    title = "Facturas"

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)
        bar = self.toolbar()
        self.client = SearchCombo(empty_label="Todos los clientes")
        self.status = ChoiceCombo(
            [("Todos los estados", None)] + [(v, k) for k, v in STATUS_LABELS.items()]
        )
        self.due_from = OptionalDateEdit("Vence desde")
        self.due_to = OptionalDateEdit("hasta")
        self.number = QLineEdit()
        self.number.setPlaceholderText("Número…")
        self.number.returnPressed.connect(self.search_now)
        search_btn = QPushButton("Buscar")
        search_btn.clicked.connect(self.search_now)
        for w in (self.client, self.status, self.due_from, self.due_to, self.number, search_btn):
            bar.addWidget(w)

        self.table = DataTable(INVOICE_COLUMNS)
        self.table.doubleClicked.connect(self.open_selected)
        self.layout_.addWidget(self.table, 1)
        self.pager = Pager(PAGE_SIZE)
        self.pager.changed.connect(lambda _p: self.refresh())
        self.layout_.addWidget(self.pager)

        actions = self.toolbar()
        self.new_btn = QPushButton("Nueva factura")
        self.edit_btn = QPushButton("Editar")
        self.detail_btn = QPushButton("Ver detalle y pagos")
        self.pay_btn = QPushButton("Registrar pago")
        self.void_btn = QPushButton("Anular factura")
        self.void_btn.setVisible(ctx.api.is_admin)
        self.new_btn.clicked.connect(self.create)
        self.edit_btn.clicked.connect(self.edit_selected)
        self.detail_btn.clicked.connect(self.open_selected)
        self.pay_btn.clicked.connect(self.pay_selected)
        self.void_btn.clicked.connect(self.void_selected)
        for b in (self.new_btn, self.edit_btn, self.detail_btn, self.pay_btn, self.void_btn):
            actions.addWidget(b)
        actions.addStretch(1)
        self._clients_loaded = False

    def _load_clients(self) -> None:
        items = self.ctx.call(self, self.ctx.client_items)
        if items is not None:
            self.client.set_items(items)
            self._clients_loaded = True

    def search_now(self) -> None:
        self.pager.reset()
        self.refresh()

    def refresh(self) -> None:
        if not self._clients_loaded or self.ctx._clients is None:
            self._load_clients()
        status = self.status.value()
        page = self.ctx.call(
            self,
            self.ctx.api.list_invoices,
            client_id=self.client.value(),
            status=status,
            due_from=self.due_from.value(),
            due_to=self.due_to.value(),
            q=self.number.text().strip() or None,
            include_void=status == "ANULADA",
            page=self.pager.page,
            page_size=PAGE_SIZE,
            sort="due_date",
        )
        if page is None:
            return
        self.table.set_rows(page["items"])
        self.pager.update_total(page["total"])

    def _selected(self) -> dict | None:
        inv = self.table.selected()
        if inv is None:
            messages.show_info(self, "Seleccioná una factura de la lista.")
        return inv

    def create(self) -> None:
        if not self.ctx.call(self, self.ctx.client_items, True):
            messages.show_info(self, "Primero cargá un cliente activo.")
            return
        if InvoiceDialog(self.ctx, parent=self).exec():
            self.refresh()

    def edit_selected(self) -> None:
        inv = self._selected()
        if inv is None:
            return
        if inv["is_void"]:
            messages.show_info(self, "La factura está anulada y no se puede modificar.")
            return
        if InvoiceDialog(self.ctx, inv, parent=self).exec():
            self.refresh()

    def open_selected(self) -> None:
        inv = self._selected()
        if inv is not None:
            self.open_invoice(inv["id"])

    def open_invoice(self, invoice_id: str) -> None:
        dlg = InvoiceDetailDialog(self.ctx, invoice_id, parent=self)
        dlg.exec()
        if dlg.changed:
            self.refresh()

    def pay_selected(self) -> None:
        from desktop.app.views.payments import PaymentDialog

        inv = self._selected()
        if inv is None:
            return
        if not is_open(inv):
            messages.show_info(self, "La factura no tiene saldo pendiente.")
            return
        if PaymentDialog(self.ctx, inv, parent=self).exec():
            self.refresh()

    def void_selected(self) -> None:
        inv = self._selected()
        if inv is None or inv["is_void"]:
            return
        text = (
            f"¿Anular la factura {inv['invoice_number']} de {inv['client_name']}?\n"
            "La anulación no se puede revertir."
        )
        if messages.ask_yes_no(self, text) and self.ctx.call(
            self, self.ctx.api.void_invoice, inv["id"]
        ):
            self.refresh()
