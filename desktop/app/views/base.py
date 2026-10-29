"""Piezas comunes de las vistas: contexto de la app, página base y formulario base."""

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from desktop.app.core.config import AppConfig
from desktop.app.services.api import ApiClient, ApiError, SessionExpired
from desktop.app.widgets import messages
from desktop.app.widgets.common import FieldError, busy

ERROR_STYLE = "border: 1px solid #cf222e;"


class AppContext(QObject):
    """Estado compartido por todas las pantallas: API, configuración y clientes en caché."""

    # Emitida cuando la sesión venció y el usuario no quiso/pudo volver a ingresar.
    session_lost = Signal()

    def __init__(self, api: ApiClient, config: AppConfig) -> None:
        super().__init__()
        self.api = api
        self.config = config
        self._clients: list[dict] | None = None
        # La ventana principal reemplaza esto por el diálogo real de login.
        self.relogin_handler: Callable[[QWidget | None], bool] = lambda _parent: False

    # --- Caché de clientes para combos ---
    def clients(self, force: bool = False) -> list[dict]:
        if self._clients is None or force:
            self._clients = self.api.all_clients(is_active=None)
        return self._clients

    def invalidate_clients(self) -> None:
        self._clients = None

    def client_items(self, only_active: bool = False) -> list[tuple[str, str]]:
        rows = self.clients()
        return [(c["name"], c["id"]) for c in rows if c["is_active"] or not only_active]

    # --- Llamadas a la API con manejo uniforme de errores ---
    def relogin(self, parent: QWidget | None) -> bool:
        if self.relogin_handler(parent):
            return True
        self.session_lost.emit()
        return False

    def call(self, parent: QWidget | None, fn: Callable[..., Any], *args: Any, **kwargs: Any):
        """Ejecuta fn; ante error muestra el mensaje y devuelve None."""
        for attempt in (1, 2):
            try:
                with busy():
                    return fn(*args, **kwargs)
            except SessionExpired:
                if attempt == 1 and self.relogin(parent):
                    continue
                return None
            except ApiError as exc:
                messages.show_error(parent, exc.message)
                return None
        return None


class BasePage(QWidget):
    """Página de la ventana principal. refresh() se llama cada vez que se muestra."""

    title = ""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.layout_ = QVBoxLayout(self)
        heading = QLabel(self.title)
        heading.setStyleSheet("font-size: 18px; font-weight: 600; margin-bottom: 4px;")
        self.layout_.addWidget(heading)

    def toolbar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.layout_.addLayout(row)
        return row

    def refresh(self) -> None:  # pragma: no cover - lo implementa cada página
        pass


class FormDialog(QDialog):
    """Formulario modal: valida, llama a la API y resalta el campo con error.

    Las subclases agregan campos con add_row(...) e implementan submit(), que devuelve el
    resultado (se guarda en self.result_data y cierra) o None (queda abierto).
    """

    ok_text = "Guardar"

    def __init__(self, ctx: AppContext, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(440)
        self.result_data: Any = None
        self._fields: dict[str, QWidget] = {}

        self.form = QFormLayout()
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #cf222e;")
        self.error_label.hide()
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.ok_text)
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        self.buttons.accepted.connect(self.on_accept)
        self.buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addLayout(self.form)
        lay.addWidget(self.error_label)
        lay.addWidget(self.buttons)

    def add_row(self, label: str, widget: QWidget, field: str | None = None) -> QWidget:
        self.form.addRow(label, widget)
        if field:
            self._fields[field] = widget
        return widget

    @staticmethod
    def money(widget, field: str):
        """Lee un MoneyEdit; si el texto es inválido, error asociado al campo."""
        try:
            return widget.value()
        except ValueError as exc:
            raise FieldError(field, str(exc)) from exc

    def submit(self) -> Any:  # pragma: no cover - lo implementa cada formulario
        raise NotImplementedError

    def show_error(self, message: str, field: str | None = None) -> None:
        self.error_label.setText(message)
        self.error_label.show()
        widget = self._fields.get(field or "")
        if widget is not None:
            widget.setStyleSheet(ERROR_STYLE)
            widget.setFocus()

    def clear_errors(self) -> None:
        self.error_label.hide()
        for widget in self._fields.values():
            widget.setStyleSheet("")

    def on_accept(self) -> None:
        self.clear_errors()
        for attempt in (1, 2):
            try:
                with busy():
                    result = self.submit()
            except FieldError as exc:
                self.show_error(exc.message, exc.field)
                return
            except SessionExpired:
                if attempt == 1 and self.ctx.relogin(self):
                    continue
                self.reject()
                return
            except ApiError as exc:
                self.show_error(exc.message, exc.field)
                return
            except ValueError as exc:  # p. ej. importe mal escrito
                self.show_error(str(exc))
                return
            if result is not None:
                self.result_data = result
                self.accept()
            return
