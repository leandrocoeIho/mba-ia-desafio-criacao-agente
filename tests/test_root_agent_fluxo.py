import uuid
from datetime import date

import pytest
from google.genai import types

from app import db, repository
from app.adk_app import ADK_USER_ID, APP_NAME, make_runner, make_session_service
from app.adk_runtime import confirmacoes_pendentes, montar_resposta_confirmacao, run_com_retry
from app.agents.root import build_root_agent


@pytest.mark.asyncio
async def test_reserva_sem_taxa_nao_gera_confirmacao(session_factory):
    db.configurar_session_factory(session_factory)
    session_service = make_session_service()
    session_id = str(uuid.uuid4())
    await session_service.create_session(app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id, state={"apartamento": "101"})
    runner = make_runner(build_root_agent(), session_service)

    msg = types.Content(role="user", parts=[types.Part(text="Reserve a quadra para 2030-04-06")])
    await run_com_retry(runner, user_id=ADK_USER_ID, session_id=session_id, new_message=msg)

    session = await session_service.get_session(app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id)
    assert confirmacoes_pendentes(session.events) == []

    async with session_factory() as db_session:
        reservas = await repository.listar_reservas(db_session, "101")
    assert any(r.area == "quadra" and r.data == date(2030, 4, 6) for r in reservas)


@pytest.mark.asyncio
async def test_reserva_com_taxa_exige_confirmacao_e_so_grava_apos_aprovar(session_factory):
    db.configurar_session_factory(session_factory)
    session_service = make_session_service()
    session_id = str(uuid.uuid4())
    await session_service.create_session(app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id, state={"apartamento": "101"})
    runner = make_runner(build_root_agent(), session_service)

    msg = types.Content(role="user", parts=[types.Part(text="Reserve o salão de festas para 2030-04-20")])
    await run_com_retry(runner, user_id=ADK_USER_ID, session_id=session_id, new_message=msg)

    session = await session_service.get_session(app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id)
    pendentes = confirmacoes_pendentes(session.events)
    assert len(pendentes) == 1
    assert pendentes[0].detalhes.get("area") == "salao-de-festas"
    assert pendentes[0].detalhes.get("data") == "2030-04-20"

    async with session_factory() as db_session:
        reservas_antes = await repository.listar_reservas(db_session, "101")
    assert reservas_antes == []

    resposta = montar_resposta_confirmacao(pendentes[0].id, True)
    await run_com_retry(
        runner,
        user_id=ADK_USER_ID,
        session_id=session_id,
        invocation_id=pendentes[0].invocation_id,
        new_message=resposta,
    )

    async with session_factory() as db_session:
        reservas_depois = await repository.listar_reservas(db_session, "101")
    assert any(r.area == "salao-de-festas" and r.data == date(2030, 4, 20) for r in reservas_depois)
