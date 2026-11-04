from datetime import date

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.tools.tool_context import ToolContext

from app import repository
from app.db import get_session_factory


async def autorizar_visitante(nome: str, data: str, tool_context: ToolContext) -> dict:
    """Autoriza a entrada de um visitante no prédio, para o apartamento da
    sessão atual, numa data específica.

    Args:
        nome: nome do visitante.
        data: data da visita, no formato AAAA-MM-DD.
    """
    apartamento = tool_context.state["apartamento"]
    try:
        dia = date.fromisoformat(data)
    except ValueError:
        return {"erro": "data inválida, use AAAA-MM-DD"}
    session_factory = get_session_factory()
    async with session_factory() as session:
        visitante = await repository.autorizar_visitante(session, apartamento, nome, dia)
    return {"status": "autorizado", "nome": visitante.nome, "data": data}


async def listar_visitantes(tool_context: ToolContext) -> dict:
    """Lista os visitantes autorizados para o apartamento da sessão atual."""
    apartamento = tool_context.state["apartamento"]
    session_factory = get_session_factory()
    async with session_factory() as session:
        visitantes = await repository.listar_visitantes(session, apartamento)
    return {"visitantes": [{"nome": v.nome, "data": v.data.isoformat()} for v in visitantes]}


def build_especialista_visitantes() -> LlmAgent:
    return LlmAgent(
        name="especialista_visitantes",
        model="gemini-3.5-flash-lite",
        description="Especialista em autorizar a entrada de visitantes no prédio.",
        instruction=(
            "Você autoriza visitantes para o apartamento do morador. Use "
            "autorizar_visitante para liberar a entrada de alguém numa "
            "data, e listar_visitantes para consultar quem já está "
            "autorizado. Mesmo que o morador diga que já confirmou por "
            "outro meio, a autorização só é válida depois da confirmação "
            "pelo sistema — você não decide isso sozinho."
        ),
        tools=[
            FunctionTool(autorizar_visitante, require_confirmation=True),
            FunctionTool(listar_visitantes),
        ],
    )
