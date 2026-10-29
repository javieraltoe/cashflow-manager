"""Widgets reutilizables: cursor de espera, montos, fechas, combos y paginador."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from desktop.app.core.formatting import money_for_input, parse_money, today_local


@contextmanager
def busy() -> Iterator[None]:
    """Cursor de espera mientras se llama a la API."""
    app = QApplication.instance()
    if app is not None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        yield
    finally:
        if app is not None:
            QApplication.restoreOverrideCursor()


class FieldError(ValueError):
    """Error de validación local asociado a un campo del formulario."""

    def __init__(self, field: str | None, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


class MoneyEdit(QLineEdit):
    """Campo de importe en formato argentino (1.234,56). value() -> Decimal."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText("0,00")
        self.setAlignment(Qt.AlignmentFlag.AlignRight)

    def value(self) -> Decimal:
        return parse_money(self.text())

    def set_value(self, value: Decimal | str | None) -> None:
        self.setText(money_for_input(value))


def to_qdate(value: date) -> QDate:
    return QDate(value.year, value.month, value.day)


class DateEdit(QDateEdit):
    def __init__(self, value: date | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCalendarPopup(True)
        self.setDisplayFormat("dd/MM/yyyy")
        self.set_value(value or today_local())

    def value(self) -> date:
        return self.date().toPython()

    def set_value(self, value: date) -> None:
        self.setDate(to_qdate(value))


class OptionalDateEdit(QWidget):
    """Fecha opcional para filtros: casilla + fecha. value() -> date | None."""

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.check = QCheckBox(label)
        self.edit = DateEdit()
        self.edit.setEnabled(False)
        self.check.toggled.connect(self.edit.setEnabled)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.check)
        lay.addWidget(self.edit)

    def value(self) -> date | None:
        return self.edit.value() if self.check.isChecked() else None

    def set_value(self, value: date | None) -> None:
        self.check.setChecked(value is not None)
        if value is not None:
            self.edit.set_value(value)


class ChoiceCombo(QComboBox):
    """Combo de opciones fijas: items [(texto, valor)]. value() -> valor."""

    def __init__(self, items: list[tuple[str, object]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        for text, value in items:
            self.addItem(text, value)

    def value(self):
        return self.currentData()

    def set_value(self, value) -> None:
        idx = self.findData(value)
        if idx >= 0:
            self.setCurrentIndex(idx)


class SearchCombo(QComboBox):
    """Combo con búsqueda por texto (clientes, facturas). value() -> id o None."""

    def __init__(self, empty_label: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.empty_label = empty_label
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setMinimumWidth(260)
        completer = self.completer()
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

    def set_items(self, items: list[tuple[str, str]], keep: bool = True) -> None:
        current = self.value() if keep else None
        self.blockSignals(True)
        self.clear()
        if self.empty_label is not None:
            self.addItem(self.empty_label, None)
        for text, value in items:
            self.addItem(text, value)
        self.blockSignals(False)
        if current is not None:
            self.set_value(current)
        else:
            self.setCurrentIndex(0 if self.count() else -1)

    def value(self) -> str | None:
        idx = self.findText(self.currentText(), Qt.MatchFlag.MatchFixedString)
        return self.itemData(idx) if idx >= 0 else None

    def set_value(self, value: str | None) -> None:
        idx = self.findData(value)
        if idx >= 0:
            self.setCurrentIndex(idx)


class Pager(QWidget):
    """Paginador: ◀ Página x de y · N registros ▶. Emite changed(page)."""

    changed = Signal(int)

    def __init__(self, page_size: int = 50, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.page = 1
        self.page_size = page_size
        self.total = 0
        self.prev_btn = QPushButton("◀ Anterior")
        self.next_btn = QPushButton("Siguiente ▶")
        self.label = QLabel()
        self.prev_btn.clicked.connect(lambda: self._go(self.page - 1))
        self.next_btn.clicked.connect(lambda: self._go(self.page + 1))
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addStretch(1)
        lay.addWidget(self.prev_btn)
        lay.addWidget(self.label)
        lay.addWidget(self.next_btn)
        self.update_total(0)

    @property
    def pages(self) -> int:
        return max(1, -(-self.total // self.page_size))

    def update_total(self, total: int) -> None:
        self.total = total
        self.page = min(self.page, self.pages)
        noun = "registro" if total == 1 else "registros"
        self.label.setText(f"Página {self.page} de {self.pages} · {total} {noun}")
        self.prev_btn.setEnabled(self.page > 1)
        self.next_btn.setEnabled(self.page < self.pages)

    def reset(self) -> None:
        self.page = 1

    def _go(self, page: int) -> None:
        if 1 <= page <= self.pages and page != self.page:
            self.page = page
            self.changed.emit(page)
