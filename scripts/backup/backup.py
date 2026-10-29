"""Backup, verificación por restauración y restauración de PostgreSQL (spec §8 y §11).

Solo usa la biblioteca estándar: funciona en Windows (vía Docker) y en el servidor.

    python scripts/backup/backup.py backup                    # crea backups/cashflow_<fecha>.dump
    python scripts/backup/backup.py backup --s3 s3://mi-bucket/cashflow --keep 14
    python scripts/backup/backup.py verify backups/archivo.dump
    python scripts/backup/backup.py restore backups/archivo.dump --target-db cashflow_copia
    python scripts/backup/backup.py restore backups/archivo.dump --replace   # base principal

--via docker (por defecto) ejecuta las herramientas dentro del contenedor "db" de
docker compose; --via local usa pg_dump/pg_restore/psql instalados en la máquina.
"verify" restaura en una base temporal, compara conteos y totales con la base original
y la borra: es la prueba de que el backup se puede restaurar.
"""

import argparse
import contextlib
import hashlib
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECK_DB = "cashflow_restore_check"

# Huella de la base: si coincide entre original y restaurada, el backup es completo.
FINGERPRINT_SQL = """
SELECT 'users', count(*)::text FROM users
UNION ALL SELECT 'clients', count(*)::text FROM clients
UNION ALL SELECT 'invoices', count(*)::text FROM invoices
UNION ALL SELECT 'payments', count(*)::text FROM payments
UNION ALL SELECT 'client_credits', count(*)::text FROM client_credits
UNION ALL SELECT 'audit_events', count(*)::text FROM audit_events
UNION ALL SELECT 'import_batches', count(*)::text FROM import_batches
UNION ALL SELECT 'suma_facturas', COALESCE(SUM(amount), 0)::text FROM invoices
UNION ALL SELECT 'suma_pagos_vigentes', COALESCE(SUM(amount), 0)::text FROM payments
          WHERE NOT is_void
UNION ALL SELECT 'suma_creditos_vigentes', COALESCE(SUM(amount), 0)::text FROM client_credits
          WHERE NOT is_void
UNION ALL SELECT 'version_esquema', version_num FROM alembic_version
"""


class BackupError(Exception):
    pass


def load_env() -> dict[str, str]:
    """Variables de .env (raíz del repo), con prioridad para las del entorno."""
    env: dict[str, str] = {}
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip().strip('"').strip("'")
    for key in ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_HOST",
                "POSTGRES_PORT", "COMPOSE_FILE"):  # fmt: skip
        if os.getenv(key):
            env[key] = os.environ[key]
    for key in ("POSTGRES_DB", "POSTGRES_USER"):
        if not env.get(key):
            raise BackupError(f"Falta {key} en .env")
    return env


class Runner:
    """Ejecuta herramientas de PostgreSQL vía docker compose o instaladas localmente."""

    def __init__(self, via: str, env: dict[str, str], compose_file: str | None) -> None:
        self.via = via
        self.env = env
        self.compose = ["docker", "compose"] + (["-f", compose_file] if compose_file else [])

    def cmd(self, tool: str, *args: str) -> list[str]:
        if self.via == "docker":
            return [*self.compose, "exec", "-T", "db", tool, *args]
        if shutil.which(tool) is None:
            raise BackupError(f"No se encontró '{tool}'. Usá --via docker o instalá PostgreSQL.")
        return [tool, *args]

    def proc_env(self) -> dict[str, str]:
        env = dict(os.environ)
        if self.via == "local":
            env["PGPASSWORD"] = self.env.get("POSTGRES_PASSWORD", "")
            env["PGHOST"] = self.env.get("POSTGRES_HOST", "localhost")
            env["PGPORT"] = self.env.get("POSTGRES_PORT", "5432")
        return env

    def run(self, tool: str, *args: str, stdin=None, stdout=None) -> str:
        result = subprocess.run(  # noqa: S603 - comandos armados por el script, sin shell
            self.cmd(tool, *args),
            stdin=stdin,
            stdout=stdout if stdout is not None else subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self.proc_env(),
            check=False,
        )
        if result.returncode != 0:
            raise BackupError(f"{tool} falló: {result.stderr.decode(errors='replace').strip()}")
        return result.stdout.decode() if stdout is None and result.stdout else ""

    def psql(self, db: str, sql: str) -> str:
        user = self.env["POSTGRES_USER"]
        return self.run("psql", "-U", user, "-d", db, "-v", "ON_ERROR_STOP=1", "-tA", "-c", sql)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def do_backup(r: Runner, out_dir: Path, s3: str | None, keep: int | None) -> Path:
    db, user = r.env["POSTGRES_DB"], r.env["POSTGRES_USER"]
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%SZ")
    target = out_dir / f"cashflow_{db}_{stamp}.dump"
    partial = target.with_suffix(".dump.partial")
    with partial.open("wb") as fh:
        r.run("pg_dump", "-U", user, "-d", db, "-Fc", "--no-owner", "--no-privileges", stdout=fh)
    if partial.stat().st_size == 0:
        partial.unlink()
        raise BackupError("pg_dump no generó datos")
    partial.replace(target)
    with contextlib.suppress(OSError):  # en Windows no aplica
        target.chmod(0o600)  # contiene datos de clientes: solo el dueño
    digest = sha256(target)
    target.with_suffix(".dump.sha256").write_text(f"{digest}  {target.name}\n", encoding="utf-8")
    print(f"Backup creado: {target} ({target.stat().st_size / 1024:.0f} KB) sha256={digest[:16]}…")

    if s3:
        if shutil.which("aws") is None:
            raise BackupError("Para --s3 hace falta AWS CLI (aws) instalado y con permisos.")
        for f in (target, target.with_suffix(".dump.sha256")):
            dest = f"{s3.rstrip('/')}/{f.name}"
            aws_cmd = ["aws", "s3", "cp", str(f), dest, "--sse", "aws:kms", "--only-show-errors"]
            subprocess.run(aws_cmd, check=True)  # noqa: S603
        print(f"Copiado a {s3} (cifrado en reposo con KMS)")

    if keep:
        dumps = sorted(out_dir.glob(f"cashflow_{db}_*.dump"))
        for old in dumps[:-keep]:
            old.unlink()
            old.with_suffix(".dump.sha256").unlink(missing_ok=True)
            print(f"Eliminado por retención: {old.name}")
    return target


