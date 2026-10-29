import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, StringConstraints, field_validator

from app.core.security import MIN_PASSWORD_LENGTH
from app.models.user import Role
from app.schemas.common import ORMModel

FullName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Password = Annotated[str, Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)]


class UserOut(ORMModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: Role
    is_active: bool
    created_at: datetime


class UserCreate(BaseModel):
    email: EmailStr
    full_name: FullName
    role: Role = Role.OPERATOR
    password: Password

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()


class UserUpdate(BaseModel):
    full_name: FullName | None = None
    role: Role | None = None
    is_active: bool | None = None
    # Restablecer contraseña (lo hace un administrador).
    password: Password | None = None


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: Password
