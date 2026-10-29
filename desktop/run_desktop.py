"""Punto de entrada para PyInstaller (el .exe arranca acá)."""

import sys

from desktop.app.main import main

if __name__ == "__main__":
    sys.exit(main())