def check_digest(dump: Path) -> None:
    sidecar = dump.with_suffix(".dump.sha256")
    if sidecar.exists():
        expected = sidecar.read_text(encoding="utf-8").split()[0]
        if sha256(dump) != expected:
            raise BackupError("El archivo no coincide con su .sha256: está dañado o incompleto.")


def restore_into(r: Runner, dump: Path, db: str) -> None:
    user = r.env["POSTGRES_USER"]
    with dump.open("rb") as fh:
        r.run("pg_restore", "-U", user, "-d", db, "--no-owner", "--no-privileges",
              "--exit-on-error", stdin=fh)  # fmt: skip


def fingerprint(r: Runner, db: str) -> dict[str, str]:
    out = r.psql(db, FINGERPRINT_SQL)
    return dict(line.split("|", 1) for line in out.strip().splitlines() if "|" in line)


def do_verify(r: Runner, dump: Path) -> bool:
    check_digest(dump)
    user, source = r.env["POSTGRES_USER"], r.env["POSTGRES_DB"]
    r.run("dropdb", "-U", user, "--if-exists", CHECK_DB)
    r.run("createdb", "-U", user, CHECK_DB)
    try:
        restore_into(r, dump, CHECK_DB)
        restored = fingerprint(r, CHECK_DB)
        original = fingerprint(r, source)
    finally:
        r.run("dropdb", "-U", user, "--if-exists", CHECK_DB)
    print(f"{'Dato':26} {'Base actual':>20} {'Backup restaurado':>20}")
    ok = True
    for key in original:
        mark = "" if original[key] == restored.get(key) else "  <-- DIFERENTE"
        ok = ok and not mark
        print(f"{key:26} {original[key]:>20} {restored.get(key, '-'):>20}{mark}")
    print(
        "\nRESTAURACIÓN VERIFICADA: el backup está completo."
        if ok
        else "\nATENCIÓN: hay diferencias (normal si hubo movimientos después del backup)."
    )
    return ok


def do_restore(r: Runner, dump: Path, target_db: str | None, replace: bool, yes: bool) -> None:
    check_digest(dump)
    user, main_db = r.env["POSTGRES_USER"], r.env["POSTGRES_DB"]
    db = main_db if replace else target_db
    if not db:
        raise BackupError("Indicá --target-db NOMBRE o --replace para la base principal.")
    if db == main_db and not replace:
        raise BackupError("Para restaurar sobre la base principal usá --replace.")
    if replace and not yes:
        print(f"Esto BORRA la base '{main_db}' y la reemplaza por {dump.name}.")
        print("Detené antes la API (docker compose stop api dashboard).")
        if input("Escribí RESTAURAR para continuar: ").strip() != "RESTAURAR":
            raise BackupError("Cancelado.")
    r.run("dropdb", "-U", user, "--if-exists", db)
    r.run("createdb", "-U", user, db)
    restore_into(r, dump, db)
    print(f"Restaurado en '{db}': {fingerprint(r, db)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backups de CashFlow Manager")
    parser.add_argument("--via", choices=["docker", "local"], default="docker")
    parser.add_argument("--compose-file", help="p. ej. docker-compose.prod.yml")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("backup", help="Genera un backup (.dump + .sha256)")
    b.add_argument("--out", default=str(ROOT / "backups"))
    b.add_argument("--s3", help="s3://bucket/prefijo (requiere AWS CLI)")
    b.add_argument("--keep", type=int, help="Conservar solo los últimos N backups locales")
    v = sub.add_parser("verify", help="Restaura en una base temporal y compara")
    v.add_argument("dump")
    rs = sub.add_parser("restore", help="Restaura un backup")
    rs.add_argument("dump")
    rs.add_argument("--target-db")
    rs.add_argument("--replace", action="store_true", help="Reemplaza la base principal")
    rs.add_argument("--yes", action="store_true", help="No pedir confirmación (scripts)")
    args = parser.parse_args(argv)

    try:
        env = load_env()
        runner = Runner(args.via, env, args.compose_file or env.get("COMPOSE_FILE"))
        if args.command == "backup":
            do_backup(runner, Path(args.out), args.s3, args.keep)
            return 0
        dump = Path(args.dump)
        if not dump.exists():
            raise BackupError(f"No existe {dump}")
        if args.command == "verify":
            return 0 if do_verify(runner, dump) else 1
        do_restore(runner, dump, args.target_db, args.replace, args.yes)
        return 0
    except BackupError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
