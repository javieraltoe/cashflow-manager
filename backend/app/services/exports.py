"""Exportación CSV de facturas con los mismos filtros del listado (spec §9, HU08).

- Las primeras 6 columnas son las de importación (§10): el archivo exportado se puede
  volver a importar en otra instalación.
- UTF-8 con BOM (Excel en español), coma como separador, punto decimal, fechas ISO.
- Protección contra inyección de fórmulas: un texto que empieza con = + - @ tab o CR se
  antepone con un apóstrofo, así Excel no lo ejecuta.
"""

import csv
import io
from datetime import date

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Invoice
from app.services.invoices import SORTS, InvoiceFilters, filtered_query, to_out

MAX_ROWS = 50_000
HEADER = [
    "client_name",
    "invoice_number",
    "issue_date",
    "due_date",
    "amount",
    "description",
    "paid_amount",
    "balance",
    "status",
    "days_overdue",
]
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def safe_text(value: str | None) -> str:
    text = value or ""
    return f"'{text}" if text.startswith(_FORMULA_START) else text


def invoices_csv(db: Session, filters: InvoiceFilters, today: date, sort: str) -> bytes:
    stmt = filtered_query(filters, today)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    if total > MAX_ROWS:
        raise AppError(
            "export_too_large",
            f"La exportación tiene {total} facturas (máximo {MAX_ROWS}). Acotá los filtros.",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(HEADER)
    for r in db.execute(stmt.order_by(SORTS[sort], Invoice.id)):
        inv = to_out(r.Invoice, r.client_name, r.paid, today)
        writer.writerow(
            [
                safe_text(inv.client_name),
                safe_text(inv.invoice_number),
                inv.issue_date.isoformat(),
                inv.due_date.isoformat(),
                f"{inv.amount:.2f}",
                safe_text(inv.description),
                f"{inv.paid_amount:.2f}",
                f"{inv.balance:.2f}",
                inv.status.value,
                inv.days_overdue,
            ]
        )
    return ("﻿" + buf.getvalue()).encode("utf-8")
