"""GET /api/v1/health: salud del servicio. No revela datos sensibles."""

from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from app.core.config import get_settings
from app.db import session as db_session

router = APIRouter(tags=["health"])


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]
    version: str


@router.get("/health", response_model=HealthOut)
def health(response: Response) -> HealthOut:
    db_ok = db_session.check_database()
    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthOut(
        status="ok" if db_ok else "degraded",
        database="ok" if db_ok else "unavailable",
        version=get_settings().app_version,
    )
