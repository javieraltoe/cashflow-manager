import uuid

from fastapi import status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Client, User
from app.schemas.client import ClientCreate, ClientUpdate
from app.schemas.common import Pagination
from app.services import audit

SORTS = {
    "name": func.lower(Client.name).asc(),
    "-name": func.lower(Client.name).desc(),
    "created_at": Client.created_at.asc(),
    "-created_at": Client.created_at.desc(),
}


def like_pattern(q: str) -> str:
    """Patrón ILIKE con los comodines del usuario escapados."""
    escaped = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _name_taken() -> AppError:
    return AppError(
        "client_name_taken", "Ya existe un cliente con ese nombre", status.HTTP_409_CONFLICT, "name"
    )


def _check_name_free(db: Session, name: str, exclude_id: uuid.UUID | None = None) -> None:
    stmt = select(Client.id).where(func.lower(Client.name) == name.lower())
    if exclude_id is not None:
        stmt = stmt.where(Client.id != exclude_id)
    if db.scalar(stmt) is not None:
        raise _name_taken()


def get_client(db: Session, client_id: uuid.UUID) -> Client:
    client = db.get(Client, client_id)
    if client is None:
        raise AppError("client_not_found", "Cliente inexistente", status.HTTP_404_NOT_FOUND)
    return client


def list_clients(
    db: Session,
    pagination: Pagination,
    q: str | None = None,
    is_active: bool | None = None,
    sort: str = "name",
) -> tuple[list[Client], int]:
    stmt = select(Client)
    if q and q.strip():
        pattern = like_pattern(q)
        stmt = stmt.where(
            or_(
                Client.name.ilike(pattern, escape="\\"),
                Client.tax_id.ilike(pattern, escape="\\"),
                Client.email.ilike(pattern, escape="\\"),
            )
        )
    if is_active is not None:
        stmt = stmt.where(Client.is_active.is_(is_active))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(SORTS[sort], Client.id).offset(pagination.offset).limit(pagination.page_size)
    ).all()
    return list(rows), total


def create_client(db: Session, data: ClientCreate, actor: User) -> Client:
    _check_name_free(db, data.name)
    client = Client(id=uuid.uuid4(), **data.model_dump())
    db.add(client)
    try:
        db.flush()
    except IntegrityError as exc:  # carrera entre dos altas simultáneas
        db.rollback()
        raise _name_taken() from exc
    audit.record(
        db,
        actor_id=actor.id,
        entity_type="client",
        entity_id=client.id,
        action="create",
        details=data.model_dump(),
    )
    db.commit()
    db.refresh(client)
    return client


def update_client(db: Session, client_id: uuid.UUID, data: ClientUpdate, actor: User) -> Client:
    client = get_client(db, client_id)
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes:
        if changes["name"] is None:
            raise AppError("validation_error", "El nombre es obligatorio", field="name")
        _check_name_free(db, changes["name"], exclude_id=client.id)
    if changes.get("is_active", True) is None:
        changes.pop("is_active")

    details = audit.diff(client, changes)
    if not details:
        return client
    for field, value in changes.items():
        setattr(client, field, value)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _name_taken() from exc
    action = "deactivate" if details.get("is_active", {}).get("to") is False else "update"
    audit.record(
        db,
        actor_id=actor.id,
        entity_type="client",
        entity_id=client.id,
        action=action,
        details=details,
    )
    db.commit()
    db.refresh(client)
    return client
