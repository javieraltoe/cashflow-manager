import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DbSession, Today
from app.schemas.common import Page, Pagination, pagination_params
from app.schemas.invoice import InvoiceCreate, InvoiceOut, InvoiceUpdate
from app.services import invoices as invoices_service
from app.services.invoice_rules import InvoiceStatus

router = APIRouter(prefix="/invoices", tags=["invoices"])

InvoiceSort = Literal[
    "due_date", "-due_date", "issue_date", "-issue_date", "amount", "-amount",
    "invoice_number", "-invoice_number", "created_at", "-created_at",
]  # fmt: skip


def invoice_filters(
    client_id: uuid.UUID | None = None,
    status: InvoiceStatus | None = None,
    issue_from: date | None = None,
    issue_to: date | None = None,
    due_from: date | None = None,
    due_to: date | None = None,
    q: Annotated[str | None, Query(max_length=50, description="Busca por número")] = None,
    include_void: bool = False,
) -> invoices_service.InvoiceFilters:
    return invoices_service.InvoiceFilters(
        client_id=client_id,
        status=status,
        issue_from=issue_from,
        issue_to=issue_to,
        due_from=due_from,
        due_to=due_to,
        q=q,
        include_void=include_void,
    )


@router.get("", response_model=Page[InvoiceOut])
def list_invoices(
    db: DbSession,
    _: CurrentUser,
    today: Today,
    filters: Annotated[invoices_service.InvoiceFilters, Depends(invoice_filters)],
    pagination: Annotated[Pagination, Depends(pagination_params)],
    sort: InvoiceSort = "due_date",
) -> Page[InvoiceOut]:
    items, total = invoices_service.list_invoices(db, filters, pagination, today, sort)
    return Page[InvoiceOut](
        items=items, total=total, page=pagination.page, page_size=pagination.page_size
    )


@router.post("", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED)
def create_invoice(
    data: InvoiceCreate, db: DbSession, user: CurrentUser, today: Today
) -> InvoiceOut:
    return invoices_service.create_invoice(db, data, user, today)


@router.get("/{invoice_id}", response_model=InvoiceOut)
def get_invoice(invoice_id: uuid.UUID, db: DbSession, _: CurrentUser, today: Today) -> InvoiceOut:
    return invoices_service.get_invoice(db, invoice_id, today)


@router.patch("/{invoice_id}", response_model=InvoiceOut)
def update_invoice(
    invoice_id: uuid.UUID, data: InvoiceUpdate, db: DbSession, user: CurrentUser, today: Today
) -> InvoiceOut:
    """Editar datos o anular (`{"is_void": true}`, solo administrador y sin pagos vigentes)."""
    return invoices_service.update_invoice(db, invoice_id, data, user, today)
