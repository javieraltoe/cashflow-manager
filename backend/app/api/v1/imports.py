"""Importación CSV de facturas en dos pasos (spec §9 y §10, HU07)."""

from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile, status

from app.api.deps import CurrentUser, DbSession
from app.core.errors import AppError
from app.schemas.imports import ImportPreview, ImportResult
from app.services import imports as imports_service

router = APIRouter(prefix="/imports", tags=["imports"])

Upload = Annotated[UploadFile, File(description="CSV UTF-8, máximo 5 MB y 5.000 filas")]
CreateMissing = Annotated[
    bool, Form(description="Crear los clientes que no existan (por defecto se rechazan)")
]


def _read(file: UploadFile) -> bytes:
    # Se lee como máximo 1 byte más que el límite: nunca se carga un archivo enorme.
    # Starlette guarda las subidas grandes en un archivo temporal privado que se borra
    # al terminar el request; la aplicación no escribe el CSV en disco.
    content = file.file.read(imports_service.MAX_BYTES + 1)
    if len(content) > imports_service.MAX_BYTES:
        raise AppError(
            "file_too_large",
            "El archivo supera el máximo de 5 MB",
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "file",
        )
    return content


@router.post("/invoices/preview", response_model=ImportPreview)
def preview(
    db: DbSession, _: CurrentUser, file: Upload, create_missing_clients: CreateMissing = False
) -> ImportPreview:
    """Valida el archivo y muestra cada fila con sus errores. No guarda nada."""
    content = _read(file)
    return imports_service.preview(db, content, file.filename or "", create_missing_clients)


@router.post("/invoices/commit", response_model=ImportResult)
def commit(
    db: DbSession, user: CurrentUser, file: Upload, create_missing_clients: CreateMissing = False
) -> ImportResult:
    """Carga las filas válidas del archivo. Repetirlo no duplica facturas."""
    content = _read(file)
    return imports_service.commit(db, content, file.filename or "", create_missing_clients, user)
