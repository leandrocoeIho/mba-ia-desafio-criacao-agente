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


import asyncio

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


