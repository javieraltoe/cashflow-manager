import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, EmailStr, StringConstraints

from app.schemas.common import ORMModel, clean_optional

ClientName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
OptStr20 = Annotated[
    Annotated[str, StringConstraints(max_length=20)] | None, BeforeValidator(clean_optional)
]
OptStr50 = Annotated[
    Annotated[str, StringConstraints(max_length=50)] | None, BeforeValidator(clean_optional)
]
OptEmail = Annotated[EmailStr | None, BeforeValidator(clean_optional)]


class ClientCreate(BaseModel):
    name: ClientName
    tax_id: OptStr20 = None
    email: OptEmail = None
    phone: OptStr50 = None


class ClientUpdate(BaseModel):
    name: ClientName | None = None
    tax_id: OptStr20 = None
    email: OptEmail = None
    phone: OptStr50 = None
    is_active: bool | None = None


class ClientOut(ORMModel):
    id: uuid.UUID
    name: str
    tax_id: str | None
    email: str | None
    phone: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
