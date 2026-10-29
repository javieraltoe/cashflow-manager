import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_database_url_usa_psycopg_y_escapa_la_contrasena():
    s = Settings(_env_file=None, postgres_password="p@ss:w/rd", postgres_port=5433)
    assert s.database_url.startswith("postgresql+psycopg://")
    assert "p%40ss%3Aw%2Frd" in s.database_url
    assert ":5433/" in s.database_url


def test_cors_origins_se_parsea_como_lista():
    s = Settings(_env_file=None, cors_origins="http://a.com, http://b.com ,")
    assert s.cors_origin_list == ["http://a.com", "http://b.com"]


def test_produccion_rechaza_secret_key_por_defecto():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production")


def test_produccion_rechaza_cors_comodin():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="production",
            secret_key="una-clave-larga-y-aleatoria-1234567890",
            cors_origins="*",
        )


def test_produccion_valida_con_configuracion_segura():
    s = Settings(
        _env_file=None,
        app_env="production",
        secret_key="una-clave-larga-y-aleatoria-1234567890",
        cors_origins="https://dashboard.midominio.com",
    )
    assert s.is_production


def test_produccion_deshabilita_docs(monkeypatch):
    from app import main
    from app.core import config

    prod = Settings(
        _env_file=None,
        app_env="production",
        secret_key="una-clave-larga-y-aleatoria-1234567890",
        cors_origins="https://dashboard.midominio.com",
    )
    monkeypatch.setattr(main, "get_settings", lambda: prod)
    monkeypatch.setattr(config, "get_settings", lambda: prod)
    app = main.create_app()
    assert app.docs_url is None
    assert app.openapi_url is None
