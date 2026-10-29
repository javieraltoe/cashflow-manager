"""Configuración de la app de escritorio.

La URL del servidor se toma de la variable CASHFLOW_API_URL; en el Sprint 3 se
podrá editar desde la pantalla de Configuración y se guardará con QSettings.
"""

import os

DEFAULT_API_URL = "http://localhost:8000/api/v1"


def get_api_url() -> str:
    return os.getenv("CASHFLOW_API_URL", DEFAULT_API_URL).rstrip("/")
