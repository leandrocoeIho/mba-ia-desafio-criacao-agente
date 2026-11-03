import asyncio
from datetime import date

import pytest

from app import repository


# Confere que criar_reserva grava no banco e devolve um objeto com o codigo gerado
async def test_criar_reserva_retorna_codigo_unico(session_factory):
    async with session_factory() as session:
        reserva = await repository.criar_reserva(session, "101", "quadra", date(2030, 4, 6))
    assert reserva.codigo.startswith("RSV-")
    assert reserva.apartamento == "101"
    assert reserva.status == "ativa"


# Confere que a segunda reserva pra mesma area/data e recusada (AreaOcupadaError),
# nunca permitindo duas reservas ativas conflitantes
async def test_segunda_reserva_mesma_area_data_e_recusada(session_factory):
    async with session_factory() as session:
        await repository.criar_reserva(session, "101", "salao-de-festas", date(2030, 4, 20))

    async with session_factory() as session:
        with pytest.raises(repository.AreaOcupadaError):
            await repository.criar_reserva(session, "201", "salao-de-festas", date(2030, 4, 20))


# Dispara duas tentativas de reserva pra mesma area/data "ao mesmo tempo" (concorrentes).
# So uma pode vencer - a outra tem que ser recusada, nunca as duas podem ter sucesso.
async def test_duas_reservas_concorrentes_so_uma_vence(session_factory):
    async def tentar(apartamento: str):
        async with session_factory() as session:
            try:
                return await repository.criar_reserva(session, apartamento, "salao-de-festas", date(2030, 5, 11))
            except repository.AreaOcupadaError:
                return None

    r1, r2 = await asyncio.gather(tentar("101"), tentar("201"))
    sucesso = [r for r in (r1, r2) if r is not None]
    assert len(sucesso) == 1


# Confere que cancelar e soft-delete: o status muda pra "cancelada", a reserva some
# da listagem de ativas, mas o codigo continua existindo (nunca e reaproveitado).
async def test_cancelar_reserva_e_soft_delete(session_factory):
    async with session_factory() as session:
        reserva = await repository.criar_reserva(session, "101", "quadra", date(2030, 4, 6))

    async with session_factory() as session:
        cancelada = await repository.cancelar_reserva(session, "101", reserva.codigo)
    assert cancelada is True

    async with session_factory() as session:
        reservas = await repository.listar_reservas(session, "101")
    assert reservas == []

    async with session_factory() as session:
        nova = await repository.criar_reserva(session, "201", "quadra", date(2030, 4, 6))
    assert nova.codigo != reserva.codigo


# Confere que um apartamento nao consegue cancelar a reserva de outro (Garantia 2).
async def test_cancelar_reserva_de_outro_apartamento_nao_funciona(session_factory):
    async with session_factory() as session:
        reserva = await repository.criar_reserva(session, "302", "churrasqueira", date(2030, 6, 1))

    async with session_factory() as session:
        resultado = await repository.cancelar_reserva(session, "101", reserva.codigo)
    assert resultado is False

    async with session_factory() as session:
        reservas_302 = await repository.listar_reservas(session, "302")
    assert any(r.codigo == reserva.codigo for r in reservas_302)


async def test_data_disponivel(session_factory):
    async with session_factory() as session:
        assert await repository.data_disponivel(session, "quadra", date(2030, 4, 6)) is True
        await repository.criar_reserva(session, "101", "quadra", date(2030, 4, 6))
    async with session_factory() as session:
        assert await repository.data_disponivel(session, "quadra", date(2030, 4, 6)) is False


async def test_autorizar_e_listar_visitantes(session_factory):
    async with session_factory() as session:
        await repository.autorizar_visitante(session, "101", "Joana Ribeiro", date(2030, 4, 21))
    async with session_factory() as session:
        visitantes = await repository.listar_visitantes(session, "101")
    assert [v.nome for v in visitantes] == ["Joana Ribeiro"]

    async with session_factory() as session:
        visitantes_outro_apto = await repository.listar_visitantes(session, "302")
    assert visitantes_outro_apto == []

