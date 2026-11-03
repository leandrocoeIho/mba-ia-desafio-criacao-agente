import uuid

from fastapi import APIRouter, Depends, HTTPException
from google.genai import types

from app import adk_runtime
from app.adk_app import ADK_USER_ID, APP_NAME
from app.api.deps import get_runner, get_session_service
from app.api.schemas import (
    ConfirmacaoPendenteResponse,
    CriarSessaoRequest,
    CriarSessaoResponse,
    EnviarMensagemRequest,
    MensagemResponse,
    ResponderConfirmacaoRequest,
)

router = APIRouter()


def _montar_resposta(events, session) -> MensagemResponse:
    textos = [
        part.text
        for event in events
        if event.content and event.content.parts
        for part in event.content.parts
        if part.text
    ]
    pendentes = adk_runtime.confirmacoes_pendentes(session.events)
    return MensagemResponse(
        resposta="".join(textos),
        confirmacoes_pendentes=[
            ConfirmacaoPendenteResponse(id=p.id, acao=p.acao, detalhes=p.detalhes) for p in pendentes
        ],
    )


@router.post("/sessoes", status_code=201)
async def criar_sessao(body: CriarSessaoRequest, session_service=Depends(get_session_service)) -> CriarSessaoResponse:
    session_id = str(uuid.uuid4())
    await session_service.create_session(
        app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id, state={"apartamento": body.apartamento}
    )
    return CriarSessaoResponse(session_id=session_id)


@router.post("/sessoes/{session_id}/mensagens")
async def enviar_mensagem(
    session_id: str,
    body: EnviarMensagemRequest,
    runner=Depends(get_runner),
    session_service=Depends(get_session_service),
) -> MensagemResponse:
    session = await session_service.get_session(app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id)
    if session is None:
        raise HTTPException(status_code=404)
    msg = types.Content(role="user", parts=[types.Part(text=body.texto)])
    events = await adk_runtime.run_com_retry(runner, user_id=ADK_USER_ID, session_id=session_id, new_message=msg)
    session = await session_service.get_session(app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id)
    return _montar_resposta(events, session)


@router.post("/sessoes/{session_id}/confirmacoes")
async def responder_confirmacao(
    session_id: str,
    body: ResponderConfirmacaoRequest,
    runner=Depends(get_runner),
    session_service=Depends(get_session_service),
) -> MensagemResponse:
    session = await session_service.get_session(app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id)
    if session is None:
        raise HTTPException(status_code=404)
    pendente = adk_runtime.encontrar_confirmacao_pendente(session.events, body.id)
    if pendente is None:
        raise HTTPException(status_code=409)
    resposta = adk_runtime.montar_resposta_confirmacao(body.id, body.confirmado)
    events = await adk_runtime.run_com_retry(
        runner,
        user_id=ADK_USER_ID,
        session_id=session_id,
        invocation_id=pendente.invocation_id,
        new_message=resposta,
    )
    session = await session_service.get_session(app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id)
    return _montar_resposta(events, session)


@router.get("/sessoes/{session_id}/eventos")
async def listar_eventos(session_id: str, session_service=Depends(get_session_service)):
    session = await session_service.get_session(app_name=APP_NAME, user_id=ADK_USER_ID, session_id=session_id)
    if session is None:
        raise HTTPException(status_code=404)
    return [event.model_dump(mode="json", exclude_none=True) for event in session.events]
