from datetime import date

from sqlalchemy import Date, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ReservaModel(Base):
    __tablename__ = "reservas"

    codigo: Mapped[str] = mapped_column(String(32), primary_key=True)
    apartamento: Mapped[str] = mapped_column(String(16), nullable=False)
    area: Mapped[str] = mapped_column(String(64), nullable=False)
    data: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ativa")

    __table_args__ = (
        Index(
            "ix_reservas_area_data_ativa",
            "area",
            "data",
            unique=True,
            postgresql_where=text("status = 'ativa'"),
        ),
    )
class VisitanteModel(Base):
    __tablename__ = "visitantes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    apartamento: Mapped[str] = mapped_column(String(16), nullable=False)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    data: Mapped[date] = mapped_column(Date, nullable=False)
