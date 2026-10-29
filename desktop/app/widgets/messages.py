"""Mensajes al usuario. Centralizados para poder reemplazarlos en los tests.

Las vistas SIEMPRE los llaman como `messages.show_error(...)` (no con from-import),
así un test puede sustituirlos sin abrir cuadros de diálogo modales.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

APP_TITLE = "CashFlow Manager"


@contextmanager
def _normal_cursor() -> Iterator[None]:
    """Quita el cursor de espera mientras el usuario lee el mensaje."""
    removed = 0
    while QApplication.overrideCursor() is not None:
        QApplication.restoreOverrideCursor()
        removed += 1
    try:
        yield
    finally:
        for _ in range(removed):
            QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))


def show_error(parent: QWidget | None, text: str, title: str = APP_TITLE) -> None:
    with _normal_cursor():
        QMessageBox.warning(parent, title, text)


def show_info(parent: QWidget | None, text: str, title: str = APP_TITLE) -> None:
    with _normal_cursor():
        QMessageBox.information(parent, title, text)


def ask_yes_no(parent: QWidget | None, text: str, title: str = APP_TITLE) -> bool:
    with _normal_cursor():
        answer = QMessageBox.question(
            parent,
            title,
            text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
    return answer == QMessageBox.StandardButton.Yes
