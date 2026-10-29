from sqlalchemy import Boolean, Index, String, func, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import CreatedAt, UpdatedAt, UUIDPk


class Client(UUIDPk, CreatedAt, UpdatedAt, Base):
    __tablename__ = "clients"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    tax_id: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())


# Nombre único sin distinguir mayúsculas: la importación CSV identifica al cliente
# por nombre (spec §10), así que no puede haber ambigüedad. También cumple el rol del
# índice clients(name) recomendado en §7 (búsqueda y orden por nombre).
Index("uq_clients_name_lower", func.lower(Client.name), unique=True)
