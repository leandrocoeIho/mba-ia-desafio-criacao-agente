import uuid

import pytest
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.genai import types

from app import adk_runtime
from app.adk_app import ADK_USER_ID, APP_NAME, make_runner, make_session_service

EXECUTADO: list[str] = []


def _acao_critica(valor: str) -> dict:
    EXECUTADO.append(valor)
    return {"status": "ok", "valor": valor}


def _build_agente_fixture() -> LlmAgent:
    return LlmAgent(
        name="agente_fixture",
        model="gemini-3.5-flash-lite",
        description="Agente de teste com uma tool que exige confirmação.",
        instruction="Quando o usuário pedir pra executar algo, chame acao_critica com o valor pedido.",
        tools=[FunctionTool(_acao_critica, require_confirmation=True)],
    )


@pytest.mark.asyncio
async def test_confirmacao_sobrevive_a_novo_runner_mesmo_banco():
    EXECUTADO.clear()
    session_service = make_session_service()
    session_id = str(uuid.uuid4())
    await session_service.create_session(app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id)
    runner = make_runner(_build_agente_fixture(), session_service)

    msg = types.Content(role="user", parts=[types.Part(text="Execute a ação crítica com o valor 'teste123'")])
    await adk_runtime.run_com_retry(runner, user_id=ADK_USER_ID, session_id=session_id, new_message=msg)

    session = await session_service.get_session(app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id)
    pendentes = adk_runtime.confirmacoes_pendentes(session.events)
    assert len(pendentes) == 1
    assert not EXECUTADO

    # Simula reinício do processo: nova instância de session_service/runner, mesmo banco.
    session_service2 = make_session_service()
    runner2 = make_runner(_build_agente_fixture(), session_service2)
    pendente = pendentes[0]
    resposta = adk_runtime.montar_resposta_confirmacao(pendente.id, True)
    await adk_runtime.run_com_retry(
        runner2,
        user_id=ADK_USER_ID,
        session_id=session_id,
        invocation_id=pendente.invocation_id,
        new_message=resposta,
    )

    assert EXECUTADO == ["teste123"]

    session_depois = await session_service2.get_session(app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id)
    assert adk_runtime.confirmacoes_pendentes(session_depois.events) == []
