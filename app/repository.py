import random
import string
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models import ReservaModel, VisitanteModel


@dataclass(frozen=True)
class Reserva:
    codigo: str
    apartamento: str
    area: str
    data: date
    status: str


@dataclass(frozen=True)
class Visitante:
    apartamento: str
    nome: str
    data: date


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


async def cancelar_reserva(session: AsyncSession, apartamento: str, codigo: str) -> bool:
    result = await session.execute(
        select(ReservaModel).where(
            ReservaModel.codigo == codigo,
            ReservaModel.apartamento == apartamento,
            ReservaModel.status == "ativa",
        )
    )
    reserva = result.scalar_one_or_none()
    if reserva is None:
        return False
    reserva.status = "cancelada"
    await session.commit()
    return True


async def listar_reservas(session: AsyncSession, apartamento: str) -> list[Reserva]:
    result = await session.execute(
        select(ReservaModel).where(ReservaModel.apartamento == apartamento, ReservaModel.status == "ativa")
    )
    return [
        Reserva(codigo=r.codigo, apartamento=r.apartamento, area=r.area, data=r.data, status=r.status)
        for r in result.scalars()
    ]


async def data_disponivel(session: AsyncSession, area: str, data: date) -> bool:
    result = await session.execute(
        select(ReservaModel).where(ReservaModel.area == area, ReservaModel.data == data, ReservaModel.status == "ativa")
    )
    return result.scalar_one_or_none() is None


async def autorizar_visitante(session: AsyncSession, apartamento: str, nome: str, data: date) -> Visitante:
    session.add(VisitanteModel(apartamento=apartamento, nome=nome, data=data))
    await session.commit()
    return Visitante(apartamento=apartamento, nome=nome, data=data)


async def listar_visitantes(session: AsyncSession, apartamento: str) -> list[Visitante]:
    result = await session.execute(select(VisitanteModel).where(VisitanteModel.apartamento == apartamento))
    return [Visitante(apartamento=v.apartamento, nome=v.nome, data=v.data) for v in result.scalars()]
