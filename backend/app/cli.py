"""Comandos de administración.

Crear el primer administrador (pide la contraseña sin mostrarla):
    python -m app.cli create-admin --email admin@miempresa.com.ar --name "Administrador"
En Docker:
    docker compose exec api python -m app.cli create-admin --email ... --name ...
"""

import argparse
import getpass
import sys

from pydantic import ValidationError

from app.core.errors import AppError
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("create-admin", help="Crea un usuario administrador")
    p.add_argument("--email", required=True)
    p.add_argument("--name", required=True)
    args = parser.parse_args(argv)
    if args.command == "create-admin":
        return _create_admin(args.email, args.name)
    return 1


if __name__ == "__main__":
    sys.exit(main())
