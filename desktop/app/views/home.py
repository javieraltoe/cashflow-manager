"""Inicio: conteos esenciales, próximos vencimientos y acceso al dashboard web."""

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from desktop.app.core.formatting import format_date, format_money, status_label
from desktop.app.core.summary import load_home_summary
from desktop.app.views.base import AppContext, BasePage
from desktop.app.widgets import messages
from desktop.app.widgets.table import Column, DataTable, field, status_color


class StatCard(QFrame):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.value = QLabel("—")
        self.value.setStyleSheet("font-size: 24px; font-weight: 600;")
        caption = QLabel(title)
        caption.setStyleSheet("color: #57606a;")
        self.detail = QLabel()
        self.detail.setStyleSheet("color: #57606a;")
        lay = QVBoxLayout(self)
        lay.addWidget(caption)
        lay.addWidget(self.value)
        lay.addWidget(self.detail)

    def set_value(self, value: str, detail: str = "") -> None:
        self.value.setText(value)
        self.detail.setText(detail)


def invoices_label(count: int) -> str:
    return "1 factura" if count == 1 else f"{count:,} facturas".replace(",", ".")


class HomePage(BasePage):
    title = "Inicio"
    # Pide a la ventana principal abrir el detalle de una factura (por id).
    open_invoice = Signal(str)

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)
        cards = QGridLayout()
        self.receivable = StatCard("Saldo total por cobrar")
        self.overdue = StatCard("Saldo vencido")
        self.due_soon = StatCard("Vence en los próximos 7 días")
        for i, card in enumerate((self.receivable, self.overdue, self.due_soon)):
            cards.addWidget(card, 0, i)
        self.layout_.addLayout(cards)

        self.layout_.addWidget(QLabel("Próximos vencimientos (7 días)"))
        self.table = DataTable(
            [
                Column("Vence", field("due_date", format_date)),
                Column("Factura", field("invoice_number")),
                Column("Cliente", field("client_name")),
                Column("Saldo", field("balance", format_money), align_right=True),
                Column("Estado", field("status", status_label), color=status_color()),
            ]
        )
        self.table.doubleClicked.connect(self._open_selected)
        self.layout_.addWidget(self.table, 1)

        bar = self.toolbar()
        refresh = QPushButton("Actualizar")
        refresh.clicked.connect(self.refresh)
        dashboard = QPushButton("Abrir dashboard web")
        dashboard.clicked.connect(self.open_dashboard)
        bar.addWidget(refresh)
        bar.addStretch(1)
        bar.addWidget(QLabel("Saldos y cobranzas en detalle:"))
        bar.addWidget(dashboard)

    def refresh(self) -> None:
        summary = self.ctx.call(self, load_home_summary, self.ctx.api)
        if summary is None:
            return
        self.receivable.set_value(format_money(summary.total_receivable), "a hoy")
        self.overdue.set_value(
            format_money(summary.overdue_balance), invoices_label(summary.overdue_count)
        )
        self.due_soon.set_value(
            format_money(summary.due_soon_balance), invoices_label(summary.due_soon_count)
        )
        self.table.set_rows(summary.upcoming)

    def open_dashboard(self) -> None:
        url = QUrl(self.ctx.config.dashboard_url)
        if not url.isValid() or not QDesktopServices.openUrl(url):
            messages.show_error(
                self, "No se pudo abrir el dashboard. Revisá la dirección en Configuración."
            )

    def _open_selected(self) -> None:
        row = self.table.selected()
        if row:
            self.open_invoice.emit(row["id"])
