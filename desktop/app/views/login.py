"""Inicio de sesión: servidor, email y contraseña."""

import contextlib

from PySide6.QtWidgets import QLabel, QLineEdit, QWidget

from desktop.app.core.config import is_insecure_remote, normalize_api_url, save_config
from desktop.app.views.base import AppContext, FormDialog
from desktop.app.widgets.common import FieldError


class LoginDialog(FormDialog):
    ok_text = "Ingresar"

    def __init__(
        self, ctx: AppContext, parent: QWidget | None = None, relogin: bool = False
    ) -> None:
        super().__init__(ctx, "CashFlow Manager · Iniciar sesión", parent)
        self.relogin = relogin
        if relogin:
            note = QLabel("Tu sesión venció. Ingresá de nuevo para continuar.")
            note.setWordWrap(True)
            self.form.addRow(note)

        self.server = QLineEdit(ctx.config.api_url)
        self.server.setPlaceholderText("https://cobranzas.miempresa.com")
        self.server.setEnabled(not relogin)
        self.server.textChanged.connect(self._update_warning)
        self.email = QLineEdit(ctx.config.last_email)
        self.email.setPlaceholderText("usuario@empresa.com.ar")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.warning = QLabel(
            "⚠ Conexión sin cifrar: usá una dirección https:// para servidores en Internet."
        )
        self.warning.setWordWrap(True)
        self.warning.setStyleSheet("color: #9a6700;")

        self.add_row("Servidor", self.server, "server")
        self.add_row("Email", self.email, "email")
        self.add_row("Contraseña", self.password, "password")
        self.form.addRow(self.warning)
        self._update_warning()
        (self.password if ctx.config.last_email else self.email).setFocus()

    def _update_warning(self) -> None:
        try:
            insecure = is_insecure_remote(normalize_api_url(self.server.text()))
        except ValueError:
            insecure = False
        self.warning.setVisible(insecure)

    def submit(self):
        try:
            url = normalize_api_url(self.server.text())
        except ValueError as exc:
            raise FieldError("server", str(exc)) from exc
        email = self.email.text().strip()
        if not email:
            raise FieldError("email", "Ingresá tu email")
        if not self.password.text():
            raise FieldError("password", "Ingresá tu contraseña")

        self.ctx.api.base_url = url
        try:
            user = self.ctx.api.login(email, self.password.text())
        finally:
            self.password.clear()
        self.ctx.config.api_url = url
        self.ctx.config.last_email = email.lower()
        with contextlib.suppress(OSError):  # no poder guardar preferencias no impide trabajar
            save_config(self.ctx.config)
        return user
