from typing import Annotated, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, ConfigDict

MAX_PAGE_SIZE = 100

T = TypeVar("T")


class Page(BaseModel, Generic[T]):  # noqa: UP046  (sintaxis compatible con pydantic 2.11)
    items: list[T]
    total: int
    page: int
    page_size: int


class Pagination(BaseModel):
    page: int = 1
    page_size: int = 20

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def pagination_params(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
) -> Pagination:
    return Pagination(page=page, page_size=page_size)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def clean_optional(value: str | None) -> str | None:
    """Recorta espacios; cadena vacía -> None."""
    if value is None:
        return None
    value = value.strip()
    return value or None
