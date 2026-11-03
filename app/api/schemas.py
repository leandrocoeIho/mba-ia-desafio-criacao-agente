from typing import Any

from pydantic import BaseModel


class CriarSessaoRequest(BaseModel):
    apartamento: str


class CriarSessaoResponse(BaseModel):
    session_id: str


class EnviarMensagemRequest(BaseModel):
    texto: str


class ConfirmacaoPendenteResponse(BaseModel):
    id: str
    acao: str
    detalhes: dict[str, Any]


class MensagemResponse(BaseModel):
    resposta: str
    confirmacoes_pendentes: list[ConfirmacaoPendenteResponse]


class ResponderConfirmacaoRequest(BaseModel):
    id: str
    confirmado: bool


class ReservaResponse(BaseModel):
    codigo: str
    area: str
    data: str


class VisitanteResponse(BaseModel):
    nome: str
    data: str
