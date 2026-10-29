"""CashFlow Manager · escritorio.

Ejecutar desde la raíz del repo:  python -m desktop.app.main
(o .\\scripts\\dev.ps1 desktop). El ejecutable de Windows se arma con
.\\scripts\\build\\build-desktop.ps1.
"""

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from desktop.app import __version__
from desktop.app.core.config import load_config
from desktop.app.services.api import ApiClient
from desktop.app.views.base import AppContext
from desktop.app.views.login import LoginDialog
from desktop.app.views.main_window import MainWindow


def icon_path() -> Path:
    """Ícono empaquetado por PyInstaller (sys._MEIPASS) o el del repo en desarrollo."""
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle) / "assets" / "cashflow.ico"
    return Path(__file__).resolve().parents[1] / "packaging" / "cashflow.ico"


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("CashFlow Manager")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("CashFlowManager")
    app.setStyle("Fusion")
    if icon_path().exists():
        app.setWindowIcon(QIcon(str(icon_path())))

    config = load_config()
    ctx = AppContext(ApiClient(config.api_url), config)
    if not LoginDialog(ctx).exec():
        return 0

    window = MainWindow(ctx)
    ctx.session_lost.connect(window.logout)
    window.show()
    code = app.exec()
    ctx.api.logout()
    ctx.api.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
