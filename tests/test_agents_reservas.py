import inspect
from datetime import date

from app import db, repository
from app.agents.reservas import (
    build_especialista_reservas,
    cancelar_reserva,
    listar_reservas,
    reservar_area,
    verificar_disponibilidade,
)


class _ToolContextFake:
    def __init__(self, state: dict):
        self.state = state


def test_reservar_area_nao_aceita_apartamento_como_parametro():
    assert "apartamento" not in inspect.signature(reservar_area).parameters


def test_cancelar_reserva_nao_aceita_apartamento_como_parametro():
    assert "apartamento" not in inspect.signature(cancelar_reserva).parameters


async def test_reservar_area_sem_taxa_nao_pede_confirmacao_e_usa_apartamento_da_sessao(session_factory):
    db.configurar_session_factory(session_factory)
    ctx = _ToolContextFake({"apartamento": "101"})
    resultado = await reservar_area(area="quadra", data="2030-04-06", tool_context=ctx)
    assert resultado["status"] == "reservada"

    async with session_factory() as session:
        reservas = await repository.listar_reservas(session, "101")
    assert any(r.area == "quadra" and r.data == date(2030, 4, 6) for r in reservas)


async def test_reservar_area_ocupada_e_recusada_sem_excecao(session_factory):
    db.configurar_session_factory(session_factory)
    ctx1 = _ToolContextFake({"apartamento": "101"})
    ctx2 = _ToolContextFake({"apartamento": "201"})
    await reservar_area(area="churrasqueira", data="2030-06-01", tool_context=ctx1)
    resultado = await reservar_area(area="churrasqueira", data="2030-06-01", tool_context=ctx2)
    assert resultado["status"] == "recusada"


async def test_cancelar_reserva_usa_apartamento_da_sessao(session_factory):
    db.configurar_session_factory(session_factory)
    ctx_101 = _ToolContextFake({"apartamento": "101"})
    criada = await reservar_area(area="quadra", data="2030-04-06", tool_context=ctx_101)

    ctx_302 = _ToolContextFake({"apartamento": "302"})
    resultado_errado = await cancelar_reserva(codigo=criada["codigo"], tool_context=ctx_302)
    assert resultado_errado["status"] == "nao_encontrada"

    resultado_certo = await cancelar_reserva(codigo=criada["codigo"], tool_context=ctx_101)
    assert resultado_certo["status"] == "cancelada"


async def test_listar_reservas_usa_apartamento_da_sessao(session_factory):
    db.configurar_session_factory(session_factory)
    await reservar_area(area="quadra", data="2030-04-06", tool_context=_ToolContextFake({"apartamento": "101"}))
    resultado = await listar_reservas(tool_context=_ToolContextFake({"apartamento": "101"}))
    assert len(resultado["reservas"]) == 1
    resultado_outro = await listar_reservas(tool_context=_ToolContextFake({"apartamento": "302"}))
    assert resultado_outro["reservas"] == []


async def test_verificar_disponibilidade_so_diz_livre_ou_ocupada(session_factory):
    db.configurar_session_factory(session_factory)
    await reservar_area(area="quadra", data="2030-04-06", tool_context=_ToolContextFake({"apartamento": "302"}))
    ocupada = await verificar_disponibilidade(area="quadra", data="2030-04-06")
    assert ocupada == {"area": "quadra", "data": "2030-04-06", "disponivel": False}
    livre = await verificar_disponibilidade(area="quadra", data="2030-04-07")
    assert livre["disponivel"] is True


async def test_data_invalida_vira_erro_e_nao_excecao(session_factory):
    db.configurar_session_factory(session_factory)
    resultado = await reservar_area(area="quadra", data="2030-02-30", tool_context=_ToolContextFake({"apartamento": "101"}))
    assert "erro" in resultado


def test_build_especialista_reservas_tem_as_quatro_tools():
    agente = build_especialista_reservas()
    nomes = {tool.name for tool in agente.tools}
    assert nomes == {"verificar_disponibilidade", "reservar_area", "cancelar_reserva", "listar_reservas"}
