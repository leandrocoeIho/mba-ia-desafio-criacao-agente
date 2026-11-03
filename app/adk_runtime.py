import asyncio
from dataclasses import dataclass
from typing import Any

from google.adk.events.event import Event
from google.genai import errors as genai_errors
from google.genai import types

CONFIRMATION_FUNCTION_NAME = "adk_request_confirmation"


@dataclass(frozen=True)
class ConfirmacaoPendente:
    id: str
    acao: str
    detalhes: dict[str, Any]
    invocation_id: str


def _function_calls(events: list[Event]):
    for event in events:
        if not event.content or not event.content.parts:
            continue
        for part in event.content.parts:
            if part.function_call:
                yield event, part.function_call


def _ids_respondidos(events: list[Event]) -> set[str]:
    ids: set[str] = set()
    for event in events:
        if not event.content or not event.content.parts:
            continue
        for part in event.content.parts:
            if part.function_response and part.function_response.id:
                ids.add(part.function_response.id)
    return ids


def confirmacoes_pendentes(events: list[Event]) -> list[ConfirmacaoPendente]:
    respondidos = _ids_respondidos(events)
    pendentes: list[ConfirmacaoPendente] = []
    for event, call in _function_calls(events):
        if call.name != CONFIRMATION_FUNCTION_NAME or call.id in respondidos:
            continue
        original = (call.args or {}).get("originalFunctionCall") or {}
        pendentes.append(
            ConfirmacaoPendente(
                id=call.id,
                acao=original.get("name", ""),
                detalhes=original.get("args") or {},
                invocation_id=event.invocation_id,
            )
        )
    return pendentes


def encontrar_confirmacao_pendente(events: list[Event], call_id: str) -> ConfirmacaoPendente | None:
    for pendente in confirmacoes_pendentes(events):
        if pendente.id == call_id:
            return pendente
    return None


def montar_resposta_confirmacao(call_id: str, confirmado: bool) -> types.Content:
    return types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    id=call_id,
                    name=CONFIRMATION_FUNCTION_NAME,
                    response={"confirmed": confirmado},
                )
            )
        ],
    )


async def run_com_retry(runner, **kwargs) -> list[Event]:
    """Coleta todos os eventos de run_async, tentando de novo em caso de 503
    transitorio ou 429 (cota excedida) do Gemini — ambos observados no tier
    gratuito durante o desenvolvimento. Um ClientError que nao seja 429 (ex.:
    400/404) nao e retentavel e sobe na hora."""
    ultimo_erro: Exception | None = None
    for tentativa in range(5):
        try:
            return [event async for event in runner.run_async(**kwargs)]
        except genai_errors.ServerError as exc:
            ultimo_erro = exc
            await asyncio.sleep(5 * (tentativa + 1))
        except genai_errors.ClientError as exc:
            if exc.code != 429:
                raise
            ultimo_erro = exc
            await asyncio.sleep(20 * (tentativa + 1))
    assert ultimo_erro is not None
    raise ultimo_erro
