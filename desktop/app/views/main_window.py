"""Ventana principal: menú lateral, páginas y sesión."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from desktop.app import __version__
from desktop.app.core.config import is_insecure_remote
from desktop.app.core.formatting import role_label
from desktop.app.views.base import AppContext, BasePage
from desktop.app.views.clients import ClientsPage
from desktop.app.views.credits import CreditsPage
from desktop.app.views.home import HomePage
from desktop.app.views.imports import ImportPage
from desktop.app.views.invoices import InvoicesPage
from desktop.app.views.login import LoginDialog
from desktop.app.views.payments import PaymentsPage
from desktop.app.views.settings import SettingsPage


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        ctx.relogin_handler = self._relogin
        self.setWindowTitle(f"CashFlow Manager {__version__}")
        self.resize(1200, 760)

        # --- Encabezado ---
        self.user_label = QLabel()
        logout = QPushButton("Cerrar sesión")
        logout.clicked.connect(self.logout)
        header = QHBoxLayout()
        title = QLabel("CashFlow Manager")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.user_label)
        header.addWidget(logout)

        # --- Páginas ---
        self.home = HomePage(ctx)
        self.clients = ClientsPage(ctx)
        self.invoices = InvoicesPage(ctx)
        self.payments = PaymentsPage(ctx)
        self.credits = CreditsPage(ctx)
        self.imports = ImportPage(ctx)
        self.settings = SettingsPage(ctx)
        self.pages: list[BasePage] = [
            self.home,
            self.clients,
            self.invoices,
            self.payments,
            self.credits,
            self.imports,
            self.settings,
        ]
        self.stack = QStackedWidget()
        self.nav = QListWidget()
        self.nav.setFixedWidth(170)
        for page in self.pages:
            self.stack.addWidget(page)
            self.nav.addItem(page.title)
        self.nav.currentRowChanged.connect(self._show_page)
        self.home.open_invoice.connect(self.invoices.open_invoice)
        self.settings.password_changed.connect(self.logout)

        body = QHBoxLayout()
        body.addWidget(self.nav)
        body.addWidget(self.stack, 1)
        root = QVBoxLayout()
        root.addLayout(header)
        root.addLayout(body, 1)
        container = QWidget()
        container.setLayout(root)
        self.setCentralWidget(container)

        self.update_session_info()
        self.nav.setCurrentRow(0)

    def _show_page(self, row: int) -> None:
        if 0 <= row < len(self.pages):
            self.stack.setCurrentIndex(row)
            self.pages[row].refresh()

    def update_session_info(self) -> None:
        user = self.ctx.api.user or {}
        self.user_label.setText(f"{user.get('full_name', '')} · {role_label(user.get('role'))}")
        insecure = is_insecure_remote(self.ctx.config.api_url)
        msg = f"Servidor: {self.ctx.config.api_url}"
        if insecure:
            msg += "  ·  ⚠ Conexión sin cifrar"
        self.statusBar().showMessage(msg)
        # Botones de administrador según el rol actual
        is_admin = self.ctx.api.is_admin
        self.invoices.void_btn.setVisible(is_admin)
        self.payments.void_btn.setVisible(is_admin)
        self.credits.void_btn.setVisible(is_admin)

    def _relogin(self, parent: QWidget | None) -> bool:
        dlg = LoginDialog(self.ctx, parent or self, relogin=True)
        ok = bool(dlg.exec())
        if ok:
            self.update_session_info()
        return ok

    def logout(self) -> None:
        self.ctx.api.logout()
        self.hide()
        dlg = LoginDialog(self.ctx)
        if dlg.exec():
            self.ctx.invalidate_clients()
            self.update_session_info()
            self.nav.setCurrentRow(0)
            self.home.refresh()
            self.show()
        else:
            self.close()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - API de Qt
        # F5 actualiza la página visible
        if event.key() == Qt.Key.Key_F5:
            self.pages[self.stack.currentIndex()].refresh()
        else:
            super().keyPressEvent(event)
