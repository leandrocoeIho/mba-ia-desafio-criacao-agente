from fastapi import APIRouter, Depends

from app import repository
from app.api.deps import get_db_session_factory
from app.api.schemas import ReservaResponse, VisitanteResponse

router = APIRouter()


@router.get("/apartamentos/{numero}/reservas")
async def reservas_do_apartamento(numero: str, session_factory=Depends(get_db_session_factory)) -> list[ReservaResponse]:
    async with session_factory() as session:
        reservas = await repository.listar_reservas(session, numero)
    return [ReservaResponse(codigo=r.codigo, area=r.area, data=r.data.isoformat()) for r in reservas]


@router.get("/apartamentos/{numero}/visitantes")
async def visitantes_do_apartamento(numero: str, session_factory=Depends(get_db_session_factory)) -> list[VisitanteResponse]:
    async with session_factory() as session:
        visitantes = await repository.listar_visitantes(session, numero)
    return [VisitanteResponse(nome=v.nome, data=v.data.isoformat()) for v in visitantes]
