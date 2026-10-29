import json

import pytest

from desktop.app.core.config import (
    DEFAULT_API_URL,
    AppConfig,
    config_path,
    is_insecure_remote,
    load_config,
    normalize_api_url,
    save_config,
)


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("localhost:8000", "http://localhost:8000/api/v1"),
        ("http://localhost:8000/", "http://localhost:8000/api/v1"),
        ("https://cobranzas.miempresa.com", "https://cobranzas.miempresa.com/api/v1"),
        ("https://cobranzas.miempresa.com/api/v1/", "https://cobranzas.miempresa.com/api/v1"),
    ],
)
def test_normalize_api_url(entrada, esperado):
    assert normalize_api_url(entrada) == esperado


@pytest.mark.parametrize("entrada", ["", "   ", "ftp://servidor", "http://"])
def test_normalize_api_url_invalida(entrada):
    with pytest.raises(ValueError):
        normalize_api_url(entrada)


def test_http_remoto_es_inseguro():
    assert is_insecure_remote("http://192.168.0.10:8000/api/v1")
    assert not is_insecure_remote("http://localhost:8000/api/v1")
    assert not is_insecure_remote("https://cobranzas.miempresa.com/api/v1")


def test_sin_archivo_usa_valores_por_defecto():
    assert load_config() == AppConfig()


def test_guardar_y_leer():
    save_config(AppConfig(api_url="https://srv.com/api/v1", last_email="a@b.com"))
    cfg = load_config()
    assert cfg.api_url == "https://srv.com/api/v1"
    assert cfg.last_email == "a@b.com"
    # Nunca se guardan secretos
    assert "password" not in config_path().read_text() and "token" not in config_path().read_text()


def test_archivo_corrupto_no_rompe():
    config_path().parent.mkdir(parents=True, exist_ok=True)
    config_path().write_text("{no es json", encoding="utf-8")
    assert load_config().api_url == DEFAULT_API_URL


def test_valores_raros_se_ignoran():
    config_path().parent.mkdir(parents=True, exist_ok=True)
    config_path().write_text(json.dumps({"api_url": 123, "otra": "x", "api": "y"}))
    assert load_config() == AppConfig()


def test_variable_de_entorno_tiene_prioridad(monkeypatch):
    save_config(AppConfig(api_url="https://srv.com/api/v1"))
    monkeypatch.setenv("CASHFLOW_API_URL", "http://otro:9000")
    assert load_config().api_url == "http://otro:9000/api/v1"
