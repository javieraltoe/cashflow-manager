from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.user import PasswordChange, UserOut
from app.services import users as users_service

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(data: PasswordChange, user: CurrentUser, db: DbSession) -> Response:
    users_service.change_own_password(db, user, data.current_password, data.new_password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
