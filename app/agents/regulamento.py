from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from app.regulamento import carregar_capitulos

_CAPITULOS = {c.titulo: c.conteudo for c in carregar_capitulos()}
_TITULOS = list(_CAPITULOS.keys())


def consultar_regulamento(titulo_capitulo: str) -> dict:
    """Devolve o conteúdo de um capítulo do regulamento interno do condomínio.

    Args:
        titulo_capitulo: o título exato de um dos capítulos disponíveis.
    """
    conteudo = _CAPITULOS.get(titulo_capitulo)
    if conteudo is None:
        return {"erro": "capítulo não encontrado", "capitulos_disponiveis": _TITULOS}
    return {"titulo": titulo_capitulo, "conteudo": conteudo}


def build_especialista_regulamento() -> LlmAgent:
    lista = "\n".join(f"- {titulo}" for titulo in _TITULOS)
    return LlmAgent(
        name="especialista_regulamento",
        model="gemini-3.5-flash-lite",
        description="Especialista em responder dúvidas sobre o regulamento interno do condomínio.",
        instruction=(
            "Você responde dúvidas sobre o regulamento interno do "
            "condomínio. Os capítulos disponíveis são:\n"
            f"{lista}\n\n"
            "Escolha o título EXATO do capítulo mais relevante pra "
            "pergunta e chame consultar_regulamento com esse título. "
            "Responda de forma completa em relação ao artigo encontrado "
            "(não corte a resposta na primeira frase que bate com a "
            "pergunta). Se o próprio regulamento remeter a outro "
            "documento (como 'a Convenção') para um dado específico, "
            "deixe isso explícito na resposta em vez de parecer uma "
            "resposta completa. Nunca responda com base em capítulos que "
            "você não consultou."
        ),
        tools=[FunctionTool(consultar_regulamento)],
    )
