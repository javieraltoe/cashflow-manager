import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.client import ClientCreate, ClientOut, ClientUpdate
from app.schemas.common import Page, Pagination, pagination_params
from app.services import clients as clients_service

router = APIRouter(prefix="/clients", tags=["clients"])

ClientSort = Literal["name", "-name", "created_at", "-created_at"]


@router.get("", response_model=Page[ClientOut])
def list_clients(
    db: DbSession,
    _: CurrentUser,
    pagination: Annotated[Pagination, Depends(pagination_params)],
    q: Annotated[
        str | None, Query(max_length=100, description="Busca en nombre, CUIT o email")
    ] = None,
    is_active: bool | None = None,
    sort: ClientSort = "name",
) -> Page[ClientOut]:
    rows, total = clients_service.list_clients(db, pagination, q=q, is_active=is_active, sort=sort)
    return Page[ClientOut](
        items=[ClientOut.model_validate(c) for c in rows],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.post("", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
def create_client(data: ClientCreate, db: DbSession, user: CurrentUser) -> ClientOut:
    return ClientOut.model_validate(clients_service.create_client(db, data, user))


@router.get("/{client_id}", response_model=ClientOut)
def get_client(client_id: uuid.UUID, db: DbSession, _: CurrentUser) -> ClientOut:
    return ClientOut.model_validate(clients_service.get_client(db, client_id))


@router.patch("/{client_id}", response_model=ClientOut)
def update_client(
    client_id: uuid.UUID, data: ClientUpdate, db: DbSession, user: CurrentUser
) -> ClientOut:
    """Editar datos o desactivar (`{"is_active": false}`)."""
    return ClientOut.model_validate(clients_service.update_client(db, client_id, data, user))
