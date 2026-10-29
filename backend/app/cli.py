"""Comandos de administración.

Crear el primer administrador (pide la contraseña sin mostrarla):
    python -m app.cli create-admin --email admin@miempresa.com.ar --name "Administrador"
En Docker:
    docker compose exec api python -m app.cli create-admin --email ... --name ...

Datos de demostración (HU06) y de volumen (prueba de rendimiento):
    python -m app.cli seed-demo [--reset]
    python -m app.cli seed-perf [--reset]
--reset borra clientes, facturas, pagos y créditos (no usuarios). Nunca en producción.
"""

import argparse
import getpass
import sys

from pydantic import ValidationError

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.timeutils import today_local
from app.db.session import SessionLocal
from app.models import Role
from app.schemas.user import UserCreate
from app.services import users as users_service


def _create_admin(email: str, name: str) -> int:
    password = getpass.getpass("Contraseña (mín. 10 caracteres): ")
    if password != getpass.getpass("Repetir contraseña: "):
        print("Las contraseñas no coinciden.", file=sys.stderr)
        return 1
    try:
        data = UserCreate(email=email, full_name=name, role=Role.ADMIN, password=password)
    except ValidationError as exc:
        for err in exc.errors():
            print(
                f"Dato inválido en {'.'.join(map(str, err['loc']))}: {err['msg']}", file=sys.stderr
            )
        return 1
    with SessionLocal() as db:
        try:
            user = users_service.create_user(db, data, actor=None)
        except AppError as exc:
            print(exc.message, file=sys.stderr)
            return 1
    print(f"Administrador creado: {user.email} (id {user.id})")
    return 0


def _seed(kind: str, reset: bool) -> int:
    from sqlalchemy import func, select

    from app import perfdata, seed
    from app.models import Client

    if get_settings().is_production:
        print("Los datos de prueba no se cargan en producción.", file=sys.stderr)
        return 1
    with SessionLocal() as db:
        try:
            actor = seed.first_admin(db)
            if kind == "demo":
                result = seed.seed_demo(db, today_local(), actor, reset=reset)
            else:
                if reset:
                    seed.reset_business_data(db)
                elif db.scalar(select(func.count()).select_from(Client)):
                    raise seed.SeedError(
                        "La base ya tiene clientes. Usá --reset para reemplazarlos (borra datos)."
                    )
                result = perfdata.seed_perf(db, today_local(), actor.id)
        except seed.SeedError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    print(f"Datos cargados: {result}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("create-admin", help="Crea un usuario administrador")
    p.add_argument("--email", required=True)
    p.add_argument("--name", required=True)
    for name, help_ in (
        ("seed-demo", "Carga el dataset de demostración reconciliado (HU06)"),
        ("seed-perf", "Carga 1.000 clientes, 20.000 facturas y 50.000 pagos"),
    ):
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("--reset", action="store_true", help="Borra antes los datos de negocio")
    args = parser.parse_args(argv)
    if args.command == "create-admin":
        return _create_admin(args.email, args.name)
    if args.command in ("seed-demo", "seed-perf"):
        return _seed(args.command.removeprefix("seed-"), args.reset)
    return 1


if __name__ == "__main__":
    sys.exit(main())
