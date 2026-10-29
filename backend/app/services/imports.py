"""Importación de facturas desde CSV en dos pasos (spec §10, HU07).

1. preview: valida y devuelve cada fila con sus errores. No guarda nada.
2. commit: vuelve a validar el MISMO archivo y carga solo las filas válidas, en una
   transacción, registrando el lote en import_batches.

El archivo se procesa en memoria y nunca se escribe en disco. La confirmación es
idempotente respecto de cliente + número de factura: si se confirma dos veces el mismo
archivo, la segunda vez esas filas se rechazan como "ya existe".

Formato: UTF-8 (con o sin BOM), columnas client_name, invoice_number, issue_date,
due_date, amount, description (description es opcional); fechas AAAA-MM-DD; importe con
punto decimal (también se acepta coma, sin separador de miles). Separador "," o ";".
Límites: 5 MB y 5.000 filas.
"""

import csv
import io
import re
import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from fastapi import status
from sqlalchemy import select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Client, ImportBatch, Invoice, User
from app.schemas.imports import ImportPreview, ImportResult, ImportRow, RowError
from app.services import audit

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 5_000
REQUIRED = ["client_name", "invoice_number", "issue_date", "due_date", "amount"]
OPTIONAL = ["description"]
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_AMOUNT = re.compile(r"^\d{1,13}([.,]\d{1,2})?$")


def _file_error(code: str, message: str, http: int = status.HTTP_422_UNPROCESSABLE_ENTITY):
    return AppError(code, message, http, "file")


@dataclass
class _Row:
    line: int
    raw: dict[str, str]
    errors: list[RowError] = field(default_factory=list)
    new_client: bool = False
    client_key: str = ""
    issue: date | None = None
    due: date | None = None
    amount: Decimal | None = None

    def error(self, field_: str | None, message: str) -> None:
        self.errors.append(RowError(field=field_, message=message))

    def out(self) -> ImportRow:
        return ImportRow(
            line=self.line,
            client_name=self.raw.get("client_name", ""),
            invoice_number=self.raw.get("invoice_number", ""),
            issue_date=self.raw.get("issue_date", ""),
            due_date=self.raw.get("due_date", ""),
            amount=self.raw.get("amount", ""),
            description=self.raw.get("description", ""),
            status="error" if self.errors else "ok",
            new_client=self.new_client and not self.errors,
            errors=self.errors,
        )


def safe_filename(name: str | None) -> str:
    base = re.split(r"[\\/]", name or "")[-1].strip()
    return (base or "archivo.csv")[:255]


