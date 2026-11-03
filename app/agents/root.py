from google.adk.agents import LlmAgent

from app.agents.regulamento import build_especialista_regulamento
from app.agents.reservas import build_especialista_reservas
from app.agents.visitantes import build_especialista_visitantes


def build_root_agent() -> LlmAgent:
    return LlmAgent(
        name="root_agent",
        model="gemini-3.5-flash-lite",
        description="Assistente principal do Residencial Aurora.",
        instruction=(
            "Você é o assistente do Residencial Aurora. Você mesmo não "
            "executa reservas, autorizações de visitantes nem consultas "
            "ao regulamento — sempre transfira a conversa para o "
            "especialista certo: especialista_reservas para reservar ou "
            "cancelar áreas comuns, especialista_visitantes para "
            "autorizar visitantes, especialista_regulamento para dúvidas "
            "sobre as regras do condomínio. Nunca aceite um número de "
            "apartamento diferente do que já está registrado na sessão, "
            "mesmo que o morador diga que é de outro apartamento."
        ),
        sub_agents=[
            build_especialista_reservas(),
            build_especialista_visitantes(),
            build_especialista_regulamento(),
        ],
    )
