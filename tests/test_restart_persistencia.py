import uuid

import pytest
from google.genai import types

from app import db
from app.adk_app import ADK_USER_ID, APP_NAME, make_runner, make_session_service
from app.adk_runtime import run_com_retry
from app.agents.root import build_root_agent


@pytest.mark.asyncio
async def test_sessao_sobrevive_a_novo_processo_simulado(session_factory):
    db.configurar_session_factory(session_factory)

    session_service_1 = make_session_service()
    session_id = str(uuid.uuid4())
    await session_service_1.create_session(app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id, state={"apartamento": "101"})
    runner_1 = make_runner(build_root_agent(), session_service_1)

    msg1 = types.Content(role="user", parts=[types.Part(text="Reserve a quadra para 2030-04-06")])
    await run_com_retry(runner_1, user_id=ADK_USER_ID, session_id=session_id, new_message=msg1)

    sessao_antes = await session_service_1.get_session(app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id)
    quantidade_eventos_antes = len(sessao_antes.events)

    # "Reinício": instâncias novas de tudo, mesmo Postgres por baixo.
    session_service_2 = make_session_service()
    runner_2 = make_runner(build_root_agent(), session_service_2)

    sessao_depois_reinicio = await session_service_2.get_session(app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id)
    assert len(sessao_depois_reinicio.events) == quantidade_eventos_antes

    msg2 = types.Content(role="user", parts=[types.Part(text="Quais são minhas reservas agora?")])
    await run_com_retry(runner_2, user_id=ADK_USER_ID, session_id=session_id, new_message=msg2)

    sessao_final = await session_service_2.get_session(app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id)
    assert len(sessao_final.events) > quantidade_eventos_antes
