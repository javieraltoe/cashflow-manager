import pytest

from app import cli
from app.services import users as users_service

pytestmark = pytest.mark.integration


def test_create_admin(db, monkeypatch, capsys):
    monkeypatch.setattr(cli, "SessionLocal", lambda: db)
    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: "clave-admin-segura")
    code = cli.main(["create-admin", "--email", "Jefa@Empresa.com.ar", "--name", "Jefa"])
    assert code == 0
    assert "Administrador creado" in capsys.readouterr().out
    user = users_service.get_by_email(db, "jefa@empresa.com.ar")
    assert user is not None
    assert user.role == "admin"


def test_create_admin_rechaza_password_corta(db, monkeypatch, capsys):
    monkeypatch.setattr(cli, "SessionLocal", lambda: db)
    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: "corta")
    assert cli.main(["create-admin", "--email", "a@empresa.com.ar", "--name", "A"]) == 1
    assert "password" in capsys.readouterr().err
