"""Administración de usuarios: solo rol administrador (HU01)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import AdminUser, DbSession
from app.schemas.common import Page, Pagination, pagination_params
from app.schemas.user import UserCreate, UserOut, UserUpdate
from app.services import users as users_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=Page[UserOut])
def list_users(
    db: DbSession,
    _: AdminUser,
    pagination: Annotated[Pagination, Depends(pagination_params)],
) -> Page[UserOut]:
    rows, total = users_service.list_users(db, pagination)
    return Page[UserOut](
        items=[UserOut.model_validate(u) for u in rows],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(data: UserCreate, db: DbSession, admin: AdminUser) -> UserOut:
    return UserOut.model_validate(users_service.create_user(db, data, admin))


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: uuid.UUID, data: UserUpdate, db: DbSession, admin: AdminUser) -> UserOut:
    return UserOut.model_validate(users_service.update_user(db, user_id, data, admin))
