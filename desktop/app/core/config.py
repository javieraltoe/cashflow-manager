"""Configuración local del escritorio (URL del servidor, último email usado).

Se guarda en JSON en %APPDATA%\\CashFlowManager\\config.json (Windows). Nunca se guardan
contraseñas ni tokens. CASHFLOW_API_URL (variable de entorno) tiene prioridad sobre el
archivo, y CASHFLOW_CONFIG_DIR permite cambiar la carpeta (lo usan los tests).
"""

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_API_URL = "http://localhost:8000/api/v1"
DEFAULT_DASHBOARD_URL = "http://localhost:8501"
API_SUFFIX = "/api/v1"
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


@dataclass
class AppConfig:
    api_url: str = DEFAULT_API_URL
    dashboard_url: str = DEFAULT_DASHBOARD_URL
    last_email: str = ""


def config_dir() -> Path:
    if custom := os.getenv("CASHFLOW_CONFIG_DIR"):
        return Path(custom)
    if appdata := os.getenv("APPDATA"):
        return Path(appdata) / "CashFlowManager"
    return Path.home() / ".config" / "cashflow-manager"


def config_path() -> Path:
    return config_dir() / "config.json"


def normalize_api_url(url: str) -> str:
    """'servidor:8000' -> 'http://servidor:8000/api/v1'. ValueError si no es válida."""
    url = (url or "").strip()
    if not url:
        raise ValueError("Ingresá la dirección del servidor")
    if "://" not in url:
        url = f"http://{url}"
    url = url.rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(
            "La dirección del servidor no es válida (ej.: https://cobranzas.miempresa.com)"
        )
    if not url.endswith(API_SUFFIX):
        url = f"{url}{API_SUFFIX}"
    return url


def is_insecure_remote(url: str) -> bool:
    """True si la conexión va sin cifrar (http) a un servidor que no es esta PC."""
    parsed = urlparse(url)
    return parsed.scheme == "http" and (parsed.hostname or "") not in _LOCAL_HOSTS


def load_config(path: Path | None = None) -> AppConfig:
    path = path or config_path()
    cfg = AppConfig()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    if isinstance(raw, dict):
        known = {f.name for f in fields(AppConfig)}
        for key, value in raw.items():
            if key in known and isinstance(value, str):
                setattr(cfg, key, value)
    if env_url := os.getenv("CASHFLOW_API_URL"):
        cfg.api_url = env_url
    try:
        cfg.api_url = normalize_api_url(cfg.api_url)
    except ValueError:
        cfg.api_url = DEFAULT_API_URL
    return cfg


def save_config(cfg: AppConfig, path: Path | None = None) -> None:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(cfg), indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
