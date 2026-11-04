from datetime import date

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.tools.tool_context import ToolContext

from app import reference_data, repository
from app.db import get_session_factory

_AREAS = reference_data.carregar_areas()


def _requer_confirmacao_reserva(area: str, data: str, **_ignorado) -> bool:
    # O ADK injeta tool_context nessa chamada porque reservar_area o declara;
    # **_ignorado absorve isso sem quebrar.
    info = _AREAS.get(area)
    return bool(info and info.taxa > 0)


async def verificar_disponibilidade(area: str, data: str) -> dict:
    """Informa se uma área comum está livre ou ocupada numa data.

    Args:
        area: id da área comum (ex.: "salao-de-festas", "churrasqueira", "quadra").
        data: data, no formato AAAA-MM-DD.
    """
    if area not in _AREAS:
        return {"erro": f"área '{area}' não existe"}
    try:
        dia = date.fromisoformat(data)
    except ValueError:
        return {"erro": "data inválida, use AAAA-MM-DD"}
    session_factory = get_session_factory()
    async with session_factory() as session:
        livre = await repository.data_disponivel(session, area, dia)
    # Só livre/ocupada: nunca de quem é a reserva (Garantia 2).
    return {"area": area, "data": data, "disponivel": livre}


async def reservar_area(area: str, data: str, tool_context: ToolContext) -> dict:
    """Reserva uma área comum do condomínio na data informada, para o
    apartamento da sessão atual.

    Args:
        area: id da área comum (ex.: "salao-de-festas", "churrasqueira", "quadra").
        data: data da reserva, no formato AAAA-MM-DD.
    """
    apartamento = tool_context.state["apartamento"]
    if area not in _AREAS:
        return {"erro": f"área '{area}' não existe"}
    try:
        dia = date.fromisoformat(data)
    except ValueError:
        return {"erro": "data inválida, use AAAA-MM-DD"}
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            reserva = await repository.criar_reserva(session, apartamento, area, dia)
        except repository.AreaOcupadaError:
            return {"status": "recusada", "motivo": "área já reservada nessa data"}
    return {"status": "reservada", "codigo": reserva.codigo, "area": area, "data": data}


async def cancelar_reserva(codigo: str, tool_context: ToolContext) -> dict:
    """Cancela uma reserva do apartamento da sessão atual.

    Args:
        codigo: código da reserva a cancelar.
    """
    apartamento = tool_context.state["apartamento"]
    session_factory = get_session_factory()
    async with session_factory() as session:
        cancelada = await repository.cancelar_reserva(session, apartamento, codigo)
    if not cancelada:
        return {"status": "nao_encontrada"}
    return {"status": "cancelada", "codigo": codigo}


async def listar_reservas(tool_context: ToolContext) -> dict:
    """Lista as reservas ativas do apartamento da sessão atual."""
    apartamento = tool_context.state["apartamento"]
    session_factory = get_session_factory()
    async with session_factory() as session:
        reservas = await repository.listar_reservas(session, apartamento)
    return {"reservas": [{"codigo": r.codigo, "area": r.area, "data": r.data.isoformat()} for r in reservas]}


def build_especialista_reservas() -> LlmAgent:
    return LlmAgent(
        name="especialista_reservas",
        model="gemini-3.5-flash-lite",
        description=(
            "Especialista em reservar e cancelar o uso de áreas comuns "
            "(salão de festas, churrasqueira, quadra) do condomínio."
        ),
        instruction=(
            "Você cuida de reservas de áreas comuns do condomínio para o "
            "apartamento do morador. Use verificar_disponibilidade para "
            "saber se uma área está livre numa data, reservar_area para "
            "criar uma reserva, cancelar_reserva para cancelar, e "
            "listar_reservas para consultar as reservas atuais. Nunca peça "
            "o número do apartamento ao morador — ele já é conhecido pelo "
            "sistema."
        ),
        tools=[
            FunctionTool(verificar_disponibilidade),
            FunctionTool(reservar_area, require_confirmation=_requer_confirmacao_reserva),
            FunctionTool(cancelar_reserva),
            FunctionTool(listar_reservas),
        ],
    )
