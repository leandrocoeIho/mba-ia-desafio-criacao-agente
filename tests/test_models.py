from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import ReservaModel, VisitanteModel


async def test_criar_tabelas_e_inserir_reserva(session_factory):
    async with session_factory() as session:
        session.add(
            ReservaModel(
                codigo="RSV-TESTE",
                apartamento="101",
                area="quadra",
                data=date(2030, 4, 6),
                status="ativa",
            )
        )
        await session.commit()

        result = await session.execute(
            select(ReservaModel).where(ReservaModel.codigo == "RSV-TESTE")
        )
        reserva = result.scalar_one()
        assert reserva.apartamento == "101"
        assert reserva.status == "ativa"


async def test_duas_reservas_ativas_mesma_area_data_violam_unique(session_factory):
    async with session_factory() as session:
        session.add(
            ReservaModel(codigo="RSV-A", apartamento="101", area="salao-de-festas", data=date(2030, 5, 11), status="ativa")
        )
        await session.commit()

    async with session_factory() as session:
        session.add(
            ReservaModel(codigo="RSV-B", apartamento="201", area="salao-de-festas", data=date(2030, 5, 11), status="ativa")
        )
        try:
            await session.commit()
            assert False, "deveria ter violado a constraint UNIQUE"
        except IntegrityError:
            await session.rollback()

async def test_insere_visitante(session_factory):
    async with session_factory() as session:
        session.add(VisitanteModel(apartamento="101", nome="Joana Ribeiro", data=date(2030, 4, 21)))
        await session.commit()
