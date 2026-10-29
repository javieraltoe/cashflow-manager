"""Configuración: perfil, cambio de contraseña, servidor y usuarios (solo administrador)."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desktop.app.core.config import save_config
from desktop.app.core.formatting import role_label
from desktop.app.services.api import ApiError, SessionExpired
from desktop.app.views.base import AppContext, BasePage, FormDialog
from desktop.app.widgets import messages
from desktop.app.widgets.common import ChoiceCombo, FieldError
from desktop.app.widgets.table import Column, DataTable, field

MIN_PASSWORD = 10
ROLE_CHOICES = [("Operador", "operator"), ("Administrador", "admin")]


def _password(widget: QLineEdit, field_name: str, required: bool = True) -> str | None:
    value = widget.text()
    if not value and not required:
        return None
    if len(value) < MIN_PASSWORD:
        raise FieldError(field_name, f"La contraseña debe tener al menos {MIN_PASSWORD} caracteres")
    return value


class UserDialog(FormDialog):
    def __init__(self, ctx: AppContext, user: dict | None = None, parent: QWidget | None = None):
        super().__init__(ctx, "Editar usuario" if user else "Nuevo usuario", parent)
        self.user = user
        self.email = QLineEdit((user or {}).get("email", ""))
        self.email.setEnabled(user is None)
        self.full_name = QLineEdit((user or {}).get("full_name", ""))
        self.role = ChoiceCombo(ROLE_CHOICES)
        self.role.set_value((user or {}).get("role", "operator"))
        self.active = QCheckBox("Usuario activo")
        self.active.setChecked((user or {}).get("is_active", True))
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.add_row("Email *", self.email, "email")
        self.add_row("Nombre *", self.full_name, "full_name")
        self.add_row("Rol *", self.role, "role")
        if user:
            self.add_row("", self.active, "is_active")
            self.password.setPlaceholderText("Dejar vacío para no cambiarla")
            self.add_row("Nueva contraseña", self.password, "password")
        else:
            self.add_row("Contraseña inicial *", self.password, "password")

    def submit(self):
        name = self.full_name.text().strip()
        if not name:
            raise FieldError("full_name", "El nombre es obligatorio")
        if self.user is None:
            email = self.email.text().strip()
            if "@" not in email:
                raise FieldError("email", "Ingresá un email válido")
            return self.ctx.api.create_user(
                {
                    "email": email,
                    "full_name": name,
                    "role": self.role.value(),
                    "password": _password(self.password, "password"),
                }
            )
        changes: dict = {}
        if name != self.user["full_name"]:
            changes["full_name"] = name
        if self.role.value() != self.user["role"]:
            changes["role"] = self.role.value()
        if self.active.isChecked() != self.user["is_active"]:
            changes["is_active"] = self.active.isChecked()
        if new := _password(self.password, "password", required=False):
            changes["password"] = new
        if not changes:
            return self.user
        return self.ctx.api.update_user(self.user["id"], changes)


class SettingsPage(BasePage):
    title = "Configuración"
    # La contraseña cambió: el servidor cerró todas las sesiones, hay que volver a ingresar.
    password_changed = Signal()

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)

        # --- Perfil ---
        profile = QGroupBox("Mi perfil")
        pf = QFormLayout(profile)
        self.p_name, self.p_email, self.p_role = QLabel(), QLabel(), QLabel()
        pf.addRow("Nombre", self.p_name)
        pf.addRow("Email", self.p_email)
        pf.addRow("Rol", self.p_role)
        self.layout_.addWidget(profile)

        # --- Contraseña ---
        pwd = QGroupBox("Cambiar contraseña")
        pw = QFormLayout(pwd)
        self.current_pwd, self.new_pwd, self.repeat_pwd = QLineEdit(), QLineEdit(), QLineEdit()
        for w in (self.current_pwd, self.new_pwd, self.repeat_pwd):
            w.setEchoMode(QLineEdit.EchoMode.Password)
        self.pwd_btn = QPushButton("Cambiar contraseña")
        self.pwd_btn.clicked.connect(self.change_password)
        pw.addRow("Contraseña actual", self.current_pwd)
        pw.addRow(f"Nueva (mín. {MIN_PASSWORD})", self.new_pwd)
        pw.addRow("Repetir nueva", self.repeat_pwd)
        pw.addRow("", self.pwd_btn)
        self.layout_.addWidget(pwd)

        # --- Servidor ---
        server = QGroupBox("Conexión")
        sf = QFormLayout(server)
        self.api_url = QLabel()
        self.api_url.setToolTip("Se cambia desde la pantalla de inicio de sesión")
        self.dashboard_url = QLineEdit()
        save_btn = QPushButton("Guardar")
        save_btn.clicked.connect(self.save_dashboard_url)
        sf.addRow("Servidor (API)", self.api_url)
        sf.addRow("Dashboard web", self.dashboard_url)
        sf.addRow("", save_btn)
        self.layout_.addWidget(server)

        # --- Usuarios (admin) ---
        self.users_box = QGroupBox("Usuarios")
        ub = QVBoxLayout(self.users_box)
        self.users = DataTable(
            [
                Column("Nombre", field("full_name")),
                Column("Email", field("email")),
                Column("Rol", field("role", role_label)),
                Column("Estado", lambda u: "Activo" if u["is_active"] else "Inactivo"),
            ]
        )
        self.users.doubleClicked.connect(self.edit_user)
        ub.addWidget(self.users)
        row = QHBoxLayout()
        self.new_user_btn = QPushButton("Nuevo usuario")
        self.edit_user_btn = QPushButton("Editar")
        self.new_user_btn.clicked.connect(self.create_user)
        self.edit_user_btn.clicked.connect(self.edit_user)
        row.addWidget(self.new_user_btn)
        row.addWidget(self.edit_user_btn)
        row.addStretch(1)
        ub.addLayout(row)
        self.layout_.addWidget(self.users_box, 1)
        self.layout_.addStretch(0)

    def refresh(self) -> None:
        user = self.ctx.api.user or {}
        self.p_name.setText(user.get("full_name", ""))
        self.p_email.setText(user.get("email", ""))
        self.p_role.setText(role_label(user.get("role")))
        self.api_url.setText(self.ctx.config.api_url)
        self.dashboard_url.setText(self.ctx.config.dashboard_url)
        self.users_box.setVisible(self.ctx.api.is_admin)
        if self.ctx.api.is_admin:
            page = self.ctx.call(self, self.ctx.api.list_users)
            if page is not None:
                self.users.set_rows(page["items"])

    def change_password(self) -> None:
        current, new, repeat = (
            self.current_pwd.text(),
            self.new_pwd.text(),
            self.repeat_pwd.text(),
        )
        if not current:
            messages.show_error(self, "Ingresá tu contraseña actual.")
            return
        if len(new) < MIN_PASSWORD:
            messages.show_error(
                self, f"La nueva contraseña debe tener al menos {MIN_PASSWORD} caracteres."
            )
            return
        if new != repeat:
            messages.show_error(self, "Las contraseñas nuevas no coinciden.")
            return
        try:
            self.ctx.api.change_password(current, new)
        except SessionExpired:
            self.ctx.relogin(self)
            return
        except ApiError as exc:
            messages.show_error(self, exc.message)
            return
        finally:
            for w in (self.current_pwd, self.new_pwd, self.repeat_pwd):
                w.clear()
        messages.show_info(self, "Contraseña cambiada. Por seguridad, volvé a ingresar.")
        self.password_changed.emit()

    def save_dashboard_url(self) -> None:
        url = self.dashboard_url.text().strip()
        if not url.startswith(("http://", "https://")):
            messages.show_error(self, "La dirección debe empezar con http:// o https://")
            return
        self.ctx.config.dashboard_url = url
        try:
            save_config(self.ctx.config)
        except OSError as exc:
            messages.show_error(self, f"No se pudo guardar la configuración: {exc}")
            return
        messages.show_info(self, "Dirección del dashboard guardada.")

    def create_user(self) -> None:
        if UserDialog(self.ctx, parent=self).exec():
            self.refresh()

    def edit_user(self) -> None:
        user = self.users.selected()
        if user is None:
            messages.show_info(self, "Seleccioná un usuario.")
            return
        if UserDialog(self.ctx, user, parent=self).exec():
            self.refresh()
