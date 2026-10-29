from fastapi import APIRouter, Response, status

from app.api.deps import DbSession
from app.schemas.auth import LoginIn, RefreshIn, TokenOut
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, db: DbSession) -> TokenOut:
    user = auth_service.authenticate(db, data.email, data.password)
    return auth_service.issue_tokens(db, user)


@router.post("/refresh", response_model=TokenOut)
def refresh(data: RefreshIn, db: DbSession) -> TokenOut:
    return auth_service.refresh(db, data.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(data: RefreshIn, db: DbSession) -> Response:
    auth_service.logout(db, data.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
