import uuid

from pydantic import BaseModel


class RowError(BaseModel):
    field: str | None
    message: str


class ImportRow(BaseModel):
    line: int  # número de línea en el archivo (la cabecera es la 1)
    client_name: str
    invoice_number: str
    issue_date: str
    due_date: str
    amount: str
    description: str
    status: str  # "ok" | "error"
    new_client: bool = False  # se creará el cliente (solo con create_missing_clients)
    errors: list[RowError] = []


class ImportPreview(BaseModel):
    filename: str
    row_count: int
    valid_count: int
    rejected_count: int
    new_clients: list[str]
    rows: list[ImportRow]


class ImportResult(BaseModel):
    batch_id: uuid.UUID
    filename: str
    row_count: int
    imported_count: int
    rejected_count: int
    created_clients: list[str]
    rejected: list[ImportRow]
