from google.adk.events.event import Event
from google.genai import types

from app.adk_runtime import confirmacoes_pendentes, encontrar_confirmacao_pendente, montar_resposta_confirmacao


def _evento_pedido_confirmacao(invocation_id: str, call_id: str, nome_tool: str, args_tool: dict) -> Event:
    return Event(
        invocation_id=invocation_id,
        author="especialista_reservas",
        content=types.Content(
            role="model",
            parts=[
                types.Part(
                    function_call=types.FunctionCall(
                        id=call_id,
                        name="adk_request_confirmation",
                        args={"originalFunctionCall": {"id": "orig-1", "name": nome_tool, "args": args_tool}},
                    )
                )
            ],
        ),
    )


def _evento_resposta_confirmacao(invocation_id: str, call_id: str, confirmado: bool) -> Event:
    return Event(
        invocation_id=invocation_id,
        author="user",
        content=montar_resposta_confirmacao(call_id, confirmado),
    )


def test_confirmacao_sem_resposta_aparece_como_pendente():
    eventos = [_evento_pedido_confirmacao("inv-1", "call-1", "reservar_area", {"area": "salao-de-festas", "data": "2030-04-20"})]
    pendentes = confirmacoes_pendentes(eventos)
    assert len(pendentes) == 1
    assert pendentes[0].id == "call-1"
    assert pendentes[0].acao == "reservar_area"
    assert pendentes[0].detalhes == {"area": "salao-de-festas", "data": "2030-04-20"}
    assert pendentes[0].invocation_id == "inv-1"


def test_confirmacao_respondida_nao_aparece_mais_como_pendente():
    eventos = [
        _evento_pedido_confirmacao("inv-1", "call-1", "reservar_area", {"area": "quadra", "data": "2030-04-06"}),
        _evento_resposta_confirmacao("inv-1", "call-1", True),
    ]
    assert confirmacoes_pendentes(eventos) == []


def test_encontrar_confirmacao_pendente_por_id():
    eventos = [_evento_pedido_confirmacao("inv-1", "call-1", "autorizar_visitante", {"nome": "Joana Ribeiro", "data": "2030-04-21"})]
    achada = encontrar_confirmacao_pendente(eventos, "call-1")
    assert achada is not None
    assert achada.acao == "autorizar_visitante"

    assert encontrar_confirmacao_pendente(eventos, "id-inexistente") is None


def test_id_ja_respondido_nao_e_encontrado_de_novo():
    eventos = [
        _evento_pedido_confirmacao("inv-1", "call-1", "reservar_area", {"area": "quadra", "data": "2030-04-06"}),
        _evento_resposta_confirmacao("inv-1", "call-1", True),
    ]
    assert encontrar_confirmacao_pendente(eventos, "call-1") is None
