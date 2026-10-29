"""Utilidades para los tests."""

from datetime import date

from sqlalchemy.orm import Session

from app.api.deps import get_today
from app.core.security import create_access_token
from app.main import app
from app.models import Role, User
from app.schemas.user import UserCreate
from app.services import users as users_service

TEST_PASSWORD = "clave-de-prueba-123"


def set_today(value: date) -> None:
    """Fija la fecha de negocio que ve la API (para probar vencimientos)."""
    app.dependency_overrides[get_today] = lambda: value


def make_user(db: Session, email: str, role: Role, name: str = "Usuario Test") -> User:
    data = UserCreate(email=email, full_name=name, role=role, password=TEST_PASSWORD)
    return users_service.create_user(db, data, actor=None)


def auth_headers(user: User) -> dict[str, str]:
    token, _ = create_access_token(user.id, user.role)
    return {"Authorization": f"Bearer {token}"}
