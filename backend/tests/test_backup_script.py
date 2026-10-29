"""Backup + restauración verificada (checklist §18: "backup restaurable").

Usa pg_dump/pg_restore instalados en la máquina (--via local). Se saltea si no están o si
su versión es menor que la del servidor (en Windows se usa --via docker; ver runbook).
"""

import importlib.util
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import text

from app.core.config import get_settings

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "backup_script", ROOT / "scripts/backup/backup.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def pg_tools(db_connection):
    for tool in ("pg_dump", "pg_restore", "psql", "createdb", "dropdb"):
        if shutil.which(tool) is None:
            pytest.skip(f"{tool} no está instalado (usá --via docker)")
    out = subprocess.run(["pg_dump", "--version"], capture_output=True, text=True, check=True)  # noqa: S603, S607
    client_major = int(re.search(r"(\d+)\.", out.stdout).group(1))
    server_major = int(db_connection.execute(text("SHOW server_version_num")).scalar_one()) // 10000
    if client_major < server_major:
        pytest.skip(f"pg_dump {client_major} es anterior al servidor {server_major}")


def test_backup_y_verificacion_por_restauracion(pg_tools, tmp_path, monkeypatch):
    s = get_settings()
    for key, value in {
        "POSTGRES_DB": s.postgres_db,
        "POSTGRES_USER": s.postgres_user,
        "POSTGRES_PASSWORD": s.postgres_password,
        "POSTGRES_HOST": s.postgres_host,
        "POSTGRES_PORT": str(s.postgres_port),
    }.items():
        monkeypatch.setenv(key, value)
    script = _load_script()
    out = tmp_path / "backups"
    assert script.main(["--via", "local", "backup", "--out", str(out)]) == 0
    dumps = list(out.glob("*.dump"))
    assert len(dumps) == 1
    assert dumps[0].with_suffix(".dump.sha256").exists()
    assert script.main(["--via", "local", "verify", str(dumps[0])]) == 0

    # Un archivo alterado se rechaza antes de restaurar
    dumps[0].write_bytes(dumps[0].read_bytes() + b"x")
    assert script.main(["--via", "local", "verify", str(dumps[0])]) == 1
