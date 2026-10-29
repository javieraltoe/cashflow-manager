"""Tabla genérica sobre listas de diccionarios (las respuestas JSON de la API)."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableView, QWidget

STATUS_COLORS = {
    "VENCIDA": "#cf222e",
    "PARCIAL": "#9a6700",
    "PAGADA": "#1a7f37",
    "ANULADA": "#6e7781",
}

_LEFT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
_RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


@dataclass
class Column:
    header: str
    value: Callable[[dict], Any]
    align_right: bool = False
    color: Callable[[dict], str | None] | None = None


def field(key: str, fmt: Callable[[Any], str] | None = None) -> Callable[[dict], Any]:
    """Acceso a una clave del dict, con formato opcional."""

    def getter(row: dict) -> Any:
        value = row.get(key)
        return fmt(value) if fmt else ("" if value is None else value)

    return getter


def status_color(key: str = "status") -> Callable[[dict], str | None]:
    return lambda row: STATUS_COLORS.get(row.get(key) or "")


class DictTableModel(QAbstractTableModel):
    def __init__(self, columns: list[Column], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.columns = columns
        self.rows: list[dict] = []

    def set_rows(self, rows: list[dict]) -> None:
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()

    def row_at(self, row: int) -> dict | None:
        return self.rows[row] if 0 <= row < len(self.rows) else None

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008, N802
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008, N802
        return 0 if parent.isValid() else len(self.columns)

    def data(
        self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole
    ):
        if not index.isValid():
            return None
        row, col = self.rows[index.row()], self.columns[index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            return str(col.value(row))
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return _RIGHT if col.align_right else _LEFT
        if role == Qt.ItemDataRole.ForegroundRole and col.color:
            color = col.color(row)
            return QBrush(QColor(color)) if color else None
        return None

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ):  # noqa: N802
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.columns[section].header
        return None


class DataTable(QTableView):
    """QTableView de solo lectura, selección de una fila."""

    def __init__(self, columns: list[Column], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.table_model = DictTableModel(columns, self)
        self.setModel(self.table_model)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)

    def set_rows(self, rows: list[dict]) -> None:
        self.table_model.set_rows(rows)
        self.resizeColumnsToContents()

    def selected(self) -> dict | None:
        rows = self.selectionModel().selectedRows()
        return self.table_model.row_at(rows[0].row()) if rows else None

    def select_first(self) -> None:
        if self.table_model.rowCount():
            self.selectRow(0)
