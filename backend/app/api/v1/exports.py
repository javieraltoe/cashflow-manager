"""GET /exports/invoices.csv: exportación autenticada con filtros (spec §9, HU08)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.deps import CurrentUser, DbSession, Today
from app.api.v1.invoices import InvoiceSort, invoice_filters
from app.services import exports as exports_service
from app.services.invoices import InvoiceFilters

router = APIRouter(prefix="/exports", tags=["exports"])


@router.get(
    "/invoices.csv",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}, "description": "CSV UTF-8 con BOM"}},
)
def export_invoices(
    db: DbSession,
    _: CurrentUser,
    today: Today,
    filters: Annotated[InvoiceFilters, Depends(invoice_filters)],
    sort: InvoiceSort = "due_date",
) -> Response:
    """Mismos filtros que GET /invoices, sin paginar (máximo 50.000 filas)."""
    content = exports_service.invoices_csv(db, filters, today, sort)
    filename = f"facturas_{today:%Y%m%d}.csv"
    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
