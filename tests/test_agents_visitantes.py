import inspect

from app import db
from app.agents.visitantes import autorizar_visitante, build_especialista_visitantes, listar_visitantes


class _ToolContextFake:
    def __init__(self, state: dict):
        self.state = state


def test_autorizar_visitante_nao_aceita_apartamento_como_parametro():
    assert "apartamento" not in inspect.signature(autorizar_visitante).parameters


async def test_autorizar_e_listar_usa_apartamento_da_sessao(session_factory):
    db.configurar_session_factory(session_factory)
    resultado = await autorizar_visitante(
        nome="Joana Ribeiro", data="2030-04-21", tool_context=_ToolContextFake({"apartamento": "101"})
    )
    assert resultado["status"] == "autorizado"

    visitantes_101 = await listar_visitantes(tool_context=_ToolContextFake({"apartamento": "101"}))
    assert visitantes_101["visitantes"] == [{"nome": "Joana Ribeiro", "data": "2030-04-21"}]

    visitantes_302 = await listar_visitantes(tool_context=_ToolContextFake({"apartamento": "302"}))
    assert visitantes_302["visitantes"] == []


def test_build_especialista_visitantes_tem_as_duas_tools_e_exige_confirmacao():
    agente = build_especialista_visitantes()
    tools_por_nome = {tool.name: tool for tool in agente.tools}
    assert set(tools_por_nome) == {"autorizar_visitante", "listar_visitantes"}
    assert tools_por_nome["autorizar_visitante"]._require_confirmation is True