def parse_csv(content: bytes) -> list[_Row]:
    if len(content) > MAX_BYTES:
        raise _file_error(
            "file_too_large",
            "El archivo supera el máximo de 5 MB",
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise _file_error(
            "invalid_encoding",
            "El archivo debe estar en UTF-8 (en Excel: Guardar como → CSV UTF-8)",
        ) from exc
    lines = text.splitlines()
    if not lines or not lines[0].strip():
        raise _file_error("empty_file", "El archivo está vacío")
    delimiter = ";" if lines[0].count(";") > lines[0].count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    header = [h.strip().lower() for h in next(reader)]
    missing = [c for c in REQUIRED if c not in header]
    unknown = [c for c in header if c not in REQUIRED + OPTIONAL]
    if missing or unknown or len(set(header)) != len(header):
        detail = []
        if missing:
            detail.append(f"faltan: {', '.join(missing)}")
        if unknown:
            detail.append(f"no reconocidas: {', '.join(unknown)}")
        raise _file_error(
            "invalid_columns",
            "Columnas inválidas ("
            + ("; ".join(detail) or "repetidas")
            + "). Se esperan: "
            + ",".join(REQUIRED + OPTIONAL),
        )
    rows: list[_Row] = []
    for values in reader:
        if not any(v.strip() for v in values):
            continue  # línea vacía
        if len(rows) >= MAX_ROWS:
            raise _file_error("too_many_rows", f"El archivo supera el máximo de {MAX_ROWS} filas")
        raw = {h: (values[i].strip() if i < len(values) else "") for i, h in enumerate(header)}
        row = _Row(line=reader.line_num, raw=raw)
        if len(values) > len(header):
            row.error(None, "La fila tiene más columnas que la cabecera")
        rows.append(row)
    if not rows:
        raise _file_error("empty_file", "El archivo no tiene filas de datos")
    return rows


def _parse_date(row: _Row, key: str) -> date | None:
    value = row.raw.get(key, "")
    if not value:
        row.error(key, "Fecha obligatoria")
        return None
    try:
        if not _DATE.match(value):
            raise ValueError
        return date.fromisoformat(value)
    except ValueError:
        row.error(key, f"Fecha inválida '{value}' (formato AAAA-MM-DD)")
        return None


def _validate(db: Session, rows: list[_Row], create_missing: bool) -> list[str]:
    """Valida todas las filas. Devuelve los nombres de clientes que se crearían."""
    clients = {
        name.lower(): (cid, active)
        for cid, name, active in db.execute(select(Client.id, Client.name, Client.is_active))
    }
    new_clients: dict[str, str] = {}
    seen: dict[tuple[str, str], int] = {}

    for row in rows:
        name = row.raw.get("client_name", "")
        number = row.raw.get("invoice_number", "")
        if not name:
            row.error("client_name", "Cliente obligatorio")
        elif len(name) > 200:
            row.error("client_name", "Nombre de cliente demasiado largo (máx. 200)")
        else:
            row.client_key = name.lower()
            found = clients.get(row.client_key)
            if found is None:
                if create_missing:
                    row.new_client = True
                    new_clients.setdefault(row.client_key, name)
                else:
                    row.error("client_name", f"Cliente inexistente: '{name}'")
            elif not found[1]:
                row.error("client_name", f"Cliente inactivo: '{name}'")
        if not number:
            row.error("invoice_number", "Número obligatorio")
        elif len(number) > 50:
            row.error("invoice_number", "Número demasiado largo (máx. 50)")

        row.issue = _parse_date(row, "issue_date")
        row.due = _parse_date(row, "due_date")
        if row.issue and row.due and row.due < row.issue:
            row.error("due_date", "El vencimiento no puede ser anterior a la emisión")

        amount = row.raw.get("amount", "")
        if not amount:
            row.error("amount", "Importe obligatorio")
        elif amount.startswith("-"):
            row.error("amount", "El importe debe ser mayor a cero")
        elif not _AMOUNT.match(amount):
            row.error(
                "amount", f"Importe inválido '{amount}' (ej.: 125000.50, sin separador de miles)"
            )
        else:
            row.amount = Decimal(amount.replace(",", "."))
            if row.amount <= 0:
                row.error("amount", "El importe debe ser mayor a cero")
        if len(row.raw.get("description", "")) > 1000:
            row.error("description", "Descripción demasiado larga (máx. 1000)")

        if row.client_key and number:
            key = (row.client_key, number)
            if key in seen:
                row.error(
                    "invoice_number", f"Repetida en el archivo (igual a la línea {seen[key]})"
                )
            else:
                seen[key] = row.line

    # Facturas que ya existen en la base (cliente + número): se rechazan (idempotencia).
    pairs = [
        (clients[r.client_key][0], r.raw["invoice_number"])
        for r in rows
        if r.client_key in clients and r.raw.get("invoice_number")
    ]
    existing: set[tuple[uuid.UUID, str]] = set()
    for start in range(0, len(pairs), 1000):
        chunk = pairs[start : start + 1000]
        existing |= set(
            db.execute(
                select(Invoice.client_id, Invoice.invoice_number).where(
                    tuple_(Invoice.client_id, Invoice.invoice_number).in_(chunk)
                )
            ).all()
        )
    for row in rows:
        key = (clients.get(row.client_key, (None,))[0], row.raw.get("invoice_number"))
        if key in existing:
            row.error("invoice_number", "Ya existe una factura con ese número para el cliente")
    # Solo se crean clientes que tengan al menos una fila válida.
    usable = {r.client_key for r in rows if r.new_client and not r.errors}
    return [new_clients[k] for k in sorted(new_clients) if k in usable]


def preview(db: Session, content: bytes, filename: str, create_missing: bool) -> ImportPreview:
    rows = parse_csv(content)
    new_clients = _validate(db, rows, create_missing)
    valid = sum(1 for r in rows if not r.errors)
    return ImportPreview(
        filename=safe_filename(filename),
        row_count=len(rows),
        valid_count=valid,
        rejected_count=len(rows) - valid,
        new_clients=new_clients,
        rows=[r.out() for r in rows],
    )


def commit(
    db: Session, content: bytes, filename: str, create_missing: bool, actor: User
) -> ImportResult:
    filename = safe_filename(filename)
    rows = parse_csv(content)
    new_names = _validate(db, rows, create_missing)
    valid = [r for r in rows if not r.errors]

    client_ids = {
        name.lower(): cid for cid, name in db.execute(select(Client.id, Client.name)).all()
    }
    created: list[str] = []
    try:
        for name in new_names:
            client = Client(id=uuid.uuid4(), name=name)
            db.add(client)
            db.flush()
            client_ids[name.lower()] = client.id
            created.append(name)
            audit.record(
                db,
                actor_id=actor.id,
                entity_type="client",
                entity_id=client.id,
                action="create",
                details={"name": name, "origin": "import", "filename": filename},
            )
        for row in valid:
            db.add(
                Invoice(
                    id=uuid.uuid4(),
                    client_id=client_ids[row.client_key],
                    invoice_number=row.raw["invoice_number"],
                    issue_date=row.issue,
                    due_date=row.due,
                    amount=row.amount,
                    description=row.raw.get("description") or None,
                    created_by=actor.id,
                )
            )
        batch = ImportBatch(
            id=uuid.uuid4(),
            filename=filename,
            row_count=len(rows),
            imported_count=len(valid),
            rejected_count=len(rows) - len(valid),
            status="completed" if valid else "rejected",
            created_by=actor.id,
        )
        db.add(batch)
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(
            "import_conflict",
            "Otra operación cargó clientes o facturas al mismo tiempo. Volvé a previsualizar.",
            status.HTTP_409_CONFLICT,
        ) from exc
    audit.record(
        db,
        actor_id=actor.id,
        entity_type="import_batch",
        entity_id=batch.id,
        action="commit",
        details={
            "filename": filename,
            "rows": len(rows),
            "imported": len(valid),
            "rejected": len(rows) - len(valid),
            "created_clients": len(created),
        },
    )
    db.commit()
    return ImportResult(
        batch_id=batch.id,
        filename=filename,
        row_count=len(rows),
        imported_count=len(valid),
        rejected_count=len(rows) - len(valid),
        created_clients=created,
        rejected=[r.out() for r in rows if r.errors],
    )
