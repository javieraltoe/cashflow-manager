"""CashFlow Manager - escritorio (Sprint 0: ventana de verificación de conexión).

Ejecutar desde la raíz del repo:  python -m desktop.app.main
Login y pantallas reales llegan en el Sprint 3.
"""

import sys

import httpx
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desktop.app.config import get_api_url


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.api_url = get_api_url()
        self.setWindowTitle("CashFlow Manager")
        self.resize(480, 260)

        title = QLabel("CashFlow Manager")
        title.setStyleSheet("font-size: 22px; font-weight: 600;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.server_label = QLabel(f"Servidor: {self.api_url}")
        self.server_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.status_label = QLabel("Estado: sin verificar")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        check_btn = QPushButton("Probar conexión")
        check_btn.clicked.connect(self.check_connection)

        layout = QVBoxLayout()
        for w in (title, self.server_label, self.status_label, check_btn):
            layout.addWidget(w)
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.check_connection()

    def check_connection(self) -> None:
        try:
            resp = httpx.get(f"{self.api_url}/health", timeout=3)
            if resp.status_code == 200:
                text, color = "Conectado · API y base de datos OK", "#1a7f37"
            else:
                text, color = "API conectada · base de datos no disponible", "#b35900"
        except httpx.HTTPError:
            text, color = "Sin conexión con el servidor", "#cf222e"
        self.status_label.setText(f"Estado: {text}")
        self.status_label.setStyleSheet(f"color: {color}; font-weight: 600;")


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
