import uuid

from fastapi import status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import hash_password, verify_password
from app.core.timeutils import utcnow
from app.models import RefreshToken, User
from app.schemas.common import Pagination
from app.schemas.user import UserCreate, UserUpdate
from app.services import audit


def get_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.strip().lower()))


def get_user(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise AppError("user_not_found", "Usuario inexistente", status.HTTP_404_NOT_FOUND)
    return user


def list_users(db: Session, pagination: Pagination) -> tuple[list[User], int]:
    total = db.scalar(select(func.count()).select_from(User)) or 0
    rows = db.scalars(
        select(User)
        .order_by(func.lower(User.full_name), User.id)
        .offset(pagination.offset)
        .limit(pagination.page_size)
    ).all()
    return list(rows), total


def create_user(db: Session, data: UserCreate, actor: User | None) -> User:
    """`actor=None` solo para el alta inicial por CLI (el usuario se audita a sí mismo)."""
    if get_by_email(db, data.email):
        raise AppError(
            "email_taken", "Ya existe un usuario con ese email", status.HTTP_409_CONFLICT, "email"
        )
    user = User(
        id=uuid.uuid4(),
        email=data.email.lower(),
        full_name=data.full_name,
        role=data.role.value,
        password_hash=hash_password(data.password),
        is_active=True,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(
            "email_taken", "Ya existe un usuario con ese email", status.HTTP_409_CONFLICT, "email"
        ) from exc
    audit.record(
        db,
        actor_id=actor.id if actor else user.id,
        entity_type="user",
        entity_id=user.id,
        action="create",
        details={"email": user.email, "role": user.role, "full_name": user.full_name},
    )
    db.commit()
    return user


def revoke_all_refresh_tokens(db: Session, user_id: uuid.UUID) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )


def update_user(db: Session, user_id: uuid.UUID, data: UserUpdate, actor: User) -> User:
    user = get_user(db, user_id)
    changes = data.model_dump(exclude_unset=True, exclude={"password"})
    if "role" in changes and changes["role"] is not None:
        changes["role"] = changes["role"].value
    changes = {k: v for k, v in changes.items() if v is not None}

    if user.id == actor.id and (
        changes.get("is_active") is False or changes.get("role", user.role) != user.role
    ):
        raise AppError(
            "cannot_modify_self",
            "No podés desactivarte ni cambiar tu propio rol",
            status.HTTP_400_BAD_REQUEST,
        )

    details: dict = audit.diff(user, changes)
    for field, value in changes.items():
        setattr(user, field, value)

    if data.password:
        user.password_hash = hash_password(data.password)
        details["password_reset"] = True  # se registra el hecho, nunca el valor
    if data.password or changes.get("is_active") is False:
        revoke_all_refresh_tokens(db, user.id)

    if details:
        audit.record(
            db,
            actor_id=actor.id,
            entity_type="user",
            entity_id=user.id,
            action="update",
            details=details,
        )
    db.commit()
    return user


def change_own_password(db: Session, user: User, current: str, new: str) -> None:
    if not verify_password(current, user.password_hash):
        raise AppError(
            "invalid_password",
            "La contraseña actual es incorrecta",
            status.HTTP_400_BAD_REQUEST,
            "current_password",
        )
    user.password_hash = hash_password(new)
    revoke_all_refresh_tokens(db, user.id)
    audit.record(
        db,
        actor_id=user.id,
        entity_type="user",
        entity_id=user.id,
        action="change_password",
    )
    db.commit()
