import random
import string
from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models import ReservaModel


@dataclass(frozen=True)
class Reserva:
    codigo: str
    apartamento: str
    area: str
    data: date
    status: str

class AreaOcupadaError(Exception):
    """A área já tem uma reserva ativa na data pedida."""

def _gerar_codigo() -> str:
    sufixo = "".join(random.choices(string.digits, k=4))
    return f"RSV-{sufixo}"


async def criar_reserva(session: AsyncSession, apartamento: str, area: str, data: date) -> Reserva:
    codigo = _gerar_codigo()
    session.add(ReservaModel(codigo=codigo, apartamento=apartamento, area=area, data=data, status="ativa"))
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        constraint = getattr(exc.orig.__cause__, "constraint_name", None)
        if constraint == "ix_reservas_area_data_ativa":
            raise AreaOcupadaError(f"{area} já reservada em {data}") from exc
        raise
    return Reserva(codigo=codigo, apartamento=apartamento, area=area, data=data, status="ativa")

