"""Diálogos de archivo. Centralizados (como messages) para poder reemplazarlos en tests."""

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QWidget

CSV_FILTER = "Archivos CSV (*.csv);;Todos los archivos (*)"


def ask_open_csv(parent: QWidget | None) -> str | None:
    path, _ = QFileDialog.getOpenFileName(parent, "Elegir archivo CSV", "", CSV_FILTER)
    return path or None


def ask_save_csv(parent: QWidget | None, default_name: str) -> str | None:
    start = str(Path.home() / "Documents" / default_name)
    path, _ = QFileDialog.getSaveFileName(parent, "Guardar CSV", start, CSV_FILTER)
    if not path:
        return None
    return path if path.lower().endswith(".csv") else f"{path}.csv"
